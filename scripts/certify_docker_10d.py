"""Crea y conserva infraestructura exclusiva 10D; no altera el proyecto original."""
from pathlib import Path
import datetime
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
APP_IMAGE='sha256:a77f24483c87e509b9c48d34fe1a76f115ac92688c4156b7ab1d8e049f1e7a10'
STATE={}


def command(args):
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:raise RuntimeError('Docker certification command failed: '+args[0]+' code '+str(r.returncode))
    return r.stdout.strip()


def save(stage):
    STATE['stage']=stage
    STATE['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (ROOT/'phase10d-environment.json').write_text(json.dumps(STATE,indent=2),encoding='utf-8')


def healthy(name):
    for _ in range(80):
        c=json.loads(command(['docker','inspect',name]))[0]
        if not c['State']['Running']:raise RuntimeError('Temporary container stopped: '+name)
        if c['State'].get('Health',{}).get('Status')=='healthy':return
        time.sleep(1)
    raise RuntimeError('Temporary health timeout: '+name)


def exec_logged(kind,args):
    base=Path(STATE['directory'])
    with (base/'results'/f'{kind}-stdout.txt').open('x',encoding='utf-8') as stdout, \
         (base/'results'/f'{kind}-stderr.txt').open('x',encoding='utf-8') as stderr:
        r=subprocess.run(['docker','exec',STATE['containers']['runner'],'python','-B',*args],
                         stdout=stdout,stderr=stderr,timeout=1200)
    log=(base/'results'/f'{kind}-stderr.txt').read_text(encoding='utf-8')
    STATE.setdefault('runs',{})[kind]={'returncode':r.returncode,'pass':r.returncode==0}
    save('FINISHED_'+kind.upper())
    print(kind,'code',r.returncode,log[-2800:],flush=True)
    if r.returncode:raise RuntimeError('Certification suite failed: '+kind)


def main():
    if (ROOT/'phase10d-environment.json').exists():
        prior=json.loads((ROOT/'phase10d-environment.json').read_text())
        assert '--retry-preprovision' in sys.argv and 'project' not in prior and prior.get('error',{}).get('type') in ('TypeError','StopIteration'), 'Inspect existing 10D environment before retry'
        archive=ROOT/f"phase10d-preprovision-attempt{1+len(list(ROOT.glob('phase10d-preprovision-attempt*.json')))}.json"
        with archive.open('x') as f:json.dump(prior,f,indent=2)
        STATE['resolved_setup_issue']='A Docker network has null IPAM.Config; safely treated as no subnets. Prior files retained; no Docker resource had yet been created.'
    assert json.loads((ROOT/'phase10d-preflight.json').read_text())['checks']['status']=='PASS'
    project='geology-pdfa10d-20261107-'+uuid.uuid4().hex[:8]
    base=Path.home()/'GEOLOGY_PDFA_Docker_Cert'/project;base.mkdir(parents=True,exist_ok=False)
    # Restrict new credentials and synthetic evidence before creating credential files.
    sid=command(['powershell','-NoProfile','-Command', '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'])
    command(['icacls',str(base),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'])
    for folder in ['results','audit','tmp','regression','bin']: (base/folder).mkdir()
    for folder in ['geology','tests']:shutil.copytree(ROOT/folder,base/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(ROOT/'scripts/client_pdfa_cert_10d.py',base/'client.py')
    shutil.copy2(ROOT/'scripts/worker_pdfa_cert_10d.py',base/'worker.py')
    pg_password=secrets.token_hex(32);app_password=secrets.token_hex(32);redis_password=secrets.token_hex(32)
    def write(name,lines):
        with (base/name).open('x',encoding='utf-8',newline='\n') as f:f.write(lines)
    write('private.json',json.dumps({'admin_url':f'postgresql+psycopg2://cert_admin:{pg_password}@pg:5432/geology_cert10d','app_password':app_password}))
    write('pg-private.env',f'POSTGRES_USER=cert_admin\nPOSTGRES_PASSWORD={pg_password}\nPOSTGRES_DB=geology_cert10d\n')
    write('redis-private.env',f'REDISCLI_AUTH={redis_password}\n')
    write('redis-private.conf',f'bind 0.0.0.0\nprotected-mode yes\nrequirepass {redis_password}\nappendonly yes\nappendfsync everysec\ndir /data\n')
    env={'DATABASE_URL':f'postgresql+psycopg2://cert_worker:{app_password}@pg:5432/geology_cert10d',
        'PG_USUARIO':'cert_worker','PG_CLAVE':app_password,'PG_BASE':'geology_cert10d','PG_SERVIDOR':'pg','PG_PUERTO':'5432',
        'CELERY_BROKER_URL':f'redis://:{redis_password}@redis:6379/0',
        'CELERY_RESULT_BACKEND':f'redis://:{redis_password}@redis:6379/1',
        'GEOLOGY_LOCAL_PROJECT':project,'GEOLOGY_COLA':project+'-tasks','GEOLOGY_ENTORNO':'test',
        'GEOLOGY_CLAVE':secrets.token_hex(48),'LEVANTAR_AL_CARGAR':'no','PDFA_PERFIL':'1b','GEOLOGY_PERMITIR_DDL':'0',
        'VERAPDF_BIN':'/cert/bin/verapdf','PATH':'/cert/bin:/opt/geology-ghostscript/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'PYTHONPATH':'/srv/geology','TMPDIR':'/cert/tmp','PYTHONDONTWRITEBYTECODE':'1'}
    for name in ['ANTHROPIC_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY',*[f'GEMINI_API_KEY_{i}' for i in range(1,8)]]:env[name]=''
    write('app-private.env',''.join(k+'='+v+'\n' for k,v in env.items()))
    for tool,actual,marker in [('ocrmypdf','/usr/local/bin/ocrmypdf','/cases/conversion_error/'),('verapdf','/opt/verapdf/verapdf','/cases/validation_error/')]:
        write('bin/'+tool,'#!/usr/local/bin/python\nimport os,sys\n'+
            f'if any({marker!r} in a for a in sys.argv[1:]):\n print("SINTETICO 10D fallo controlado",file=sys.stderr);sys.exit(71)\n'+
            f'os.execv({actual!r},[{actual!r}]+sys.argv[1:])\n')
    network=project+'_internal';volumes=[project+'_pgdata',project+'_redisdata']
    network_ids=command(['docker','network','ls','-q']).splitlines()
    networks=json.loads(command(['docker','network','inspect',*network_ids]));used=[ipaddress.ip_network(c['Subnet']) for n in networks for c in (n['IPAM'].get('Config') or []) if 'Subnet' in c]
    subnet=next(ipaddress.ip_network(f'10.254.{i}.0/28') for i in range(240,255) if not any(ipaddress.ip_network(f'10.254.{i}.0/28').overlaps(n) for n in used if n.version==4))
    STATE.update(project=project,directory=str(base),network=network,subnet=str(subnet),volumes=volumes,
        containers={k:project+'-'+k for k in ['pg','redis','worker','runner']},app_image=APP_IMAGE,
        source_sha256={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (base/'geology').rglob('*.py')},
        original_resources_used=False,external_ports=False,new_credentials=True,retained_for_review=True)
    save('FILES_PREPARED')
    command(['docker','network','create','--internal','--subnet',str(subnet),'--label','com.docker.compose.project='+project,network])
    for volume in volumes:command(['docker','volume','create','--label','com.docker.compose.project='+project,volume])
    pre=json.loads((ROOT/'phase10d-preflight.json').read_text());pg_image=pre['services']['almacen_datos']['image'];redis_image=pre['services']['mensajeria']['image']
    common=['docker','run','-d','--pull','never','--network',network,'--label','com.docker.compose.project='+project]
    command(common+['--name',STATE['containers']['pg'],'--network-alias','pg','--cpus','1','--memory','768m',
        '--env-file',str(base/'pg-private.env'),'-v',volumes[0]+':/var/lib/postgresql/data',
        '--health-cmd','pg_isready -U cert_admin -d geology_cert10d','--health-interval','2s','--health-timeout','3s','--health-retries','30',pg_image])
    healthy(STATE['containers']['pg']);save('PG_HEALTHY')
    command(common+['--name',STATE['containers']['redis'],'--network-alias','redis','--cpus','0.5','--memory','256m',
        '--env-file',str(base/'redis-private.env'),'-v',volumes[1]+':/data','-v',str(base/'redis-private.conf')+':/cert-redis.conf:ro',
        '--health-cmd','redis-cli ping','--health-interval','2s','--health-timeout','3s','--health-retries','30',redis_image,'redis-server','/cert-redis.conf'])
    healthy(STATE['containers']['redis']);save('REDIS_HEALTHY')
    mounts=['-v',str(base)+':/cert','-v',str(base/'geology')+':/srv/geology/geology:ro',
            '-v',str(base/'tests')+':/srv/geology/tests:ro','-v',str(base/'regression')+':/work',
            '--env-file',str(base/'app-private.env'),'-w','/srv/geology','--entrypoint','python']
    command(common+['--name',STATE['containers']['runner'],'--cpus','2','--memory','3g',*mounts,APP_IMAGE,'-B','-c','import time;time.sleep(86400)'])
    exec_logged('prepare',['/cert/client.py','--prepare'])
    command(common+['--name',STATE['containers']['worker'],'--cpus','2','--memory','3g','--memory-swap','3g','--pids-limit','256',*mounts,APP_IMAGE,'-B','/cert/worker.py'])
    for _ in range(90):
        c=json.loads(command(['docker','inspect',STATE['containers']['worker']]))[0]
        if not c['State']['Running']:raise RuntimeError('Temporary worker startup failed; inspect retained log')
        r=subprocess.run(['docker','logs',STATE['containers']['worker']],capture_output=True,text=True)
        if ' ready.' in r.stdout+r.stderr:break
        time.sleep(1)
    else:raise RuntimeError('Temporary worker ready timeout')
    save('WORKER_READY')
    exec_logged('operational',['/cert/client.py'])
    exec_logged('unit',['-m','unittest','discover','-s','tests','-p','test_*.py'])
    exec_logged('isolated_tools',['tests/integration_pdfa_controlado.py'])
    save('CERTIFIED_PENDING_ORIGINAL_FINAL_COMPARISON')
    print(json.dumps({'project':project,'directory':str(base),'runs':STATE['runs']},indent=2),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        STATE['error']={'type':type(exc).__name__,'message':str(exc)};save('STOPPED_FOR_DIAGNOSIS')
        print('Certification stopped: '+str(exc),flush=True)
        raise SystemExit(1)
