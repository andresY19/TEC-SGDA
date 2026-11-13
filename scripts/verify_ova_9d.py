"""Read-only SHA-256 of the two explicitly authorized OVA candidates.

Does not extract appliance contents or query/stop any virtual machine.
"""
from pathlib import Path
import hashlib,json,time,os

ROOT=Path(__file__).resolve().parents[1]
PATHS=[Path('D:/VMImport/SupersetDev08/SUPERSET-DEV08.ova'),
       Path('D:/Proyectos/Personales/Julio/MV/SUPERSET-DEV08.ova')]

def main():
    records=[];started=time.monotonic()
    checkpoint=ROOT/'phase9d-ova-hashes-progress.json'
    if checkpoint.exists():
        saved=json.loads(checkpoint.read_text())
        for i,row in enumerate(saved):
            assert i<len(PATHS) and Path(row['path'])==PATHS[i]
            s=PATHS[i].stat()
            assert row['bytes']==s.st_size and row['mtime_ns']==s.st_mtime_ns and row['file_identity']['inode']==s.st_ino
            assert row['stable_during_hash'] and len(row['sha256'])==64
        records=saved
    for index,path in enumerate(PATHS,1):
        if index<=len(records):continue
        initial=path.stat();assert path.is_file() and not path.is_symlink()
        h=hashlib.sha256();done=0;last=time.monotonic();begin=last
        with path.open('rb',buffering=0) as stream:
            while True:
                chunk=stream.read(8*1024*1024)
                if not chunk:break
                h.update(chunk);done+=len(chunk)
                now=time.monotonic()
                if now-last>=25:
                    status={'file':index,'of':2,'percent':round(100*done/initial.st_size,1),
                        'read_GiB':round(done/2**30,2),'elapsed_seconds':int(now-started),'time_epoch':time.time()}
                    (ROOT/'phase9d-ova-read-status.json').write_text(json.dumps(status),encoding='utf-8')
                    print(json.dumps(status),flush=True)
                    last=now
        final=path.stat()
        assert (initial.st_size,initial.st_mtime_ns,initial.st_ino)==(final.st_size,final.st_mtime_ns,final.st_ino)
        assert done==initial.st_size
        records.append({'path':str(path),'bytes':done,'sha256':h.hexdigest(),'mtime_ns':initial.st_mtime_ns,
            'file_identity':{'device':initial.st_dev,'inode':initial.st_ino,'hardlink_count':initial.st_nlink},
            'seconds':time.monotonic()-begin,'stable_during_hash':True})
        checkpoint.write_text(json.dumps(records,indent=2),encoding='utf-8')
        print(json.dumps({'file_completed':index,'sha256':h.hexdigest(),'seconds':records[-1]['seconds']}),flush=True)
    for row in records:
        s=Path(row['path']).stat()
        assert (s.st_size,s.st_mtime_ns,s.st_ino)==(row['bytes'],row['mtime_ns'],row['file_identity']['inode'])
    result={'files':records,'identical':records[0]['bytes']==records[1]['bytes'] and records[0]['sha256']==records[1]['sha256'],
        'same_physical_file':records[0]['file_identity']['inode']==records[1]['file_identity']['inode'] and records[0]['file_identity']['device']==records[1]['file_identity']['device'],
        'elapsed_seconds':time.monotonic()-started,'read_only':True,'extracted':False,'deleted':False}
    (ROOT/'phase9d-ova-comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
