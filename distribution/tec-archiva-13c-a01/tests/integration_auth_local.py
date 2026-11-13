"""HTTP real: única cuenta sintética 8C. Secretos solo por stdin y memoria.

Ejecutar una vez durante el cambio inicial; no es una prueba destructiva ni un
bootstrap repetible. No genera cuentas adicionales ni escribe documentos.
"""
import json,sys,os,unittest,urllib.request,urllib.error
from geology.nucleo.bd import SesionLocal,motor
from geology.modelos import UsuarioBD
from geology.dominio.estados import Rol
from geology.rutas.cuentas import _validar_rol_y_funcion

DATOS=None
CORREO='admin.local.8c@example.invalid'


class AutenticacionLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DATOS is None:raise unittest.SkipTest('Requiere secretos efímeros por stdin y autorización local')
        assert os.environ.get('GEOLOGY_LOCAL_PROJECT')=='geology-local-20261106-57a99a'
        assert motor.url.host=='almacen_datos' and DATOS['correo']==CORREO
        cls.temporal=DATOS['temporal'];cls.nueva=DATOS['nueva'];cls.id=DATOS['id'];cls.token=''

    def api(self,path,method='GET',body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request('http://127.0.0.1:8080'+path,data=data,headers=headers,method=method)
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8) as r:
                return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)

    def login(self,clave):return self.api('/cuentas/ingresar','POST',{'correo':CORREO,'clave':clave})

    def estado_fixture(self,**cambios):
        if 'rol' in cambios:_validar_rol_y_funcion(cambios['rol'],'Ambas')
        with SesionLocal.begin() as s:
            assert s.query(UsuarioBD).count()==1
            u=s.get(UsuarioBD,self.id)
            assert u.correo==CORREO and u.nombre=='Administración sintética local 8C'
            for k,v in cambios.items():
                assert k in ('rol','activo');setattr(u,k,v)

    def test_01_clave_incorrecta(self):self.assertEqual(self.login('Incorrecta-sintética-sin-valor')[0],401)

    def test_02_ingreso_valido_provisional(self):
        status,r=self.login(self.temporal);self.assertEqual(status,200)
        type(self).token=r['pase'];self.assertTrue(r['usuario']['debe_cambiar_clave'])

    def test_03_token_manipulado(self):
        partes=self.token.split('.');partes[-1]=('A' if partes[-1][0]!='A' else 'B')+partes[-1][1:]
        self.assertEqual(self.api('/cuentas/yo',token='.'.join(partes))[0],401)

    def test_04_identidad_autenticada(self):
        status,r=self.api('/cuentas/yo',token=self.token);self.assertEqual(status,200)
        self.assertEqual(r['correo'],CORREO);self.assertTrue(r['debe_cambiar_clave'])

    def test_05_bloqueo_provisional(self):
        for path in ('/cuentas','/unidades/resumen'):
            self.assertEqual(self.api(path,token=self.token)[0],403)

    def test_06_cambio_invalido_no_desbloquea(self):
        self.assertEqual(self.api('/cuentas/cambiar-clave','POST',{'clave_actual':self.temporal,'clave_nueva':'corta'},self.token)[0],422)
        self.assertTrue(self.api('/cuentas/yo',token=self.token)[1]['debe_cambiar_clave'])

    def test_07_cambio_exige_clave_actual_y_distinta(self):
        self.assertEqual(self.api('/cuentas/cambiar-clave','POST',{'clave_actual':'Errada-sintética','clave_nueva':self.nueva},self.token)[0],401)
        self.assertEqual(self.api('/cuentas/cambiar-clave','POST',{'clave_actual':self.temporal,'clave_nueva':self.temporal},self.token)[0],422)

    def test_08_cambio_real(self):
        self.assertEqual(self.api('/cuentas/cambiar-clave','POST',{'clave_actual':self.temporal,'clave_nueva':self.nueva},self.token)[0],200)
        self.assertFalse(self.api('/cuentas/yo',token=self.token)[1]['debe_cambiar_clave'])
        self.assertEqual(self.login(self.temporal)[0],401)

    def test_09_acceso_administrativo(self):
        status,r=self.login(self.nueva);self.assertEqual(status,200)
        type(self).token_nuevo=r['pase']
        status,cuentas=self.api('/cuentas',token=self.token_nuevo)
        self.assertEqual(status,200);self.assertEqual(len(cuentas),1)
        self.assertEqual(cuentas[0]['rol'],Rol.ADMINISTRADORA.value)

    def test_10_cuenta_inactiva(self):
        self.estado_fixture(activo=False)
        try:
            self.assertEqual(self.api('/cuentas/yo',token=self.token_nuevo)[0],403)
            self.assertEqual(self.login(self.nueva)[0],401)
        finally:self.estado_fixture(activo=True)

    def test_11_otros_perfiles_no_administran(self):
        for rol in (Rol.EQUIPO,Rol.CONSULTA,Rol.LIDER,Rol.ENTIDAD):
            self.estado_fixture(rol=rol.value)
            try:
                self.assertEqual(self.api('/cuentas',token=self.token_nuevo)[0],403)
                cuerpo={'nombre':'No debe crearse','correo':'never-created@example.invalid','rol':'equipo','funcion':'Ambas'}
                self.assertEqual(self.api('/cuentas/crear','POST',cuerpo,self.token_nuevo)[0],403)
                if rol is Rol.ENTIDAD:
                    self.assertEqual(self.api('/unidades/resumen',token=self.token_nuevo)[0],403)
                    self.assertEqual(self.api('/consulta/yo',token=self.token_nuevo)[0],200)
            finally:self.estado_fixture(rol=Rol.ADMINISTRADORA.value)

    def test_12_admin_no_se_desactiva_ni_degrada(self):
        for cuerpo in ({'activo':False},{'rol':'equipo'}):
            self.assertEqual(self.api('/cuentas/'+CORREO,'PUT',cuerpo,self.token_nuevo)[0],409)

    def test_13_limite_revocacion_confirmado(self):
        # Comportamiento actual documentado, no se introduce un protocolo de token nuevo.
        self.assertEqual(self.api('/cuentas/yo',token=self.token)[0],200)

    def test_14_una_cuenta_y_estado_final(self):
        with SesionLocal() as s:
            self.assertEqual(s.query(UsuarioBD).count(),1)
            u=s.get(UsuarioBD,self.id)
            self.assertTrue(u.activo);self.assertFalse(u.debe_cambiar_clave)
            self.assertEqual(u.rol,Rol.ADMINISTRADORA.value)
        self.assertEqual(self.login(self.nueva)[0],200)


if __name__=='__main__':
    DATOS=json.load(sys.stdin)
    unittest.main()
