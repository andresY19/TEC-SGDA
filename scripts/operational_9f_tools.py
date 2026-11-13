"""Read-only helpers for 9F. No Celery publication or restore operations."""
from pathlib import Path
import subprocess,json,hashlib,datetime,decimal,collections,re
ROOT=Path(__file__).resolve().parents[1]
PROJECT='geology-local-20261106-57a99a'

def command(args,**kw):
    return subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',**kw)
def checked(args,**kw):
    p=command(args,**kw)
    if p.returncode:raise RuntimeError('Command failed: '+args[0]+' exit '+str(p.returncode))
    return p.stdout
def inspect(name):return json.loads(checked(['docker','inspect',name]))[0]
def object_inspect(kind,name):return json.loads(checked(['docker',kind,'inspect',name]))[0]
def summary(c):
    return {'id':c['Id'],'image':c['Image'],'status':c['State']['Status'],
        'health':c['State'].get('Health',{}).get('Status'),'started_at':c['State']['StartedAt'],
        'finished_at':c['State']['FinishedAt'],'restart_count':c['RestartCount'],
        'mounts':c['Mounts'],'networks':sorted(c['NetworkSettings'].get('Networks') or {}),
        'port_bindings':c['HostConfig']['PortBindings']}
def sql(query):
    return checked(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on',PROJECT+'-almacen_datos-1',
        'psql','-X','-v','ON_ERROR_STOP=1','-U','geology','-d','geology','-At','-c',query]).strip()
def quote(s):return '"'+s.replace('"','""')+'"'
def digest(data):return hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
def native_json(v):
    if isinstance(v,decimal.Decimal):return float(v)
    if isinstance(v,list):return [native_json(x) for x in v]
    if isinstance(v,dict):return {k:native_json(x) for k,x in v.items()}
    return v

def database_snapshot():
    tables=json.loads(sql("select coalesce(json_agg(tablename order by tablename),'[]') from pg_tables where schemaname='public'"))
    cols=json.loads(sql("select json_agg(row_to_json(x)) from (select table_name,column_name,data_type from information_schema.columns where table_schema='public' order by table_name,ordinal_position) x"))
    pk=json.loads(sql("select json_object_agg(table_name,cols) from (select k.table_name,json_agg(k.column_name order by k.ordinal_position) cols from information_schema.table_constraints t join information_schema.key_column_usage k on k.constraint_name=t.constraint_name and k.constraint_schema=t.constraint_schema where t.constraint_schema='public' and t.constraint_type='PRIMARY KEY' group by k.table_name) x"))
    constraints=json.loads(sql("select json_agg(row_to_json(x)) from (select c.oid,c.conrelid::regclass::text as table_name,c.conname,c.contype,c.convalidated,pg_get_constraintdef(c.oid) as definition from pg_constraint c join pg_namespace n on n.oid=c.connamespace where n.nspname='public' order by c.oid) x"))
    indexes=json.loads(sql("select json_agg(row_to_json(x)) from (select i.oid,t.relname as table_name,i.relname as index_name,ix.indisvalid,ix.indisready,pg_get_indexdef(i.oid) as definition from pg_index ix join pg_class i on i.oid=ix.indexrelid join pg_class t on t.oid=ix.indrelid join pg_namespace n on n.oid=t.relnamespace where n.nspname='public' order by i.oid) x"))
    objects=json.loads(sql("select json_agg(row_to_json(x)) from (select c.oid,c.relname,c.relkind from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' order by c.oid) x"))
    data={};types={(c['table_name'],c['column_name']):c['data_type'] for c in cols}
    for table in tables:
        order=','.join(quote(k) for k in pk[table])
        rows=json.loads(sql('select coalesce(json_agg(row_to_json(x)),\'[]\') from (select * from public.'+quote(table)+' order by '+order+') x'),parse_float=decimal.Decimal)
        for row in rows:
            for key,value in list(row.items()):
                if value is None:continue
                kind=types[(table,key)]
                if kind.startswith('timestamp'):row[key]=datetime.datetime.fromisoformat(value)
                elif kind=='date':row[key]=datetime.date.fromisoformat(value)
                elif kind=='numeric':row[key]=decimal.Decimal(str(value))
                elif kind in ('real','double precision'):row[key]=float(value)
                elif kind in ('json','jsonb'):row[key]=native_json(value)
                elif kind=='bytea':row[key]=bytes.fromhex(value[2:])
        data[table]=rows
    schema=checked(['docker','exec',PROJECT+'-almacen_datos-1','pg_dump','-U','geology','-d','geology','--schema-only','--no-owner','--no-acl'])
    schema_hash=hashlib.sha256('\n'.join(x for x in schema.splitlines() if not x.startswith(('\\restrict','\\unrestrict'))).encode()).hexdigest()
    admin=[x for x in data.get('cuenta',[]) if x['correo']=='admin.local.8c@example.invalid']
    refs=[]
    for table,rows in data.items():
        for row in rows:
            for key,path in row.items():
                if key.startswith('ruta') and isinstance(path,str) and path:
                    refs.append({'table':table,'id':row.get('id'),'column':key,'path':path,
                        'sha256':row.get('sha256') if key=='ruta' else None})
    # Never return/persist raw account rows or password hashes.
    return {'tables':len(tables),'table_names':tables,'row_counts':{k:len(v) for k,v in data.items()},
        'records':sum(len(v) for v in data.values()),'schema_sha256':schema_hash,'data_sha256':digest(data),
        'catalog_object_fingerprint':digest([objects,constraints,indexes]),
        'constraint_counts':dict(collections.Counter(x['contype'] for x in constraints)),
        'all_constraints_valid':all(x['convalidated'] for x in constraints),
        'index_count':len(indexes),'all_indexes_valid':all(x['indisvalid'] and x['indisready'] for x in indexes),
        'admin':{'present':len(admin)==1,'active':admin[0]['activo'] if admin else False,
            'role':admin[0]['rol'] if admin else None,'provisional':admin[0]['debe_cambiar_clave'] if admin else None,
            'password_hash_present':bool(admin and admin[0]['clave_hash'])},
        'traces':len(data.get('trazabilidad',[])),'document_references':refs,
        'expediente_states':{x['codigo_carpeta']:x['estado'] for x in data.get('unidad_documental',[])}}

def redis_json(db,*args):
    return json.loads(checked(['docker','exec',PROJECT+'-mensajeria-1','redis-cli','--json','-n',str(db),*map(str,args)]))

def queue_snapshot():
    queue=PROJECT+'-tasks';prefix=PROJECT+':'
    known_binding=prefix+'_kombu.binding.'+queue
    counts={'pending_messages':0,'unacked':0,'unacked_index':0,'unknown_keys':0,'binding_members':0,'event_binding_members':0,'transport_locks':0}
    keys=[];cursor='0'
    while True:
        cursor,batch=redis_json(0,'SCAN',cursor,'COUNT',1000);keys+=batch
        if str(cursor)=='0':break
    for key in keys:
        kind=redis_json(0,'TYPE',key)
        if key==known_binding and kind=='set':
            members=redis_json(0,'SMEMBERS',key)
            if any(queue not in x for x in members):counts['unknown_keys']+=1
            counts['binding_members']+=len(members)
        elif key==prefix+'_kombu.binding.celeryev' and kind=='set':
            members=redis_json(0,'SMEMBERS',key)
            for member in members:
                parts=member.split('\x06\x16')
                if len(parts)!=3 or parts[0]!='worker.#' or parts[1]!='' or not re.fullmatch(r'celeryev\.[0-9a-f-]{36}',parts[2]):counts['unknown_keys']+=1
            counts['event_binding_members']+=len(members)
        elif key==prefix+queue or key.startswith(prefix+queue+'\x06\x16'):
            if kind!='list':counts['unknown_keys']+=1
            else:counts['pending_messages']+=redis_json(0,'LLEN',key)
        elif key==prefix+'unacked' and kind=='hash':counts['unacked']+=redis_json(0,'HLEN',key)
        elif key==prefix+'unacked_index' and kind=='zset':counts['unacked_index']+=redis_json(0,'ZCARD',key)
        elif key==prefix+'unacked_mutex' and kind=='string':counts['transport_locks']+=1
        elif kind!='none':counts['unknown_keys']+=1
    counts['safe_empty']=all(counts[k]==0 for k in ('pending_messages','unacked','unacked_index','unknown_keys'))
    counts['queue']=queue;counts['broker_db']=0;counts['result_db']=1
    return counts
