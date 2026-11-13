"""New isolated 11A project; baked application/tests, no source bind mounts.

Only credential configuration files are mounted from the private control folder.
Original, 9E and 10D containers/volumes/networks are never started or changed.
"""
from pathlib import Path
import hashlib
import ipaddress
import json
import secrets
import socket
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
STATE={}


def cmd(args):
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:raise RuntimeError('11B command failed: '+' '.join(args[:4])+'; code '+str(r.returncode)+'; '+r.stderr[-400:])
    return r.stdout.strip()


def save(stage):
    STATE['stage']=stage
    (ROOT/'phase11e-environment.json').write_text(json.dumps(STATE,indent=2),encoding='utf-8')


def compose(*args):
    return cmd(['docker','compose','--env-file',str(Path(STATE['control'])/'compose-private.env'),
                '-p',STATE['project'],'-f',str(ROOT/'distribution/autonomous11e/compose.certification.yml'),*args])


def cid(service):
    return compose('ps','-aq',service)


def ready(service,worker=False):
    for _ in range(100):
        c=json.loads(cmd(['docker','inspect',cid(service)]))[0]
        if not c['State']['Running']:raise RuntimeError('11A service stopped: '+service)
        if worker:
            p=subprocess.run(['docker','logs','--since',c['State']['StartedAt'],c['Id']],capture_output=True,text=True)
            if ' ready.' in p.stdout+p.stderr:return
        elif c['State'].get('Health',{}).get('Status')=='healthy':return
        time.sleep(1)
    raise RuntimeError('11A readiness timeout: '+service)


def logged(kind,args):
    out=Path(STATE['directory'])/'results'
    attempt=1+len(list(out.glob(kind+'-stdout*.txt')))
    stdout_path=out/f'{kind}-stdout-{attempt}.txt';stderr_path=out/f'{kind}-stderr-{attempt}.txt'
    with stdout_path.open('x',encoding='utf-8') as stdout, stderr_path.open('x',encoding='utf-8') as stderr:
        r=subprocess.run(['docker','exec',cid('runner'),'python','-B',*args],stdout=stdout,stderr=stderr,timeout=1200)
    STATE.setdefault('runs',{})[kind]={'returncode':r.returncode,'pass':r.returncode==0,'stdout':str(stdout_path),'stderr':str(stderr_path)}
    save('FINISHED_'+kind.upper());print(kind,r.returncode,stderr_path.read_text(encoding='utf-8')[-2500:],flush=True)
    if r.returncode:raise RuntimeError('11A test failed: '+kind)


def main():
    retry_volume='--retry-new-volumes' in sys.argv
    if (ROOT/'phase11e-environment.json').exists() and '--retry-preprovision' in sys.argv:
        old=json.loads((ROOT/'phase11e-environment.json').read_text());assert 'project' not in old
        with (ROOT/f"phase11e-setup-attempt{1+len(list(ROOT.glob('phase11e-setup-attempt*.json')))}.json").open('x') as f:json.dump(old,f,indent=2)
    elif (ROOT/'phase11e-environment.json').exists() and not retry_volume:
        assert '--resume-packaging' in sys.argv
        STATE.update(json.loads((ROOT/'phase11e-environment.json').read_text()))
        assert STATE['stage']=='STOPPED_FOR_DIAGNOSIS' and not STATE['runs']['prepare']['pass']
        with (ROOT/'phase11e-environment-attempt1.json').open('x') as f:json.dump(STATE,f,indent=2)
        build=json.loads((ROOT/'phase11e-build.json').read_text());control=Path(STATE['control'])
        path=control/'compose-private.env';lines=path.read_text().splitlines()
        replacements={'WEB_IMAGE':build['tags']['fastapi'],'WORKER_IMAGE':build['tags']['celery'],'CERT_IMAGE':build['tags']['certification']}
        path.write_text(''.join(k+'='+replacements.get(k,v)+'\n' for k,v in (x.split('=',1) for x in lines)),encoding='utf-8')
        STATE['images']=build['images'];STATE['resolved_packaging_issue']='Image PYTHONPATH now includes its baked /srv/geology source; no source bind needed.';STATE.pop('error',None)
        compose('up','-d','--force-recreate','runner')
        logged('prepare',['/opt/geology-cert/client.py','--prepare'])
        certify_services();return
    build=json.loads((ROOT/'phase11e-build.json').read_text());assert len(build['images'])==4
    base=Path(build['directory']);control=base/(('control-retry-'+uuid.uuid4().hex[:6]) if '--retry-preprovision' in sys.argv else ('control-r3' if retry_volume else 'control'));control.mkdir(exist_ok=True);project='geology-auto11e-'+uuid.uuid4().hex[:8]
    for k,v in build['images'].items():assert json.loads(cmd(['docker','image','inspect',build['tags'][k]]))[0]['Id']==v['id']
    subnets=[];ids=cmd(['docker','network','ls','-q']).splitlines()
    for n in json.loads(cmd(['docker','network','inspect',*ids])):
        subnets += [ipaddress.ip_network(x['Subnet']) for x in (n['IPAM'].get('Config') or []) if 'Subnet' in x]
    available=[ipaddress.ip_network(f'10.254.{i}.0/28') for i in range(240,255) if not any(ipaddress.ip_network(f'10.254.{i}.0/28').overlaps(n) for n in subnets if n.version==4)]
    assert len(available)>=2
    for port in range(18081,18101):
        try:
            with socket.socket() as s:s.bind(('127.0.0.1',port))
            break
        except OSError:continue
    else:raise RuntimeError('No free localhost test port')
    pg=secrets.token_hex(32);app=secrets.token_hex(32);redis=secrets.token_hex(32)
    def write(name,value):
        with (control/name).open('x',encoding='utf-8',newline='\n') as f:f.write(value)
    write('private.json',json.dumps({'admin_url':f'postgresql+psycopg2://cert_admin:{pg}@pg:5432/geology_cert10d','app_password':app}))
    write('pg-private.env',f'POSTGRES_USER=cert_admin\nPOSTGRES_PASSWORD={pg}\nPOSTGRES_DB=geology_cert10d\n')
    write('redis-private.env',f'REDISCLI_AUTH={redis}\n')
    write('redis-private.conf',f'bind 0.0.0.0\nprotected-mode yes\nrequirepass {redis}\nappendonly yes\nappendfsync always\ndir /data\n')
    env={'DATABASE_URL':f'postgresql+psycopg2://cert_worker:{app}@pg:5432/geology_cert10d',
         'PG_USUARIO':'cert_worker','PG_CLAVE':app,'PG_BASE':'geology_cert10d','PG_SERVIDOR':'pg','PG_PUERTO':'5432',
         'CELERY_BROKER_URL':f'redis://:{redis}@redis:6379/0','CELERY_RESULT_BACKEND':f'redis://:{redis}@redis:6379/1','AUTH_REDIS_URL':f'redis://:{redis}@redis:6379/2',
         'GEOLOGY_LOCAL_PROJECT':project,'GEOLOGY_COLA':project+'-tasks','GEOLOGY_ENTORNO':'test',
         'GEOLOGY_CLAVE':secrets.token_hex(48),'LEVANTAR_AL_CARGAR':'no','PDFA_PERFIL':'1b','GEOLOGY_PERMITIR_DDL':'0',
         'VERAPDF_BIN':'/opt/verapdf/verapdf','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':'/tmp'}
    for k in ['ANTHROPIC_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY',*[f'GEMINI_API_KEY_{i}' for i in range(1,8)]]:env[k]=''
    write('app-private.env',''.join(k+'='+v+'\n' for k,v in env.items()))
    pre=json.loads((ROOT/'phase11e-preflight.json').read_text())
    params={'CERT_PROJECT':project,'CERT_CONTROL':control.as_posix(),'WEB_IMAGE':build['tags']['fastapi'],
            'WORKER_IMAGE':build['tags']['celery'],'CERT_IMAGE':build['tags']['certification'],
            'PG_IMAGE':pre['services']['almacen_datos']['image'],'REDIS_IMAGE':pre['services']['mensajeria']['image'],
            'BACKEND_SUBNET':str(available[0]),'FRONTEND_SUBNET':str(available[1]),'WEB_PORT':str(port)}
    write('compose-private.env',''.join(k+'='+v+'\n' for k,v in params.items()))
    def app_service(image):
        return {'image':image,'pull_policy':'never','user':'10001:10001','read_only':True,
                'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
                'env_file':['${CERT_CONTROL}/app-private.env'],'working_dir':'/srv/geology',
                'networks':['backend'],'cpus':2,'mem_limit':'3g',
                'tmpfs':['/tmp:uid=10001,gid=10001,mode=1770','/home/geology:uid=10001,gid=10001,mode=0700'],
                'volumes':['documents:/cert','deposito:/srv/geology/deposito','expedidos:/srv/geology/expedidos']}
    web=app_service('${WEB_IMAGE}');web['networks']=['backend','frontend'];web['ports']=['127.0.0.1:${WEB_PORT}:8080'];web['healthcheck']={'test':['CMD','python','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/estado',timeout=3)"],'interval':'3s','timeout':'5s','retries':30}
    worker=app_service('${WORKER_IMAGE}')
    runner=app_service('${CERT_IMAGE}');runner['volumes']+=['regression:/work','${CERT_CONTROL}/private.json:/run/secrets/cert-private.json:ro']
    fault=app_service('${CERT_IMAGE}');fault['command']=['python','-B','/opt/geology-cert/worker.py'];fault['environment']={'VERAPDF_BIN':'/opt/geology-cert/bin/verapdf','PATH':'/opt/geology-cert/bin:/opt/geology-ghostscript/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}
    config={'name':'${CERT_PROJECT}','services':{
      'pg':{'image':'${PG_IMAGE}','pull_policy':'never','env_file':['${CERT_CONTROL}/pg-private.env'],'volumes':['pgdata:/var/lib/postgresql/data'],'networks':['backend'],'cpus':1,'mem_limit':'768m','healthcheck':{'test':['CMD-SHELL','pg_isready -U cert_admin -d geology_cert10d'],'interval':'2s','timeout':'3s','retries':30}},
      'redis':{'image':'${REDIS_IMAGE}','pull_policy':'never','env_file':['${CERT_CONTROL}/redis-private.env'],'volumes':['redisdata:/data','${CERT_CONTROL}/redis-private.conf:/cert-redis.conf:ro'],'command':['redis-server','/cert-redis.conf'],'networks':['backend'],'cpus':.5,'mem_limit':'256m','healthcheck':{'test':['CMD','redis-cli','ping'],'interval':'2s','timeout':'3s','retries':30}},
      'web':web,'worker':worker,'runner':runner,'faultworker':fault},
      'networks':{'backend':{'internal':True,'ipam':{'config':[{'subnet':'${BACKEND_SUBNET}'}]}},'frontend':{'ipam':{'config':[{'subnet':'${FRONTEND_SUBNET}'}]}}},
      'volumes':{k:{} for k in ['pgdata','redisdata','documents','deposito','expedidos','regression']}}
    (ROOT/'distribution/autonomous11e/compose.certification.yml').write_text(json.dumps(config,indent=2),encoding='utf-8')
    STATE.update(project=project,directory=str(base),control=str(control),port=port,images=build['images'],no_source_bind_mounts=True)
    save('COMPOSE_PREPARED')
    compose('config','--quiet')
    compose('up','-d','pg','redis','runner');ready('pg');ready('redis')
    cmd(['docker','exec',cid('runner'),'python','-B','-c',"from pathlib import Path;[Path(x).mkdir(mode=0o770,parents=True,exist_ok=True) for x in ['/cert/results','/cert/tmp']]"])
    logged('prepare',['/opt/geology-cert/client.py','--prepare'])
    certify_services()


def certify_services():
    compose('up','-d','web','worker');ready('web');ready('worker',True);save('AUTONOMOUS_SERVICES_READY')
    # Keep the standard runtime worker container intact; tests use a separate, baked adapter.
    compose('stop','worker')
    compose('up','-d','faultworker');ready('faultworker',True)
    logged('operational',['/opt/geology-cert/client.py'])
    logged('unit',['-m','unittest','discover','-s','tests','-p','test_*.py'])
    logged('isolated_tools',['tests/integration_pdfa_controlado.py'])
    compose('stop','faultworker');compose('start','worker');ready('worker',True)
    save('REGRESSION_PASS_PENDING_NORMAL_TASKS_AND_RESTART')
    print(json.dumps({'project':STATE['project'],'port':STATE['port'],'runs':STATE['runs']},indent=2),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as e:
        STATE['error']={'type':type(e).__name__,'message':str(e)};save('STOPPED_FOR_DIAGNOSIS');print('11A stopped: '+str(e),flush=True);raise SystemExit(1)
