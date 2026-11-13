"""Native login with simulated connection loss and a real recovery upload."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

from e2e_windows import URL, credentials, sql
from server_policy import institutional_url, configure_institutional
from tec_sgdea import Desktop
from workspace import Api, ConnectionLost, Workspace

pilot, fixture, output = map(Path, sys.argv[1:])
output.mkdir()
email, password = credentials(pilot)
db = output/'cache.sqlite3'
code = json.loads((fixture/'result.json').read_text())['code']
assert institutional_url('https://sgdea.example.org:443/') == 'https://sgdea.example.org'
for unsafe in ('http://sgdea.example.org', 'https://127.0.0.1', 'https://user@sgdea.example.org',
               'https://sgdea.example.org/path', 'https://sgdea.example.org:444'):
    try:
        institutional_url(unsafe)
    except ValueError:
        pass
    else:
        raise AssertionError(unsafe)
with patch('server_policy.ctypes.windll.shell32.IsUserAnAdmin', return_value=0):
    try:
        configure_institutional('https://sgdea.example.org')
    except PermissionError:
        pass
    else:
        raise AssertionError('La configuración permitió un usuario no autorizado')
with patch('server_policy.ctypes.windll.shell32.IsUserAnAdmin', return_value=1), \
     patch('server_policy.Api.probe', side_effect=ConnectionLost('Certificado no confiable')), \
     patch('server_policy.winreg.CreateKeyEx') as registry:
    try:
        configure_institutional('https://sgdea.example.org')
    except ConnectionLost:
        registry.assert_not_called()
    else:
        raise AssertionError('Se aceptó una conexión no validada')

ws = Workspace(db, URL)
try:
    ws.enable(email, password)
    data = ws.refresh_work(code)
    operation = ws.save_sheet(code, {**data['sheet'], 'nombre_expediente':'Reconexión sintética '+code,
                                    'tramites':[{'tipo_documental':'Ensayo de recuperación'}]}, data['version'])
finally:
    ws.close()

root = tk.Tk()
view = Desktop(root, db, URL)
available = False
real_probe = Api.probe


def probe(api):
    if not available:
        raise ConnectionLost('Desconexión simulada')
    return real_probe(api)


def wait(condition, action, deadline=None):
    deadline = deadline or time.monotonic()+90
    if condition():
        action()
    elif time.monotonic() > deadline:
        raise AssertionError(view.status.get())
    else:
        root.after(100, lambda: wait(condition, action, deadline))


def login():
    view.email.set(email)
    view.password.set(password)
    view.actions['online'].invoke()
    wait(lambda: not view.busy, offline)


def offline():
    assert view.mode == 'Sin conexión' and view.operations[0]['state']=='pending'
    assert view.reconnect_credentials is not None
    (output/'offline.ready').touch()
    wait(lambda: (output/'reconnect').exists(), reconnect)


def reconnect():
    global available
    available = True
    wait(lambda: view.mode == 'Con sesión' and not view.busy and view.operations[0]['state']=='synced', done)


def done():
    assert view.reconnect_credentials is None
    assert view.operations[0]['id']==operation
    assert sql(f"SELECT count(*) FROM offline_sheet_receipt WHERE operation_id='{operation}'")==['1']
    assert sql(f"SELECT nombre_expediente FROM unidad_documental WHERE codigo_carpeta='{code}'")==[
        'Reconexión sintética '+code]
    (output/'result.json').write_text(json.dumps({'code':code,'offline_fallback':True,
         'automatic_sync':True,'receipt_count':1,'server_change_requires_admin':True,
         'untrusted_probe_blocks_config':True,'invalid_urls_rejected':5},indent=2))
    view.close()


def failed(_type, error, traceback):
    root.destroy()
    raise error.with_traceback(traceback)


root.report_callback_exception = failed
with patch.object(Api, 'probe', probe):
    root.after(150, lambda: wait(lambda: view.backend_status.get()=='Servidor no disponible',
                               lambda: (output/'login.ready').touch()))
    root.after(200, lambda: wait(lambda: (output/'show-offline').exists(), login))
    root.mainloop()
assert (output/'result.json').exists()
