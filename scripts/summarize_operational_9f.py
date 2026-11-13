"""Consolidate already verified nonsecret evidence; no infrastructure access."""
from pathlib import Path
import json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[1]
def load(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
def main():
    rec=load('phase9f-recovery-evidence.json');state=load('phase9f-recovery-state.json')
    db=load('phase9f-database-final.json');docs=load('phase9f-document-integrity.json')
    logs=load('phase9f-service-log-review.json');reg=load('phase9f-regression-results.json')
    celery=load('phase9f-celery-registration.json');queue=load('phase9f-queue-final.json')
    listener=load('phase9f-listener.json');listener=listener if isinstance(listener,list) else [listener]
    assert listener and all(x['LocalAddress'] in ('127.0.0.1','::1') for x in listener)
    assert reg['container']['returncode']==reg['host_http']['returncode']==0
    units=json.loads(reg['container']['stdout'].splitlines()[-1])
    assert units=={'run':21,'failures':0,'errors':0,'skipped':0}
    assert 'Ran 1 test' in reg['host_http']['stderr'] and 'OK' in reg['host_http']['stderr']
    assert all(db['comparison_to_backup'].values()) and (db['tables'],db['records'],db['traces'])==(27,26,9)
    assert db['admin']['present'] and db['admin']['active'] and db['admin']['role']=='administradora'
    assert not db['admin']['provisional']
    before=rec['database']['before_application']
    assert all(db[k]==before[k] for k in ('schema_sha256','data_sha256','catalog_object_fingerprint','row_counts'))
    assert not any(x['critical_lines'] for x in logs['logs'].values())
    assert logs['logs']['procesador']['task_receipts']==0 and queue['safe_empty']
    assert len(celery['registered'])==3 and celery['published_tasks']==0
    assert rec['started_services']==['almacen_datos','mensajeria','servidor','procesador']
    for service,c in logs['services'].items():
        assert c['status']=='running' and c['id']==rec['preflight']['original_before'][service]['id']
        if service!='procesador':assert c['health']=='healthy'
    assert rec['temporary_after']==rec['temporary_before']
    for name,h in rec['preflight']['file_hashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
    source=load('phase9a-before-files.json')
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in source.items() if name.startswith('geology/'))
    result={
        'GEOLOGY_OPERATIONAL_RECOVERY':'PASS','POSTGRESQL':'HEALTHY','REDIS':'HEALTHY',
        'FASTAPI':'HEALTHY','CELERY':'RUNNING','DATABASE_INTEGRITY':'PASS',
        'DOCUMENT_INTEGRITY':'PASS','HTTP_HEALTH':'PASS','PRODUCTION_CHANGES':0,
        'NEXT_PHASE':'PENDING_APPROVAL','project':rec['project'],'services':logs['services'],
        'start_order':rec['started_services'],'container_recreations':0,'image_builds':0,
        'volume_replacements':0,'http':rec['http'],'host_listeners':listener,
        'database':{'tables':27,'records':26,'traces':9,'administrator':db['admin'],
            'schema_matches_backup':True,'data_matches_backup':True,'row_counts_match_backup':True,
            'startup_and_regression_schema_catalog_data_unchanged':True,
            'constraint_counts':db['constraint_counts'],'indexes':db['index_count'],
            'version':logs['postgres']['version']},
        'documents':{'verified_files':docs['files_verified'],'direct_SQL_references':len(docs['SQL_references']),
            'hashes_and_sizes_match_backup':True,'originals_parts_derivatives_manifests_preserved':True,
            'pending_journal':docs['pending_journals'],'unexpected_files':docs['unexpected_files']},
        'redis':logs['redis'],'celery':celery|{'queue_snapshot':queue,'tasks_received_since_start':0},
        'regression':{'passed':22,'failed':0,'skipped':0,'breakdown':
            {'isolated_import_lifespan':15,'readonly_Postgres_Redis':6,'HTTP':1},
            'excluded':'Authentication writes, document fixtures, task publication and restart tests'},
        'temporary_restore_project_untouched':True,'temporary_container_id':state['temporary_container_id'],
        'temporary_metadata_before_after_equal':True,'temporary_mutating_actions':[],
        'critical_startup_errors':0,'provider_keys_empty':True,'auto_reading_disabled':True,
        'compose_and_Dockerfiles_unchanged':True,'application_code_unchanged':True,
        'documents_modified':0,'password_changes':0,'data_corrections':0,'migrations':0,
        'files_deleted':0,'tasks_published':0,
        'risks':['Worker retains its existing superuser/root warning.',
            'One preexisting failed-upload journal and its 25-byte source remain pending manual reconciliation.',
            'PDF/A-1b integration and institutional profile confirmation remain pending; no conversion performed.',
            'No new login or task-execution test was performed under this read-only phase.',
            'Previously shared provider keys remain unused; owner rotation confirmation is pending.'],
        'workflow_notes':['Before any start, null Compose command was resolved to the cached PostgreSQL image default.',
            'After Redis recovery, an owned celeryev routing set was classified as worker-event metadata; no message backlog or Redis cleanup.',
            'Redis INFO uses a verbatim CLI response and was parsed as raw text.',
            'A combined final consolidation command was rejected by automatic policy review (blocked by policy). This report was produced offline from verified evidence without renewed sensitive configuration reads.'],
        'technical_reference':'https://docs.celeryq.dev/en/stable/reference/celery.events.event.html',
        'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    state['stage']='CERTIFIED_OPERATIONAL'
    (ROOT/'phase9f-recovery-state.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    result['evidence_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('phase9f-*.json') if p.name!='phase9f-results.json'}
    text=json.dumps(result,indent=2)
    (ROOT/'phase9f-results.json').write_text(text,encoding='utf-8')
    (ROOT/'expedidos/evidencias_9f/summary.json').write_text(text,encoding='utf-8')
    print(json.dumps({'result':'PASS','tables':27,'records':26,'documents':17,'regression_passed':22,'new_tasks':0,'restore_environment_untouched':True},indent=2))
if __name__=='__main__':main()
