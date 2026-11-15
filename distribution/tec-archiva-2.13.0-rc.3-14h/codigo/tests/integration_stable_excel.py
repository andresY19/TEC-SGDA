import asyncio, hashlib, io, json
from datetime import date
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from geology.nucleo.bd import Base,motor,SesionLocal
from geology.modelos import UnidadInventario,Expediente,Trazabilidad,Tramite
from geology.rutas.cargue import importar_hoja
from geology.dominio.estados import Usuario,Rol
from sqlalchemy import inspect

if inspect(motor).get_table_names():
    raise RuntimeError("La integración requiere una base PostgreSQL sintética y vacía.")
Base.metadata.create_all(motor)
codes=[f'AC-CP-{n}' for n in range(99800,99804)]
with SesionLocal.begin() as db:
    db.add_all([UnidadInventario(codigo_carpeta=c,caja_origen='SINTETICO',folios=1) for c in codes])
def book(tabs, bad=False):
    w=Workbook();w.remove(w.active)
    for i,tab in enumerate(tabs):
        h=w.create_sheet(tab)
        for k,v in {'A1':'F-GDM-007 v4','I6':'01','I7':'01.02','B11':1,'E11':'Sintético','G11':1,'H11':1,'D33':date.today()}.items():h[k]=v
        if bad and i:h['E11']=None
    f=io.BytesIO();w.save(f);return f.getvalue()
def call(raw,code=None,role=Rol.ADMINISTRADORA,verify=True):
    f=io.BytesIO(raw); before=hashlib.sha256(raw).digest()
    with SesionLocal() as db:
        try:
            result=asyncio.run(importar_hoja(UploadFile(f,filename='AC-CP-99800.xlsx'),verify,db,Usuario('Sintético','s@example.invalid',role)))
            assert code is None
            return result
        except HTTPException as e:
            assert e.status_code==code,(e.status_code,e.detail)
        finally:assert hashlib.sha256(f.getvalue()).digest()==before
def totals():
    with SesionLocal() as db:
        expenses=db.query(Expediente).all()
        assert all(len(e.tramites)==1 and len(e.trazabilidad)==1 for e in expenses)
        return [len(expenses),db.query(Tramite).count(),db.query(Trazabilidad).count()]
res=call(book(codes[:2][::-1]))
assert [x['carpeta'] for x in res['resultados']]==codes[:2][::-1],res
assert res['importadas']==res['hojas_leidas']==2 and totals()==[2,2,2]
with motor.begin() as c:
    c.execute(text("""CREATE FUNCTION fixture_failure() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF EXISTS (SELECT 1 FROM unidad_documental WHERE id=NEW.expediente_id AND codigo_carpeta='AC-CP-99803') THEN
    IF NOT EXISTS (SELECT 1 FROM unidad_documental WHERE codigo_carpeta='AC-CP-99802') THEN RAISE EXCEPTION 'first_missing'; END IF;
    RAISE EXCEPTION 'fixture_second_sheet'; END IF; RETURN NEW; END $$"""))
    c.execute(text("CREATE TRIGGER fixture_failure BEFORE INSERT ON trazabilidad FOR EACH ROW EXECUTE FUNCTION fixture_failure()"))
try:call(book(codes[2:]),verify=False)
except DBAPIError as e:assert 'fixture_second_sheet' in str(e.orig),str(e.orig)
else:raise AssertionError('No hubo fallo en la segunda hoja')
assert totals()==[2,2,2]
call(book(['Hoja A','Hoja B']),422)
call(book(codes[2:],True),422)
call(b'invalid',422)
call(book(codes[2:]),403,Rol.CONSULTA)
assert totals()==[2,2,2]
print(json.dumps(dict(importadas=2,expedientes=2,tramites=2,trazas=2,rollback_postgresql=True,duplicado=422,incompleto=422,invalido=422,consulta=403,sha256=True,huerfanos=0)))
