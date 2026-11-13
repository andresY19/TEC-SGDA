"""Real HTTP security scenarios. Tokens/passwords stay in process memory only."""
from pathlib import Path
import hashlib
import json
import os
import secrets
import time
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch

from sqlalchemy import text
from geology.nucleo.bd import SesionLocal, motor
from geology.modelos import UsuarioBD, cifrar_clave
from geology.nucleo import pases, sesiones

assert os.environ['GEOLOGY_LOCAL_PROJECT'].startswith('geology-auto11e-')
ROOT=Path('/cert/auth')


def control(operation):
    directory=Path('/cert/auth-control');directory.mkdir(mode=0o770,exist_ok=True)
    ident=uuid.uuid4().hex
    with (directory/(ident+'.request.json')).open('x') as f:json.dump({'operation':operation,'id':ident},f)
    answer=directory/(ident+'.answer.json')
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if answer.exists():
            result=json.loads(answer.read_text())
            if result.get('status')!='ok':raise AssertionError('Isolated control operation failed: '+operation)
            return result
        time.sleep(.2)
    raise AssertionError('Isolated control timeout: '+operation)


class SessionHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ROOT.mkdir(mode=0o770,exist_ok=False)
        cls.passwords={name:secrets.token_urlsafe(28) for name in ['admin','alice','entity','provisional','logout_provisional','clock','binding']}
        cls.tokens={};cls.events=[];cls.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with SesionLocal() as db:
            for name,password in cls.passwords.items():
                assert not db.query(UsuarioBD).filter(UsuarioBD.correo==name+'11b@example.invalid').first()
                row=UsuarioBD(nombre='SINTETICO SESIONES '+name,correo=name+'11b@example.invalid',
                    rol='administradora' if name=='admin' else ('entidad' if name=='entity' else 'equipo'),
                    funcion='Ambas',activo=True,debe_cambiar_clave=name in ['provisional','logout_provisional'],
                    intentos_fallidos=0,clave_hash=cifrar_clave(password))
                db.add(row)
            db.commit()

    def request(self,method,path,token=None,data=None,expected=200):
        headers={};payload=None
        if token:headers['Authorization']='Bearer '+token
        if data is not None:
            payload=json.dumps(data).encode();headers['Content-Type']='application/json'
        assert 'g1.' not in path and 'Bearer' not in path
        req=urllib.request.Request('http://web:8080'+path,data=payload,headers=headers,method=method)
        try:
            with self.opener.open(req,timeout=20) as response:status=response.status;body=response.read()
        except urllib.error.HTTPError as exc:status=exc.code;body=exc.read()
        self.events.append({'method':method,'path':path,'status':status,'expected':expected})
        self.assertEqual(status,expected,method+' '+path+' unexpected status')
        try:return json.loads(body)
        except ValueError:return {}

    def login(self,name,expected=200,password=None):
        result=self.request('POST','/cuentas/ingresar',data={'correo':name+'11b@example.invalid',
            'clave':password or self.passwords[name]},expected=expected)
        return result.get('pase')

    def identity(self,token,status=200):return self.request('GET','/cuentas/yo',token,expected=status)

    def test_01_login_and_identity(self):
        self.tokens['admin']=self.login('admin');self.tokens['a1']=self.login('alice')
        self.assertEqual(self.identity(self.tokens['a1'])['rol'],'equipo')

    def test_02_wrong_credentials(self):
        self.login('alice',401,password=secrets.token_urlsafe(28))

    def test_03_concurrent_sessions(self):
        self.tokens['a2']=self.login('alice');self.tokens['a3']=self.login('alice')
        for key in ['a1','a2','a3']:self.identity(self.tokens[key])

    def test_04_password_change_returns_new_session(self):
        new=secrets.token_urlsafe(28)
        response=self.request('POST','/cuentas/cambiar-clave',self.tokens['a1'],
            {'clave_actual':self.passwords['alice'],'clave_nueva':new})
        self.passwords['alice']=new;self.tokens['anew']=response['pase'];self.identity(self.tokens['anew'])

    def test_05_all_prior_password_sessions_rejected(self):
        for key in ['a1','a2','a3']:self.identity(self.tokens[key],401)

    def test_06_logout_revokes_current_session(self):
        self.request('POST','/cuentas/salir',self.tokens['anew']);self.identity(self.tokens['anew'],401)

    def test_07_revoked_token_cannot_be_reused(self):
        self.request('POST','/cuentas/salir',self.tokens['anew'],expected=401)
        self.request('GET','/cuentas',self.tokens['anew'],expected=401)

    def test_08_account_disable_revokes(self):
        self.tokens['disabled']=self.login('alice')
        self.request('PUT','/cuentas/alice11b@example.invalid',self.tokens['admin'],{'activo':False})
        self.identity(self.tokens['disabled'],401);self.login('alice',401)

    def test_09_reactivation_does_not_revive_old_session(self):
        self.request('PUT','/cuentas/alice11b@example.invalid',self.tokens['admin'],{'activo':True})
        self.identity(self.tokens['disabled'],401);self.tokens['alive']=self.login('alice');self.identity(self.tokens['alive'])

    def test_10_roles_and_administrative_routes(self):
        entity=self.login('entity');self.identity(entity)
        self.request('GET','/cuentas',entity,expected=403)
        self.request('GET','/unidades',entity,expected=403)
        self.request('GET','/cuentas',self.tokens['alive'],expected=403)
        self.request('GET','/cuentas',self.tokens['admin'])
        self.request('PUT','/cuentas/admin11b@example.invalid',self.tokens['admin'],{'activo':False},409)

    def test_11_provisional_password_still_required(self):
        token=self.login('provisional');self.assertTrue(self.identity(token)['debe_cambiar_clave'])
        self.request('GET','/cuentas',token,expected=403)
        new=secrets.token_urlsafe(28)
        response=self.request('POST','/cuentas/cambiar-clave',token,
            {'clave_actual':self.passwords['provisional'],'clave_nueva':new})
        self.passwords['provisional']=new;self.identity(token,401)
        self.assertFalse(self.identity(response['pase'])['debe_cambiar_clave'])

    def test_12_provisional_session_can_logout(self):
        token=self.login('logout_provisional');self.request('POST','/cuentas/salir',token);self.identity(token,401)

    def test_13_expired_signed_registered_token(self):
        with SesionLocal() as db:
            user=db.query(UsuarioBD).filter(UsuarioBD.correo=='clock11b@example.invalid').one()
            credential=user.clave_hash
        with patch.object(pases.time,'time',return_value=int(time.time())-9*3600):
            token=pases.crear_pase('clock11b@example.invalid');sesiones.registrar(token,credential)
        self.identity(token,401)

    def test_14_malformed_and_tampered_tokens(self):
        for token in ['invalid','g1.bad.bad',self.tokens['alive']+'x']:self.identity(token,401)

    def test_15_unregistered_legacy_token_denied(self):
        token=pases.crear_pase('alice11b@example.invalid')
        self.assertIsNotNone(pases.leer_pase(token));self.identity(token,401)

    def test_16_credential_binding_defends_external_password_update(self):
        token=self.login('binding');new=secrets.token_urlsafe(28)
        with SesionLocal() as db:
            user=db.query(UsuarioBD).filter(UsuarioBD.correo=='binding11b@example.invalid').one()
            user.clave_hash=cifrar_clave(new);db.commit()
        self.passwords['binding']=new;self.identity(token,401)
        self.tokens['binding']=self.login('binding')

    def test_17_administrative_reset_revokes(self):
        result=self.request('POST','/cuentas/binding11b@example.invalid/restablecer',self.tokens['admin'])
        self.identity(self.tokens['binding'],401);self.passwords['binding']=result['clave_provisional']
        token=self.login('binding');self.assertTrue(self.identity(token)['debe_cambiar_clave'])

    def test_18_redis_outage_fails_closed_then_recovers(self):
        with SesionLocal() as db:
            before=db.query(UsuarioBD).filter(UsuarioBD.correo=='alice11b@example.invalid').one().clave_hash
        control('stop_redis')
        self.identity(self.tokens['alive'],503)
        self.request('POST','/cuentas/salir',self.tokens['alive'],expected=503)
        self.login('alice',503)
        self.request('PUT','/cuentas/alice11b@example.invalid',self.tokens['admin'],{'activo':False},503)
        self.identity('invalid',401)
        with SesionLocal() as db:
            user=db.query(UsuarioBD).filter(UsuarioBD.correo=='alice11b@example.invalid').one()
            self.assertTrue(user.clave_hash==before);self.assertTrue(user.activo)
        control('start_redis');self.identity(self.tokens['alive']);self.identity(self.tokens['anew'],401)

    def test_19_application_restarts_preserve_revocation(self):
        control('restart_apps');self.identity(self.tokens['alive']);self.identity(self.tokens['admin'])
        for key in ['a1','anew','disabled']:self.identity(self.tokens[key],401)

    def test_20_logout_keeps_other_sessions_active(self):
        another=self.login('alice');self.request('POST','/cuentas/salir',another)
        self.identity(another,401);self.identity(self.tokens['alive'])

    def test_21_registry_contains_no_raw_secrets(self):
        import redis
        client=redis.Redis.from_url(os.environ['AUTH_REDIS_URL'],decode_responses=True)
        keys=list(client.scan_iter());self.assertTrue(keys)
        for key in keys:
            self.assertTrue(key.startswith(os.environ['GEOLOGY_LOCAL_PROJECT']+':auth:v1:'))
            self.assertNotIn('@',key);value=client.get(key)
            self.assertNotIn('g1.',value);self.assertNotIn('240000$',value);self.assertNotIn('@',value)
            if ':s:' in key:self.assertGreater(client.ttl(key),0)

    def test_22_logs_and_urls_do_not_expose_tokens(self):
        result=control('audit_logs');self.assertEqual(result['token_matches'],0)
        self.assertTrue(all('g1.' not in event['path'] for event in self.events))

    @classmethod
    def tearDownClass(cls):
        with (ROOT/'http-results.json').open('x') as f:
            json.dump({'events':cls.events,'accounts_created':7,'passwords_or_tokens_persisted_in_evidence':False,
                'contract':'g1 signature/expiry plus mandatory durable registry; old unregistered tokens require login',
                'schema_migration_executed':False},f,indent=2)
        cls.passwords.clear();cls.tokens.clear()


if __name__=='__main__':unittest.main(verbosity=2)
