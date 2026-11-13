"""D: metadata-only audit. Never reads file contents or follows reparse points.

Duplicate groups are candidates by name/size/mtime, never certified duplicates.
All byte totals are logical sizes, not NTFS allocated/compressed disk usage.
"""
from pathlib import Path
import os,stat,time,json,collections,heapq,shutil

ROOT=Path(__file__).resolve().parents[1]
CACHE={'.cache','.npm','.nuget','node_modules','.next','.turbo','__pycache__','bin','obj','target','build','dist','codextemp','temp','tmp'}
ARCHIVES={'.zip','.7z','.rar','.tar','.gz','.tgz','.iso'}
BACKUPS={'.bak','.backup','.dump','.vhdx','.vhd','.bkp'}

def main():
    start=time.monotonic();last=start;stack=[('D:\\',False)];sizes={};direct={};dates={};counts=collections.Counter()
    errors=[];caches=[];largest=[];groups={};extensions=collections.Counter();categories=collections.Counter()
    projects=[];hardlinks=0;seen_links=set();hardlink_repeat_bytes=0
    while stack:
        path,visited=stack.pop()
        if visited:
            total=direct.get(path,0)
            for child in sizes.get(path,[]):total+=direct.get(child,0)
            direct[path]=total
            continue
        children=[];own=0
        try:
            with os.scandir(path) as entries:
                for e in entries:
                    try:
                        s=e.stat(follow_symlinks=False)
                        if s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                            counts['reparse_skipped']+=1;continue
                        if stat.S_ISDIR(s.st_mode):
                            children.append(e.path);dates[e.path]=s.st_mtime
                            if e.name.lower() in CACHE:caches.append(e.path)
                            if e.name.lower() in ('proyectos','projects','repos','repositories'):projects.append(e.path)
                        elif stat.S_ISREG(s.st_mode):
                            counts['files']+=1;own+=s.st_size
                            if s.st_nlink>1:
                                hardlinks+=1;key=(s.st_dev,s.st_ino)
                                if key in seen_links:hardlink_repeat_bytes+=s.st_size
                                seen_links.add(key)
                            ext=os.path.splitext(e.name)[1].lower();extensions[ext]+=s.st_size
                            kind='compressed_distributions' if ext in ARCHIVES else 'backups_and_disk_images' if ext in BACKUPS else 'temporary_files' if ext in ('.tmp','.temp','.dmp','.part','.crdownload') else None
                            if kind:categories[kind]+=s.st_size
                            if len(largest)<30:heapq.heappush(largest,(s.st_size,e.path,s.st_mtime))
                            elif s.st_size>largest[0][0]:heapq.heapreplace(largest,(s.st_size,e.path,s.st_mtime))
                            # Limit metadata grouping to >=10 MiB to avoid millions of tiny files.
                            if s.st_size>=10*1024*1024:
                                key=(e.name.lower(),s.st_size,s.st_mtime_ns)
                                if key in groups:groups[key].append(e.path)
                                else:groups[key]=[e.path]
                    except OSError as ex:
                        counts['entry_errors']+=1
                        if len(errors)<30:errors.append({'directory':path,'error':type(ex).__name__})
        except OSError as ex:
            counts['directory_errors']+=1
            if len(errors)<30:errors.append({'directory':path,'error':type(ex).__name__})
        counts['directories']+=1;direct[path]=own;sizes[path]=children
        stack.append((path,True));stack.extend((p,False) for p in children)
        now=time.monotonic()
        if now-last>25:
            print(json.dumps({'elapsed_seconds':int(now-start),'files':counts['files'],'directories':counts['directories']}),flush=True);last=now
    def record(path):return {'path':path,'logical_bytes':direct.get(path,0),'mtime_epoch':dates.get(path)}
    top=sorted((p for p in direct if p!='D:\\'),key=direct.get,reverse=True)[:20]
    duplicate_candidates=[{'bytes_each':key[1],'mtime_ns':key[2],'paths':v,'potential_repeated_bytes':key[1]*(len(v)-1)} for key,v in groups.items() if len(v)>1]
    duplicate_candidates.sort(key=lambda x:x['potential_repeated_bytes'],reverse=True)
    result={'scope':'D: file metadata only; file contents never opened. Reparse points skipped. No deletion/move.',
        'logical_bytes_scanned':direct['D:\\'],'elapsed_seconds':time.monotonic()-start,'counts':dict(counts),'errors_sample':errors,
        'top20_directories_inclusive':[record(p) for p in top],
        'top_level_disjoint':sorted((record(p) for p in sizes['D:\\']),key=lambda x:x['logical_bytes'],reverse=True),
        'cache_candidates_inclusive':sorted((record(p) for p in caches),key=lambda x:x['logical_bytes'],reverse=True)[:100],
        'project_roots':[record(p) for p in projects],
        'largest_files_metadata':[{'bytes':a,'path':b,'mtime_epoch':c} for a,b,c in sorted(largest,reverse=True)],
        'file_category_logical_bytes':dict(categories),'extension_totals':dict(extensions.most_common(30)),
        'duplicate_candidates_not_verified':duplicate_candidates[:50],
        'hardlink_file_entries':hardlinks,'hardlink_repeat_logical_bytes':hardlink_repeat_bytes,
        'free_bytes':shutil.disk_usage('D:/').free,'total_bytes':shutil.disk_usage('D:/').total,
        'limitations':['Nested directory totals overlap; do not sum top20.','Logical sizes may differ from allocated bytes due to hardlinks, sparse/compressed files and denied paths.','Potential duplicates use metadata only; they are not safe deletion candidates.','Cache-like names do not prove that contents are disposable.']}
    (ROOT/'phase9c-drive-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'top20':result['top20_directories_inclusive'],'counts':result['counts'],'elapsed_seconds':result['elapsed_seconds']},indent=2),flush=True)

if __name__=='__main__':main()
