"""Read-only final evidence; emits no credentials or tokens."""
import subprocess,json,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROJECT='geology-local-20261106-57a99a'

def main():
    result={'services':{},'production_changes':0}
    for service in ('almacen_datos','mensajeria','servidor','procesador'):
        c=json.loads(subprocess.check_output(['docker','inspect',PROJECT+'-'+service+'-1'],text=True))[0]
        assert c['Config']['Labels']['com.docker.compose.project']==PROJECT
        result['services'][service]={'id':c['Id'],'image':c['Image'],'status':c['State']['Status'],
            'health':c['State'].get('Health',{}).get('Status'),'networks':list(c['NetworkSettings']['Networks'])}
    raw=subprocess.check_output(['docker','exec',PROJECT+'-almacen_datos-1','pg_dump','-U','geology','-d','geology','--schema-only','--no-owner','--no-acl'],text=True)
    digest=hashlib.sha256('\n'.join(x for x in raw.splitlines() if not x.startswith(('\\restrict','\\unrestrict'))).encode()).hexdigest()
    result['schema_sha256']=digest
    result['schema_unchanged']=digest==json.loads((ROOT/'phase8b-schema-before-http.json').read_text())['sha256']
    code='''import json,os,redis,hashlib,shutil
from pathlib import Path
from sqlalchemy import inspect,select
from geology.nucleo.bd import motor,Base,SesionLocal,registrar_modelos
from geology.modelos import Archivo,Expediente,UsuarioBD,Trazabilidad
registrar_modelos()
r=redis.Redis.from_url(os.environ['CELERY_BROKER_URL']);pending={}
for k in r.scan_iter():
 t=r.type(k)
 n=r.llen(k) if t==b'list' else r.hlen(k) if b'unacked' in k and t==b'hash' else r.zcard(k) if b'unacked' in k and t==b'zset' else 0
 if n:pending[k.decode()]=n
d={'pending':pending,'table_count':len(inspect(motor).get_table_names()),'ai_keys_empty':all(not v for k,v in os.environ.items() if k.startswith(('GEMINI_API_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY'))),'auto_reader_disabled':os.environ['LEVANTAR_AL_CARGAR'].lower() in ('no','0','false'),'free_bytes':shutil.disk_usage('/srv/geology/deposito').free}
with SesionLocal() as s:
 d['row_counts']={t.name:len(s.execute(select(t)).all()) for t in Base.metadata.sorted_tables}
 d['synthetic_files']=[{'id':a.id,'code':a.codigo_carpeta,'path':a.ruta,'pages':a.paginas,'sha256':a.sha256,'page_first':a.pagina_inicial,'page_last':a.pagina_final,'matrix':a.ruta_matriz,'consultation':a.ruta_consulta,'processing_error':a.error_proceso} for a in s.query(Archivo).filter(Archivo.codigo_carpeta.in_(('AC-CP-99001','AC-CP-99002')))]
 d['synthetic_states']={e.codigo_carpeta:{'state':e.estado,'approved':e.aprobo is not None,'published':e.publicado_consulta,'traces':s.query(Trazabilidad).filter_by(expediente_id=e.id).count()} for e in s.query(Expediente).filter(Expediente.codigo_carpeta.in_(('AC-CP-99001','AC-CP-99002')))}
 a=s.query(UsuarioBD).filter_by(correo='admin.local.8c@example.invalid').one()
 d['existing_admin']={'active':a.activo,'role':a.rol,'provisional':a.debe_cambiar_clave}
print(json.dumps(d,default=str))
'''
    p=subprocess.run(['docker','exec','-i',PROJECT+'-servidor-1','python','-B','-'],input=code,text=True,capture_output=True,check=True)
    result.update(json.loads(p.stdout))
    root=ROOT/'deposito';known=set();manifests=[]
    def local(path):return ROOT/Path(path).relative_to('/srv/geology')
    for a in result['synthetic_files']:
        for key in ('path','matrix','consultation'):
            if a[key]:known.add(local(a[key]))
    for manifest in root.glob('operaciones/*/operacion.json'):
        d=json.loads(manifest.read_text(encoding='utf-8'))
        assert d['codigo_carpeta'] in ('AC-CP-99001','AC-CP-99002')
        manifests.append({'path':str(manifest.relative_to(ROOT)),'status':d['estado'],'sql_confirmed':d['sql_confirmado'],'reconciliation':d.get('requiere_conciliacion')})
        known.add(manifest)
        if d.get('original'):
            original=local(d['original']['ruta']);known.add(original)
            assert original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()==d['original']['sha256']
        for part in d.get('partes',[]):known.add(local(part['ruta']))
    fixture=json.loads((ROOT/'expedidos/pruebas_sinteticas_9a/evidence.json').read_text())
    known.update(local(p) for p in fixture['source_hashes'])
    known.add(local(fixture['input_directory'])/'hoja_manual_sintetica.json')
    result['manifests']=manifests
    result['unexpected_depot_files']=[str(p.relative_to(ROOT)) for p in root.rglob('*') if p.is_file() and p not in known]
    result['temporary_files']=[str(p.relative_to(ROOT)) for p in root.rglob('*') if p.is_file() and p.suffix in ('.tmp','.part')]
    result['depot_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    result['code_files_changed']=[]
    for name,h in json.loads((ROOT/'phase9a-before-files.json').read_text()).items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:result['code_files_changed'].append(name)
    (ROOT/'phase9a-final-verification.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('schema_unchanged','table_count','pending','ai_keys_empty','auto_reader_disabled','unexpected_depot_files','temporary_files','code_files_changed','synthetic_states')},indent=2))

if __name__=='__main__':main()
