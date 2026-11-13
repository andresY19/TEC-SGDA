#!/usr/bin/env python3
"""Renew only the TEC-SGDEA certificate and deploy it with rollback."""
import fcntl
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time

DOMAIN = 'demo-sgdea.innovationsapps.cloud'
ROOT = Path('/opt/tec-sgdea-demo')
WEBROOT = '/opt/nginx-central/shared/acme/tec-sgdea'
TLS = Path('/opt/nginx-central/shared/tls/tec-sgdea')
IMAGE = 'goacme/lego@sha256:22961472b128731cb576368e2c5b4824f2a1f6811b00e58716d071bf011caff3'


def run(*args, capture=False):
    return subprocess.run(args, check=True, capture_output=capture).stdout


def nginx(*args):
    run('docker', 'exec', 'hostinger-nginx-central-proxy-1', 'nginx', *args)


def verify_live(cert):
    expected = run('openssl', 'x509', '-in', str(cert), '-outform', 'DER', capture=True)
    context = ssl.create_default_context()
    for _ in range(6):
        with socket.create_connection(('127.0.0.1', 443), timeout=4) as connection:
            with context.wrap_socket(connection, server_hostname=DOMAIN) as tls:
                if tls.getpeercert(binary_form=True) == expected:
                    run('curl', '-fsS', '--max-time', '10', f'https://{DOMAIN}/estado')
                    return
        time.sleep(1)
    raise RuntimeError('Nginx no sirve el certificado nuevo')


def replace(path, data, mode, group):
    with tempfile.NamedTemporaryFile(dir=TLS, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fchown(stream.fileno(), 0, group)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def renew(staging):
    account = ROOT / ('acme-stage' if staging else 'acme-live')
    host = 'acme-staging-v02' if staging else 'acme-v02'
    cert = account / 'certificates' / (DOMAIN + '.crt')
    key = cert.with_suffix('.key')
    if not cert.is_file() or not key.is_file():
        raise RuntimeError('Falta el par ACME esperado')
    run('docker', 'run', '--rm', '--pull', 'never', '-v', f'{account}:/certs',
        '-v', f'{WEBROOT}:/acme', IMAGE, 'run', '--path', '/certs',
        '--server', f'https://{host}.api.letsencrypt.org/directory',
        '--accept-tos', '--domains', DOMAIN, '--http', '--http.webroot', '/acme',
        *(['--renew-force'] if staging else ['--ari-disable', '--renew-days', '30']))
    run('openssl', 'x509', '-in', str(cert), '-noout', '-checkhost', DOMAIN, '-checkend', '86400')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    if staging:
        print('STAGING_HTTP01_PASS; certificado activo intacto', flush=True)
        return
    pair = [(TLS/'fullchain.pem', cert, 0o644, 0), (TLS/'privkey.pem', key, 0o640, 101)]
    if all(active.read_bytes() == candidate.read_bytes() for active, candidate, _, _ in pair):
        print('LIVE_UNCHANGED; sin recarga', flush=True)
        return
    nginx('-t')
    previous = [(active, active.read_bytes(), mode, group) for active, _, mode, group in pair]
    rollback = Path(tempfile.mkdtemp(prefix='tls-rollback-', dir=ROOT))
    for active, data, _, _ in previous:
        (rollback/active.name).write_bytes(data)
    try:
        for active, candidate, mode, group in pair:
            replace(active, candidate.read_bytes(), mode, group)
        nginx('-t')
        nginx('-s', 'reload')
        verify_live(cert)
    except BaseException:
        for active, data, mode, group in previous:
            replace(active, data, mode, group)
        nginx('-t')
        nginx('-s', 'reload')
        raise
    print('LIVE_RENEWED; Nginx y HTTPS verificados', flush=True)


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--staging']):
        raise SystemExit('Uso: renew-tls.py [--staging]')
    os.umask(0o077)
    with (ROOT/'tls-renew.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        renew(sys.argv[1:] == ['--staging'])
