"""Installation policy. The distributed development build is loopback-only."""
import ctypes
import re
from urllib.parse import urlsplit
import winreg

from workspace import Api


DEVELOPMENT = True
LOCAL_SERVER = 'http://127.0.0.1:18099'
HOSTINGER_DEMO = 'https://demo-sgdea.innovationsapps.cloud'
REGISTRY_KEY = r'SOFTWARE\TEC-SGDEA\Institutional'
REGISTRY_VIEW = winreg.KEY_WOW64_64KEY


def institutional_url(value):
    url = urlsplit(value)
    host = url.hostname or ''
    if (url.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', host)
            or not host.rsplit('.', 1)[-1][0].isalpha()
            or url.netloc.lower() not in (host, host+':443')
            or url.path not in ('', '/') or url.query or url.fragment
            or any(ord(ch) <= 32 or ch == '\\' for ch in value)):
        raise ValueError('Se requiere una URL HTTPS institucional con nombre DNS y puerto estándar.')
    return 'https://'+host


def configured_server():
    if DEVELOPMENT:
        return LOCAL_SERVER
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0,
                            winreg.KEY_READ | REGISTRY_VIEW) as key:
            value, kind = winreg.QueryValueEx(key, 'Backend')
    except FileNotFoundError as error:
        raise ValueError('El administrador aún no ha configurado el servidor institucional.') from error
    if kind != winreg.REG_SZ:
        raise ValueError('La política de conexión institucional es inválida.')
    return institutional_url(value)


def require_admin():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('La configuración requiere un administrador de Windows elevado.')


def configure_institutional(value):
    require_admin()
    server = institutional_url(value)
    Api(server).probe()
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0,
                           winreg.KEY_SET_VALUE | REGISTRY_VIEW) as key:
        winreg.SetValueEx(key, 'Backend', 0, winreg.REG_SZ, server)
