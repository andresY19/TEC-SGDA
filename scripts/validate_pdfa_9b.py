"""Independent, read-only validation of the six existing synthetic derivatives.

Installs pinned official veraPDF only inside a disposable container's tmpfs.
No application environment or credentials are passed to this container.
Network is disconnected before opening any document. Existing files are read-only.
"""
from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NAME='geology-local-20261106-57a99a-verapdf-9b'
OUT=ROOT/'expedidos/pruebas_sinteticas_9b/attempt-2'
URL='https://software.verapdf.org/releases/1.30/verapdf-greenfield-1.30.3-installer.zip'

def command(args,**kw):
    return subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',**kw)

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    old=json.loads((ROOT/'phase9a-final-verification.json').read_text())
    paths=[a[k] for a in old['synthetic_files'] for k in ('matrix','consultation')]
    assert len(paths)==6 and all(paths)
    before={p:hashlib.sha256((ROOT/Path(p).relative_to('/srv/geology')).read_bytes()).hexdigest() for p in paths}
    p=command(['docker','run','-d','--rm','--name',NAME,'--read-only','--tmpfs','/tmp:rw,size=512m',
        '--memory','768m','--cpus','1','--cap-drop','ALL','--security-opt','no-new-privileges',
        '-e','HOME=/tmp','-v',str(ROOT/'deposito')+':/srv/geology/deposito:ro',
        '-v',str(ROOT/'scripts')+':/work/scripts:ro','--entrypoint','sleep',
        'geology-local-20261106-57a99a:2.13.0-9a','3600'])
    assert p.returncode==0,p.stderr
    install='''import urllib.request,zipfile,io,hashlib,subprocess,json
from pathlib import Path
url=URL_VALUE
with urllib.request.urlopen(url,timeout=60) as f:
 assert f.url.startswith('https://software.verapdf.org/')
 data=f.read(40*1024*1024)
target=Path('/tmp/installer');target.mkdir()
with zipfile.ZipFile(io.BytesIO(data)) as z:
 for name in z.namelist():assert (target/name).resolve().is_relative_to(target)
 z.extractall(target)
jar=list(target.rglob('verapdf-izpack-installer-*.jar'));assert len(jar)==1
xml=Path('/work/scripts/verapdf-auto.xml').read_text().replace('/opt/verapdf','/tmp/verapdf')
Path('/tmp/auto.xml').write_text(xml)
p=subprocess.run(['java','-DINSTALL_PATH=/tmp/verapdf','-jar',str(jar[0]),'/tmp/auto.xml'],capture_output=True,text=True,timeout=150)
assert p.returncode==0,(p.stdout+p.stderr)[-2000:]
print(json.dumps({'url':url,'installer_sha256':hashlib.sha256(data).hexdigest(),'installer_bytes':len(data),
 'installed_files':[str(p) for p in Path('/tmp/verapdf').glob('*')], 'installer_output':p.stdout+p.stderr}))
'''.replace('URL_VALUE',repr(URL))
    try:
        p=command(['docker','exec','-i',NAME,'python','-B','-'],input=install,timeout=240)
        (OUT/'installation.log').write_text(p.stdout+p.stderr,encoding='utf-8')
        assert p.returncode==0,p.stderr[-2000:]
        origin=json.loads(p.stdout)
        p=command(['docker','network','disconnect','bridge',NAME]);assert p.returncode==0,p.stderr
        p=command(['docker','exec',NAME,'sh','/tmp/verapdf/verapdf','--version'])
        (OUT/'version-command.json').write_text(json.dumps({'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},indent=2))
        assert p.returncode==0,p.stdout+p.stderr
        version=p.stdout+p.stderr;(OUT/'version.txt').write_text(version,encoding='utf-8')
        reports=[]
        for i,path in enumerate(paths,1):
            p=command(['docker','exec',NAME,'sh','/tmp/verapdf/verapdf','--flavour','2b','--format','xml','--addlogs','--loglevel','2',path],timeout=180)
            (OUT/f'validation-{i:02}.xml').write_text(p.stdout,encoding='utf-8')
            (OUT/f'validation-{i:02}.stderr.txt').write_text(p.stderr,encoding='utf-8')
            tree=ET.fromstring(p.stdout)
            elements=list(tree.iter())
            validation=[x for x in elements if x.tag.split('}')[-1]=='validationReport']
            assert len(validation)==1
            details=[x for x in validation[0].iter() if x.tag.split('}')[-1]=='details'][0]
            entry={'path':path,'sha256':before[path],'returncode':p.returncode,
                'validation':validation[0].attrib,'details':details.attrib,'stderr':p.stderr,
                'report':f'validation-{i:02}.xml'}
            reports.append(entry)
        for path,h in before.items():
            assert hashlib.sha256((ROOT/Path(path).relative_to('/srv/geology')).read_bytes()).hexdigest()==h
        result={'origin':origin,'version':version,'profile':'PDF/A-2b (effective local output; institutional requirement not supplied)',
            'network_disconnected_before_documents':True,'read_only_documents':True,'reports':reports,
            'all_compliant':all(x['validation']['isCompliant']=='true' and x['details']['failedChecks']=='0' for x in reports)}
        (OUT/'validation-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        # Stops only the new, disposable validator; never any application service.
        command(['docker','stop',NAME])

if __name__=='__main__':main()
