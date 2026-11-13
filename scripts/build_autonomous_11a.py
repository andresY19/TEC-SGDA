"""Build new offline, non-root images from a separately allowlisted context."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
TOOLCHAIN_ID='sha256:a77f24483c87e509b9c48d34fe1a76f115ac92688c4156b7ab1d8e049f1e7a10'


def run(args):
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:raise RuntimeError('Image preparation command failed: '+args[0])
    return r.stdout.strip()


def main():
    if (ROOT/'phase11a-build.json').exists():
        assert '--resume' in sys.argv, 'Inspect existing 11A build before repeating'
        state=json.loads((ROOT/'phase11a-build.json').read_text());ctx=Path(state['context'])
        manifest=json.loads((ctx/'build-manifest.json').read_text())
        manifest['source_sha256']={k.replace(chr(92),'/'):v for k,v in manifest['source_sha256'].items()}
        (ctx/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        state['context_files']['build-manifest.json']=hashlib.sha256((ctx/'build-manifest.json').read_bytes()).hexdigest()
        state['resolved_build_diagnostic']='Normalized Windows manifest paths to POSIX before Linux image verification.'
        build_images(state);return
    pre=json.loads((ROOT/'phase11a-preflight.json').read_text());assert pre['status']=='PASS'
    base=Path.home()/'GEOLOGY_Autonomous_11A'/('build-'+uuid.uuid4().hex[:10]);ctx=base/'context';ctx.mkdir(parents=True)
    (base/'results').mkdir();(base/'control').mkdir()
    sid=run(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'])
    run(['icacls',str(base),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'])
    for folder in ('geology','tests'):
        assert not any(p.is_symlink() for p in (ROOT/folder).rglob('*'))
        shutil.copytree(ROOT/folder,ctx/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for path in (ROOT/'distribution/local11a').glob('Dockerfile.*'):shutil.copy2(path,ctx/path.name)
    shutil.copy2(ROOT/'distribution/local11a/run_worker.py',ctx/'run_worker.py')
    cert=ctx/'cert';(cert/'bin').mkdir(parents=True)
    for source,target in [('client_pdfa_cert_10d.py','client.py'),('worker_pdfa_cert_10d.py','worker.py')]:
        code=(ROOT/'scripts'/source).read_text(encoding='utf-8').replace("startswith('geology-pdfa10d-')","startswith('geology-auto11a-')")
        if target=='client.py':code=code.replace("ROOT/'private.json'","Path('/run/secrets/cert-private.json')")
        (cert/target).write_text(code,encoding='utf-8',newline='\n')
    for tool,actual,marker in [('ocrmypdf','/usr/local/bin/ocrmypdf','/cases/conversion_error/'),('verapdf','/opt/verapdf/verapdf','/cases/validation_error/')]:
        (cert/'bin'/tool).write_text('#!/usr/local/bin/python\nimport os,sys\n'+
            f'if any({marker!r} in x for x in sys.argv[1:]):\n print("SINTETICO 11A fallo controlado",file=sys.stderr);sys.exit(71)\n'+
            f'os.execv({actual!r},[{actual!r}]+sys.argv[1:])\n',encoding='utf-8',newline='\n')
    inventory=json.loads((ROOT/'phase11a-toolchain-inventory.json').read_text())
    manifest={'toolchain_configuration_digest':TOOLCHAIN_ID,'python':inventory['python'],
              'python_packages':inventory['packages'],'debian_packages':inventory['dpkg'],
              'source_sha256':{k.replace(chr(92),'/'):v for k,v in pre['source_hashes'].items()},'distribution_scope':'Local synthetic development; not certified original release.'}
    (ctx/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    lock=''.join(k+'=='+v+'\n' for k,v in sorted(inventory['packages'].items()))
    (ctx/'requirements.autonomous.lock').write_text(lock,encoding='utf-8')
    (ROOT/'distribution/local11a/requirements.autonomous.lock').write_text(lock,encoding='utf-8')
    (ctx/'.dockerignore').write_text('**\n!Dockerfile.*\n!geology/\n!geology/**\n!tests/\n!tests/**\n!cert/\n!cert/**\n!run_worker.py\n!build-manifest.json\n!requirements.autonomous.lock\n**/__pycache__/\n**/*.pyc\n**/.env*\n',encoding='utf-8')
    # Scan against actual original secrets in memory. Never pass them to the builder.
    original=json.loads(run(['docker','inspect',pre['services']['servidor']['id']]))[0]
    env=dict(x.split('=',1) for x in original['Config']['Env'] if '=' in x)
    secrets=[v.encode() for k,v in env.items() if v and (k in ('PG_CLAVE','GEOLOGY_CLAVE','AWS_SECRET_ACCESS_KEY') or 'API_KEY' in k)]
    files=[p for p in ctx.rglob('*') if p.is_file()]
    forbidden={'.pdf','.xlsx','.zip','.dump','.pem','.key','.sql','.bak'}
    assert not any(p.suffix.lower() in forbidden or p.name.startswith('.env') for p in files)
    assert not any(secret in p.read_bytes() for p in files for secret in secrets)
    assert run(['docker','image','inspect',TOOLCHAIN_ID,'--format','{{.Id}}'])==TOOLCHAIN_ID
    base_tag='geology-autonomous11a-toolchain:'+TOOLCHAIN_ID.split(':')[1][:12]
    run(['docker','tag',TOOLCHAIN_ID,base_tag])  # New alias only; original tags untouched.
    ident=base.name.split('-')[1];tags={k:'geology-autonomous11a-'+k+':'+ident for k in ['runtime','fastapi','celery','certification']}
    state={'directory':str(base),'context':str(ctx),'toolchain_id':TOOLCHAIN_ID,'toolchain_alias':base_tag,
           'tags':tags,'images':{},'context_files':{str(p.relative_to(ctx)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
           'context_bytes':sum(p.stat().st_size for p in files),'context_secret_scan':'PASS','package_downloads':0}
    (ROOT/'phase11a-build.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    build_images(state)


def build_images(state):
    base=Path(state['directory']);ctx=Path(state['context']);tags=state['tags'];base_tag=state['toolchain_alias']
    assert run(['docker','image','inspect',base_tag,'--format','{{.Id}}'])==TOOLCHAIN_ID, 'Toolchain digest mismatch'
    for kind,args in [('runtime',['TOOLCHAIN_IMAGE='+base_tag]),('fastapi',['RUNTIME_IMAGE='+tags['runtime']]),
                      ('celery',['RUNTIME_IMAGE='+tags['runtime']]),('certification',['WORKER_IMAGE='+tags['celery']])]:
        if kind in state['images']:
            assert run(['docker','image','inspect',tags[kind],'--format','{{.Id}}'])==state['images'][kind]['id'];continue
        cmd=['docker','buildx','build','--builder','desktop-linux','--load','--network','none','--pull=false',
             '--progress','plain','-f',str(ctx/('Dockerfile.'+kind)),'-t',tags[kind]]
        for arg in args:cmd+=['--build-arg',arg]
        logpath=base/'results'/f"build-{kind}-{len(list((base/'results').glob('build-'+kind+'*.log')))+1}.log"
        with logpath.open('x',encoding='utf-8') as log:
            r=subprocess.run(cmd+[str(ctx)],stdout=log,stderr=subprocess.STDOUT,timeout=900)
        if r.returncode:raise RuntimeError('Build failed; inspect retained build log: '+kind)
        image=json.loads(run(['docker','image','inspect',tags[kind]]))[0]
        assert image['Config']['User']=='10001:10001'
        state['images'][kind]={'id':image['Id'],'repo_digests':image.get('RepoDigests',[]),'created':image['Created'],'size':image['Size'],'user':image['Config']['User']}
        (ROOT/'phase11a-build.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
        print(kind,image['Id'],flush=True)
    print('Autonomous image builds completed',flush=True)


if __name__=='__main__':main()
