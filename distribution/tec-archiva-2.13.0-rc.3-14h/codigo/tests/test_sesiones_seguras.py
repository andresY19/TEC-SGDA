"""Autenticación real con cuentas sintéticas; sin servidor, red, DB ni DDL."""
import ast
import base64
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import secrets
import unittest
from unittest.mock import patch, Mock


ROOT = Path(__file__).resolve().parents[1]


class SesionesSeguras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = contextlib.ExitStack()
        cls.key = secrets.token_urlsafe(32)
        cls.stack.enter_context(patch.dict(os.environ, {
            'GEOLOGY_CLAVE':cls.key,'GEOLOGY_HORAS_SESION':'8',
            'DATABASE_URL':'postgresql+psycopg2://synthetic:synthetic@db.invalid:5432/synthetic'},clear=True))
        cls.guards = [cls.stack.enter_context(patch(name,side_effect=AssertionError('Efecto prohibido')))
            for name in ('socket.socket.connect','socket.create_connection','psycopg2.connect',
                'sqlalchemy.engine.Engine.connect','sqlalchemy.sql.schema.MetaData.create_all',
                'celery.app.task.Task.apply_async','celery.app.task.Task.apply','kombu.Connection.connect')]
        cls.pases = importlib.import_module('geology.nucleo.pases')
        cls.cuentas = importlib.import_module('geology.rutas.cuentas')
        from starlette.requests import Request
        cls.Request = Request
        from geology.modelos import UsuarioBD
        cls.UsuarioBD = UsuarioBD

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def setUp(self):
        # Mock only the storage boundary; signature/expiry and route rules remain real.
        records = {}; generations = {}
        def register(token, credential):
            claims = self.pases.detalles_pase(token)
            records[claims['jti']] = (credential, generations.get(claims['sub'], 0))
        def validate(token, credential):
            claims = self.pases.detalles_pase(token)
            return bool(claims and records.get(claims['jti']) == (credential, generations.get(claims['sub'], 0)))
        def invalidate(correo): generations[correo] = generations.get(correo, 0) + 1
        def revoke(token): records.pop(self.pases.detalles_pase(token)['jti'], None)
        for name, fn in [('registrar',register),('validar',validate),('invalidar_usuario',invalidate),('revocar',revoke)]:
            patcher = patch.object(self.cuentas.sesiones, name, side_effect=fn)
            patcher.start();self.addCleanup(patcher.stop)

    def cuenta(self, provisional=False, activo=True, rol='equipo'):
        return self.UsuarioBD(nombre='Persona sintética',correo='persona@example.invalid',
            cargo=None,rol=rol,funcion='Ambas',clave_hash='synthetic',activo=activo,
            debe_cambiar_clave=provisional,intentos_fallidos=0)

    def db(self, cuenta):
        db = Mock()
        q = db.query.return_value.filter.return_value
        q.populate_existing.return_value = q
        q.with_for_update.return_value = q
        # Comprueba que el consumidor filtra la actividad y correo al autenticar.
        def filter_(*condiciones):
            texto=' '.join(str(c) for c in condiciones)
            if 'cuenta.activo IS true' in texto:
                db.query.return_value.filter.return_value.first.return_value = cuenta if cuenta and cuenta.activo else None
            else:
                db.query.return_value.filter.return_value.first.return_value = cuenta
            return db.query.return_value.filter.return_value
        db.query.return_value.filter.side_effect=filter_
        return db

    def autenticar(self, cuenta, ruta='/cuentas', metodo='GET', token=None):
        request=self.Request({'type':'http','method':metodo,'path':ruta,'headers':[],
            'scheme':'http','server':('test.invalid',80),'query_string':b''})
        if token is None:
            token = self.pases.crear_pase('persona@example.invalid')
            if cuenta: self.cuentas.sesiones.registrar(token, cuenta.clave_hash)
        return self.cuentas.usuario_actual(request, 'Bearer '+token,self.db(cuenta))

    def rechaza(self, cuenta, ruta='/cuentas', metodo='GET', status=403):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            self.autenticar(cuenta,ruta,metodo)
        self.assertEqual(error.exception.status_code,status)

    def token(self, instante=1000):
        with patch.object(self.pases.time,'time',return_value=instante):
            return self.pases.crear_pase('persona@example.invalid')

    def test_01_emision_y_lectura(self):
        token=self.pases.crear_pase(' Persona@EXAMPLE.INVALID ')
        self.assertEqual(self.pases.leer_pase(token),'persona@example.invalid')
        self.assertTrue(token.startswith('g1.'))

    def test_02_expiracion_exacta(self):
        token=self.token()
        with patch.object(self.pases.time,'time',return_value=1000+8*3600-1):
            self.assertIsNotNone(self.pases.leer_pase(token))
        with patch.object(self.pases.time,'time',return_value=1000+8*3600):
            self.assertIsNone(self.pases.leer_pase(token))

    def test_03_emision_futura(self):
        token=self.token(2000)
        with patch.object(self.pases.time,'time',return_value=1000):
            self.assertIsNone(self.pases.leer_pase(token))

    def test_04_firma_manipulada(self):
        token=self.pases.crear_pase('persona@example.invalid')
        a,b,c=token.split('.')
        self.assertIsNone(self.pases.leer_pase('.'.join((a,b,('A' if c[0]!='A' else 'B')+c[1:]))))

    def test_05_identidad_manipulada(self):
        token=self.pases.crear_pase('persona@example.invalid')
        a,b,c=token.split('.')
        datos=json.loads(base64.urlsafe_b64decode(b+'='*(-len(b)%4)))
        datos['sub']='otro@example.invalid'
        self.assertIsNone(self.pases.leer_pase(a+'.'+self.pases._b64(json.dumps(datos).encode())+'.'+c))

    def test_06_clave_ausente(self):
        token=self.pases.crear_pase('persona@example.invalid')
        with patch.dict(os.environ,{'GEOLOGY_CLAVE':''}):
            self.assertFalse(self.pases.llave_configurada())
            self.assertIsNone(self.pases.leer_pase(token))
            with self.assertRaises(RuntimeError): self.pases.crear_pase('persona@example.invalid')

    def test_07_clave_corta(self):
        with patch.dict(os.environ,{'GEOLOGY_CLAVE':'corta'}):
            self.assertFalse(self.pases.llave_configurada())

    def test_08_rotacion_invalida_tokens(self):
        token=self.pases.crear_pase('persona@example.invalid')
        with patch.dict(os.environ,{'GEOLOGY_CLAVE':secrets.token_urlsafe(32)}):
            self.assertIsNone(self.pases.leer_pase(token))

    def test_09_formatos_invalidos(self):
        for token in (None,123,{},'', 'abc','a.b.c.d','g1.@@@.x','g1.a.===','x'*2049,'eyJhbGciOiJub25lIn0.e30.'):
            with self.subTest(tipo=type(token).__name__): self.assertIsNone(self.pases.leer_pase(token))

    def test_10_comparacion_segura(self):
        token=self.pases.crear_pase('persona@example.invalid')
        with patch.object(self.pases.hmac,'compare_digest',wraps=self.pases.hmac.compare_digest) as comparar:
            self.assertIsNotNone(self.pases.leer_pase(token))
        comparar.assert_called_once()

    def test_11_tokens_distintos(self):
        self.assertNotEqual(self.token(),self.token())

    def test_12_identidades_invalidas(self):
        for correo in ('sin-arroba','@dominio','x@','a b@c','a@@c','a'*151+'@b'):
            with self.subTest(correo=correo), self.assertRaises(ValueError): self.pases.crear_pase(correo)

    def test_13_horas_invalidas(self):
        for valor in ('0','25','1.5','inf','secreto'):
            with patch.dict(os.environ,{'GEOLOGY_HORAS_SESION':valor}), self.assertRaises(RuntimeError) as error:
                self.pases._horas()
            self.assertNotIn(valor,str(error.exception)) if valor=='secreto' else None

    def test_14_cuenta_inactiva(self):
        self.rechaza(self.cuenta(activo=False),status=401)

    def test_15_cuenta_inexistente(self):
        self.rechaza(None,status=401)

    def test_16_provisional_bloquea_roles_incluso_admin(self):
        from geology.dominio.estados import Rol
        for rol in Rol:
            self.rechaza(self.cuenta(provisional=True,rol=rol.value))

    def test_17_provisional_permite_identidad(self):
        self.assertEqual(self.autenticar(self.cuenta(provisional=True),'/cuentas/yo').correo,'persona@example.invalid')

    def test_18_provisional_permite_cambio(self):
        self.assertIsNotNone(self.autenticar(self.cuenta(provisional=True),'/cuentas/cambiar-clave','POST'))

    def test_19_sufijos_no_evaden(self):
        for ruta in ('/cuentas/yo/extra','/cuentas/yo-mal','/cuentas/cambiar-clave/extra','/cuentas/yo/'):
            self.rechaza(self.cuenta(provisional=True),ruta)

    def test_20_metodos_no_evaden(self):
        for ruta,metodo in (('/cuentas/yo','POST'),('/cuentas/cambiar-clave','GET'),('/cuentas/yo','HEAD')):
            self.rechaza(self.cuenta(provisional=True),ruta,metodo)

    def test_21_acceso_directo_api(self):
        for ruta in ('/unidades','/consulta','/cargue','/ubicacion','/cuentas/crear','/cuentas/alguien/restablecer'):
            self.rechaza(self.cuenta(provisional=True),ruta,'POST')

    def test_22_cambio_real_desbloquea(self):
        u=self.cuenta(provisional=True)
        u.clave_hash=self.cuentas.cifrar_clave('Inicial-Sintetica-1')
        db=self.db(u)
        quien=self.autenticar(u,'/cuentas/cambiar-clave','POST')
        self.cuentas.cambiar_clave(self.cuentas.CambioDeClave(clave_actual='Inicial-Sintetica-1',clave_nueva='Nueva-Sintetica-2'),db,quien)
        db.commit.assert_called_once()
        self.assertFalse(u.debe_cambiar_clave)
        self.assertTrue(self.cuentas.clave_correcta('Nueva-Sintetica-2',u.clave_hash))
        self.assertFalse(self.cuentas.clave_correcta('Inicial-Sintetica-1',u.clave_hash))
        self.assertIsNotNone(self.autenticar(u))

    def test_23_cambio_incorrecto_no_desbloquea(self):
        from fastapi import HTTPException
        u=self.cuenta(provisional=True); db=self.db(u)
        with self.assertRaises(HTTPException):
            self.cuentas.cambiar_clave(self.cuentas.CambioDeClave(clave_actual='Errada-1',clave_nueva='Nueva-Sintetica-2'),db,self.autenticar(u,'/cuentas/cambiar-clave','POST'))
        self.assertTrue(u.debe_cambiar_clave)
        db.commit.assert_not_called()

    def test_24_permisos_entidad_conservados(self):
        self.rechaza(self.cuenta(rol='entidad'),'/unidades')
        self.assertTrue(self.autenticar(self.cuenta(rol='entidad'),'/consulta').es_entidad)

    def test_25_permisos_admin_conservados(self):
        from geology.dominio.estados import Rol
        admin=self.autenticar(self.cuenta(rol=Rol.ADMINISTRADORA.value))
        self.cuentas._solo_direccion(admin)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): self.cuentas._solo_direccion(self.autenticar(self.cuenta()))

    def test_26_bearer_obligatorio(self):
        from fastapi import HTTPException
        req=self.Request({'type':'http','method':'GET','path':'/cuentas/yo','headers':[]})
        for header in ('','Basic xxx','Bearer basura'):
            with self.assertRaises(HTTPException) as error: self.cuentas.usuario_actual(req,header,self.db(self.cuenta()))
            self.assertEqual(error.exception.status_code,401)

    def test_27_ingreso_sin_clave_no_escribe(self):
        from fastapi import HTTPException
        db=self.db(self.cuenta())
        with patch.dict(os.environ,{'GEOLOGY_CLAVE':''}), self.assertRaises(HTTPException) as error:
            self.cuentas.ingresar(self.cuentas.Ingreso(correo='persona@example.invalid',clave='Sintetica'),db)
        self.assertEqual(error.exception.status_code,503)
        db.commit.assert_not_called(); db.query.assert_not_called()

    def test_28_no_filtracion_en_salida(self):
        salida=io.StringIO()
        token=self.pases.crear_pase('persona@example.invalid')
        with contextlib.redirect_stdout(salida),contextlib.redirect_stderr(salida):
            self.pases.leer_pase(token+'x')
            with patch.dict(os.environ,{'GEOLOGY_CLAVE':''}), self.assertRaises(RuntimeError) as error:
                self.pases.crear_pase('persona@example.invalid')
        self.assertEqual(salida.getvalue(),'')
        self.assertNotIn(self.key,str(error.exception)); self.assertNotIn(token,str(error.exception))

    def test_29_todas_rutas_protegidas_usan_dependencia(self):
        sin_control=[]; total=0
        for p in (ROOT/'geology/rutas').glob('*.py'):
            tree = ast.parse(p.read_text(encoding='utf-8-sig'))
            guards = {'usuario_actual'}
            if p.name == 'offline_sync.py':
                offline_guard = next(fn for fn in tree.body
                                     if isinstance(fn, ast.FunctionDef) and fn.name == 'authorized')
                self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                    and n.func.id == 'Depends' and n.args
                                    and isinstance(n.args[0], ast.Name) and n.args[0].id == 'usuario_actual'
                                    for n in ast.walk(offline_guard.args)))
                guards.add('authorized')
            for fn in tree.body:
                if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
                if not any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Name)
                           and d.func.value.id=='router' for d in fn.decorator_list): continue
                total+=1
                if not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='Depends'
                    and n.args and isinstance(n.args[0],ast.Name) and n.args[0].id in guards for n in ast.walk(fn.args)):
                    sin_control.append((p.name,fn.name))
        self.assertGreater(total,100)
        self.assertEqual(sin_control,[('cuentas.py','ingresar')])

    def test_30_sin_efectos(self):
        for g in self.guards: g.assert_not_called()

    def test_31_payloads_firmados_invalidos(self):
        import hashlib, hmac
        with patch.object(self.pases.time,'time',return_value=1000):
            datos=json.loads(self.pases._decodificar(self.token().split('.')[1]))
            variantes=[{k:v for k,v in datos.items() if k!='exp'},
                dict(datos,exp=999),dict(datos,iat=True),dict(datos,exp='3000'),
                dict(datos,exp=1000+25*3600),dict(datos,jti=''),dict(datos,sub='sin-correo'),
                dict(datos,adicional=True),[],None]
            for variante in variantes:
                cuerpo=self.pases._b64(json.dumps(variante,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('ascii'))
                mensaje='g1.'+cuerpo
                firma=self.pases._b64(hmac.digest(self.key.encode(),self.pases._PROPOSITO+mensaje.encode(),hashlib.sha256))
                self.assertIsNone(self.pases.leer_pase(mensaje+'.'+firma))

    def test_32_version_y_base64_no_canonico(self):
        token=self.pases.crear_pase('persona@example.invalid')
        self.assertIsNone(self.pases.leer_pase(token.replace('g1.','g2.',1)))
        a,b,c=token.split('.')
        self.assertIsNone(self.pases.leer_pase(a+'.'+b+'.'+c+'='))

    def test_33_ingreso_provisional_no_concede_operaciones(self):
        u=self.cuenta(provisional=True)
        u.clave_hash=self.cuentas.cifrar_clave('Inicial-Sintetica-1')
        db=self.db(u)
        respuesta=self.cuentas.ingresar(self.cuentas.Ingreso(correo=u.correo,clave='Inicial-Sintetica-1'),db)
        self.assertTrue(respuesta['usuario']['debe_cambiar_clave'])
        self.assertEqual(self.pases.leer_pase(respuesta['pase']),u.correo)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error: self.autenticar(u,token=respuesta['pase'])
        self.assertEqual(error.exception.status_code,403)

    def test_34_desactivacion_revoca_acceso_con_token_valido(self):
        u=self.cuenta(); token=self.pases.crear_pase(u.correo)
        self.cuentas.sesiones.registrar(token,u.clave_hash)
        self.assertIsNotNone(self.autenticar(u,token=token))
        u.activo=False
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): self.autenticar(u,token=token)

    def test_35_nueva_clave_igual_no_desbloquea(self):
        from fastapi import HTTPException
        u=self.cuenta(provisional=True); u.clave_hash=self.cuentas.cifrar_clave('Inicial-Sintetica-1')
        db=self.db(u)
        with self.assertRaises(HTTPException) as error:
            self.cuentas.cambiar_clave(self.cuentas.CambioDeClave(clave_actual='Inicial-Sintetica-1',clave_nueva='Inicial-Sintetica-1'),db,self.autenticar(u,'/cuentas/cambiar-clave','POST'))
        self.assertEqual(error.exception.status_code,422)
        self.assertTrue(u.debe_cambiar_clave); db.commit.assert_not_called()


if __name__=='__main__': unittest.main()
