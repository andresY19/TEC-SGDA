"""Capture and exercise the Tk views against the persistent synthetic workspace."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk

from e2e_windows import URL, credentials
from tec_sgdea import Desktop
from work_panel import show_work

base, run, output = map(Path, sys.argv[1:])
output.mkdir(exist_ok=True)
code = json.loads((run/'result.json').read_text())['code']
root = tk.Tk()
view = Desktop(root, run/'work.sqlite3')
view.server.set(URL)
view.password.set(credentials(base)[1])
view.actions['unlock'].invoke()


def until(condition, next_step, deadline=None):
    deadline = deadline or time.monotonic()+150
    if condition():
        next_step()
    elif time.monotonic() > deadline:
        raise AssertionError('La prueba de interfaz excedió el tiempo disponible')
    else:
        root.after(100, lambda: until(condition, next_step, deadline))


def open_views():
    assert view.mode == 'Sin conexión'
    view.navigate(2)
    view.queue_filter.set('Completadas')
    view.render()
    assert len(view.queue.get_children()) == 1
    assert view.queue.item(view.queue.get_children()[0], 'values')[1]=='Hoja de control'
    view.queue_filter.set('Conflictos')
    view.render()
    assert not view.queue.get_children()
    view.queue_filter.set('Completadas')
    view.render()
    (output/'queue.ready').touch()
    until(lambda: (output/'show-work').exists(),
          lambda: view.perform('Abriendo ficha de trabajo…', lambda: view.workspace.work(code), loaded))


def loaded(data):
    assert len(data['documents']) == 2 and all(doc['cached'] for doc in data['documents'])
    assert any(row['accion']=='guardar_avance' for row in data['trace'])
    show_work(view, root, data)
    window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    panel = next(w for w in window.winfo_children() if isinstance(w, ttk.Frame))
    tabs = next(w for w in panel.winfo_children() if isinstance(w, ttk.Notebook))
    (output/'technical.ready').touch()

    def select(index, marker, command):
        tabs.select(index)
        (output/marker).touch()
        until(lambda: (output/command[0]).exists(), command[1])

    def finish():
        (output/'ui-tests.json').write_text(json.dumps({'offline_tabs':3, 'queue_filters':2,
                                                      'cached_derivatives':2, 'trace_visible':True}))
        view.close()

    until(lambda: (output/'show-sheet').exists(), lambda: select(1,'sheet.ready',
          ('show-trace', lambda: select(2,'trace.ready',('finish', finish)))))


def failed(_type, error, traceback):
    root.destroy()
    raise error.with_traceback(traceback)


root.report_callback_exception = failed
root.after(0, lambda: until(lambda: not view.busy, open_views))
root.mainloop()
assert (output/'ui-tests.json').exists()
