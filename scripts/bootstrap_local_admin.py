"""Bootstrap explícito local único; secreto por stdin, nunca en argumentos/salida.

No usar contra una base con cuentas. No crea tablas ni inicia componentes.
"""
import json,os,sys
from sqlalchemy import inspect
from geology.nucleo.bd import motor,SesionLocal,registrar_modelos
from geology.modelos import UsuarioBD,cifrar_clave,clave_correcta
from geology.rutas.cuentas import CuentaNueva,_validar_rol_y_funcion,_a_usuario
from geology.dominio.estados import Rol

CORREO='admin.local.8c@example.invalid'
NOMBRE='Administración sintética local 8C'


def crear(datos):
    if os.environ.get('GEOLOGY_LOCAL_PROJECT')!='geology-local-20261106-57a99a' or motor.url.host!='almacen_datos' or motor.url.database!='geology':
        raise RuntimeError('Destino local no autorizado.')
    if os.environ.get('GEOLOGY_ENTORNO','').lower() not in ('local','desarrollo','test'):
        raise RuntimeError('Entorno no autorizado.')
    registrar_modelos()
    if len(inspect(motor).get_table_names(schema='public'))!=27:raise RuntimeError('Esquema no validado.')
    clave=datos.get('clave','')
    if not isinstance(clave,str) or len(clave)<32:raise ValueError('Credencial de bootstrap inválida.')
    cuenta=CuentaNueva(nombre=NOMBRE,correo=CORREO,rol=Rol.ADMINISTRADORA.value,funcion='Ambas',clave=clave)
    rol,funcion=_validar_rol_y_funcion(cuenta.rol,cuenta.funcion)
    with SesionLocal.begin() as s:
        if s.query(UsuarioBD).count()!=0:raise RuntimeError('Bootstrap rechazado: ya hay cuentas.')
        u=UsuarioBD(nombre=cuenta.nombre,correo=cuenta.correo,cargo='Desarrollo sintético',rol=rol,
            funcion=funcion,clave_hash=cifrar_clave(clave),debe_cambiar_clave=True,activo=True,
            intentos_fallidos=0,ve_hojas_control=True,ve_isadg=True,ve_fuid=True,ve_imagenes=False,
            sin_limites=False,aprueba_lo_propio=False)
        s.add(u);s.flush()
        assert clave_correcta(clave,u.clave_hash) and _a_usuario(u).rol is Rol.ADMINISTRADORA
        salida={'created':True,'id':u.id,'correo':u.correo,'rol':u.rol,'debe_cambiar_clave':u.debe_cambiar_clave}
    return salida


if __name__=='__main__':
    try:
        print(json.dumps(crear(json.load(sys.stdin)),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'created':False,'error_type':type(exc).__name__}))
        sys.exit(1)
