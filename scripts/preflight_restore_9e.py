"""Read-only checks before creating the single authorized 9E restore project."""
from pathlib import Path,PurePosixPath
import json,hashlib,zipfile,subprocess,shutil,ipaddress,uuid,os,stat
ROOT=Path(__file__).resolve().parents[1]
def docker(*args):return json.loads(subprocess.check_output(['docker',*args],text=True))
def main():
    r=ROOT;assert not (r/'phase9e-run-state.json').exists(),'Inspect existing 9E run; do not duplicate it'
    b=Path(json.loads((r/'phase9d-backup-copy.json').read_text())['destination'])
    ref=json.loads((b/'recovery-reference.json').read_text())
    index=json.loads((b/'backup-files-sha256.json').read_text())
    anchor=json.loads((r/'phase9d-final-backup-acl.json').read_text(encoding='utf-8-sig'))
    for x in anchor['files']:assert hashlib.sha256((b/x['name']).read_bytes()).hexdigest()==x['sha256']
    for x in index['files']:assert hashlib.sha256((b/x['name']).read_bytes()).hexdigest()==x['sha256']
    assert (b/'postgres-local.dump').read_bytes().startswith(b'PGDMP')
    expected={Path(n).as_posix():h for n,h in ref['depot_hashes'].items()}
    sizes={x['entry']:x['bytes'] for x in json.loads((b/'verification-manifest.json').read_text())['document_entries']}
    with zipfile.ZipFile(b/'deposito-sintetico.zip') as z:
        infos=z.infolist();assert len(infos)==17 and set(z.namelist())==set(expected) and z.testzip() is None
        assert len({x.filename.casefold() for x in infos})==17
        for x in infos:
            p=PurePosixPath(x.filename)
            assert not p.is_absolute() and '..' not in p.parts and '\\' not in x.filename and ':' not in x.filename
            assert not x.is_dir() and not stat.S_ISLNK(x.external_attr>>16) and not x.flag_bits&1
            assert x.file_size==sizes[x.filename] and hashlib.sha256(z.read(x.filename)).hexdigest()==expected[x.filename]
        zip_bytes=sum(x.file_size for x in infos)
    cat=(b/'postgres-catalog.txt').read_text();assert sum(' TABLE DATA ' in x for x in cat.splitlines())==27
    info=docker('info','--format','{{json .}}');assert info['OSType']=='linux'
    image=docker('image','inspect',ref['postgres_image'])[0];assert image['Os']=='linux'
    original={};volumes={};project=ref['source_project']
    prior=json.loads((r/'phase9a-final-verification.json').read_text())
    for service in ('almacen_datos','mensajeria','servidor','procesador'):
        c=docker('inspect',project+'-'+service+'-1')[0]
        assert c['Id']==prior['services'][service]['id'] and c['Config']['Labels']['com.docker.compose.project']==project
        assert not c['State']['Running']
        original[service]={'id':c['Id'],'status':c['State']['Status'],'started_at':c['State']['StartedAt'],
            'finished_at':c['State']['FinishedAt'],'mounts':c['Mounts'],'networks':list(c['NetworkSettings'].get('Networks') or {})}
        for m in c['Mounts']:
            if m['Type']=='volume':
                v=docker('volume','inspect',m['Name'])[0]
                assert v['Labels']['com.docker.compose.project']==project and v['Driver']=='local'
                volumes[m['Name']]=v
    ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split()
    nets=docker('network','inspect',*ids)
    occupied=[ipaddress.ip_network(x['Subnet'],strict=False) for n in nets for x in (n.get('IPAM',{}).get('Config') or []) if x.get('Subnet')]
    candidates=[ipaddress.ip_network(f'10.253.{n}.0/28') for n in range(249,255)]
    subnet=next((n for n in candidates if all(n.version!=a.version or not n.overlaps(a) for a in occupied)),None)
    assert subnet is not None
    settings=json.loads((Path(os.environ['APPDATA'])/'Docker/settings-store.json').read_text())
    drive=Path(settings['CustomWslDistroDir']).drive;host_free=shutil.disk_usage(drive+'/').free
    assert host_free>1024**3 and shutil.disk_usage('C:/').free>16*1024**2
    name='geology-restore-9e-20261107-'+uuid.uuid4().hex[:8]
    result={'status':'PASS','backup':str(b),'backup_hashes_verified':True,'zip_entries':17,
        'zip_uncompressed_bytes':zip_bytes,'catalog_integrity_verified_against_9D':True,
        'live_catalog_recheck_before_DDL_required':True,'postgres_image':ref['postgres_image'],
        'engine':'linux','engine_version':info['ServerVersion'],'new_project':name,
        'available_subnet':str(subnet),'docker_storage_drive':drive,
        'free_bytes':{'C':shutil.disk_usage('C:/').free,'Docker_host':host_free},
        'capacity_budget':{'C_bytes':16*1024**2,'Docker_host_bytes':1024**3,
            'basis':'395920 document bytes; small metadata; source PG ~49.5 MB; cached image; new cluster and WAL capped at 128 MB with conservative headroom.'},
        'original_containers':original,'original_volumes':volumes,
        'original_file_hashes':{p:hashlib.sha256((r/p).read_bytes()).hexdigest() for p in ('docker-compose.yml','compose.local.yml','Dockerfile','Dockerfile.compat.local','Dockerfile.document.local')}}
    (r/'phase9e-preflight.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','new_project','available_subnet','zip_entries','engine','engine_version','free_bytes')},indent=2))
if __name__=='__main__':main()
