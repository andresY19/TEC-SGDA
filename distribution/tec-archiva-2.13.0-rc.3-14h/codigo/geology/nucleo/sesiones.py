"""Registro revocable, de aceptación explícita y persistencia confirmada en Redis.

Sin DDL ni conexiones al importar. Una caída o pérdida del registro deniega acceso.
Sólo se almacenan identificadores HMAC, generaciones aleatorias y vínculos HMAC
a la huella de contraseña; nunca pases, contraseñas ni huellas PBKDF2 completas.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

import redis
from geology.nucleo import pases


class SesionesNoDisponibles(RuntimeError):
    def __init__(self):
        super().__init__('El registro de sesiones no está disponible; no se autorizó la operación.')


def _cliente():
    try:
        project=os.environ.get('GEOLOGY_LOCAL_PROJECT','')
        url=os.environ.get('AUTH_REDIS_URL','');u=urlsplit(url)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',project):raise ValueError()
        if u.scheme not in ('redis','rediss') or not u.hostname or (not re.fullmatch(r'/[0-9]+',u.path) or int(u.path[1:])<2):raise ValueError()
        if u.query or u.fragment:raise ValueError()
        return redis.Redis.from_url(url,decode_responses=True,socket_timeout=4,
                                    socket_connect_timeout=2,retry_on_timeout=False),project+':auth:v1:'
    except Exception:
        raise SesionesNoDisponibles() from None


def _digest(kind,value):
    return hmac.digest(pases._llave(),('geology-auth-v1:'+kind+':'+value).encode(),hashlib.sha256).hex()


def _keys(prefix,claims):
    return prefix+'u:'+_digest('user',claims['sub']),prefix+'s:'+_digest('session',claims['jti'])


def _durable(client,script,keys,args):
    try:
        # Same Redis connection: WAITAOF must cover the preceding mutation.
        with client.pipeline(transaction=False) as pipeline:
            pipeline.eval(script,len(keys),*keys,*args)
            pipeline.execute_command('WAITAOF',1,0,2000)
            result,ack=pipeline.execute()
        if not isinstance(ack,list) or ack[0]<1:raise ValueError()
        return result
    except Exception:
        raise SesionesNoDisponibles() from None
    finally:
        client.close()


REGISTER="""
local generation=redis.call('GET',KEYS[1])
if not generation then generation=ARGV[1];redis.call('SET',KEYS[1],generation) end
local data=cjson.encode({g=generation,c=ARGV[2]})
return redis.call('SET',KEYS[2],data,'EX',ARGV[3],'NX')
"""
CHECK="""
local data=redis.call('GET',KEYS[2])
local generation=redis.call('GET',KEYS[1])
if not data or not generation then return false end
local parsed=cjson.decode(data)
if parsed.g~=generation then return false end
return data
"""


def registrar(pase,clave_hash):
    claims=pases.detalles_pase(pase)
    if not claims:raise ValueError('Pase inválido; no se registró sesión.')
    client,prefix=_cliente();keys=_keys(prefix,claims)
    ttl=claims['exp']-int(time.time())
    if ttl<=0:raise ValueError('Pase vencido; no se registró sesión.')
    result=_durable(client,REGISTER,keys,[secrets.token_hex(16),_digest('credential',clave_hash),ttl])
    if result!='OK':raise SesionesNoDisponibles()


def validar(pase,clave_hash):
    claims=pases.detalles_pase(pase)
    if not claims:return False
    client=None
    try:
        client,prefix=_cliente();raw=client.eval(CHECK,2,*_keys(prefix,claims))
        if raw is None:return False
        data=json.loads(raw)
        return isinstance(data,dict) and isinstance(data.get('c'),str) and hmac.compare_digest(data['c'],_digest('credential',clave_hash))
    except SesionesNoDisponibles:raise
    except Exception:
        raise SesionesNoDisponibles() from None
    finally:
        if client is not None:client.close()


def invalidar_usuario(correo):
    client,prefix=_cliente()
    _durable(client,"return redis.call('SET',KEYS[1],ARGV[1])",
             [prefix+'u:'+_digest('user',correo)],[secrets.token_hex(16)])


def revocar(pase):
    claims=pases.detalles_pase(pase)
    if not claims:return
    client,prefix=_cliente();_,key=_keys(prefix,claims)
    _durable(client,"return redis.call('DEL',KEYS[1])",[key],[])
