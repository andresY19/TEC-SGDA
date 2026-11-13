"""Offline digitization, control-sheet and audit views."""
import tkinter as tk
from tkinter import ttk

from pdf_viewer import PdfViewer, center


HEADERS = [('nombre_expediente', 'Nombre del expediente'), ('archivo_origen', 'Archivo de origen'),
           ('fecha_diligenciamiento', 'Fecha de diligenciamiento'), ('periodo_manual', 'Período manual')]
FIELDS = [('tipo_documental', 'Tipo documental'), ('fecha', 'Fecha'), ('folio_desde', 'Folio inicial'),
          ('folio_hasta', 'Folio final'), ('no_radicado', 'Radicado'), ('sistema_informacion', 'Sistema'),
          ('expediente_sgdea', 'Expediente SGDEA'), ('enlace_acceso', 'Enlace'), ('observaciones', 'Observaciones')]


def show_work(app, parent, data):
    code = data['code']
    window = tk.Toplevel(parent)
    window.title('TEC-SGDEA | Trabajo documental')
    center(window, parent, 900, 580)
    window.transient(parent)
    window.grab_set()

    def close(_=None):
        window.destroy()
        parent.grab_set()

    window.protocol('WM_DELETE_WINDOW', close)
    window.bind('<Escape>', close)
    body = ttk.Frame(window, padding=15)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text=code+' · '+data['state'], font=('Segoe UI', 16, 'bold')).pack(anchor='w')
    tabs = ttk.Notebook(body)
    tabs.pack(fill='both', expand=True, pady=8)
    technical, sheet, trace = (ttk.Frame(tabs, padding=10) for _ in range(3))
    for tab, label in zip((technical, sheet, trace), ('Digitalización', 'Hoja de control', 'Trazabilidad')):
        tabs.add(tab, text=label)

    status = tk.StringVar(value='Datos de la última consulta al servidor.')
    ttk.Label(body, textvariable=status, wraplength=770).pack(side='left')
    ttk.Button(body, text='Cerrar', command=close).pack(side='right')
    technical_details = tk.StringVar(value='Seleccione una copia guardada para abrirla.')
    ttk.Label(technical, textvariable=technical_details, wraplength=800).pack(anchor='w')
    ttk.Button(technical, text='Abrir derivado', command=lambda: open_pdf()).pack(side='bottom', anchor='w', pady=5)
    tech_rows = app.make_table(technical, [('subject', 'Archivo', 230), ('processed', 'Procesado el', 170),
                                         ('copies', 'Derivados en servidor', 180), ('state', 'Resultado informado', 210)])
    for i, entry in enumerate(data['processing']):
        tech_rows.insert('', 'end', iid=str(i), values=(entry['name'], entry['processed'] or 'Sin fecha registrada',
                        ', '.join(entry['derivatives']) or 'Sin copias disponibles', entry['error'] or ''))
    tech_rows.bind('<<TreeviewSelect>>', lambda _: technical_details.set(
        data['processing'][int(tech_rows.selection()[0])]['error'] or 'Seleccione una copia guardada para abrirla.'
    ) if tech_rows.selection() else None)
    docs = app.make_table(technical, [('subject', 'Copia derivada', 400), ('state', 'Disponibilidad', 180)])
    for i, doc in enumerate(data['documents']):
        docs.insert('', 'end', iid=str(i), values=(doc['name'], 'Guardada localmente' if doc['cached'] else 'Sin descargar'))

    def open_pdf():
        selected = docs.selection()
        if not selected:
            return
        doc = data['documents'][int(selected[0])]
        if doc['cached']:
            app.perform('Verificando SHA-256 del derivado…', lambda: app.workspace.preview_derivative(code, doc),
                        lambda pdf: PdfViewer(window, doc['name'], pdf) if window.winfo_exists() else None)

    docs.bind('<Return>', lambda _: open_pdf())

    trail = app.make_table(trace, [('source', 'Origen', 90), ('date', 'Fecha', 155), ('subject', 'Acción', 170),
                                   ('state', 'Resultado', 190), ('user', 'Usuario', 160)])
    notes = []
    for event in data['trace']:
        trail.insert('', 'end', iid=str(len(notes)), values=('Servidor', event['fecha'], event['accion'],
                     event['a'], event['usuario']))
        notes.append(event.get('motivo') or '')
    for row in data['operations']:
        trail.insert('', 'end', iid=str(len(notes)), values=('Escritorio', row.get('saved', ''),
                     'Avance de hoja' if row.get('kind') == 'sheet' else 'Cargue PDF',
                     app.state_label(row), ''))
        notes.append(row.get('error') or row['id'])
    trace_note = tk.StringVar()
    ttk.Label(trace, textvariable=trace_note, wraplength=800).pack(anchor='w')
    trail.bind('<<TreeviewSelect>>', lambda _: trace_note.set(notes[int(trail.selection()[0])])
               if trail.selection() else None)

    prior = next((r for r in reversed(data['operations']) if r.get('kind') == 'sheet' and r['state'] != 'synced'), None)
    editable = data['editable'] and (not prior or prior['state'] == 'pending' and not prior.get('attempted'))
    current = prior['sheet'] if prior else data['sheet']
    fields = ttk.Frame(sheet)
    fields.pack(fill='x')
    values = {}
    for index, (key, label) in enumerate(HEADERS):
        col, row = index % 2, (index // 2)*2
        fields.columnconfigure(col, weight=1)
        ttk.Label(fields, text=label).grid(row=row, column=col, sticky='w')
        values[key] = tk.StringVar(value=current.get(key) or '')
        entry = ttk.Entry(fields, textvariable=values[key])
        entry.grid(row=row+1, column=col, sticky='ew', padx=(0,8), pady=(0,4))
        if not editable:
            entry.state(['readonly'])
    rows = [dict(row) for row in current['tramites']]
    table = app.make_table(sheet, [('subject', 'Tipo documental', 420), ('date', 'Fecha', 150),
                                  ('start', 'Folio inicial', 95), ('end', 'Folio final', 95)])

    def render():
        table.delete(*table.get_children())
        for i, row in enumerate(rows):
            table.insert('', 'end', iid=str(i), values=tuple(row.get(key) or '' for key, _ in FIELDS[:4]))

    def edit(index=None):
        editor = tk.Toplevel(window)
        editor.title('TEC-SGDEA | Trámite')
        center(editor, window, 660, 510)
        editor.transient(window)
        editor.grab_set()
        form = ttk.Frame(editor, padding=12)
        form.pack(fill='both', expand=True)
        fields = {}
        existing = rows[index] if index is not None else {}
        for key, label in FIELDS:
            ttk.Label(form, text=label).pack(anchor='w')
            fields[key] = tk.StringVar(value=existing.get(key) or '')
            entry = ttk.Entry(form, textvariable=fields[key])
            entry.pack(fill='x')
            if not editable:
                entry.state(['readonly'])

        def finish():
            editor.destroy()
            window.grab_set()

        def apply():
            row = {key: value.get() for key, value in fields.items()}
            if index is None:
                rows.append(row)
            else:
                rows[index] = row
            render()
            finish()

        editor.protocol('WM_DELETE_WINDOW', finish)
        editor.bind('<Escape>', lambda _: finish())
        if editable:
            ttk.Button(form, text='Aplicar al borrador', command=apply).pack(side='left', pady=5)
        ttk.Button(form, text='Cerrar', command=finish).pack(side='right', pady=5)

    def selected_row():
        return int(table.selection()[0]) if table.selection() else None

    def view_row():
        index = selected_row()
        if index is not None:
            edit(index)

    def remove_row():
        index = selected_row()
        if index is not None:
            rows.pop(index)
            render()

    def save():
        payload = {key: value.get() for key, value in values.items()}
        payload['periodo_manual'] = payload['periodo_manual'] or None
        payload['tramites'] = [dict(row) for row in rows]
        app.perform('Guardando avance cifrado…',
                    lambda: app.workspace.save_sheet(code, payload, data['version']),
                    lambda _: status.set('Avance local guardado · Pendiente de sincronizar') if window.winfo_exists() else None,
                    lambda error: status.set(error) if window.winfo_exists() else None)

    toolbar = ttk.Frame(sheet)
    toolbar.pack(fill='x', pady=4)
    if editable:
        ttk.Button(toolbar, text='Agregar trámite', command=edit).pack(side='left')
        ttk.Button(toolbar, text='Quitar trámite del borrador', command=remove_row).pack(side='left')
        ttk.Button(toolbar, text='Guardar avance local', style='Accent.TButton', command=save).pack(side='right')
    ttk.Button(toolbar, text='Abrir trámite', command=view_row).pack(side='left')
    table.bind('<Return>', lambda _: view_row())
    render()
