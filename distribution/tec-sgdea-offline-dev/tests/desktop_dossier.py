"""Verify the native dossier and viewer using the synthetic E2E workspace."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk

from e2e_windows import URL, credentials
from tec_sgdea import Desktop

parent, session, output = map(Path, sys.argv[1:])
result = json.loads((session/'result.json').read_text())
root = tk.Tk()
view = Desktop(root, session/'cache.sqlite3', URL)
view.password.set(credentials(parent)[1])
view.actions['unlock'].invoke()
deadline = time.monotonic()+15


def wait(predicate, action, expires):
    if predicate():
        action()
    elif time.monotonic() > expires:
        raise AssertionError('La vista esperada no apareció')
    else:
        root.after(100, lambda: wait(predicate, action, expires))


def widgets(window, kind):
    for child in window.winfo_children():
        if isinstance(child, kind):
            yield child
        yield from widgets(child, kind)


def open_sheet():
    assert view.mode == 'Sin conexión'
    view.navigate(1)
    view.inventory.selection_set(result['code'])
    view.selection_changed()
    view.actions['dossier'].invoke()
    wait(lambda: bool(list(widgets(root, tk.Toplevel))), sheet_ready, deadline)


def sheet_ready():
    sheet = next(widgets(root, tk.Toplevel))
    table = next(widgets(sheet, ttk.Treeview))
    assert len(table.get_children()) == 2
    table.selection_set('0')
    table.event_generate('<<TreeviewSelect>>')
    (output/'sheet.ready').touch()

    def open_viewer():
        preview = next(b for b in widgets(sheet, ttk.Button) if b.cget('text') == 'Abrir visor PDF')
        assert preview.instate(['!disabled'])
        preview.invoke()
        wait(lambda: bool(list(widgets(sheet, tk.Toplevel))), lambda: viewer_ready(sheet), time.monotonic()+15)

    wait(lambda: (output/'show-viewer').exists(), open_viewer, time.monotonic()+240)


def viewer_ready(sheet):
    viewer = next(widgets(sheet, tk.Toplevel))
    assert next(widgets(viewer, tk.Canvas)).find_all()
    assert any('Página 1 de 1' in root.getvar(label.cget('textvariable'))
               for label in widgets(viewer, ttk.Label) if label.cget('textvariable'))
    (output/'viewer.ready').touch()

    def finish():
        (output/'ui-tests.json').write_text(json.dumps({'offline_dossier': True, 'viewer_pixels': True,
                                                      'local_and_server_document': True}))
        view.close()

    wait(lambda: (output/'finish').exists(), finish, time.monotonic()+240)


def failed(_type, error, traceback):
    root.destroy()
    raise error.with_traceback(traceback)


root.report_callback_exception = failed
root.after(0, lambda: wait(lambda: not view.busy, open_sheet, deadline))
root.mainloop()
assert (output/'ui-tests.json').exists()
