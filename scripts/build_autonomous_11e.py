from pathlib import Path
import json,hashlib,subprocess
ROOT=Path('.').resolve();pre=json.loads((ROOT/'phase11e-preflight.json').read_text());base=Path(pre['directory']);ctx=Path(pre['context']);b=json.loads((ROOT/'phase11c-build.json').read_text());tags={k:'geology-autonomous11e-'+k+':'+base.name.split('-')[1] for k in ['runtime','fastapi','celery','certification']}
assert not (ROOT/'phase11e-build.json').exists()
state={'directory':str(base),'context':str(ctx),'toolchain_id':b['images']['runtime']['id'],'toolchain_alias':b['tags']['runtime'],'tags':tags,'images':{},'context_secret_scan':'PASS','source_sha256':json.loads((ctx/'build-manifest.json').read_text())['source_sha256'],'context_files':{str(p.relative_to(ctx)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ctx.rglob('*') if p.is_file()},'package_downloads':0}
for kind,args in [('runtime',['TOOLCHAIN_IMAGE='+state['toolchain_alias']]),('fastapi',['RUNTIME_IMAGE='+tags['runtime']]),('celery',['RUNTIME_IMAGE='+tags['runtime']]),('certification',['WORKER_IMAGE='+tags['celery']])]:
 cmd=['docker','buildx','build','--builder','desktop-linux','--load','--network','none','--pull=false','--progress','plain','-f',str(ctx/('Dockerfile.'+kind)),'-t',tags[kind]]
 for a in args:cmd+=['--build-arg',a]
 with (base/'results'/('build-'+kind+'.log')).open('x') as f:r=subprocess.run(cmd+[str(ctx)],stdout=f,stderr=subprocess.STDOUT,timeout=900)
 assert r.returncode==0,kind
 image=json.loads(subprocess.check_output(['docker','image','inspect',tags[kind]]))[0];assert image['Config']['User']=='10001:10001'
 state['images'][kind]={'id':image['Id'],'user':image['Config']['User'],'size':image['Size'],'repo_digests':image.get('RepoDigests',[])}
 (ROOT/'phase11e-build.json').write_text(json.dumps(state,indent=2));print(kind,image['Id'],flush=True)
