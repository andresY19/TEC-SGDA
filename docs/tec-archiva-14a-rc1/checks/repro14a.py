from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
import json,re,subprocess,time,hashlib,sys
from datetime import datetime, timezone
from original14a import docker,pg,schema,catalog,service,sha
B=Path(__file__).resolve().parent; R=Path.cwd(); E=B/'campaign-full'
state=json.loads((E/'phase14a-environment.json').read_text()); project=state['project']; assert project=='geology-auto11e-a11y14a-full-66ad0b80'
control=Path(state['control']); assert control.parent==E
build=json.loads((B/'build14a.json').read_text())
original_pg=service('almacen_datos')
def ids_for(name):
 ids=docker('ps','-q','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service='+name).decode().split()
 assert len(ids)==1,name
 return ids[0]
pg_id=ids_for('pg'); redis_id=ids_for('redis')
db='geology_14a_empty_boot'
schema_original=schema(original_pg,'geology','geology')
schema_rc=schema(pg_id,'cert_admin','geology_cert10d')
column_original=catalog(original_pg,'geology','geology')
column_rc=catalog(pg_id,'cert_admin','geology_cert10d')
schema_compatible={'original_tables':len(column_original),'rc_tables':len(column_rc),'schema_hash_original':sha(schema_original),'schema_hash_rc':sha(schema_rc),'exact_normalized_schema':schema_original==schema_rc,'columns_equal':column_original==column_rc}
if column_original!=column_rc:
 schema_compatible['different_table_columns']=[t for t in sorted(column_original.keys()|column_rc.keys()) if column_original.get(t)!=column_rc.get(t)]
assert len(column_original)==len(column_rc)==27
backend=project+'_backend'
network=json.loads(docker('network','inspect',backend))[0]
assert network['Internal'] and network['Labels']['com.docker.compose.project']==project
assert not json.loads(docker('inspect',pg_id))[0]['HostConfig']['PortBindings']
assert not json.loads(docker('inspect',redis_id))[0]['HostConfig']['PortBindings']
docker('exec',pg_id,'createdb','-U','cert_admin','-O','cert_worker',db)
def psql(sql):return docker('exec',pg_id,'psql','-XAt','-v','ON_ERROR_STOP=1','-U','cert_admin','-d','postgres','-c',sql).decode().strip()
psql(f"ALTER DATABASE {db} SET log_statement = 'ddl'")
assert pg(pg_id,'show log_statement','cert_worker',db)=='ddl'
def objects():
 return json.loads(pg(pg_id,"""SELECT json_build_object(
 'tables', (SELECT count(*) FROM pg_tables WHERE schemaname='public'),
 'indexes', (SELECT count(*) FROM pg_indexes WHERE schemaname='public'),
 'public_relations', (SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace),
 'user_schemas',(SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('information_schema','public') AND nspname NOT LIKE 'pg_%'),
 'public_routines',(SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace))""",'cert_admin',db))
before=objects(); assert all(n==0 for n in before.values())
env=dict(line.split('=',1) for line in (control/'app-private.env').read_text().splitlines() if '=' in line)
parsed=urlsplit(env['DATABASE_URL']); assert parsed.hostname=='pg' and parsed.username=='cert_worker'
env['DATABASE_URL']=urlunsplit(parsed._replace(path='/'+db)); env['PG_BASE']=db
env['GEOLOGY_COLA']=project+'-bootproof'
env.pop('GEOLOGY_PERMITIR_DDL',None)
config=control/'empty-boot-private.env'
with config.open('x',encoding='utf-8') as f:f.write(''.join(k+'='+v+'\n' for k,v in env.items()))
def startup(kind):
 name=project+'-boot-'+kind
 image=build['tags'][kind]
 cmd=['run','-d','--pull=never','--name',name,'--label','com.docker.compose.project='+project,'--label','tec-archiva.probe=empty-schema','--network',backend,'--env-file',str(config),
      '--user','10001:10001','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
      '--tmpfs','/tmp:uid=10001,gid=10001,mode=1770','--tmpfs','/home/geology:uid=10001,gid=10001,mode=0700']
 return docker(*cmd,image).decode().strip()
def ready(id,kind):
 for _ in range(65):
  if kind=='fastapi':
   r=subprocess.run(['docker','exec',id,'python','-B','-c',"import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/estado',timeout=2); assert json.load(r)['estado']=='operativo'"],capture_output=True)
   if not r.returncode:return
  else:
   r=subprocess.run(['docker','logs',id],capture_output=True)
   if b' ready.' in r.stdout+r.stderr:return
  time.sleep(1)
 raise RuntimeError(kind+' did not become ready')
def runtime_evidence(id,kind):
 x=json.loads(docker('inspect',id))[0]
 assert x['Image']==build['images'][kind]['id']
 assert x['HostConfig']['ReadonlyRootfs'] and x['Config']['User']=='10001:10001' and 'ALL' in x['HostConfig']['CapDrop']
 assert list(x['NetworkSettings']['Networks'])==[backend] and not x['HostConfig']['PortBindings']
 assert not any(m['Type']=='bind' for m in x['Mounts'])
 pid_user=docker('exec',id,'id','-u').decode().strip(); pid_group=docker('exec',id,'id','-g').decode().strip()
 assert (pid_user,pid_group)==('10001','10001')
 p='/opt/geology-distribution/build-manifest.json'
 manifest=docker('exec',id,'cat',p)
 expected=(R/'distribution/tec-archiva-13g-a01/build-manifest.json').read_bytes()
 assert manifest==expected
 verify="import hashlib,json,pathlib; r=pathlib.Path('/srv/geology'); m=json.loads(pathlib.Path('/opt/geology-distribution/build-manifest.json').read_text()); assert all(hashlib.sha256((r/k).read_bytes()).hexdigest()==v for k,v in m['source_sha256'].items());print(len(m['source_sha256']))"
 count=int(docker('exec',id,'python','-B','-c',verify))
 return {'image':x['Image'],'uid':int(pid_user),'gid':int(pid_group),'source_files_verified':count,'read_only_root':True,'bind_mounts':0,'ports_published':0}
started={}
since=datetime.now(timezone.utc).isoformat()
try:
 for kind in ['fastapi','celery']:
  started[kind]=startup(kind);ready(started[kind],kind)
 after=objects()
 log=subprocess.run(['docker','logs','--since',since,pg_id],capture_output=True,check=True)
 ddl_lines=sum(bool(re.search(rb'(?:statement|STATEMENT):\s*(?:CREATE|ALTER|DROP|TRUNCATE|REINDEX|COMMENT|GRANT|REVOKE)\b',line,re.I)) for line in (log.stdout+log.stderr).splitlines())
 result={'project':project,'boot_database':db,'before':before,'after':after,'startup_ddl_detected':before!=after or ddl_lines>0,'ddl_log_statements':ddl_lines,'ddl_logging_verified':True,'schema_compatibility':schema_compatible,'services':{kind:runtime_evidence(id,kind) for kind,id in started.items()}}
 assert before==after and not ddl_lines
 lock=(R/'distribution/tec-archiva-13g-a01/requirements.autonomous.lock').read_text(encoding='utf-8').splitlines()
 req=dict(line.split('==',1) for line in lock if line and not line.startswith('#'))
 script="import importlib.metadata as m,json,sys; print(json.dumps({k:m.version(k) for k in json.load(sys.stdin)}))"
 versions=json.loads(docker('exec','-i',started['fastapi'],'python','-B','-c',script,source=json.dumps(list(req)).encode()))
 worker_versions=json.loads(docker('exec','-i',started['celery'],'python','-B','-c',script,source=json.dumps(list(req)).encode()))
 result['python_lock']={'entries':len(req),'matches':req==versions==worker_versions,'installed':versions}
 assert req==versions==worker_versions
 probes={'python':['python','--version'],'ghostscript':['gs','--version'],'ocrmypdf':['ocrmypdf','--version'],'tesseract':['tesseract','--version'],'verapdf':['/opt/verapdf/verapdf','--version']}
 result['tools']={}
 for name,args in probes.items():
  p=subprocess.run(['docker','exec',started['fastapi'],*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
  assert p.returncode==0,name
  result['tools'][name]=(p.stdout or p.stderr).splitlines()[0].strip()
 result['postgresql']=pg(pg_id,'show server_version','cert_admin','geology_cert10d')
 result['redis']=docker('exec',redis_id,'redis-server','--version').decode().strip()
 aof=docker('exec',redis_id,'redis-cli','CONFIG','GET','appendonly').decode().split()
 assert aof==['appendonly','yes']
 result['redis_aof']=True
 (B/'results/reproducibilidad14a.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='python_lock'}))
finally:
 for id in reversed(list(started.values())):docker('stop',id)
