"""Initialize only the exclusive synthetic database, using the owner once."""
import os

from sqlalchemy import text
from geology.nucleo.bd import crear_tablas, motor, SesionLocal
from geology.modelos import UsuarioBD, UnidadInventario, cifrar_clave

with motor.connect() as conn:
    assert conn.execute(text('SELECT current_database(), current_user')).one() == ('sgdea_demo', 'demo_owner')
    assert not conn.execute(text("SELECT to_regclass('public.cuenta')")).scalar()
crear_tablas(autorizacion_local=True)
with SesionLocal.begin() as session:
    session.add(UsuarioBD(nombre='Administrador sintético TEC-SGDEA', correo='admin.sgdea.demo@example.invalid',
                         rol='administradora', funcion='Ambas', activo=True, debe_cambiar_clave=False,
                         clave_hash=cifrar_clave(os.environ['DEMO_PASSWORD'])))
    session.add(UnidadInventario(codigo_carpeta='AC-CP-98001', caja_origen='SINTETICO SGDEA',
                                periodo='I', folios=1, asunto='Expediente sintético de demostración'))
