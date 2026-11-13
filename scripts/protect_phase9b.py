"""Snapshot and backup of this local synthetic environment; no database writes."""
from pathlib import Path
import subprocess,json,hashlib,zipfile

ROOT=Path(__file__).resolve().parents[1]
PROJECT='geology-local-20261106-57a99a'
OUT=ROOT/'expedidos/respaldo_sintetico_9b'

def read_state():
    code='''import json,hashlib,os
from sqlalchemy import select,text,inspect
from geology.nucleo.bd import motor,Base,registrar_modelos
from geology.modelos import Archivo
registrar_modelos();assert motor.url.host=='almacen_datos' and motor.url.database=='geology'
with motor.connect() as c:
 data={t.name:[dict(r) for r in c.execute(select(t).order_by(*t.primary_key.columns)).mappings()] for t in Base.metadata.sorted_tables}
 refs=[r for rows in data.values() for r in rows if 'ruta' in r]
 print(json.dumps({'data_sha256':hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest(),'rows':{k:len(v) for k,v in data.items()},'references':[r['ruta'] for r in refs],'database_bytes':c.execute(text('select pg_database_size(current_database())')).scalar_one(),'tables':len(inspect(c).get_table_names())}))
'''
    p=subprocess.run(['docker','exec','-i',PROJECT+'-servidor-1','python','-B','-'],input=code,text=True,capture_output=True,check=True)
    return json.loads(p.stdout)

def main():
    before=read_state();assert before['tables']==27
    old=json.loads((ROOT/'phase9a-final-verification.json').read_text())
    assert before['rows']==old['row_counts']
    for name,h in old['depot_hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
    services={}
    for service in ('almacen_datos','mensajeria','servidor','procesador'):
        c=json.loads(subprocess.check_output(['docker','inspect',PROJECT+'-'+service+'-1'],text=True))[0]
        assert c['Config']['Labels']['com.docker.compose.project']==PROJECT
        assert c['Id']==old['services'][service]['id'] and c['State']['Running']
        services[service]={'id':c['Id'],'health':c['State'].get('Health',{}).get('Status'),
            'mounts':[{k:m.get(k) for k in ('Type','Name','Source','Destination','RW')} for m in c['Mounts']]}
        if service in ('almacen_datos','mensajeria'):
            expected=PROJECT+('_pgdata' if service=='almacen_datos' else '_redisdata')
            mounts=[m for m in c['Mounts'] if m['Type']=='volume'];assert len(mounts)==1 and mounts[0]['Name']==expected
            v=json.loads(subprocess.check_output(['docker','volume','inspect',expected],text=True))[0]
            assert v['Labels']['com.docker.compose.project']==PROJECT
    resume=OUT.exists()
    if resume:
        assert {p.name for p in OUT.iterdir()}=={'postgres-local.dump','postgres-catalog.txt','deposito-sintetico.zip'}
        dump=(OUT/'postgres-local.dump').read_bytes()
    else:
        OUT.mkdir(exist_ok=False)
        dump=subprocess.check_output(['docker','exec',PROJECT+'-almacen_datos-1','pg_dump','-U','geology','-d','geology','--format=custom','--no-owner','--no-acl'])
        (OUT/'postgres-local.dump').write_bytes(dump)
    catalog=subprocess.run(['docker','exec','-i',PROJECT+'-almacen_datos-1','pg_restore','--list'],input=dump,capture_output=True,check=True)
    assert b'TABLE DATA' in catalog.stdout
    if resume:assert (OUT/'postgres-catalog.txt').read_bytes()==catalog.stdout
    else:(OUT/'postgres-catalog.txt').write_bytes(catalog.stdout)
    docs=[p for p in (ROOT/'deposito').rglob('*') if p.is_file()]
    if not resume:
        with zipfile.ZipFile(OUT/'deposito-sintetico.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
            for p in docs:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(OUT/'deposito-sintetico.zip') as z:
        assert z.testzip() is None
        for p in docs:assert hashlib.sha256(z.read(p.relative_to(ROOT).as_posix())).digest()==hashlib.sha256(p.read_bytes()).digest()
    after=read_state();assert before==after
    rejected=ROOT/'deposito/operaciones/cargue-6_61766_'
    journal=json.loads((rejected/'operacion.json').read_text())
    assert journal['estado']=='revertida_antes_commit' and not journal['sql_confirmado'] and journal['rollback_confirmado']
    assert str(Path('/srv/geology/deposito/operaciones/cargue-6_61766_/original.pdf')) not in after['references']
    result={'before':before,'after':after,'database_unchanged':True,'services':services,
        'backup_valid_catalog_only':True,'restore_test_performed':False,'backup_same_drive_warning':True,
        'archive_verified_entries':len(docs),'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.iterdir() if p.is_file()},
        'rejected_operation':{'journal_status':journal['estado'],'source_bytes':(rejected/'original.pdf').stat().st_size,
            'source_sha256':hashlib.sha256((rejected/'original.pdf').read_bytes()).hexdigest(),'sql_reference':False,
            'rollback_confirmed':True,'retain':True,'journal_reconciliation_flag':journal.get('requiere_conciliacion'),
            'decision':'Keep source and journal unchanged. Technical association established; manual closure of reconciliation pending owner decision.'}}
    (ROOT/'phase9b-protection.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('database_unchanged','backup_valid_catalog_only','restore_test_performed','archive_verified_entries','files','rejected_operation')},indent=2))

if __name__=='__main__':main()
