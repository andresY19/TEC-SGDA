"""Recovery of the owned 9A technical jobs; preserves initial HTTP evidence.

No login password is reset. A short-lived session of the existing synthetic
actor is signed in memory for read-only HTTP checks after restart.
"""
import os,json,time,unittest,urllib.request,hashlib
from pathlib import Path
import pikepdf
from sqlalchemy import inspect,select
from geology.nucleo.bd import motor,Base,SesionLocal,registrar_modelos
from geology.modelos import Archivo,Expediente,UsuarioBD
from geology.nucleo.cola import celery_app
from geology.nucleo.pases import crear_pase

OUT=Path('/srv/geology/expedidos/pruebas_sinteticas_9a')
CODES=('AC-CP-99001','AC-CP-99002')
EMAIL='documentos.9a@example.invalid'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def snapshot():
    with motor.connect() as c:
        return {t.name:[dict(r) for r in c.execute(select(t)).mappings()] for t in Base.metadata.sorted_tables}

@unittest.skipUnless(os.getenv('GEOLOGY_DOCUMENT_E2E')=='local-approved','Explicit local recovery only')
class DocumentRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.environ['GEOLOGY_LOCAL_PROJECT']=='geology-local-20261106-57a99a'
        assert motor.url.host=='almacen_datos' and motor.url.database=='geology'
        assert os.environ['LEVANTAR_AL_CARGAR'].lower() in ('no','false','0')
        assert all(not v for k,v in os.environ.items() if k.startswith(('GEMINI_API_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY')))
        registrar_modelos();assert len(inspect(motor).get_table_names())==27
        cls.evidence=json.loads((OUT/'evidence.json').read_text())
        assert cls.evidence['synthetic'] and tuple(cls.evidence['codes'])==CODES
        cls.results=[];cls.before=snapshot();cls.sources={}
        with SesionLocal() as s:
            actor=s.query(UsuarioBD).filter_by(correo=EMAIL).one()
            assert actor.activo and not actor.debe_cambiar_clave
            rows=s.query(Archivo).filter(Archivo.codigo_carpeta.in_(CODES)).order_by(Archivo.id).all()
            assert [a.id for a in rows]==[1,2,3]
            for a in rows:
                assert Path(a.ruta).resolve().is_relative_to(Path('/srv/geology/deposito').resolve())
                assert sha(a.ruta)==a.sha256
                assert not a.ruta_matriz and not a.ruta_consulta
                target=Path(a.ruta).parent/'preservacion'
                assert not any(target.glob('*.pdf'))
                cls.sources[a.ruta]=sha(a.ruta)
        cls.token=crear_pase(EMAIL)

    def test_01_reintentos_tecnicos_exclusivos(self):
        for ident in (1,2,3):
            job=celery_app.send_task('geology.preparar_digitalizacion',args=[ident],queue=os.environ['GEOLOGY_COLA'])
            result=job.get(timeout=300,propagate=True)
            self.results.append({'archivo_id':ident,'task_id':job.id,'state':job.state,'result':result})
            self.assertFalse(result.get('error'));self.assertEqual(result.get('problemas'),[])
            for key in ('matriz','consulta'):self.assertTrue(Path(result[key]).is_file())

    def test_02_pdf_derivados_y_referencias(self):
        with SesionLocal() as s:
            rows=s.query(Archivo).filter(Archivo.codigo_carpeta.in_(CODES)).all()
            self.assertEqual(len(rows),3)
            for a in rows:
                self.assertFalse(a.error_proceso)
                with pikepdf.open(a.ruta) as source:
                    pages=len(source.pages)
                    for path in (a.ruta_matriz,a.ruta_consulta):
                        with pikepdf.open(path) as output:
                            self.assertEqual(len(output.pages),pages)
                            with output.open_metadata() as meta:
                                self.assertIn(str(meta.get('pdfaid:part')),('1','2','3'))
                self.assertEqual(sha(a.ruta),a.sha256)
        for path,h in self.sources.items():self.assertEqual(sha(path),h)
        for path,h in self.evidence['source_hashes'].items():self.assertEqual(sha(path),h)

    def test_03_otras_filas_y_sin_aprobacion(self):
        after=snapshot()
        archivo_table=Archivo.__tablename__
        for name,rows in self.before.items():
            pk=[c.name for c in Base.metadata.tables[name].primary_key]
            for row in rows:
                if name==archivo_table and row['id'] in (1,2,3):continue
                found=[r for r in after[name] if all(r[k]==row[k] for k in pk)]
                self.assertEqual(found,[row])
        with SesionLocal() as s:
            for exp in s.query(Expediente).filter(Expediente.codigo_carpeta.in_(CODES)):
                self.assertIsNone(exp.aprobo);self.assertFalse(exp.publicado_consulta)

    def test_04_reinicio_e_integridad(self):
        if self._outcome.result.failures or self._outcome.result.errors:self.skipTest('Resolve prior failures first')
        (OUT/'ready-for-restart.json').write_text(json.dumps({'codes':CODES,'technical_retry_complete':True}))
        deadline=time.monotonic()+180
        while not (OUT/'restart-complete.json').exists():
            if time.monotonic()>deadline:self.fail('Restart confirmation timeout')
            time.sleep(1)
        for path,h in self.sources.items():self.assertEqual(sha(path),h)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path in ('/estado','/app','/unidades/'+CODES[0],'/unidades/'+CODES[1]):
            req=urllib.request.Request('http://servidor:8080'+path,headers={'Authorization':'Bearer '+self.token})
            with opener.open(req,timeout=10) as response:self.assertEqual(response.status,200)
        self.test_02_pdf_derivados_y_referencias()
        self.test_03_otras_filas_y_sin_aprobacion()

    @classmethod
    def tearDownClass(cls):
        (OUT/'recovery-evidence.json').write_text(json.dumps({'technical_jobs':cls.results,
            'source_hashes':cls.sources,'session_check':'signed synthetic actor, no password reset'},indent=2))
        cls.token=None

if __name__=='__main__':unittest.main()
