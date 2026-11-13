"""Exercise the real Tk callbacks on the persistent E2E workspace."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
from e2e_windows import URL
from tec_sgdea import Desktop

parent, session, output = map(Path, sys.argv[1:])
output.mkdir(exist_ok=True)
result = json.loads((session/'result.json').read_text())
_, _, password = (parent/'acceso-local.txt').read_text(encoding='utf-8').splitlines()
root = tk.Tk()
view = Desktop(root, session/'cache.sqlite3', URL)
root.title('TEC-SGDEA | Vista de validación')
view.password.set(password.removeprefix('Contraseña: '))
view.actions['unlock'].invoke()
until = time.monotonic()+15
def wait_for_unlock():
    if view.busy and time.monotonic()<until:
        root.after(50,wait_for_unlock)
        return
    assert view.mode=='Sin conexión'
    view.navigate(1)
    assert view.inventory.exists(result['code'])
    assert view.actions['sync'].instate(['disabled'])
    view.query.set(result['code'])
    assert view.inventory.get_children()==(result['code'],)
    view.query.set('')
    view.inventory.selection_set(result['code'])
    view.inventory.see(result['code'])
    view.selection_changed()
    assert view.actions['export'].instate(['!disabled'])
    (output/'inventory.ready').touch()
    root.after(250,wait_queue)
def wait_queue():
    if not (output/'show-queue').exists():
        root.after(250,wait_queue)
        return
    view.navigate(2)
    rows=[i for i in view.queue.get_children() if view.queue.item(i,'values')[0]==result['conflict']]
    assert len(rows)==1
    view.queue.selection_set(rows[0])
    view.selection_changed()
    assert 'El PDF local se conserva' in view.detail.get()
    assert view.actions['attach'].instate(['disabled'])
    (output/'queue.ready').touch()
    root.after(250,wait_finish)
def wait_finish():
    if not (output/'finish').exists():
        root.after(250,wait_finish)
        return
    (output/'ui-tests.json').write_text(json.dumps({'passed':['offline_unlock','filter','cached_export_enabled','sync_disabled_offline','conflict_visible','attach_disabled_in_queue']}))
    view.close()
root.after(50,wait_for_unlock)
root.mainloop()
