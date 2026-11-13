"""Start only four existing original containers; stop sequence on failed checks.

No Compose up/build, no task publication, no data correction or restore.
"""
from operational_9f_tools import *
from urllib.parse import urlsplit,unquote
import time,urllib.request,re,sys,os

ORDER=('almacen_datos','mensajeria','servidor','procesador')
OUT=ROOT/'expedidos/evidencias_9f'
R={'project':PROJECT,'started_services':[],'queue_checks':{},'database':{},'errors':[]}
STATE={}

def save(stage):
    STATE['stage']=stage
    (ROOT/'phase9f-recovery-state.json').write_text(json.dumps(STATE,indent=2),encoding='utf-8')
    (ROOT/'phase9f-recovery-evidence.json').write_text(json.dumps(R,indent=2),encoding='utf-8')
def require(ok,message):
    if not ok:raise RuntimeError(message)
def env(c):return dict(x.split('=',1) for x in c['Config']['Env'])

def preflight():
    if (ROOT/'phase9f-recovery-state.json').exists():
        old=json.loads((ROOT/'phase9f-recovery-state.json').read_text())
        prior=json.loads((ROOT/'phase9f-recovery-evidence.json').read_text())
        require('--retry-static-preflight' in sys.argv and old['stage']=='STOPPED_FOR_DIAGNOSIS'
            and not prior['started_services'] and 'container_ids' not in old,'Existing 9F run requires inspection')
        archive=ROOT/'phase9f-preflight-attempt-1.json'
        with archive.open('x',encoding='utf-8') as f:json.dump({'state':old,'evidence':prior},f,indent=2)
        R['preflight_retry_note']='Default PostgreSQL command is inherited from the image when Compose command is null; verified against cached image, no service had been started.'
    require(json.loads(checked(['docker','info','--format','{{json .OSType}}']))=='linux','Linux engine required')
    baseline=json.loads((ROOT/'phase9a-final-verification.json').read_text())
    cfg=json.loads(checked(['docker','compose','--env-file','.env','-f','compose.local.yml','-p',PROJECT,'--profile','application','config','--format','json']))
    containers={};envs={}
    for service in ORDER:
        c=inspect(PROJECT+'-'+service+'-1');containers[service]=c;envs[service]=env(c)
        require(c['Id']==baseline['services'][service]['id'],'Container identity mismatch: '+service)
        require(c['Config']['Labels']['com.docker.compose.project']==PROJECT,'Project label mismatch')
        wanted=cfg['services'][service].get('environment',{})
        mismatch=[k for k,v in wanted.items() if envs[service].get(k)!=('' if v is None else str(v))]
        require(not mismatch,'Current config mismatch variable names: '+','.join(mismatch))
        wanted_cmd=cfg['services'][service].get('command')
        if wanted_cmd is None:wanted_cmd=object_inspect('image',c['Image'])['Config']['Cmd']
        require(c['Config']['Cmd']==wanted_cmd,'Runtime command differs: '+service)
        require(c['HostConfig']['PortBindings']==({'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8080'}]} if service=='servidor' else {}),'Unsafe published binding')
        expected={PROJECT+'_network'}|({PROJECT+'_frontend'} if service=='servidor' else set())
        require(set(c['NetworkSettings'].get('Networks') or {})==expected,'Unexpected network membership')
    for service,suffix in (('almacen_datos','pgdata'),('mensajeria','redisdata')):
        vols=[m['Name'] for m in containers[service]['Mounts'] if m['Type']=='volume']
        require(vols==[PROJECT+'_'+suffix],'Unexpected original data volume')
        v=object_inspect('volume',vols[0]);require(v['Driver']=='local' and v['Labels']['com.docker.compose.project']==PROJECT,'Volume ownership mismatch')
    for suffix,internal in (('network',True),('frontend',False)):
        n=object_inspect('network',PROJECT+'_'+suffix)
        require(n['Labels']['com.docker.compose.project']==PROJECT and n['Internal']==internal,'Network isolation mismatch')
    pg_env=envs['almacen_datos']
    for service in ('servidor','procesador'):
        e=envs[service];u=urlsplit(e['DATABASE_URL'])
        require(u.scheme=='postgresql+psycopg2' and u.hostname=='almacen_datos' and u.port==5432 and u.path=='/geology','Nonlocal database configuration')
        require(unquote(u.username)==pg_env['POSTGRES_USER'] and unquote(u.password)==pg_env['POSTGRES_PASSWORD'],'Incoherent PG credentials')
        require(e.get('PG_USUARIO')==pg_env['POSTGRES_USER'] and e.get('PG_BASE')==pg_env['POSTGRES_DB'] and e.get('PG_CLAVE')==pg_env['POSTGRES_PASSWORD'],'PG variables disagree')
        require(e['CELERY_BROKER_URL']=='redis://mensajeria:6379/0' and e['CELERY_RESULT_BACKEND']=='redis://mensajeria:6379/1','Nonlocal Redis URL')
        sensitive=[k for k in e if '_API_KEY' in k or k in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','HF_TOKEN')]
        require(all(not e[k] for k in sensitive),'Nonempty provider credential; values omitted')
        require(e['LEVANTAR_AL_CARGAR'].lower() in ('no','false','0'),'Automatic reading must be disabled')
        require(e['GEOLOGY_LOCAL_PROJECT']==PROJECT and e['GEOLOGY_COLA']==PROJECT+'-tasks','Queue/project mismatch')
        require(e.get('GEOLOGY_ENTORNO','local').lower() in ('local','desarrollo','development','test','testing','pruebas'),'Nonlocal environment')
        require(e.get('GEOLOGY_PERMITIR_DDL','0')!='1','DDL permission must not be enabled')
        require(len(e['GEOLOGY_CLAVE'].encode())>=32,'Local session key not configured')
    before=json.loads((ROOT/'phase9a-before-files.json').read_text())
    require(all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in before.items() if n.startswith('geology/')),'Application source changed; review startup first')
    copy=json.loads((ROOT/'phase9d-backup-copy.json').read_text());b=Path(copy['destination'])
    anchor=json.loads((ROOT/'phase9d-final-backup-acl.json').read_text(encoding='utf-8-sig'))
    require(all(hashlib.sha256((b/x['name']).read_bytes()).hexdigest()==x['sha256'] for x in anchor['files']),'Protected backup changed')
    STATE.update(container_ids={s:c['Id'] for s,c in containers.items()},backup=str(b))
    temp=json.loads((ROOT/'phase9e-run-state.json').read_text());STATE['temporary_container_id']=temp['container_id']
    R['temporary_before']=summary(inspect(temp['container_id']))
    R['preflight']={'static_checks':'PASS','ai_credentials_empty':True,'auto_reading_disabled':True,
        'config_matches_existing_containers':True,'published_only_localhost':True,
        'queue_dynamic_check':'Required after Redis health, before server and worker',
        'original_before':{s:summary(c) for s,c in containers.items()},
        'file_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('docker-compose.yml','compose.local.yml','Dockerfile','Dockerfile.compat.local','Dockerfile.document.local')}}
    OUT.mkdir(exist_ok=False);save('PREFLIGHT_STATIC_PASS')

def start(service):
    cid=STATE['container_ids'][service];c=inspect(cid)
    require(c['Config']['Labels']['com.docker.compose.project']==PROJECT,'Start target not original')
    started=time.monotonic()
    if not c['State']['Running']:
        checked(['docker','start',cid]);R['started_services'].append(service)
    for _ in range(90):
        c=inspect(cid);require(c['Id']==cid and c['State']['Running'],'Service stopped during recovery: '+service)
        if service=='procesador':
            p=command(['docker','logs','--since',c['State']['StartedAt'],cid]);text=p.stdout+p.stderr
            if ' ready.' in text:
                require('Connected to redis://mensajeria:6379/0' in text,'Worker Redis connection not certified')
                require(all(name in text for name in ('geology.ping','geology.levantar_hoja','geology.preparar_digitalizacion')),'Worker missing required task')
                require(not re.search(r'Task\s+[^\[]+\[[^\]]+\]\s+received',text),'A task was received; inspect before continuing')
                (OUT/'worker-startup.log').write_text(text,encoding='utf-8');break
        elif c['State'].get('Health',{}).get('Status')=='healthy':break
        time.sleep(1)
    else:raise RuntimeError('Readiness timeout: '+service)
    R.setdefault('services',{})[service]=summary(c)|{'readiness_seconds':time.monotonic()-started};save('STARTED_'+service.upper())

def db_record(stage):
    snap=database_snapshot();ref=json.loads((Path(STATE['backup'])/'recovery-reference.json').read_text())
    snap['comparison_to_backup']={'schema':snap['schema_sha256']==ref['schema_sha256'],
        'data':snap['data_sha256']==ref['data_sha256'],'row_counts':snap['row_counts']==ref['expected_row_counts']}
    snap['different_row_counts']={k:{'current':snap['row_counts'].get(k),'backup':v} for k,v in ref['expected_row_counts'].items() if snap['row_counts'].get(k)!=v}
    R['database'][stage]=snap;save('DATABASE_CHECK_'+stage.upper())
    require(snap['tables']==27 and snap['all_constraints_valid'] and snap['all_indexes_valid'],'Database structure requires investigation')
    # Document any data difference, never correct or restore automatically.
    return snap

def queue_record(stage):
    q=queue_snapshot();R['queue_checks'][stage]=q;save('QUEUE_CHECK_'+stage.upper())
    require(q['safe_empty'],'Pending/unacked/unknown broker data; do not start next service')

def main():
    global R,STATE
    if '--resume-after-broker-diagnosis' in sys.argv:
        old=json.loads((ROOT/'phase9f-recovery-state.json').read_text())
        prior=json.loads((ROOT/'phase9f-recovery-evidence.json').read_text())
        require(old['stage']=='STOPPED_FOR_DIAGNOSIS' and prior['started_services']==['almacen_datos','mensajeria'],'Unexpected resume state')
        require(all(prior['database']['before_application']['comparison_to_backup'].values()),'Database differs; diagnose first')
        with (ROOT/'phase9f-broker-diagnosis.json').open('x',encoding='utf-8') as f:
            json.dump({'state':old,'evidence':prior,'diagnosis':'One owned celeryev routing-binding set, not a pending message. No list/hash/zset backlog. No keys removed.'},f,indent=2)
        R=prior;STATE=old;R['errors_resolved']=R.pop('errors');R['errors']=[]
        R['broker_metadata_note']='Owned celeryev set classified by exact key, type and worker-event routing-member format; no pending tasks and no Redis cleanup.'
        for service,cid in STATE['container_ids'].items():require(inspect(cid)['Config']['Labels']['com.docker.compose.project']==PROJECT,'Resume identity mismatch')
    else:preflight()
    start('almacen_datos');db_record('before_application')
    start('mensajeria');queue_record('before_server')
    start('servidor')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));http={}
    for path in ('/estado','/app','/openapi.json'):
        with opener.open('http://127.0.0.1:8080'+path,timeout=10) as f:
            body=f.read();require(f.status==200,'HTTP check failed')
            entry={'status':f.status,'bytes':len(body)}
            if path=='/estado':entry['json']=json.loads(body);require(entry['json']['estado']=='operativo','Application not operative')
            elif path=='/app':require(b'GEOLOGY' in body,'Unexpected web interface')
            else:
                spec=json.loads(body);entry['route_count']=len(spec['paths']);require(entry['route_count']>100,'Routes missing')
                entry['path_fingerprint']=digest(sorted(spec['paths']))
            http[path]=entry
    R['http']=http
    a=db_record('after_server');b=R['database']['before_application']
    require(a['schema_sha256']==b['schema_sha256'] and a['catalog_object_fingerprint']==b['catalog_object_fingerprint'],'Schema/catalog changed during startup')
    queue_record('before_worker');start('procesador');queue_record('after_worker')
    R['temporary_after']=summary(inspect(STATE['temporary_container_id']))
    require(R['temporary_before']==R['temporary_after'],'Temporary restore environment metadata changed')
    save('RECOVERED_PENDING_READONLY_REGRESSION')
    print(json.dumps({'started_in_order':R['started_services'],'http':R['http'],
        'rows':a['records'],'database_matches_backup':a['comparison_to_backup'],
        'queues':R['queue_checks'],'temporary_environment_untouched':True},indent=2),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as ex:
        R['errors'].append({'type':type(ex).__name__,'message':str(ex)})
        save('STOPPED_FOR_DIAGNOSIS');print('Recovery sequence stopped: '+str(ex),file=sys.stderr);sys.exit(1)
