"""Certificación host: solo dos tareas geology.ping y reinicio del worker propio.

No inspect remoto, purge, flush, forget, escrituras SQL ni tareas documentales.
Los resultados se conservan hasta su TTL natural.
"""
import hashlib,json,os,re,subprocess,time,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT='geology-local-20261106-57a99a'
WORKER=PROJECT+'-procesador-1'

PUBLISH=r'''
import json,os,uuid
from geology.nucleo.cola import celery_app,registrar_tareas
assert os.environ['GEOLOGY_LOCAL_PROJECT']=='geology-local-20261106-57a99a'
assert os.environ['LEVANTAR_AL_CARGAR'].lower() in ('no','false','0')
assert all(not v for k,v in os.environ.items() if k.startswith(('GEMINI_API_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY')))
registered=registrar_tareas()
q=celery_app.conf.task_default_queue
assert q=='geology-local-20261106-57a99a-tasks'
ident=str(uuid.uuid4())
result=celery_app.send_task('geology.ping',args=[],kwargs={},task_id=ident,queue=q,serializer='json')
value=result.get(timeout=25)
assert value=='pong'
key=celery_app.backend.get_key_for_task(ident)
raw=celery_app.backend.client.get(key)
ttl=celery_app.backend.client.ttl(key)
meta=json.loads(raw)
assert meta['status']=='SUCCESS' and meta['result']=='pong' and ttl>0
print(json.dumps({'id':ident,'result':value,'state':result.state,'result_ttl':ttl,'registered':registered,
 'queue':q,'serializer':celery_app.conf.task_serializer,'result_serializer':celery_app.conf.result_serializer,
 'accept_content':celery_app.conf.accept_content,'remote_control':celery_app.conf.worker_enable_remote_control,
 'result_persisted':True}))
'''


def snapshot(option):
    raw=subprocess.check_output(['docker','exec',PROJECT+'-almacen_datos-1','pg_dump','-U','geology','-d','geology',option,'--no-owner','--no-acl'])
    return hashlib.sha256(b'\n'.join(x for x in raw.splitlines() if not x.startswith((b'\\restrict',b'\\unrestrict')))).hexdigest()


def publish_ping():
    p=subprocess.run(['docker','exec',PROJECT+'-servidor-1','python','-B','-c',PUBLISH],capture_output=True,text=True)
    if p.returncode:raise AssertionError('Ping integration failed: '+p.stderr[-1200:])
    return json.loads(p.stdout)


def worker_ready():
    for _ in range(35):
        c=json.loads(subprocess.check_output(['docker','inspect',WORKER],text=True))[0]
        if c['State']['Status']!='running':raise AssertionError('Worker not running')
        log=subprocess.run(['docker','logs','--since',c['State']['StartedAt'],WORKER],capture_output=True,text=True)
        if ' ready.' in log.stdout+log.stderr:return c
        time.sleep(1)
    raise AssertionError('Worker readiness timeout')


@unittest.skipUnless(os.environ.get('GEOLOGY_CELERY_INTEGRATION')=='local-approved','Celery local explícito')
class CeleryLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker=worker_ready()
        assert cls.worker['Config']['Labels']['com.docker.compose.project']==PROJECT
        cls.before=json.loads((ROOT/'phase8d-database-before.json').read_text())
        assert snapshot('--schema-only')==cls.before['schema_sha256']
        assert snapshot('--data-only')==cls.before['data_sha256']
        cls.first=publish_ping()
        cls.second=None

    def test_01_registro_tres_tareas(self):
        self.assertEqual(set(self.first['registered']),{'geology.ping','geology.levantar_hoja','geology.preparar_digitalizacion'})

    def test_02_ping_ejecutado_por_worker(self):
        self.assertEqual((self.first['state'],self.first['result']),('SUCCESS','pong'))

    def test_03_resultado_temporal_persistido(self):
        self.assertTrue(self.first['result_persisted']);self.assertGreater(self.first['result_ttl'],0)

    def test_04_cola_json_exclusiva(self):
        self.assertEqual(self.first['queue'],PROJECT+'-tasks')
        self.assertEqual(self.first['accept_content'],['json'])
        self.assertEqual(self.first['serializer'],'json');self.assertEqual(self.first['result_serializer'],'json')
        cmd=self.worker['Config']['Cmd'];self.assertEqual(cmd[cmd.index('-Q')+1],PROJECT+'-tasks')

    def test_05_primer_ping_no_modifica_postgresql(self):
        self.assertEqual(snapshot('--schema-only'),self.before['schema_sha256'])
        self.assertEqual(snapshot('--data-only'),self.before['data_sha256'])

    def test_06_reinicio_sin_recrear(self):
        old=self.worker['State']['StartedAt'];ident=self.worker['Id']
        subprocess.run(['docker','restart','--time','10',WORKER],capture_output=True,check=True)
        current=worker_ready();self.assertEqual(current['Id'],ident);self.assertNotEqual(current['State']['StartedAt'],old)
        type(self).second=publish_ping()
        self.assertEqual(self.second['result'],'pong');self.assertNotEqual(self.first['id'],self.second['id'])

    def test_07_resultado_inicial_sobrevive_reinicio(self):
        code="""import json
from geology.nucleo.cola import celery_app
key=celery_app.backend.get_key_for_task(%r)
raw=celery_app.backend.client.get(key)
assert raw and json.loads(raw)['result']=='pong'
assert celery_app.backend.client.ttl(key)>0
print('retained')
""" % self.first['id']
        p=subprocess.run(['docker','exec',PROJECT+'-servidor-1','python','-B','-c',code],capture_output=True,text=True)
        self.assertEqual(p.returncode,0)

    def test_08_solo_dos_pings_sin_duplicados(self):
        self.assertIsNotNone(self.second)
        r=subprocess.run(['docker','logs',WORKER],capture_output=True,text=True)
        logs=r.stdout+r.stderr
        received=re.findall(r'Task ([\w.]+)\[([^\]]+)\] received',logs)
        succeeded=re.findall(r'Task ([\w.]+)\[([^\]]+)\] succeeded',logs)
        expected={self.first['id'],self.second['id']}
        self.assertEqual(len(received),2);self.assertEqual(len(succeeded),2)
        self.assertEqual({task for task,ident in received},{'geology.ping'})
        self.assertEqual({ident for task,ident in received},expected)
        self.assertEqual({ident for task,ident in succeeded},expected)

    def test_09_sin_efectos_documentales(self):
        self.assertEqual(snapshot('--schema-only'),self.before['schema_sha256'])
        self.assertEqual(snapshot('--data-only'),self.before['data_sha256'])
        for name,baseline in self.before['filesystem'].items():
            files=[(str(f.relative_to(ROOT/name)),f.stat().st_size,f.stat().st_mtime_ns)
                for f in (ROOT/name).rglob('*') if f.is_file()]
            self.assertEqual(hashlib.sha256(json.dumps(sorted(files)).encode()).hexdigest(),baseline['metadata_sha256'])

    def test_10_broker_sin_pendientes(self):
        code="""import os,redis
r=redis.Redis.from_url(os.environ['CELERY_BROKER_URL'])
for key in r.scan_iter():
 t=r.type(key)
 if t==b'list':assert r.llen(key)==0
 if t==b'hash':assert r.hlen(key)==0
 if t==b'zset':assert r.zcard(key)==0
print('empty')
"""
        p=subprocess.run(['docker','exec',PROJECT+'-servidor-1','python','-B','-c',code],capture_output=True,text=True)
        self.assertEqual(p.returncode,0)

    @classmethod
    def tearDownClass(cls):
        (ROOT/'phase8d-ping-evidence.json').write_text(json.dumps({'first':cls.first,'second':cls.second},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
