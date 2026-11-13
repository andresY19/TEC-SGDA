"""New 11E tests against the actual autonomous containers; no host code mounts."""
from pathlib import Path
import concurrent.futures,hashlib,json,subprocess,sys,unittest,uuid
import certify_autonomous_11e as c
ROOT=Path(__file__).resolve().parents[1]
STATE=json.loads((ROOT/'phase11e-environment.json').read_text());c.STATE.update(STATE)
assert STATE['project'].startswith('geology-auto11e-')
CLI='/opt/geology-distribution/reconcile_documents.py'

def run(service,*args):
 return subprocess.run(['docker','exec',c.cid(service),*args],capture_output=True,text=True,encoding='utf-8',errors='replace')

def code(service,source):
 r=run(service,'python','-B','-c',source);assert r.returncode==0,r.stderr[-300:];return r.stdout.strip()

class AutonomousReconciliation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.op=code('runner',"from pathlib import Path;print(next(Path('/cert/cases/commit_uncertain/preservacion/versiones').iterdir()))")
  cls.receipt=None;cls.evidence={}
  cls.auth_before=cls.auth_digest()
 @staticmethod
 def auth_digest():
  return code('runner',"import redis,os,hashlib; r=redis.Redis.from_url(os.environ['AUTH_REDIS_URL']);h=hashlib.sha256();[(h.update(k),h.update(r.dump(k))) for k in sorted(r.scan_iter())];print(h.hexdigest());r.close()")
 def invoke(self,service='worker'):
  r=run(service,'python','-B',CLI,'--operation',self.op,'--storage-root','/cert')
  self.assertEqual(r.returncode,0,r.stderr[-300:]);self.assertEqual(json.loads(r.stdout)['state'],'RECONCILED');return json.loads(r.stdout)
 def test_01_embedded_module_and_cli_in_web_and_worker(self):
  ctx=Path(json.loads((ROOT/'phase11e-build.json').read_text())['context'])
  expected={"/srv/geology/geology/dominio/conciliacion.py":hashlib.sha256((ctx/'geology/dominio/conciliacion.py').read_bytes()).hexdigest(),CLI:hashlib.sha256((ctx/'reconcile_documents.py').read_bytes()).hexdigest()}
  for name in ['web','worker']:
   value=json.loads(code(name,"import hashlib,json;from pathlib import Path;print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in "+repr(list(expected))+"}))"));self.assertEqual(value,expected)
 def test_02_nonroot_readonly_no_code_mount(self):
  for name in ['web','worker']:
   raw=json.loads(c.cmd(['docker','inspect',c.cid(name)]))[0]
   self.assertEqual(raw['Config']['User'],'10001:10001');self.assertTrue(raw['HostConfig']['ReadonlyRootfs']);self.assertIn('ALL',raw['HostConfig']['CapDrop'])
   self.assertTrue(any('no-new-privileges' in x for x in raw['HostConfig']['SecurityOpt']))
   self.assertFalse(any(m['Type']=='bind' and not m['Destination'].startswith('/run/secrets') for m in raw['Mounts']))
   self.assertEqual(code(name,'import os;print(str(os.getuid())+":"+str(os.getgid()))'),'10001:10001')
 def test_03_real_worker_cli_idempotent_and_web_compatible(self):
  sqlhash="import json,hashlib;from sqlalchemy import text;from geology.nucleo.bd import motor;\nwith motor.connect() as c:\n tables=c.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename\")).scalars().all(); data={t:[dict(r) for r in c.execute(text('SELECT * FROM \"'+t+'\" ORDER BY 1')).mappings()] for t in tables};print(hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest())"
  before=code('runner',sqlhash)
  a=self.invoke();self.assertEqual(a,self.invoke());self.assertEqual(a,self.invoke('web'))
  paths=json.loads(code('worker',"import json;from pathlib import Path;print(json.dumps([str(p) for p in Path("+repr(self.op)+").glob('reconciliation-*.json')]))"));self.assertEqual(len(paths),1);type(self).receipt=paths[0];self.assertEqual(before,code('runner',sqlhash))
 def test_04_incomplete_operation_needs_review_no_deletion(self):
  directory='/cert/isolated11e-'+uuid.uuid4().hex
  code('worker',"from pathlib import Path;p=Path("+repr(directory)+");p.mkdir();(p/'partial.pdf').write_bytes(b'SYNTHETIC INCOMPLETE 11E')")
  r=run('worker','python','-B',CLI,'--operation',directory,'--storage-root','/cert');self.assertEqual(r.returncode,2);self.assertEqual(json.loads(r.stdout)['state'],'NEEDS_REVIEW')
  self.assertEqual(code('worker',"from pathlib import Path;print((Path("+repr(directory)+")/'partial.pdf').read_bytes().decode())"),'SYNTHETIC INCOMPLETE 11E')
 def test_05_worker_restart_preserves_receipt_and_idempotency(self):
  path=type(self).receipt;self.assertTrue(path)
  before=code('worker',"from pathlib import Path;import hashlib;print(hashlib.sha256(Path("+repr(path)+").read_bytes()).hexdigest())")
  ident=c.cid('worker');c.compose('restart','worker');c.ready('worker',True);self.assertEqual(c.cid('worker'),ident)
  self.invoke();after=code('worker',"from pathlib import Path;import hashlib;print(hashlib.sha256(Path("+repr(path)+").read_bytes()).hexdigest())");self.assertEqual(before,after)
 def test_06_reconciliation_does_not_change_sessions(self):
  self.assertEqual(self.auth_before,self.auth_digest())
 @classmethod
 def tearDownClass(cls):
  (ROOT/'phase11e-autonomous-reconciliation.json').write_text(json.dumps({'project':STATE['project'],'operation':cls.op,'receipt':cls.receipt,'auth_registry_unchanged':cls.auth_before==cls.auth_digest(),'code_bind_mounts':False},indent=2))
if __name__=='__main__':
 directory=Path(STATE['directory'])/'results'
 with (directory/'autonomous-reconciliation-stderr.txt').open('x',encoding='utf-8') as stream:
  result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AutonomousReconciliation))
 print((directory/'autonomous-reconciliation-stderr.txt').read_text())
 raise SystemExit(0 if result.wasSuccessful() else 1)

