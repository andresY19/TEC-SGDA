import json,threading,time,urllib.request
from fastapi import FastAPI
import uvicorn
from geology.nucleo.bd import Base,motor,SesionLocal
from geology.dominio.estados import Estado
from geology.modelos import Expediente
from geology.rutas import unidades as u
from sqlalchemy import inspect

if inspect(motor).get_table_names():
    raise RuntimeError("La integración requiere una base PostgreSQL sintética y vacía.")
Base.metadata.create_all(motor)
app=FastAPI()
app.include_router(u.router)
app.dependency_overrides[u.usuario_actual]=lambda:None
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8891,log_level='error'))
threading.Thread(target=server.run,daemon=True).start()
for _ in range(200):
    if server.started:break
    time.sleep(.05)
assert server.started
def call(path):
    with urllib.request.urlopen('http://127.0.0.1:8891'+path,timeout=5) as r:return json.load(r)
def check():
    p=call('/unidades/produccion?dia=2000-01-01')['embudo']
    assert p==call('/unidades/ahora?minutos=5')['embudo']
    return p
cases=[check()]
with SesionLocal.begin() as db:
    for i,state in enumerate([Estado.HOJA_EN_ELABORACION,Estado.HOJA_EN_ELABORACION,Estado.RETIRADO,Estado.EN_PROCESAMIENTO,Estado.EN_COLA]):
        db.add(Expediente(codigo_carpeta=f'AC-CP-{99800+i}',estado=state.value,volumen_folios=i+1))
cases.append(check())
with SesionLocal.begin() as db:
    db.query(Expediente).filter_by(codigo_carpeta='AC-CP-99800').one().estado=Estado.RETIRADO.value
cases.append(check())
print(json.dumps(cases))
