"""Read-only preservation audit; writes only new 11E evidence."""
from pathlib import Path
import hashlib,json,sys
from operational_9f_tools import ROOT,inspect,summary,object_inspect,database_snapshot,queue_snapshot
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pre=json.loads((ROOT/'phase11e-preflight.json').read_text());db=database_snapshot()
assert db['schema_sha256']==pre['database']['schema_sha256'] and db['data_sha256']==pre['database']['data_sha256']
docs={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'deposito').rglob('*') if p.is_file()};assert docs==pre['documents']
assert all(sha(ROOT/k)==v for k,v in pre['original_source_hashes'].items());assert all(sha(ROOT/k)==v for k,v in pre['protected_hashes'].items())
cert=Path(json.loads((ROOT/'phase11c-build.json').read_text())['context']);assert all(sha(cert/k)==v for k,v in pre['certified_context_hashes'].items())
x=json.loads((ROOT/'phase11d-evidence-index.json').read_text());assert all(sha(ROOT/k)==v for k,v in x['evidence'].items());assert sha(ROOT/'docs/FASE_11D_CONCILIACION_DOCUMENTAL.md')==x['report_sha256']
changes=[];services={}
for ident,old in pre['protected_containers'].items():
 raw=inspect(ident);project=raw['Config']['Labels'].get('com.docker.compose.project','')
 if project.startswith('geology-'):
  new=summary(raw);services[ident]=new
  if new!=old:changes.append(ident)
assert not changes
b=json.loads((ROOT/'phase11c-build.json').read_text());assert all(object_inspect('image',b['tags'][k])['Id']==v['id'] for k,v in b['images'].items())
q=queue_snapshot();assert q['safe_empty']
backup=Path(json.loads((ROOT/'phase9d-backup-copy.json').read_text())['destination']);back=json.loads((ROOT/'phase9d-final-backup-acl.json').read_text());assert all(sha(backup/f['name'])==f['sha256'] for f in back['files'])
out={'database':db,'documents':docs,'original_source_unchanged':True,'protected_configuration_unchanged':True,'candidate_11c_context_unchanged':True,'certification_11d_evidence_unchanged':True,'protected_container_changes':changes,'protected_services':services,'images11c_preserved':True,'backup_hashes_verified':True,'original_queue':q,'original_data_modified':False}
(ROOT/'phase11e-original-final.json').write_text(json.dumps(out,indent=2));print('Original and all protected GEOLOGY resources: unchanged; backups and 11C images preserved.')
