import json,hashlib,tempfile
from datetime import date
from pathlib import Path
from fastapi import HTTPException
from geology.nucleo.bd import Base,motor,SesionLocal
from geology.modelos import Expediente,UnidadInventario,Periodo,Archivo,Tramite,Trazabilidad,Caja,Asignacion,UsuarioBD
from geology.dominio.estados import Estado,Rol,Usuario
from geology.rutas import ubicacion as u,seguimiento as s
from sqlalchemy import inspect

if inspect(motor).get_table_names():
    raise RuntimeError("La integración requiere una base PostgreSQL sintética y vacía.")
Base.metadata.create_all(motor)
codes=[f'AC-CP-{99860+i}' for i in range(6)]
box='AH-CJ-99860'
def actor(rol):return Usuario(rol.value,rol.value+'@example.invalid',rol)
admin,leader,team,reader=[actor(r) for r in (Rol.ADMINISTRADORA,Rol.LIDER,Rol.EQUIPO,Rol.CONSULTA)]
file=Path(tempfile.mkdtemp())/'fixture.pdf';file.write_bytes(b'%PDF-1.4\n% fixture\n')
digest=hashlib.sha256(file.read_bytes()).hexdigest()
with SesionLocal.begin() as db:
    p,q=Periodo(numero_romano='I'),Periodo(numero_romano='II');db.add_all([p,q]);db.flush()
    for i,code in enumerate(codes):
        db.add(UnidadInventario(codigo_carpeta=code,periodo='II' if i==2 else 'I',caja_origen='ORIGEN',folios=1))
        e=Expediente(codigo_carpeta=code,estado=[Estado.ARCHIVADO,Estado.EN_COLA,Estado.ARCHIVADO,Estado.ARCHIVADO,Estado.RETIRADO,Estado.EN_COLA][i].value,periodo_id=(q if i==2 else p).id,caja_origen='ORIGEN',volumen_folios=1)
        db.add(e);db.flush()
        if i==0:
            e.tramites.append(Tramite(no_item=1,tipo_documental='Acta',folio_desde=1,folio_hasta=1))
            db.add(Archivo(expediente_id=e.id,codigo_carpeta=code,fragmento=0,nombre_original='fixture.pdf',ruta=str(file),sha256=digest,tamano_bytes=file.stat().st_size))
    for x in (team,leader,reader):
        db.add(UsuarioBD(nombre=x.nombre,correo=x.correo,rol=x.rol.value,funcion='Ambas',activo=True,clave_hash='fixture'))
def call(fn,*args,user=admin,**kwargs):
    with SesionLocal() as db:return fn(*args,db=db,quien=user,**kwargs)
def reject(status,fn,*args,**kwargs):
    try:call(fn,*args,**kwargs)
    except HTTPException as e:assert e.status_code==status,(e.status_code,e.detail)
    else:raise AssertionError(status)
def move(c,*items,user=admin):return call(u.asignar,u.AsignacionEntrada(caja=c,carpetas=list(items)),user=user)
assert {x['codigo_carpeta'] for x in call(u.pendientes)}=={codes[i] for i in (0,2,3)}
reject(403,u.asignar,u.AsignacionEntrada(caja=box,carpetas=[codes[0]]),user=leader)
reject(409,u.asignar,u.AsignacionEntrada(caja=box,carpetas=[codes[0],codes[2]]))
assert not call(u.cajas)
r=move(box,codes[0],codes[1])
assert r['total_en_la_caja']==1 and r['asignadas'][0]['no_carpeta']==1 and r['rechazadas'][0]['carpeta']==codes[1]
assert not move(box,codes[0])['asignadas']
assert not move(box,codes[2])['asignadas']
reject(403,u.cerrar,box,user=team)
assert call(u.cerrar,box,user=leader)['cerrada']
reject(409,u.asignar,u.AsignacionEntrada(caja=box,carpetas=[codes[3]]))
reject(403,u.reabrir,box,user=leader)
assert not call(u.reabrir,box)['cerrada']
assert move(box,codes[3])['total_en_la_caja']==2
with SesionLocal() as db:
    e=db.query(Expediente).filter_by(codigo_carpeta=codes[0]).one();assert e.estado==Estado.EN_INVENTARIO.value and e.caja_origen=='ORIGEN'
    a=db.query(Archivo).filter_by(codigo_carpeta=codes[0]).one()
    assert a.expediente_id==e.id and a.sha256==hashlib.sha256(file.read_bytes()).hexdigest()==digest and len(e.tramites)==1
    t=db.query(Trazabilidad).filter_by(expediente_id=e.id).one()
    assert (t.accion,t.estado_anterior,t.estado_nuevo,t.usuario)==('asignar_caja',Estado.ARCHIVADO.value,Estado.EN_INVENTARIO.value,admin.nombre) and t.fecha and box in t.motivo
    b=db.query(Caja).filter_by(codigo=box).one();assert 'Reabierta' in b.observaciones and b.total_carpetas==2
def available(code):
    return call(s.disponibles,etapa='hoja_control',periodo='I',caja='ORIGEN',buscar=code,limite=20)['carpetas']
assert len(available(codes[1]))==1 and not available(codes[4]) and not available(codes[0])
payload=s.Asignar(carpetas=[codes[1],codes[1]],persona=team.correo,fecha_limite=date(2099,1,1))
reject(403,s.asignar,payload,user=leader)
reject(422,s.asignar,payload.model_copy(update={'persona':reader.correo}))
reject(422,s.asignar,payload.model_copy(update={'etapa':'invalida'}))
assert call(s.asignar,payload)['nueva']==1
assert call(s.asignar,payload)['igual']==1
assert not available(codes[1])
assert call(s.mis,user=team)['carpetas'][0]['carpeta']==codes[1]
assert not call(s.mis,user=leader)['carpetas']
assert call(s.asignar,payload.model_copy(update={'persona':leader.correo}))['reasignada']==1
assert not call(s.mis,user=team)['carpetas']
assert call(s.mis,user=leader)['carpetas'][0]['carpeta']==codes[1]
r=call(s.asignar_lote,s.AsignarLote(personas=[team.correo],por_persona=3,periodo='I',caja='ORIGEN'))
assert r['total']==1 and call(s.mis,user=team)['carpetas'][0]['carpeta']==codes[5],r
# Compare the direct endpoint against the actual candidate-selection result.
manual=call(s.asignar,payload.model_copy(update={'carpetas':[codes[4],codes[0]]}))
assert manual['nueva']==2,manual
with SesionLocal() as db:
    a=db.query(Asignacion).filter_by(codigo_carpeta=codes[1],activa=True).one()
    aid=a.id
    assert a.persona==leader.correo and a.asignado_por==admin.nombre and a.asignado_en
    assert db.query(Expediente).filter_by(codigo_carpeta=codes[1]).one().estado==Estado.EN_COLA.value
    assert db.query(Trazabilidad).join(Expediente).filter(Expediente.codigo_carpeta==codes[1]).count()==0
call(s.quitar,aid)
with SesionLocal() as db:
    a=db.get(Asignacion,aid);assert not a.activa and a.cerrada_en
    assert db.query(Asignacion).filter(Asignacion.codigo_carpeta.in_([codes[4],codes[0]]),Asignacion.activa.is_(True)).count()==2
duplicate=move('AH-CJ-99862',codes[2],'  '+codes[2].lower()+'  ')
with SesionLocal() as db:
    exp=db.query(Expediente).filter_by(codigo_carpeta=codes[2]).one()
    moves=db.query(Trazabilidad).filter_by(expediente_id=exp.id,accion='asignar_caja').all()
    duplicate_result=dict(response_rows=len(duplicate['asignadas']),persisted_total=duplicate['total_en_la_caja'],traces=len(moves),consecutive=exp.consecutivo_en_caja)
assert duplicate_result==dict(response_rows=1,persisted_total=1,traces=1,consecutive=1),duplicate_result
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
with SesionLocal.begin() as db:
    for i in range(99880,99884):
        db.add(Expediente(codigo_carpeta=f'AC-CP-{i}',estado=Estado.ARCHIVADO.value,periodo_id=db.query(Periodo).filter_by(numero_romano='I').one().id))
def parallel(a,b):
    barrier=Barrier(2)
    def task(x):
        barrier.wait(timeout=5)
        return move(*x)
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(task,[a,b]))
same=parallel(('AH-CJ-99880','AC-CP-99880'),('AH-CJ-99880','AC-CP-99880'))
assert sum(len(r['asignadas']) for r in same)==1
cross=parallel(('AH-CJ-99881','AC-CP-99881'),('AH-CJ-99882','AC-CP-99881'))
assert sum(len(r['asignadas']) for r in cross)==1
distinct=parallel(('AH-CJ-99883','AC-CP-99882'),('AH-CJ-99883','AC-CP-99883'))
assert sorted(r['asignadas'][0]['no_carpeta'] for r in distinct)==[1,2]
with SesionLocal() as db:
    for i in range(99880,99884):
        e=db.query(Expediente).filter_by(codigo_carpeta=f'AC-CP-{i}').one()
        assert db.query(Trazabilidad).filter_by(expediente_id=e.id,accion='asignar_caja').count()==1
    assert db.query(Caja).filter_by(codigo='AH-CJ-99883').one().total_carpetas==2
print(json.dumps(dict(reubicacion=dict(concurrencia_misma_caja=True,concurrencia_cajas_distintas=True,concurrencia_consecutivos=True,duplicado_misma_solicitud=duplicate_result,asignacion=True,mezcla_inicial_409=True,caja_cerrada_409=True,rol_asignar_403=True,reapertura=True,sha256=True,relaciones=True,traza=True,totales=True),seguimiento=dict(filtros=True,rol_403=True,persona_y_etapa_422=True,reintento=True,reasignacion=True,lote=True,baja_logica=True,estado_documental_intacto=True,manual_admite_retirado_y_etapa_superada=True))))
