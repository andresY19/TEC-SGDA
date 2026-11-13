from pathlib import Path
import datetime,hashlib,json,shutil,subprocess,uuid
from operational_9f_tools import ROOT,checked,inspect,summary,object_inspect,database_snapshot,queue_snapshot

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
index={k.replace('\\','/'):v for k,v in json.loads((ROOT/'phase11b-evidence-sha256.json').read_text()).items()}
files=json.loads((ROOT/'phase11b-files.json').read_text())
patch=ROOT/'distribution/session11b/staged-code.patch'
assert sha(patch)==index['distribution/session11b/staged-code.patch']
assert all(sha(Path(f['staged_path']))==f['after_sha256'] for f in files)
a11=json.loads((ROOT/'phase11a-build.json').read_text())
assert all(object_inspect('image',a11['tags'][k])['Id']==v['id'] for k,v in a11['images'].items())
assert json.loads(checked(['docker','info','--format','{{json .OSType}}']))=='linux'
last=json.loads((ROOT/'phase11b-original-final.json').read_text())
db=database_snapshot();assert db['schema_sha256']==last['database']['schema_sha256'] and db['data_sha256']==last['database']['data_sha256']
q=queue_snapshot();assert q['safe_empty']
services={}
for key,baseline in last['original_services'].items():
    c=inspect(baseline['id']);assert c['State']['Running'] and c['Image']==baseline['image'] and c['Mounts']==baseline['mounts']
    services[key]=summary(c)
    if key in ('servidor','procesador'):
        env=dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
        assert env['LEVANTAR_AL_CARGAR'].lower() in ('no','false','0')
        assert all(not v for n,v in env.items() if 'API_KEY' in n or n in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY'))
docs={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'deposito').rglob('*') if p.is_file()}
assert docs==last['documents']
b=Path(json.loads((ROOT/'phase9d-backup-copy.json').read_text())['destination'])
a=json.loads((ROOT/'phase9d-final-backup-acl.json').read_text());assert all(sha(b/x['name'])==x['sha256'] for x in a['files'])
free={d:shutil.disk_usage(d+':/').free for d in ('C','D','F')}
assert free['C']>5*1024**3 and free['F']>3*1024**3
assert not (ROOT/'phase11c-preflight.json').exists()
base=Path.home()/'GEOLOGY_Candidate_11C'/('candidate-'+uuid.uuid4().hex[:10]);ctx=base/'context';ctx.mkdir(parents=True)
(base/'control').mkdir();(base/'results').mkdir()
sid=checked(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value']).strip()
checked(['icacls',str(base),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'])
certctx=Path(a11['context'])
for name in ('geology','tests'):shutil.copytree(certctx/name,ctx/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for f in files:
    p=ctx/f['path']
    if f['before_sha256'] is not None:assert sha(p)==f['before_sha256']
    else:assert not p.exists()
canonical_patch=base/'control/staged-code.lf.patch'
canonical_patch.write_text(patch.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
args=['git','-C',str(ctx),'apply']
check=subprocess.run(args+['--check',str(canonical_patch)],capture_output=True,text=True)
if check.returncode:
    for f in files:
        p=ctx/f['path']
        if p.exists():p.write_text(p.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
    check=subprocess.run(args+['--check',str(canonical_patch)],capture_output=True,text=True)
assert check.returncode==0,check.stderr[-1000:]
p=subprocess.run(args+[str(canonical_patch)],capture_output=True,text=True);assert p.returncode==0,p.stderr[-500:]
for f in files:
    p=ctx/f['path'];certified=Path(f['staged_path'])
    assert p.read_text(encoding='utf-8')==certified.read_text(encoding='utf-8')
    # Preserve the certified byte encoding/newlines after the verified textual patch.
    p.write_bytes(certified.read_bytes());assert sha(p)==f['after_sha256']
out={'status':'PASS','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'directory':str(base),'context':str(ctx),
     'patch_sha256':sha(patch),'patch_application':'git apply --check + git apply; resulting texts and byte hashes match all certified 11B staged files',
     'database':db,'documents':docs,'queue':q,'services':services,'backup_verified':True,'free_bytes':free,
     'original_source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'geology').rglob('*') if p.is_file() and '__pycache__' not in str(p)},
     'protected_hashes':{n:sha(ROOT/n) for n in ('.env','docker-compose.yml','compose.local.yml','Dockerfile')},'images11a':a11['images']}
(ROOT/'phase11c-preflight.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','directory':str(base),'patch_applied':True,'free_GiB':{k:round(v/1024**3,2) for k,v in free.items()}},indent=2))
