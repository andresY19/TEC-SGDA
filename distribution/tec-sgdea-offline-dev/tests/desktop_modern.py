"""Exercise the login boundary, dashboard, logout and expiry on native Tk."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk

from e2e_windows import URL, credentials
from tec_sgdea import Desktop
from workspace import Api, ApiError

pilot, vault, output = map(Path, sys.argv[1:])
output.mkdir()
email, password = credentials(pilot)
root = tk.Tk()
view = Desktop(root, vault, URL)
view.email.set(email)
view.manual_offline = True
passed = []


def until(predicate, action, deadline=None):
    deadline = deadline or time.monotonic()+120
    if predicate():
        action()
    elif time.monotonic() >= deadline:
        raise AssertionError('No se alcanzó el estado esperado de la interfaz')
    else:
        root.after(75, lambda: until(predicate, action, deadline))


def locked():
    root.update_idletasks()
    assert view.login_frame.winfo_ismapped()
    assert not view.work_frame.winfo_ismapped()
    assert not view.items and not view.recent.get_children()


def initial():
    locked()
    passed.append('isolated_login')
    (output/'login.ready').touch()
    until(lambda: (output/'show-dashboard').exists(), invalid)


def invalid():
    view.password.set('contraseña sintética incorrecta')
    view.actions['unlock'].invoke()
    until(lambda: not view.busy, offline)


def offline():
    locked()
    passed.append('invalid_offline_stays_locked')
    view.password.set(password)
    view.actions['unlock'].invoke()
    until(lambda: not view.busy, dashboard)


def dashboard():
    root.update_idletasks()
    assert view.mode=='Sin conexión' and view.dashboard.winfo_ismapped()
    assert not view.login_frame.winfo_ismapped()
    assert view.metrics[0].get()==str(len(view.items))
    assert len(view.recent.get_children())==min(8,len(view.operations))
    passed.append('authorized_offline_dashboard')
    (output/'dashboard.ready').touch()
    until(lambda: (output/'finish').exists(), expiry)


def expiry():
    view.navigate(1)
    code = view.inventory.get_children()[0]
    view.inventory.selection_set(code)
    view.selection_changed()
    view.actions['dossier'].invoke()
    until(lambda: not view.busy, expire_open_dossier)


def expire_open_dossier():
    assert any(isinstance(window, tk.Toplevel) for window in root.winfo_children())
    view.deadline = (0, 1)
    until(lambda: view.mode=='Bloqueado', online)


def online():
    locked()
    assert not any(isinstance(window, tk.Toplevel) for window in root.winfo_children())
    passed.append('expiry_hides_dashboard_and_closes_document')
    view.email.set(email)
    view.password.set(password)
    view.actions['online'].invoke()
    until(lambda: not view.busy, logout)


def logout():
    assert view.connection.get().startswith('Conectado')
    token = view.pool.submit(lambda: view.workspace.api.token).result()
    view.actions['logout'].invoke()
    until(lambda: not view.busy, lambda: finished(token))


def finished(token):
    locked()
    api = Api(URL)
    api.token = token
    try:
        api.request('/offline/v1/snapshot')
    except ApiError as error:
        assert error.status==401
    else:
        raise AssertionError('El pase anterior siguió activo después del cierre')
    passed.append('logout_revokes_server_token')
    (output/'ui-tests.json').write_text(json.dumps({'passed':passed},indent=2))
    view.close()


def failed(_type, error, traceback):
    root.destroy()
    raise error.with_traceback(traceback)


root.report_callback_exception = failed
root.after(75, initial)
root.mainloop()
assert (output/'ui-tests.json').exists()
