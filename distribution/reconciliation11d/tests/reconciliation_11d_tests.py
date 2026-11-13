"""Synthetic 11D integration on the isolated PostgreSQL, never original data."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import text
from geology.nucleo.bd import SesionLocal, motor
from geology.modelos import Archivo, UnidadInventario
from geology.dominio import conciliacion as c

assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-recon11d-')
assert os.environ['LEVANTAR_AL_CARGAR'] == 'no'
ROOT = Path('/cert/reconciliation11d')
ROOT.mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


class Reconciliation(unittest.TestCase):
    def fixture(self, commit=True, rows=1):
        d = ROOT / ('cargue-' + uuid.uuid4().hex)
        d.mkdir()
        folder = 'S11D-' + uuid.uuid4().hex[:12]
        with SesionLocal() as s:
            s.add(UnidadInventario(codigo_carpeta=folder)); s.commit()
        origin = d / 'original.pdf'
        origin.write_bytes(b'SYNTHETIC 11D ' + uuid.uuid4().bytes)
        records = []
        with SesionLocal() as s:
            for i in range(rows):
                p = origin if rows == 1 else d / ('part-' + str(i) + '.pdf')
                if rows != 1:
                    p.write_bytes(b'SYNTHETIC PART ' + str(i).encode())
                row = Archivo(codigo_carpeta=folder, fragmento=i, nombre_original='SYNTHETIC.pdf',
                              ruta=str(p), tamano_bytes=p.stat().st_size, sha256=sha(p))
                s.add(row); s.flush()
                records.append({k: getattr(row,k) for k in ('id','expediente_id','codigo_carpeta','fragmento','ruta','sha256','tamano_bytes')})
            if commit:
                s.commit()
            else:
                s.rollback()
        j = {'version':1,'operacion':d.name,'codigo_carpeta':folder,
             'estado':'resultado_sql_desconocido','commit_intentado':True,
             'original':{'ruta':str(origin),'sha256':sha(origin),'tamano_bytes':origin.stat().st_size},
             'registros':records,'anteriores':[]}
        (d/'operacion.json').write_text(json.dumps(j))
        return d, j

    def run_reconcile(self, d):
        before = {str(p):sha(p) for p in d.rglob('*') if p.is_file() and not p.name.startswith(('.reconciliation','reconciliation-'))}
        with motor.connect() as conn:
            snapshot = conn.execute(text('SELECT count(*) FROM archivo_digital')).scalar_one()
        result = c.reconcile(d, Path('/cert'), SesionLocal)
        self.assertFalse(result['automatic_delivery']); self.assertFalse(result['automatic_deletion'])
        self.assertTrue(all(Path(p).is_file() and sha(Path(p))==h for p,h in before.items()))
        with motor.connect() as conn:
            self.assertEqual(snapshot,conn.execute(text('SELECT count(*) FROM archivo_digital')).scalar_one())
        return result

    def test_01_before_file_write(self):
        d = ROOT/uuid.uuid4().hex; d.mkdir()
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_02_interrupted_file_and_journal_write(self):
        d=ROOT/uuid.uuid4().hex;d.mkdir()
        (d/'partial.pdf').write_bytes(b'PARTIAL');(d/'operacion.json').write_bytes(b'{"version":')
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_03_file_written_without_sql_confirmation(self):
        d,j=self.fixture(False);self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_04_real_postgres_rollback_not_misreported(self):
        d,j=self.fixture(False)
        result=self.run_reconcile(d)
        self.assertEqual(result['reason'],'SQL_ABSENT_NOT_PROOF_OF_ROLLBACK')
        self.assertNotEqual(result['outcome'],'COMMITTED')

    def test_05_real_commit_response_lost(self):
        d,j=self.fixture(True)
        # Commit completed in PostgreSQL; journal intentionally retains uncertain acknowledgement.
        result=self.run_reconcile(d)
        self.assertEqual(result['state'],'RECONCILED');self.assertEqual(result['outcome'],'COMMITTED')

    def test_06_new_process_reuses_receipt(self):
        d,j=self.fixture();first=self.run_reconcile(d)
        code="from pathlib import Path;import json;from geology.dominio.conciliacion import reconcile;from geology.nucleo.bd import SesionLocal;print(json.dumps(reconcile(Path("+repr(str(d))+"),Path('/cert'),SesionLocal)))"
        p=subprocess.run(['python','-B','-c',code],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout),first)
        self.assertEqual(len(list(d.glob('reconciliation-*.json'))),1)

    def test_07_repeated_reconciliation_is_idempotent(self):
        d,j=self.fixture();a=self.run_reconcile(d)
        self.assertEqual(a,self.run_reconcile(d));self.assertEqual(len(list(d.glob('reconciliation-*.json'))),1)

    def test_08_two_reconcilers_exclusive(self):
        d,j=self.fixture();entered=threading.Event();release=threading.Event();original=c._upload
        def slow(*a,**kw):
            entered.set();self.assertTrue(release.wait(10));return original(*a,**kw)
        with patch.object(c,'_upload',slow), concurrent.futures.ThreadPoolExecutor(2) as pool:
            one=pool.submit(c.reconcile,d,Path('/cert'),SesionLocal)
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaisesRegex(c.EvidenceUnavailable,'CONCURRENT_RECONCILIATION'):
                    c.reconcile(d,Path('/cert'),SesionLocal)
            finally:release.set()
            self.assertEqual(one.result()['state'],'RECONCILED')
        self.assertEqual(len(list(d.glob('reconciliation-*.json'))),1)

    def test_09_missing_file(self):
        d,j=self.fixture()
        # No deletion: simulate a missing referenced path in a fresh synthetic journal.
        j['registros'][0]['ruta']=str(d/'never-created.pdf');(d/'operacion.json').write_text(json.dumps(j))
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_10_hash_mismatch(self):
        d,j=self.fixture();j['registros'][0]['sha256']='0'*64;(d/'operacion.json').write_text(json.dumps(j))
        self.assertEqual(self.run_reconcile(d)['reason'],'HASH_MISMATCH')

    def test_11_incomplete_journal(self):
        d,j=self.fixture();j.pop('registros');(d/'operacion.json').write_text(json.dumps(j))
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_12_redis_unavailable_no_dependency(self):
        import redis
        d,j=self.fixture()
        with patch.object(redis.Redis,'execute_command',side_effect=ConnectionError('synthetic')) as call:
            self.assertEqual(self.run_reconcile(d)['state'],'RECONCILED');call.assert_not_called()

    def test_13_concurrent_producer_row_lock(self):
        d,j=self.fixture();db=SesionLocal()
        try:
            db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta==j['codigo_carpeta']).with_for_update().one()
            self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')
        finally:db.rollback();db.close()
        self.assertEqual(self.run_reconcile(d)['state'],'RECONCILED')

    def test_14_sql_scope_conflict(self):
        d,j=self.fixture();j['registros'][0]['codigo_carpeta']='OTHER';(d/'operacion.json').write_text(json.dumps(j))
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_15_split_files_complete_set(self):
        d,j=self.fixture(rows=3);self.assertEqual(self.run_reconcile(d)['state'],'RECONCILED')

    def test_16_no_original_replacement_by_foreign_path(self):
        d,j=self.fixture();other,otherj=self.fixture()
        j['original']=otherj['original'];(d/'operacion.json').write_text(json.dumps(j))
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_17_historical_25_byte_rejection_metadata_copy(self):
        # New synthetic bytes only, matching the documented size; historical original untouched.
        d=ROOT/('cargue-'+uuid.uuid4().hex);d.mkdir();p=d/'original.pdf';p.write_bytes(b'X'*25)
        with SesionLocal() as s:
            s.add(UnidadInventario(codigo_carpeta=d.name[-12:]));s.commit()
        j={'version':1,'operacion':d.name,'codigo_carpeta':d.name[-12:],
           'estado':'revertida_antes_commit','commit_intentado':False,'rollback_confirmado':True,
           'original':{'ruta':str(p),'sha256':sha(p),'tamano_bytes':25},'registros':[]}
        historical=json.loads(Path('/phase11d/historical-metadata-11d.json').read_text())
        for field in ('estado','commit_intentado','sql_confirmado','rollback_confirmado','tipo_error','requiere_conciliacion'):
            j[field]=historical[field]
        self.assertEqual(historical['historical_file_bytes'],25)
        (d/'operacion.json').write_text(json.dumps(j));self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')
        self.assertEqual(p.stat().st_size,25)

    def test_18_real_pdfa_uncertain_commit(self):
        paths=list(Path('/cert/cases/commit_uncertain/preservacion/versiones').iterdir())
        self.assertEqual(len(paths),1)
        self.assertEqual(self.run_reconcile(paths[0])['state'],'RECONCILED')

    def test_19_storage_failure_no_success(self):
        d,j=self.fixture()
        def failed():raise ConnectionError('private-dsn-not-to-log')
        result=c.reconcile(d,Path('/cert'),failed)
        self.assertEqual(result['state'],'NEEDS_REVIEW');self.assertNotIn('private-dsn',json.dumps(result))

    def test_20_symlink_rejected(self):
        d,j=self.fixture();link=ROOT/uuid.uuid4().hex;link.symlink_to(d,target_is_directory=True)
        with self.assertRaises(c.EvidenceUnavailable):c.reconcile(link,Path('/cert'),SesionLocal)

    def test_21_duplicate_record_id_rejected(self):
        d,j=self.fixture();j['registros'].append(j['registros'][0]);(d/'operacion.json').write_text(json.dumps(j))
        self.assertEqual(self.run_reconcile(d)['state'],'NEEDS_REVIEW')

    def test_22_actual_http_upload_journals(self):
        root=Path('/srv/geology/deposito')
        journals=list((root/'operaciones').glob('*/operacion.json'));self.assertTrue(journals)
        states=[]
        for journal in journals:
            h=sha(journal)
            r=c.reconcile(journal.parent,root,SesionLocal)
            states.append(r['state']);self.assertEqual(sha(journal),h)
        self.assertIn('RECONCILED',states);self.assertIn('NEEDS_REVIEW',states)

    def test_23_operator_entry_point(self):
        d,j=self.fixture()
        p=subprocess.run(['python','-B','/phase11d/reconcile_documents_11d.py','--operation',str(d),'--storage-root','/cert'],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout)['state'],'RECONCILED')

    def test_24_operator_rejects_original_environment(self):
        env=os.environ.copy();env['GEOLOGY_LOCAL_PROJECT']='geology-local-20261106-57a99a'
        p=subprocess.run(['python','-B','/phase11d/reconcile_documents_11d.py','--operation','/cert','--storage-root','/cert'],env=env,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(p.returncode,0)


if __name__=='__main__':unittest.main(verbosity=2)
