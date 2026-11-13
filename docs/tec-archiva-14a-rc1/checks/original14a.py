from pathlib import Path
import hashlib,json,re,subprocess,sys
R=Path.cwd();B=Path(__file__).resolve().parent
project='geology-local-20261106-57a99a'
def docker(*args,source=None):
 r=subprocess.run(['docker',*args],input=source,capture_output=True,check=True)
 return r.stdout
def service(name):
 ids=docker('ps','-q','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service='+name).decode().split()
 assert len(ids)==1,name
 x=json.loads(docker('inspect',ids[0]))[0]
 assert x['Config']['Labels']['com.docker.compose.project']==project
 return x['Id']
def pg(id,sql,user='geology',db='geology'):
 return docker('exec','-e','PGOPTIONS=-c default_transaction_read_only=on',id,'psql','-XAt','-v','ON_ERROR_STOP=1','-U',user,'-d',db,'-c',sql).decode().strip()
def sha(data):return hashlib.sha256(data).hexdigest()
def schema(id,user,db):
 data=docker('exec','-e','PGOPTIONS=-c default_transaction_read_only=on',id,'pg_dump','--schema-only','--schema=public','--no-owner','--no-privileges','-U',user,'-d',db)
 return b'\n'.join(l for l in data.splitlines() if not l.startswith((b'\\restrict ',b'\\unrestrict ',b'--')) and l.strip())
def catalog(id,user,db):
 return json.loads(pg(id,"""SELECT coalesce(json_object_agg(t,cols ORDER BY t),'{}'::json) FROM
 (SELECT c.relname t,json_agg(json_build_array(a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid)) ORDER BY a.attnum) cols
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
 LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
 WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped GROUP BY c.relname) s""",user,db))
def snapshot():
 pg_id=service('almacen_datos');web=service('servidor')
 tables=pg(pg_id,"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
 assert tables and all(re.fullmatch('[a-z_]+',t) for t in tables)
 unions=' UNION ALL '.join(f"""SELECT '{t}' t,count(*) n,md5(coalesce(string_agg(h,'' ORDER BY h),'')) f
 FROM (SELECT md5(to_jsonb(r)::text) h FROM public."{t}" r) q""" for t in tables)
 counts=json.loads(pg(pg_id,f"SELECT json_object_agg(t,json_build_array(n,f) ORDER BY t) FROM ({unions}) s"))
 manifest=json.loads((R/'phase9e-certification-results.json').read_text(encoding='utf-8-sig'))['document_files']
 paths=[x['relative_path'] for x in manifest]
 source=b"""import hashlib,json,sys
from pathlib import Path
root=Path('/srv/geology')
out={}
for relative in json.load(sys.stdin):
 p=(root/relative).resolve()
 assert p.is_relative_to(root) and not (root/relative).is_symlink()
 if p.is_file():
  with p.open('rb') as f: out[relative]=hashlib.file_digest(f,'sha256').hexdigest()
 else: out[relative]=None
print(json.dumps(out))
"""
 hashes=json.loads(docker('exec','-i',web,'python','-B','-c',source.decode(),source=json.dumps(paths).encode()))
 return {'tables':len(tables),'records':sum(n[0] for n in counts.values()),'row_counts':{t:v[0] for t,v in counts.items()},'logical_data_fingerprint':sha(json.dumps(counts,sort_keys=True).encode()),'schema_sha256':sha(schema(pg_id,'geology','geology')),'document_files':len(paths),'documents_match_9e':sum(hashes[x['relative_path']]==x['sha256'] for x in manifest),'documents_sha256':sha(json.dumps(hashes,sort_keys=True).encode())}
if __name__=='__main__':
 result=snapshot()
 file=B/'results'/('original-'+sys.argv[1]+'.json')
 file.write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='row_counts'}))
