"""Fixtures y pruebas PostgreSQL/Redis/Celery reales, sólo en red temporal 10D."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import unittest
import uuid

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from geology.nucleo.bd import Base, motor, SesionLocal, registrar_modelos
from geology.modelos import Archivo
from geology.nucleo.cola import celery_app
from geology.dominio import pdfa_controlado as p

ROOT=Path('/cert')
CASES=['explicit_1b','explicit_2b','default','invalid_profile','corrupt',
       'conversion_error','validation_error','sql_error','commit_uncertain']
assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-pdfa10d-')
assert make_url(os.environ['DATABASE_URL']).host=='pg'
assert make_url(os.environ['DATABASE_URL']).database=='geology_cert10d'


def write_json(path, obj):
    with path.open('x',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,default=str)
        f.flush();os.fsync(f.fileno())


def pdf(path, pages, label):
    import pikepdf
    with pikepdf.Pdf.new() as doc:
        for i in range(pages):
            page=doc.add_blank_page(page_size=(300,400))
            font=pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name.Helvetica)
            page.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            page.Contents=pikepdf.Stream(doc,f'BT /F1 12 Tf 20 200 Td (SINTETICO 10D {label} PAGINA {i+1} DE {pages}) Tj ET'.encode())
        doc.save(path)


def row_snapshot(ident):
    with motor.connect() as conn:
        row=dict(conn.execute(text('SELECT * FROM archivo_digital WHERE id=:id'),{'id':ident}).mappings().one())
    return hashlib.sha256(json.dumps(row,sort_keys=True,default=str).encode()).hexdigest()


def prepare():
    config=json.loads((ROOT/'private.json').read_text())
    url=make_url(config['admin_url'])
    assert url.host=='pg' and url.database=='geology_cert10d' and url.username=='cert_admin'
    admin=create_engine(url,hide_parameters=True)
    assert not inspect(admin).get_table_names(schema='public')
    registrar_modelos()
    Base.metadata.create_all(admin)  # Explicitly authorised synthetic database only.
    assert len(inspect(admin).get_table_names(schema='public'))==27
    password=config['app_password'];assert len(password)==64 and all(c in '0123456789abcdef' for c in password)
    with admin.begin() as conn:
        conn.exec_driver_sql("CREATE ROLE cert_worker LOGIN PASSWORD '"+password+"'")
        conn.exec_driver_sql('GRANT CONNECT ON DATABASE geology_cert10d TO cert_worker')
        conn.exec_driver_sql('GRANT USAGE ON SCHEMA public TO cert_worker')
        conn.exec_driver_sql('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO cert_worker')
        conn.exec_driver_sql('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO cert_worker')
    fixtures={};hashes={}
    for name in CASES:
        directory=ROOT/'cases'/name;directory.mkdir(parents=True,exist_ok=False)
        source=directory/'original.pdf'
        if name=='corrupt':source.write_bytes(b'%PDF-SINTETICO-CORRUPTO-10D')
        else:pdf(source,3,name)
        old_matrix=directory/'old_matrix.pdf';old_consult=directory/'old_consult.pdf'
        pdf(old_matrix,1,'DERIVADO ANTERIOR MATRIZ');pdf(old_consult,1,'DERIVADO ANTERIOR CONSULTA')
        with SesionLocal() as s:
            row=Archivo(codigo_carpeta='SYN10D',fragmento=0,nombre_original=f'SINTETICO_{name}.pdf',
                ruta=str(source),tamano_bytes=source.stat().st_size,sha256=p.huella(source),
                tiene_capa_de_texto=True,paginas=3,ruta_matriz=str(old_matrix),ruta_consulta=str(old_consult))
            s.add(row);s.commit();ident=row.id
        fixtures[name]={'id':ident,'source':str(source),'old_matrix':str(old_matrix),
                        'old_consult':str(old_consult),'row_before_sha256':row_snapshot(ident)}
        for f in (source,old_matrix,old_consult):hashes[str(f)]=p.huella(f)
    write_json(ROOT/'fixtures.json',fixtures);write_json(ROOT/'fixture-hashes.json',hashes)
    print(json.dumps({'prepared':True,'synthetic_tables':27,'synthetic_files':len(hashes),'records':len(fixtures)}))


class DockerPDFa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures=json.loads((ROOT/'fixtures.json').read_text());cls.results={}
        cls.initial_hashes=json.loads((ROOT/'fixture-hashes.json').read_text())
        import redis
        cls.broker=redis.Redis.from_url(os.environ['CELERY_BROKER_URL'],decode_responses=True)
        cls.backend=redis.Redis.from_url(os.environ['CELERY_RESULT_BACKEND'])
        cls.prefix=os.environ['GEOLOGY_LOCAL_PROJECT']+':'

    def execute(self,name,profile=None,success=False):
        task_id=str(uuid.uuid4());kwargs={} if profile is None else {'perfil_solicitado':profile}
        result=celery_app.send_task('geology.preparar_digitalizacion',args=[self.fixtures[name]['id']],
            kwargs=kwargs,task_id=task_id,queue=os.environ['GEOLOGY_COLA'])
        returned=result.get(timeout=240,propagate=False)
        entry={'task_id':task_id,'state':result.state,'expected_success':success,
               'profile_requested':profile,'return':returned if success else {'error_type':type(returned).__name__}}
        self.results[name]=entry
        write_json(ROOT/'results'/f'task-{name}.json',entry)
        self.assertEqual(result.state,'SUCCESS' if success else 'FAILURE')
        if success:
            self.assertEqual(returned['problemas'],[])
            self.assertEqual(returned['perfil'],profile or '2b')
            for derivative in returned['resultados']:
                ruta=Path(derivative['ruta']);self.assertTrue(ruta.is_file())
                self.assertEqual(p.huella(ruta),derivative['sha256'])
                self.assertEqual(p.contenido(Path(self.fixtures[name]['source'])),p.contenido(ruta))
                self.assertTrue(p.validar(ruta,profile or '2b')['conforme'])
                xml=Path(derivative['informe']);self.assertTrue(xml.is_file())
                self.assertEqual(p.huella(xml),derivative['informe_sha256'])
                self.assertEqual(derivative['archivo_validado_sha256'],derivative['sha256'])
        return entry

    def test_01_isolation_and_least_privilege(self):
        self.assertEqual(len(inspect(motor).get_table_names(schema='public')),27)
        with motor.connect() as c:
            self.assertEqual(c.execute(text('SELECT current_user')).scalar_one(),'cert_worker')
            self.assertFalse(c.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one())
            self.assertFalse(c.execute(text('SELECT rolsuper FROM pg_roles WHERE rolname=current_user')).scalar_one())
        self.assertEqual(os.environ['LEVANTAR_AL_CARGAR'],'no')
        self.assertEqual(os.environ['PDFA_PERFIL'],'1b')

    def test_02_pdfa_1b_real_queue(self):self.execute('explicit_1b','1b',True)
    def test_03_pdfa_2b_real_queue(self):self.execute('explicit_2b','2b',True)
    def test_04_default_real_queue(self):self.execute('default',success=True)
    def test_05_invalid_profile(self):self.execute('invalid_profile','3b')
    def test_06_corrupt_pdf(self):self.execute('corrupt','1b')
    def test_07_conversion_process_error(self):self.execute('conversion_error','1b')
    def test_08_verapdf_process_error(self):self.execute('validation_error','2b')
    def test_09_real_sql_error_rollback(self):self.execute('sql_error','1b')
    def test_10_real_commit_accepted_ack_lost(self):self.execute('commit_uncertain','2b')

    def audit_entries(self):
        return [json.loads(x.read_text()) for x in (ROOT/'audit').glob('*.json')]

    def test_11_single_execution_and_result_persistence(self):
        for _ in range(30):
            audit=self.audit_entries()
            if sum(x['kind']=='postrun' for x in audit)==9:break
            time.sleep(.2)
        expected={r['task_id'] for r in self.results.values()};self.assertEqual(len(expected),9)
        for kind in ('received','prerun','postrun'):
            entries=[x for x in audit if x['kind']==kind]
            self.assertEqual(len(entries),9)
            self.assertEqual({x['task_id'] for x in entries},expected)
            self.assertEqual({x['task_name'] for x in entries},{'geology.preparar_digitalizacion'})
        for name,r in self.results.items():
            key=celery_app.backend.get_key_for_task(r['task_id'])
            self.assertEqual(self.backend.exists(key),1)
            self.assertGreater(self.backend.ttl(key),0)
            self.assertEqual(celery_app.AsyncResult(r['task_id']).state,r['state'])

    def test_12_sql_updates_only_after_validation_and_rollback(self):
        audit=self.audit_entries()
        validated=[x for x in audit if x['kind']=='validated_before_sql_update']
        self.assertEqual(len(validated),5)
        self.assertTrue(all(x['old_references_still_persisted'] for x in validated))
        for name in ['invalid_profile','corrupt','conversion_error','validation_error','sql_error']:
            self.assertEqual(row_snapshot(self.fixtures[name]['id']),self.fixtures[name]['row_before_sha256'])
        for name in ['sql_error','commit_uncertain']:
            self.assertEqual(sum(x['kind']=='rollback' and x.get('task_id')==self.results[name]['task_id'] for x in audit),1)

    def test_13_sql_document_references_all_exist(self):
        with SesionLocal() as s:
            rows=s.query(Archivo).all();self.assertEqual(len(rows),9)
            for row in rows:
                for path in (row.ruta,row.ruta_matriz,row.ruta_consulta):self.assertTrue(Path(path).is_file())
                self.assertEqual(p.huella(Path(row.ruta)),row.sha256)
                name=row.nombre_original.removeprefix('SINTETICO_').removesuffix('.pdf')
                if name in ['explicit_1b','explicit_2b','default','commit_uncertain']:
                    self.assertIn('/versiones/',row.ruta_matriz)
                else:self.assertEqual(row.ruta_matriz,self.fixtures[name]['old_matrix'])

    def test_14_originals_and_old_derivatives_preserved(self):
        self.assertTrue(all(p.huella(Path(path))==sha for path,sha in self.initial_hashes.items()))

    def test_15_uncertain_commit_journal_and_recovery(self):
        name='commit_uncertain'
        self.assertEqual(self.results[name]['state'],'FAILURE')
        directory=Path(self.fixtures[name]['source']).parent
        states=[json.loads(x.read_text()).get('estado') for x in directory.rglob('evento-*.json')]
        self.assertIn('commit_pendiente_conciliar_si_interrumpido',states)
        self.assertIn('no_confirmado_requiere_conciliacion',states)
        self.assertNotIn('sql_confirmado',states)
        audit=self.audit_entries();self.assertEqual(sum(x['kind']=='commit_accepted_ack_lost' for x in audit),1)
        validated=[]
        for f in (ROOT/'cases').rglob('evento-*.json'):
            if json.loads(f.read_text()).get('estado')=='validado_publicado':
                validated.append(p.verificar_diario(f))
        self.assertEqual(len(validated),10)
        self.assertTrue(all(x['verificado'] for x in validated))

    def test_16_queue_empty_and_no_unknown_tasks(self):
        pending=0;unknown=[]
        for key in self.broker.scan_iter():
            kind=self.broker.type(key)
            if kind=='list':pending+=self.broker.llen(key)
            elif kind=='hash' and key==self.prefix+'unacked':self.assertEqual(self.broker.hlen(key),0)
            elif kind=='zset' and key==self.prefix+'unacked_index':self.assertEqual(self.broker.zcard(key),0)
            elif kind=='set' and key.startswith(self.prefix+'_kombu.binding.'):pass
            elif key==self.prefix+'unacked_mutex':pass
            else:unknown.append(key)
        self.assertEqual(pending,0);self.assertEqual(unknown,[])
        self.assertFalse([x for x in self.audit_entries() if x['kind']=='network_denied'])

    @classmethod
    def tearDownClass(cls):
        versions={name:importlib.metadata.version(name) for name in ['SQLAlchemy','psycopg2-binary','celery','kombu','redis','pikepdf','ocrmypdf','pdfminer.six']}
        versions['python']=sys.version.split()[0]
        versions['ghostscript']=subprocess.run(['/opt/geology-ghostscript/bin/gs','--version'],capture_output=True,text=True).stdout.strip()
        versions['verapdf']=subprocess.run(['/opt/verapdf/verapdf','--version'],capture_output=True,text=True).stdout.splitlines()[0]
        write_json(ROOT/'results/operational-certification.json',{'cases':cls.results,'versions':versions,
            'fixtures':cls.fixtures,'original_and_prior_hashes':cls.initial_hashes,
            'published_tasks':len(cls.results),'operational_original_queue_publications':0,
            'success_cases':sum(x['state']=='SUCCESS' for x in cls.results.values()),
            'expected_failure_cases':sum(x['state']=='FAILURE' for x in cls.results.values())})


if __name__=='__main__':
    if '--prepare' in sys.argv:prepare()
    else:unittest.main(verbosity=2)
