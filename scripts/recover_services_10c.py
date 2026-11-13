"""Recuperación autorizada 10C: sólo docker start de cuatro IDs existentes.

No Compose/build/recreate, DDL, DML, publicación Celery ni restauración.
Las credenciales inspeccionadas se mantienen en memoria; nunca se serializan.
"""
from operational_9f_tools import *
from urllib.parse import urlsplit, unquote
import shutil
import sys
import time
import urllib.request

ORDER = ('almacen_datos', 'mensajeria', 'servidor', 'procesador')
RESULT = {'project': PROJECT, 'started_services': [], 'stages': [], 'errors': []}
CONTAINERS = {}
BASELINE_DB = None


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def save(stage):
    RESULT['stages'].append({'stage': stage, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    (ROOT/'phase10c-recovery-evidence.json').write_text(json.dumps(RESULT, indent=2), encoding='utf-8')


def file_hash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_documents():
    expected = json.loads((ROOT/'phase9a-final-verification.json').read_text())['depot_hashes']
    actual = {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT/'deposito').rglob('*') if p.is_file()}
    require(actual == expected, 'Active documents differ from certified 17-file manifest')
    return {'count': len(actual), 'all_hashes_match': True, 'unexpected_files': 0, 'sha256': actual}


def preflight():
    require(not (ROOT/'phase10c-recovery-evidence.json').exists(), 'Existing phase10C evidence: inspect before any repeat')
    require(json.loads(checked(['docker', 'info', '--format', '{{json .OSType}}'])) == 'linux', 'Linux Docker engine unavailable')
    reference = json.loads((ROOT/'phase10b-recovery-preconditions.json').read_text())
    previous = json.loads((ROOT/'phase10b-docker-diagnosis.json').read_text())
    cert = json.loads((ROOT/'phase10b-certification-results.json').read_text())
    require(all(cert['suites'][k]['pass'] for k in ('unit', 'integration')), '10B certification not passed')
    frozen = json.loads((Path(cert['directory'])/'results/source-hashes.json').read_text())
    require(all(file_hash(ROOT/n) == sha for n, sha in frozen.items()), 'Code differs from tested 10B frozen source')
    require({str(p.relative_to(ROOT)) for n in ('geology','tests') for p in (ROOT/n).rglob('*.py')} == set(frozen), 'Untested Python file added or removed')
    hashes = json.loads((ROOT/'phase10a-before-files.json').read_text())
    protected = {n: file_hash(ROOT/n) == hashes[n] for n in
        ('.env', 'docker-compose.yml', 'compose.local.yml', 'Dockerfile', 'Dockerfile.document.local')}
    require(all(protected.values()), 'Protected configuration changed')
    envs = {}
    for name in ORDER:
        c = inspect(reference['services'][name]['id']); CONTAINERS[name] = c
        require(c['Config']['Labels'].get('com.docker.compose.project') == PROJECT, 'Wrong project: '+name)
        require(c['Config']['Labels'].get('com.docker.compose.service') == name, 'Wrong service: '+name)
        require(c['Mounts'] == previous['services'][name]['mounts'], 'Original mounts changed: '+name)
        require(sorted(c['NetworkSettings']['Networks']) == sorted(previous['services'][name]['networks']), 'Network membership changed')
        ports = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8080'}]} if name == 'servidor' else {}
        require(c['HostConfig']['PortBindings'] == ports and not c['HostConfig']['PublishAllPorts'], 'Unsafe port publication')
        require(c['State']['Status'] in ('exited', 'created', 'running'), 'Unexpected container state')
        envs[name] = dict(x.split('=', 1) for x in c['Config']['Env'] if '=' in x)
    baseline = json.loads((ROOT/'phase10a-preflight.json').read_text())
    require(all(CONTAINERS[n]['Image'] == baseline['services'][n]['image'] for n in ORDER), 'Original image digest changed')
    pg = envs['almacen_datos']
    for name in ('servidor', 'procesador'):
        e = envs[name]; u = urlsplit(e['DATABASE_URL'])
        require(u.scheme == 'postgresql+psycopg2' and u.hostname == 'almacen_datos'
                and u.port == 5432 and u.path == '/geology', 'Nonlocal database connection')
        require(unquote(u.username or '') == pg['POSTGRES_USER'] and unquote(u.password or '') == pg['POSTGRES_PASSWORD'], 'Database credentials incoherent')
        require(all(e.get(k) == pg[v] for k,v in [('PG_USUARIO','POSTGRES_USER'), ('PG_BASE','POSTGRES_DB'), ('PG_CLAVE','POSTGRES_PASSWORD')]), 'PG variables incoherent')
        keys = [k for k in e if 'API_KEY' in k or k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'HF_TOKEN')]
        require(all(not e[k] for k in keys), 'Provider credential present; values omitted')
        require(e['LEVANTAR_AL_CARGAR'].lower() in ('no','0','false'), 'Automatic reading enabled')
        require(e['GEOLOGY_LOCAL_PROJECT'] == PROJECT and e['GEOLOGY_COLA'] == PROJECT+'-tasks', 'Wrong queue')
        require(e['CELERY_BROKER_URL'] == 'redis://mensajeria:6379/0' and e['CELERY_RESULT_BACKEND'] == 'redis://mensajeria:6379/1', 'Nonlocal broker/backend')
        require(e.get('PDFA_PERFIL') == '1b', 'Configured PDF/A default changed')
    for suffix in ('pgdata', 'redisdata'):
        v = object_inspect('volume', PROJECT+'_'+suffix)
        require(v['Labels'].get('com.docker.compose.project') == PROJECT, 'Volume ownership mismatch')
        owners = checked(['docker','ps','-aq','--no-trunc','--filter','volume='+v['Name']]).splitlines()
        expected_owner = CONTAINERS['almacen_datos' if suffix=='pgdata' else 'mensajeria']['Id']
        require(owners == [expected_owner], 'Original data volume shared with another container')
    for suffix, internal in (('network',True), ('frontend',False)):
        net = object_inspect('network', PROJECT+'_'+suffix)
        require(net['Id'] == reference['networks'][net['Name']]['id'], 'Network identity changed')
        require(net['Internal'] == internal and net['Labels'].get('com.docker.compose.project') == PROJECT, 'Network isolation changed')
        for cid in net.get('Containers', {}):
            require(inspect(cid)['Config']['Labels'].get('com.docker.compose.project') == PROJECT, 'Foreign project attached to original network')
    copy = json.loads((ROOT/'phase9d-backup-copy.json').read_text()); backup = Path(copy['destination'])
    anchor = json.loads((ROOT/'phase9d-final-backup-acl.json').read_text())
    require(all(file_hash(backup/x['name']) == x['sha256'] for x in anchor['files']), 'Protected backup integrity failure')
    free = {d:shutil.disk_usage(d+':/').free for d in ('C','D','F')}
    require(free['C'] > 512*1024**2 and free['D'] > 128*1024**2 and free['F'] > 1024**3, 'Insufficient startup/log/WAL safety reserve')
    RESULT['preflight'] = {'linux_engine':True, 'backup':str(backup), 'backup_files_verified':len(anchor['files']),
        'provider_keys_empty':True, 'automatic_reading_disabled':True, 'protected_files_unchanged':protected,
        'tested_code_unchanged':True, 'free_bytes':free, 'before':{n:summary(c) for n,c in CONTAINERS.items()},
        'documents':check_documents(), 'reserve_note':'Only service recovery and read-only checks; no conversion/export workload. C512MiB logs, D128MiB evidence, F1GiB WAL/AOF startup headroom.'}
    RESULT['backup_reference'] = json.loads((backup/'recovery-reference.json').read_text())
    save('PREFLIGHT_PASS')


def start(name):
    cid = CONTAINERS[name]['Id']; c = inspect(cid)
    require(c['Config']['Labels'].get('com.docker.compose.project') == PROJECT, 'Start identity mismatch')
    if not c['State']['Running']:
        checked(['docker','start',cid]); RESULT['started_services'].append(name)
    deadline = time.monotonic()+100
    while time.monotonic() < deadline:
        c = inspect(cid)
        require(c['State']['Running'], 'Service stopped: '+name)
        if name == 'procesador':
            p = command(['docker','logs','--since',c['State']['StartedAt'],cid]); log = p.stdout+p.stderr
            require(not re.search(r'Task\s+[^\[]+\[[^\]]+\]\s+received', log), 'Unexpected task receipt')
            if ' ready.' in log:
                names = sorted(set(re.findall(r'geology\.(?:ping|levantar_hoja|preparar_digitalizacion)',log)))
                require(len(names)==3 and 'Connected to redis://mensajeria:6379/0' in log, 'Worker registration/Redis readiness missing')
                require(not re.search(r'(?m)\[.*(?:ERROR|CRITICAL)\]|Traceback',log), 'Critical worker startup error')
                RESULT['worker'] = {'registered_tasks':names, 'redis_connected':True, 'ready':True,
                    'tasks_received':0, 'queue':PROJECT+'-tasks', 'startup_log_sha256':hashlib.sha256(log.encode()).hexdigest(),
                    'safe_startup_excerpt':[s for s in log.splitlines() if any(k in s for k in ('[tasks]','geology.','Connected to redis://',' ready.','concurrency:','exchange='))]}
                break
        elif c['State'].get('Health',{}).get('Status') == 'healthy':
            break
        time.sleep(1)
    else:
        raise RuntimeError('Readiness timeout: '+name)
    RESULT.setdefault('services',{})[name] = summary(c)
    save('READY_'+name.upper())


def database(stage):
    snap = database_snapshot(); ref = RESULT['backup_reference']
    require(snap['tables']==27 and snap['records']==26 and snap['traces']==9, 'Database reference counts differ; no automatic correction')
    require(snap['schema_sha256']==ref['schema_sha256'] and snap['data_sha256']==ref['data_sha256'], 'Database certified fingerprint mismatch')
    require(snap['all_constraints_valid'] and snap['all_indexes_valid'] and snap['admin']['present'] and snap['admin']['active'], 'Database constraints/admin invalid')
    for entry in snap['document_references']:
        path = Path(entry['path'].replace('/srv/geology/',str(ROOT)+'/',1))
        require(path.is_file(), 'Missing document reference')
        if entry['sha256']:
            require(file_hash(path)==entry['sha256'], 'Referenced document SHA mismatch')
    RESULT.setdefault('database',{})[stage] = snap
    if stage != 'before_application':
        before = RESULT['database']['before_application']
        require(snap['catalog_object_fingerprint']==before['catalog_object_fingerprint'], 'Schema objects changed during startup')
    save('DATABASE_'+stage.upper())


def queue(stage):
    q = queue_snapshot(); RESULT.setdefault('queues',{})[stage] = q
    save('QUEUE_'+stage.upper())
    require(q['safe_empty'], 'Pending/unknown/unacked messages: stop sequence')


def http():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})); result = {}
    for path in ('/estado','/app','/openapi.json'):
        with opener.open('http://127.0.0.1:8080'+path, timeout=15) as response:
            body = response.read(); require(response.status==200, 'HTTP failure')
            entry = {'status':response.status, 'bytes':len(body)}
            if path == '/estado':
                entry['json'] = json.loads(body); require(entry['json']['estado']=='operativo', 'Not operational')
            elif path == '/app':
                require(b'GEOLOGY' in body, 'Unexpected interface')
            else:
                spec = json.loads(body); entry['version']=spec['info']['version'];entry['route_count']=len(spec['paths']);entry['path_fingerprint']=digest(sorted(spec['paths']))
                baseline = json.loads((ROOT/'phase9f-results.json').read_text())['http']['/openapi.json']
                require(entry['path_fingerprint']==baseline['path_fingerprint'], 'HTTP API path registry changed')
            result[path]=entry
    RESULT['http'] = result; save('HTTP_PASS')


def main():
    preflight()
    start('almacen_datos'); database('before_application')
    start('mensajeria'); queue('before_server')
    start('servidor'); http(); database('after_server')
    queue('before_worker'); start('procesador'); queue('after_worker')
    database('after_worker'); RESULT['documents_final']=check_documents()
    save('RECOVERED_PENDING_READONLY_TESTS_AND_VERSION_AUDIT')
    print(json.dumps({'started':RESULT['started_services'], 'services':{n:c['status'] for n,c in RESULT['services'].items()},
        'http':RESULT['http'], 'database_records':RESULT['database']['after_worker']['records'],
        'queue':RESULT['queues']['after_worker'],'documents':RESULT['documents_final']['count']}, indent=2), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        RESULT['errors'].append({'type':type(exc).__name__,'message':str(exc)})
        save('STOPPED_FOR_DIAGNOSIS')
        print('Recovery stopped: '+str(exc),file=sys.stderr)
        sys.exit(1)
