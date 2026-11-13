"""Read-only inspections of only the 9C capacity candidates; no tool execution.

Only technical dependency manifests, README/CI procedures are read for Flutter.
Build/tmp/driver contents are never opened. No signing configuration is read.
"""
from pathlib import Path
import os,stat,json,re,collections,time

ROOT=Path(__file__).resolve().parents[1]
BASES=[Path('D:/Proyectos/Personales/Flutter/Tec-Tracker-Bpm/tectrackerbpm'),
       Path('D:/Proyectos/Personales/Flutter/Transporte/bufalocargo')]
OTHER=[Path('D:/Proyectos/Personales/SALUDPROGRAMS/.local/sprint9-remediation/tmp'),
       Path('D:/Proyectos/Personales/SYSTEMDESING/institutional-design-system/tmp'),
       Path('D:/Descargas/SDI/SDI_1.26.1/drivers')]

def measure(path):
    size=count=dirs=errors=0;types=collections.Counter();largest=[];stack=[path];last=time.monotonic()
    while stack:
        d=stack.pop();dirs+=1
        try:
            with os.scandir(d) as entries:
                for e in entries:
                    try:
                        s=e.stat(follow_symlinks=False)
                        if s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:continue
                        if stat.S_ISDIR(s.st_mode):stack.append(Path(e.path))
                        elif stat.S_ISREG(s.st_mode):
                            count+=1;size+=s.st_size;types[Path(e.name).suffix.lower()]+=s.st_size
                            largest.append((s.st_size,e.path))
                            if len(largest)>40:largest=sorted(largest,reverse=True)[:20]
                    except OSError:errors+=1
        except OSError:errors+=1
        now=time.monotonic()
        if now-last>25:
            print(json.dumps({'candidate':str(path),'files':count,'directories':dirs}),flush=True);last=now
    return {'logical_bytes':size,'files':count,'directories':dirs,'errors':errors,
        'extensions':dict(types.most_common(10)),
        'largest_files':[{'bytes':s,'path':p} for s,p in sorted(largest,reverse=True)[:10]]}

def save(result):
    (ROOT/'phase9d-capacity-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

def main():
    result={'flutter':[],'other_candidates':[],'complete':False,'other_projects_modified':False,
        'cleanup_performed':False,'byte_content_read_scope':'Only Flutter manifests/lockfiles and root README/CI procedures; other candidates metadata only.'}
    for base in BASES:
        pub=base/'pubspec.yaml';lock=base/'pubspec.lock'
        assert pub.resolve().is_relative_to(base.resolve())
        assert lock.resolve().is_relative_to(base.resolve())
        text=pub.read_text(encoding='utf-8',errors='replace')
        if lock.is_file():text+='\n'+lock.read_text(encoding='utf-8',errors='replace')
        sdk=[x.strip() for x in re.findall(r'^\s*(?:sdk|dart|flutter):\s*[\x27\"]?([<>=^~0-9.\s]+)',text,re.M) if any(c.isdigit() for c in x)]
        docs=list(base.glob('README*'))+list((base/'.github/workflows').glob('*.yml'))+list((base/'.github/workflows').glob('*.yaml'))
        procedures=[]
        for f in docs:
            if not f.is_file() or f.stat().st_size>1024*1024 or not f.resolve().is_relative_to(base.resolve()):continue
            content=f.read_text(encoding='utf-8',errors='replace')
            commands=sorted(set(re.findall(r'\bflutter\s+(?:pub\s+get|clean|build\s+(?:apk|appbundle|windows|web|ios)|test)\b',content)))
            if commands:procedures.append({'path':str(f),'allowlisted_commands':commands})
        entry={'project':str(base),'sources':{'lib_exists':(base/'lib').is_dir(),
            'dart_file_count':sum(1 for p in (base/'lib').rglob('*.dart') if p.is_file()),
            'pubspec':pub.is_file(),'lockfile':lock.is_file(),'SDK_constraints':sdk,
            'android':(base/'android').is_dir(),'windows':(base/'windows').is_dir(),'web':(base/'web').is_dir(),
            'fvm_config_exists':any((base/n).exists() for n in ('.fvmrc','.fvm/fvm_config.json'))},
            'documented_procedures':procedures,'build':measure(base/'build'),
            'regeneration_status':'PARTIAL','build_executed':False,
            'limits':['Sources and lockfile do not prove reproducible build.','No Flutter invocation or dependency download.','Signing configuration/keys not read; unique signed artifacts not certified replaceable.']}
        result['flutter'].append(entry);save(result)
        print(json.dumps({'flutter_completed':str(base),'bytes':entry['build']['logical_bytes']}),flush=True)
    for path in OTHER:
        entry={'path':str(path),'exists':path.exists(),'inspection':'metadata only',
            'measurement':measure(path) if path.is_dir() else None,'disposable_confirmed':False}
        result['other_candidates'].append(entry);save(result)
        print(json.dumps({'candidate_completed':str(path),'bytes':entry['measurement']['logical_bytes'] if entry['measurement'] else None}),flush=True)
    result['complete']=True;save(result)
    print('All scoped metadata/Flutter technical inspections complete.',flush=True)

if __name__=='__main__':main()
