"""Institutional desktop workspace, with network work isolated from the Tk thread."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from workspace import LIMIT, Api, ApiError, ConnectionLost, OfflineError, Workspace
from pdf_viewer import PdfViewer, center
from work_panel import show_work
from migration import CURRENT_SERVER, discover
from server_policy import HOSTINGER_DEMO, configured_server, configure_institutional

BG, WHITE, INK = '#F5F6FC', '#FFFFFF', '#172033'
INDIGO, VIOLET, BLUE = '#4848B6', '#6257DC', '#29577E'
MUTED, BORDER = '#536078', '#DADEF0'
STATES = {'draft': 'Borrador sin PDF', 'pending': 'Pendiente', 'synced': 'Sincronizado',
          'conflict': 'Conflicto · revisar', 'rejected': 'Rechazado · revisar'}


class Desktop:
    def __init__(self, root, database, server=CURRENT_SERVER, profile='Espacio consolidado'):
        self.root, self.database = root, database
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.workspace = None  # Used exclusively by the executor.
        self.busy = False
        self.deadline = None
        self.generation = 0
        self.mode = 'Bloqueado'
        self.items, self.operations = [], []
        self.server = server
        self.probe_pool = ThreadPoolExecutor(max_workers=1)
        self.probe = None
        self.reconnect_credentials = None  # Memory only, cleared on authentication or lock.
        self.manual_offline = False
        self.backend_status = tk.StringVar(value='Comprobando disponibilidad…')
        self.profile = profile
        self.email, self.password, self.query = (tk.StringVar() for _ in range(3))
        self.connection = tk.StringVar(value=self.mode)
        self.status = tk.StringVar(value='Inicie sesión para habilitar el acceso offline.')
        self.metrics = [tk.StringVar(value='—') for _ in range(3)]
        self.detail = tk.StringVar(value='Seleccione un expediente u operación.')
        self.queue_filter = tk.StringVar(value='Todas')
        self.actions = {}
        self.build()
        self.update_buttons()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(500, self.check_expiry)
        root.after(100, self.monitor_backend)

    def build(self):
        root = self.root
        root.title('TEC-SGDEA | Escritorio')
        root.geometry('1200x710')
        root.minsize(1000, 660)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), foreground=INK)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=INK)
        style.configure('TButton', padding=(10, 8), background=WHITE, bordercolor=BORDER)
        style.configure('TEntry', padding=(8, 6), fieldbackground=WHITE)
        style.map('TEntry', bordercolor=[('focus', INDIGO)])
        style.configure('Nav.TButton', anchor='w', padding=(15, 10), background=INDIGO, foreground=WHITE,
                        bordercolor=INDIGO)
        style.map('Nav.TButton', background=[('pressed', BLUE), ('active', '#38389B')],
                  foreground=[('disabled', '#D1D4EF')])
        style.configure('NavActive.TButton', anchor='w', padding=(15, 10), background=BLUE,
                        foreground=WHITE, bordercolor=WHITE)
        style.configure('Accent.TButton', background=INDIGO, foreground=WHITE)
        style.map('Accent.TButton', background=[('disabled', BORDER), ('active', VIOLET)],
                  foreground=[('disabled', MUTED)])
        style.configure('Treeview', rowheight=31, background=WHITE, fieldbackground=WHITE)
        style.configure('Treeview.Heading', padding=7, background='#EEF0FA', foreground=BLUE)
        style.map('Treeview', background=[('selected', INDIGO)], foreground=[('selected', WHITE)])
        style.configure('TNotebook', background=BG)
        style.configure('TNotebook.Tab', padding=(15, 7))
        style.map('TNotebook.Tab', background=[('selected', INDIGO)], foreground=[('selected', WHITE)])

        self.build_login()
        self.work_frame = ttk.Frame(root)
        rail = self.rail = tk.Frame(self.work_frame, bg=INDIGO, width=220)
        rail.pack(side='left', fill='y')
        rail.pack_propagate(False)
        tk.Frame(rail, bg=VIOLET, height=5).pack(fill='x')
        tk.Label(rail, text='TEC-SGDEA', font=('Segoe UI', 20, 'bold'), bg=INDIGO, fg=WHITE).pack(anchor='w', padx=14, pady=(22, 0))
        tk.Label(rail, text='Gestión documental', bg=INDIGO, fg=WHITE).pack(anchor='w', padx=15, pady=(0, 28))
        home = ttk.Button(rail, text='⌂   Dashboard', style='Nav.TButton', command=lambda: self.navigate(0))
        home.pack(fill='x', padx=6, pady=2)
        self.navigation = [home]
        self.nav_groups, self.nav_links = {}, {'home': home}
        for label, options in (
            ('▤  Inventarios', [('inventory', 'Consultar inventario', self.open_search)]),
            ('▣  Expedientes', [('search','Buscar expediente', lambda: self.open_search('search')),
                               ('draft','Nuevo borrador', self.new_draft), ('dossier','Abrir ficha', self.open_dossier)]),
            ('▧  Gestión documental', [('attach','Adjuntar PDF', self.attach),
                                       ('digital','Digitalización', lambda: self.open_dossier(0)),
                                       ('sheet','Hoja de control', lambda: self.open_dossier(1))]),
            ('↻  Seguimiento', [('trace','Trazabilidad', lambda: self.open_dossier(2)),
                                ('sync','Cola de sincronización', lambda: self.navigate(2))])
        ):
            section = tk.Frame(rail, bg=INDIGO)
            section.pack(fill='x', padx=6, pady=1)
            panel = tk.Frame(section, bg=INDIGO)
            title = ttk.Button(section, text='▸ '+label, style='Nav.TButton')
            title.configure(command=lambda n=label: self.toggle_group(n))
            title.pack(fill='x')
            self.nav_groups[label] = (title, panel)
            for key, name, command in options:
                button = ttk.Button(panel, text='    '+name, style='Nav.TButton', command=command)
                button.pack(fill='x')
                self.nav_links[key] = button
        for button in (*self.nav_links.values(), *(title for title, _ in self.nav_groups.values())):
            button.bind('<Return>', lambda event: event.widget.invoke())
        self.actions['logout'] = ttk.Button(rail, text='Cerrar sesión', style='Nav.TButton', command=self.logout)
        self.actions['logout'].pack(side='bottom', fill='x', padx=6, pady=12)
        self.actions['reconnect'] = ttk.Button(rail, text='Volver a conectar', style='Nav.TButton', command=self.reconnect)
        self.actions['reconnect'].pack(side='bottom', fill='x', padx=6)

        content = ttk.Frame(self.work_frame, padding=(24, 20))
        content.pack(fill='both', expand=True)
        header = ttk.Frame(content)
        header.pack(fill='x', pady=(0, 16))
        self.menu_toggle = ttk.Button(header, text='☰ Menú', command=self.toggle_rail)
        self.menu_toggle.pack(side='left', padx=(0, 10))
        root.bind('<Escape>', self.close_rail_on_escape)
        self.page_title = tk.StringVar(value='Inicio')
        ttk.Label(header, textvariable=self.page_title, font=('Segoe UI', 23, 'bold')).pack(side='left')
        self.badge = tk.Label(header, textvariable=self.connection, bg=BLUE, fg=WHITE, padx=14,
                              pady=7, font=('Segoe UI', 10, 'bold'))
        self.badge.pack(side='right')
        self.dashboard = ttk.Frame(content)
        self.build_dashboard()
        body = self.module_body = ttk.Frame(content)

        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill='both', expand=True)
        inventory, queue = ttk.Frame(self.tabs, padding=8), ttk.Frame(self.tabs, padding=8)
        self.tabs.add(inventory, text='Inventario')
        self.tabs.add(queue, text='Cola de sincronización')
        search = ttk.Frame(inventory)
        search.pack(fill='x', pady=(0, 6))
        ttk.Label(search, text='Buscar por carpeta o asunto').pack(side='left', padx=(0, 8))
        self.search_entry = ttk.Entry(search, textvariable=self.query, width=35)
        self.search_entry.pack(side='left', fill='x', expand=True)
        self.query.trace_add('write', lambda *_: self.render())
        self.inventory = self.make_table(inventory, [('code','Carpeta',130),('subject','Asunto',300),
                                                     ('state','Estado',175),('pdf','PDF guardados',110)])
        self.inventory_empty = ttk.Label(inventory, foreground=MUTED)
        self.inventory_empty.pack(anchor='w')
        filters = ttk.Frame(queue)
        filters.pack(fill='x')
        ttk.Label(filters, text='Mostrar operaciones').pack(side='left', padx=(0, 8))
        choice = ttk.Combobox(filters, state='readonly', textvariable=self.queue_filter,
                             values=('Todas', 'Pendientes', 'Completadas', 'Errores', 'Conflictos'))
        choice.pack(side='left', pady=(0, 5))
        choice.bind('<<ComboboxSelected>>', lambda _: self.render())
        self.queue = self.make_table(queue, [('code','Carpeta',130),('type','Operación',140),('state','Estado',170),
                                             ('id','Operación local',300)])
        self.queue_empty = ttk.Label(queue, foreground=MUTED)
        self.queue_empty.pack(anchor='w')
        self.queue.tag_configure('conflict', foreground='#8A341C')
        self.queue.tag_configure('rejected', foreground='#8A341C')
        for table in (self.inventory, self.queue):
            table.bind('<<TreeviewSelect>>', lambda _: self.selection_changed())
        self.tabs.bind('<<NotebookTabChanged>>', self.tab_changed)
        for table in (self.inventory, self.queue):
            table.bind('<Return>', lambda _: self.open_dossier() if self.actions['dossier'].instate(['!disabled']) else None)

        toolbar = ttk.Frame(body)
        for key, label, action in [
            ('download', 'Descargar PDF', self.download),
            ('export', 'Guardar copia', self.export),
            ('dossier', 'Ver ficha', self.open_dossier),
            ('draft', 'Nuevo borrador', self.new_draft),
            ('attach', 'Adjuntar PDF', self.attach),
            ('offline', 'Modo offline', self.go_offline),
            ('sync', 'Sincronizar', self.synchronize)
        ]:
            button = ttk.Button(toolbar, text=label, command=action, style='Accent.TButton' if key=='sync' else 'TButton')
            button.pack(side='left', padx=(0, 6))
            self.actions[key] = button
        ttk.Label(body, textvariable=self.detail, foreground=BLUE, wraplength=755).pack(side='bottom', anchor='w', before=self.tabs)
        toolbar.pack(side='bottom', fill='x', before=self.tabs, pady=(10, 6))
        ttk.Label(content, textvariable=self.status, foreground=MUTED, wraplength=790).pack(side='bottom', anchor='w', pady=(5, 0))
        self.login_frame.pack(fill='both', expand=True)
        self.login_email.focus_set()

    def toggle_group(self, label):
        title, panel = self.nav_groups[label]
        opening = not panel.winfo_manager()
        for other, (button, content) in self.nav_groups.items():
            content.pack_forget()
            button.configure(text='▸ '+other)
        if opening:
            panel.pack(fill='x')
            title.configure(text='▾ '+label)

    def toggle_rail(self):
        if self.rail.winfo_manager():
            self.rail.pack_forget()
            self.menu_toggle.focus_set()
        else:
            self.rail.pack(side='left', fill='y', before=self.menu_toggle.master.master)
            self.navigation[0].focus_set()

    def close_rail_on_escape(self, event):
        if str(event.widget).startswith(str(self.rail)+'.') and self.rail.winfo_manager():
            self.toggle_rail()
            return 'break'

    def highlight_navigation(self, key):
        self.active_navigation = key
        for name, button in self.nav_links.items():
            button.configure(style='NavActive.TButton' if name==key else 'Nav.TButton')

    def build_login(self):
        frame = self.login_frame = tk.Frame(self.root, bg=WHITE)
        frame.columnconfigure(0, weight=1, uniform='login')
        frame.columnconfigure(1, weight=1, uniform='login')
        frame.rowconfigure(0, weight=1)
        hero = tk.Frame(frame, bg=INDIGO, padx=46, pady=44)
        hero.grid(row=0, column=0, sticky='nsew')
        tk.Frame(hero, bg=VIOLET, height=5, width=64).pack(anchor='w', pady=(36, 20))
        tk.Label(hero, text='TEC-SGDEA', font=('Segoe UI', 36, 'bold'), bg=INDIGO, fg=WHITE).pack(anchor='w')
        tk.Label(hero, text='Gestión documental inteligente', font=('Segoe UI', 16),
                 bg=INDIGO, fg=WHITE).pack(anchor='w', pady=(8, 26))
        tk.Label(hero, text='Consulta expedientes y guarda tus avances\naunque estés sin conexión.',
                 justify='left', font=('Segoe UI', 13), bg=INDIGO, fg='#F1F1FF').pack(anchor='w')
        tk.Label(hero, text='Aplicación de escritorio', bg=INDIGO, fg=WHITE).pack(side='bottom', anchor='w')
        shell = tk.Frame(frame, bg=WHITE)
        shell.grid(row=0, column=1, sticky='nsew')
        form = tk.Frame(shell, bg=WHITE)
        form.place(relx=0.5, rely=0.5, anchor='center', relwidth=0.76)
        tk.Label(form, text='Iniciar sesión', font=('Segoe UI', 28, 'bold'), bg=WHITE, fg=INK).pack(anchor='w')
        tk.Label(form, text=self.profile, font=('Segoe UI', 11), bg=WHITE, fg=MUTED).pack(anchor='w', pady=(0, 18))
        entries = []
        for label, value, mask in (('Correo', self.email, ''), ('Contraseña', self.password, '●')):
            tk.Label(form, text=label, bg=WHITE, fg=INK, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
            entry = ttk.Entry(form, textvariable=value, show=mask)
            entry.pack(fill='x', pady=(3, 10))
            entry.bind('<Return>', lambda _: self.enter(True))
            entries.append(entry)
        self.login_email = entries[0]
        self.actions['online'] = ttk.Button(form, text='Ingresar', style='Accent.TButton', command=lambda: self.enter(True))
        self.actions['online'].pack(fill='x', pady=(8, 6))
        self.actions['unlock'] = ttk.Button(form, text='Desbloquear sin conexión', command=lambda: self.enter(False))
        self.actions['unlock'].pack(fill='x')
        tk.Label(form, textvariable=self.backend_status, bg=WHITE, fg=MUTED).pack(anchor='w', pady=(12,0))
        tk.Label(form, textvariable=self.status, bg=WHITE, fg=BLUE, justify='left',
                 wraplength=335).pack(anchor='w', pady=(13, 0))

    def build_dashboard(self):
        ttk.Label(self.dashboard, text='Resumen de tu espacio de trabajo', foreground=MUTED).pack(anchor='w', pady=(0, 16))
        cards = ttk.Frame(self.dashboard)
        cards.pack(fill='x')
        metrics = [('Carpetas disponibles', BLUE, 1, 'Abrir inventario', 'Todas'),
                   ('Pendientes de sincronizar', INDIGO, 2, 'Ver pendientes', 'Pendientes'),
                   ('Conflictos y errores', VIOLET, 2, 'Revisar operaciones', 'Todas')]
        for index, (label, color, page, action, category) in enumerate(metrics):
            card = tk.Frame(cards, bg=WHITE, highlightbackground=BORDER, highlightthickness=1, padx=12, pady=10)
            card.grid(row=0, column=index, sticky='nsew', padx=(0, 8))
            cards.columnconfigure(index, weight=1, uniform='metric')
            tk.Label(card, text=label, bg=WHITE, fg=MUTED).pack(anchor='w')
            tk.Label(card, textvariable=self.metrics[index], bg=WHITE, fg=color,
                     font=('Segoe UI', 26, 'bold')).pack(anchor='w')
            ttk.Button(card, text=action, command=lambda p=page, c=category: self.navigate(p, c)).pack(anchor='w', pady=(4, 0))
        quick = ttk.Frame(self.dashboard)
        quick.pack(fill='x', pady=16)
        ttk.Label(quick, text='Accesos rápidos', font=('Segoe UI', 12, 'bold')).pack(side='left', padx=(0, 8))
        ttk.Button(quick, text='Buscar expediente', command=self.open_search).pack(side='left', padx=4)
        self.actions['sync_home'] = ttk.Button(quick, text='Sincronizar ahora', style='Accent.TButton', command=self.synchronize)
        self.actions['sync_home'].pack(side='left', padx=4)
        ttk.Label(self.dashboard, text='Actividad local reciente', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(4, 7))
        self.recent = self.make_table(self.dashboard, [('code','Carpeta',130), ('subject','Operación',200),
                                                       ('state','Estado',180)])
        self.recent.bind('<Return>', lambda _: self.open_activity())
        self.recent.bind('<Double-1>', lambda _: self.open_activity())
        self.recent_empty = ttk.Label(self.dashboard, foreground=MUTED)
        self.recent_empty.pack(anchor='w', pady=4)

    def open_search(self, key='inventory'):
        self.navigate(1)
        self.highlight_navigation(key)
        self.search_entry.focus_set()

    def open_activity(self):
        selection = self.recent.selection()
        if selection:
            self.navigate(2, 'Todas')
            self.queue.selection_set(selection[0])
            self.queue.see(selection[0])
            self.queue.focus_set()

    def navigate(self, page, category=None):
        if self.mode == 'Bloqueado':
            return
        self.page_title.set(('Inicio', 'Inventarios y expedientes', 'Sincronización')[page])
        self.highlight_navigation(('home','inventory','sync')[page])
        self.dashboard.pack_forget()
        self.module_body.pack_forget()
        if page == 0:
            self.dashboard.pack(fill='both', expand=True)
        else:
            if category:
                self.queue_filter.set(category)
            self.module_body.pack(fill='both', expand=True)
            self.tabs.select(page-1)
            self.render()

    def tab_changed(self, _):
        if self.module_body.winfo_manager():
            self.page_title.set(('Inventarios y expedientes', 'Sincronización')[self.tabs.index('current')])
            index = self.tabs.index('current')
            if index or self.active_navigation not in ('inventory','search'):
                self.highlight_navigation(('inventory','sync')[index])
        self.selection_changed()

    def apply_lock(self):
        self.generation += 1
        self.mode, self.deadline = 'Bloqueado', None
        self.items, self.operations = [], []
        self.password.set('')
        self.reconnect_credentials = None
        self.manual_offline = False
        self.query.set('')
        for window in self.root.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.destroy()
        self.work_frame.pack_forget()
        self.login_frame.pack(fill='both', expand=True)
        self.login_email.focus_set()
        self.render()

    def check_expiry(self):
        if self.deadline is not None and not self.deadline[0] <= time.time() < self.deadline[1]:
            self.apply_lock()
            self.status.set('La habilitación offline venció. Inicie sesión en línea para continuar.')
            self.pool.submit(lambda: self.workspace and self.workspace.lock())
        self.root.after(500, self.check_expiry)

    def monitor_backend(self):
        if self.probe is None:
            self.probe = self.probe_pool.submit(lambda: Api(self.server).probe())
        if not self.probe.done():
            self.root.after(100, self.monitor_backend)
            return
        try:
            self.probe.result()
            available = True
        except (OfflineError, OSError, ValueError):
            available = False
        self.probe = None
        self.observe_backend(available)
        self.root.after(5000, self.monitor_backend)

    def observe_backend(self, available):
        self.backend_status.set('Servidor disponible' if available else 'Servidor no disponible')
        if self.busy or self.mode == 'Bloqueado' or self.manual_offline:
            return
        if not available and self.mode == 'Con sesión':
            self.mode = 'Sin conexión'
            self.refresh_badge()
            self.update_buttons()
        elif available and (self.mode == 'Sin conexión' or any(
                row['state'] == 'pending' for row in self.operations)):
            self.synchronize()

    def refresh_badge(self, syncing=False):
        label, color = ('Conectado', BLUE) if self.mode == 'Con sesión' else (self.mode, '#42536E')
        if syncing:
            label, color = 'Sincronizando', INDIGO
        elif any(row['state']=='conflict' for row in self.operations):
            label, color = label+' · Conflicto', '#8A341C'
        self.connection.set(label)
        self.badge.configure(bg=color)

    @staticmethod
    def make_table(parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', height=6, selectmode='browse')
        vertical = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        table.pack(side='left', fill='both', expand=True)
        for key, title, width in columns:
            table.heading(key, text=title)
            table.column(key, width=width, stretch=key in ('subject','id'))
        return table

    def view_data(self):
        rows = [{k: v for k, v in row.items() if k != 'pdf'} for row in self.workspace.pending()]
        items = [{**item, 'cached': self.workspace.cached_count(item)} for item in self.workspace.items()]
        return items, rows

    def perform(self, label, operation, on_success=None, on_error=None, syncing=False):
        if self.busy:
            return
        self.busy = True
        generation = self.generation
        self.status.set(label)
        self.update_buttons()
        if syncing:
            self.refresh_badge(syncing=True)

        def task():
            disconnected = False
            try:
                result, error = operation(), False
            except Exception as exc:
                result, error = str(exc), True
                if self.workspace:
                    if isinstance(exc, ApiError) and exc.status in (401, 403):
                        self.workspace.lock()
                    elif isinstance(exc, ConnectionLost) or isinstance(exc, ApiError) and exc.status == 503:
                        disconnected = True
            try:
                lease = self.workspace._require() if self.workspace else None
                items, rows = self.view_data() if lease else ([], [])
                mode = ('Con sesión' if self.workspace.api.token and not disconnected and not self.manual_offline
                        else 'Sin conexión') if lease else 'Bloqueado'
                deadline = (lease['issued'], lease['expires']) if lease else None
            except OfflineError:
                items, rows, mode, deadline = [], [], 'Bloqueado', None
            return result, error, items, rows, mode, deadline

        future = self.pool.submit(task)

        def poll():
            if not future.done():
                self.root.after(50, poll)
                return
            self.busy = False
            try:
                if generation != self.generation:
                    return
                try:
                    result, error, items, rows, mode, deadline = future.result()
                except Exception:
                    self.apply_lock()
                    self.status.set('No se pudo abrir el espacio local. Los archivos se conservan.')
                    return
                if mode == 'Bloqueado':
                    self.apply_lock()
                    self.status.set(result if isinstance(result, str) else 'Inicie sesión para continuar.')
                    return
                was_locked = self.mode == 'Bloqueado'
                self.items, self.operations, self.mode, self.deadline = items, rows, mode, deadline
                self.status.set(result if error or not on_success else 'Operación completada.')
                self.refresh_badge()
                if was_locked:
                    self.login_frame.pack_forget()
                    self.work_frame.pack(fill='both', expand=True)
                    self.navigate(0)
                    self.navigation[0].focus_set()
                self.render()
                if not error and on_success:
                    on_success(result)
                elif error and on_error:
                    on_error(result)
            finally:
                self.update_buttons()
        self.root.after(50, poll)

    def enter(self, online):
        if self.busy or self.mode != 'Bloqueado':
            return
        url, email, password = self.server, self.email.get().strip(), self.password.get()
        self.password.set('')
        if not email or not password:
            self.status.set('Ingrese su correo y contraseña.')
            return
        def login():
            if not self.workspace:
                self.workspace = Workspace(self.database, url)
            if online:
                try:
                    Api(url).probe()
                    self.workspace.enable(email, password)
                    return 'Acceso offline habilitado durante 24 horas.'
                except ConnectionLost:
                    pass
            self.workspace.unlock(password, email)
            self.reconnect_credentials = (email, password)
            return 'Espacio local abierto. Los cambios quedan en este equipo.'
        self.perform('Verificando acceso…', login)

    def render(self):
        term = self.query.get().strip().casefold()
        rows = {row['code']:row for row in self.operations if row.get('kind') != 'sheet'}
        for table in (self.inventory, self.queue):
            selected = table.selection()
            table.delete(*table.get_children())
            if table is self.inventory:
                for item in self.items:
                    code, subject = item['code'], item['subject'] or ''
                    if term and term not in (code+' '+subject).casefold():
                        continue
                    row = rows.get(code)
                    state = STATES.get(row['state'], row['state']) if row else item['state'] or 'Disponible para crear'
                    table.insert('', 'end', iid=code, values=(code, subject, state, item['cached']))
            else:
                category = {'Pendientes': {'draft', 'pending'}, 'Completadas': {'synced'},
                            'Errores': {'rejected'}, 'Conflictos': {'conflict'}}.get(self.queue_filter.get(), STATES)
                for row in self.operations:
                    if row['state'] not in category:
                        continue
                    table.insert('', 'end', iid=row['id'], tags=(row['state'],),
                                 values=(row['code'], 'Hoja de control' if row.get('kind')=='sheet' else 'Cargue PDF',
                                         self.state_label(row), row['id']))
            if selected and table.exists(selected[0]):
                table.selection_set(selected[0])
        self.inventory_empty.configure(text='' if self.inventory.get_children() else 'No hay carpetas para esta búsqueda.')
        self.queue_empty.configure(text='' if self.queue.get_children() else 'No hay operaciones en esta categoría.')
        self.recent.delete(*self.recent.get_children())
        for row in reversed(self.operations[-8:]):
            self.recent.insert('', 'end', iid=row['id'], values=(row['code'],
                               'Hoja de control' if row.get('kind')=='sheet' else 'Cargue PDF',
                               self.state_label(row)))
        self.recent_empty.configure(text='' if self.operations else 'Todavía no hay actividad local.')
        values = [len(self.items), sum(r['state']=='pending' for r in self.operations),
                  sum(r['state'] in ('conflict','rejected') for r in self.operations)]
        for widget, value in zip(self.metrics, values):
            widget.set(str(value) if self.mode!='Bloqueado' else '—')
        self.selection_changed()

    def selected(self):
        if self.tabs.index('current') != 0 or not self.inventory.selection():
            return None
        code = self.inventory.selection()[0]
        return next((item for item in self.items if item['code']==code), None)

    def selection_changed(self):
        item = self.selected()
        row = None
        if item:
            row = next((r for r in self.operations if r['code']==item['code'] and r.get('kind')!='sheet'), None)
        elif self.tabs.index('current')==1 and self.queue.selection():
            row = next((r for r in self.operations if r['id']==self.queue.selection()[0]),None)
        if row:
            message = row['code']+' · '+self.state_label(row)
            if row.get('error'):
                message += ' — '+row['error']+(' El avance local se conserva.' if row.get('kind')=='sheet'
                                               else ' El PDF local se conserva.')
            elif row.get('receipt') and row.get('kind')!='sheet':
                message += ' — Expediente web '+str(row['receipt']['id'])
            self.detail.set(message)
        elif item:
            self.detail.set(f"{item['code']} · {item['cached']} de {len(item['documents'])} PDF guardados")
        else:
            self.detail.set('Seleccione un expediente u operación.')
        self.update_buttons()

    @staticmethod
    def state_label(row):
        return STATES[row['state']]

    def update_buttons(self):
        item = self.selected()
        opened, online = self.mode!='Bloqueado', self.mode=='Con sesión'
        row = next((r for r in self.operations if item and r['code']==item['code']), None)
        available = {
            'online': not opened, 'unlock': not opened, 'offline': online,
            'logout': opened, 'reconnect': opened and not online,
            'download': online and item and item['documents'],
            'export': opened and item and item['cached']==1,
            'dossier': opened and self.dossier_code(),
            'draft': opened and item and item['state'] is None and not row,
            'attach': opened and item and item['state'] is None and (not row or row['state']=='draft'),
            'sync': online and any(row['state']=='pending' for row in self.operations)
        }
        available['sync_home'] = available['sync']
        for key, button in self.actions.items():
            button.state(['!disabled'] if available[key] and not self.busy else ['disabled'])
        for key, button in self.nav_links.items():
            enabled = available.get(key, available['dossier'] if key in ('digital','sheet','trace') else opened)
            if key == 'sync':
                enabled = opened
            button.state(['!disabled'] if enabled and not self.busy else ['disabled'])

    def download(self):
        code = self.selected()['code']
        self.perform('Descargando y comprobando SHA-256…', lambda: f'{self.workspace.download(code)} PDF guardados para uso offline.')

    def export(self):
        code = self.selected()['code']
        name = filedialog.asksaveasfilename(parent=self.root, defaultextension='.pdf', filetypes=[('PDF','*.pdf')])
        if name:
            def save():
                available = self.workspace.cached(code)
                if len(available)!=1:
                    raise OfflineError('Se requiere un único PDF descargado.')
                with open(name, 'xb') as file:
                    file.write(available[0][1])
                return 'Copia exportada como PDF legible.'
            self.perform('Guardando copia…', save)

    def attach(self):
        code = self.selected()['code']
        name = filedialog.askopenfilename(parent=self.root, filetypes=[('PDF','*.pdf')])
        if name:
            def create():
                with open(name,'rb') as file:
                    self.workspace.create(code, file.read(LIMIT+1), name)
                return 'Borrador y PDF guardados en la cola cifrada.'
            self.perform('Guardando el borrador…', create)

    def new_draft(self):
        code = self.selected()['code']
        self.perform('Guardando borrador…', lambda: self.workspace.new_draft(code) and
                     'Borrador guardado. Adjunte un PDF para ponerlo en cola.')

    def dossier_code(self):
        item = self.selected()
        if item:
            return item['code']
        selection = self.queue.selection() if self.tabs.index('current')==1 else ()
        return next((row['code'] for row in self.operations if selection and row['id']==selection[0]), None)

    def open_dossier(self, work_tab=None):
        code = self.dossier_code()
        if code:
            if work_tab is None:
                self.perform('Abriendo ficha…', lambda: self.workspace.dossier(code), self.show_dossier)
            else:
                self.perform('Abriendo trabajo documental…', lambda: self.workspace.work(code),
                             lambda data: show_work(self, self.root, data, initial_tab=work_tab))

    def show_dossier(self, data):
        item, documents, operations = data
        dialog = tk.Toplevel(self.root)
        dialog.title('TEC-SGDEA | Ficha de expediente')
        center(dialog, self.root, 920, 585)
        dialog.transient(self.root)
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=18)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text=item['code'], font=('Segoe UI', 20, 'bold'), foreground=INDIGO).pack(anchor='w')
        ttk.Label(panel, text=item['subject'] or 'Sin asunto', wraplength=830).pack(anchor='w')
        ttk.Label(panel, text='Estado en servidor: '+(item['state'] or 'Sin expediente')).pack(anchor='w')
        ttk.Label(panel, text='Versión del inventario: '+item['version']).pack(anchor='w')
        for row in operations:
            ttk.Label(panel, text=f"Operación {row['id']} · {STATES[row['state']]}").pack(anchor='w')
            if row.get('receipt') and row.get('kind') != 'sheet':
                ttk.Label(panel, text=f"Expediente web: {row['receipt']['id']}").pack(anchor='w')
            if row.get('error'):
                ttk.Label(panel, text=row['error'], wraplength=830).pack(anchor='w')
        if not operations:
            ttk.Label(panel, text='Sin operaciones locales.').pack(anchor='w')
        ttk.Label(panel, text='Documentos', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(12,4))
        table = self.make_table(panel, [('subject','Nombre',260), ('source','Origen',100),
                                        ('size','Bytes',95), ('state','Disponibilidad',150)])
        for index, doc in enumerate(documents):
            table.insert('', 'end', iid=str(index), values=(doc['name'], 'Local' if doc['source']=='local' else 'Servidor',
                         doc['bytes'] if doc['bytes'] is not None else '—',
                         'Guardado' if doc['cached'] else 'Sin descargar'))
        info = tk.StringVar(value='Seleccione un PDF para consultar su SHA-256.' if documents else 'Sin documentos.')
        ttk.Label(panel, textvariable=info, wraplength=830).pack(anchor='w')

        def selected_document():
            selection = table.selection()
            return documents[int(selection[0])] if selection else None

        def show_pdf():
            doc = selected_document()
            if not doc or not doc['cached'] or self.busy:
                return
            def display(pdf):
                if dialog.winfo_exists():
                    PdfViewer(dialog, doc['name'], pdf)
            self.perform('Verificando SHA-256 para abrir el PDF…',
                         lambda: self.workspace.preview(item['code'], doc), display)

        def refresh(_):
            doc = selected_document()
            if doc:
                info.set('SHA-256: '+doc['sha256'])
            preview.state(['!disabled'] if doc and doc['cached'] else ['disabled'])

        preview = ttk.Button(panel, text='Abrir visor PDF', command=show_pdf, style='Accent.TButton')
        preview.pack(side='left', pady=(8,0))
        preview.state(['disabled'])
        work_status = tk.StringVar()
        ttk.Label(panel, textvariable=work_status, wraplength=830).pack(anchor='w')

        def open_work(download=False):
            def loaded(data):
                if dialog.winfo_exists():
                    work_status.set('')
                    show_work(self, dialog, data)
            self.perform('Consultando trabajo documental…',
                         lambda: self.workspace.refresh_work(item['code'], True) if download
                         else self.workspace.work(item['code']), loaded,
                         lambda error: work_status.set(error) if dialog.winfo_exists() else None)

        ttk.Button(panel, text='Trabajo documental', command=open_work).pack(side='left', padx=6)
        if self.mode == 'Con sesión':
            ttk.Button(panel, text='Actualizar y guardar derivados',
                       command=lambda: open_work(True)).pack(side='left', padx=6)
        ttk.Button(panel, text='Cerrar', command=dialog.destroy).pack(side='right', pady=(8,0))
        table.bind('<<TreeviewSelect>>', refresh)
        table.bind('<Return>', lambda _: show_pdf())
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        table.focus_set()

    def go_offline(self):
        self.manual_offline = True
        self.mode = 'Sin conexión'
        self.refresh_badge()
        self.update_buttons()
        self.status.set('Modo offline manual. Use Volver a conectar para reanudar.')

    def reconnect(self):
        self.manual_offline = False
        self.synchronize()

    def logout(self):
        def end_session():
            try:
                self.workspace.lock(revoke=True)
            except OfflineError:
                return 'Espacio local bloqueado. No se pudo confirmar el cierre en el servidor.'
            return 'Sesión cerrada. Los cambios locales se conservan.'
        self.perform('Cerrando sesión…', end_session)

    def synchronize(self):
        def sync():
            Api(self.server).probe()
            if not self.workspace.api.token:
                if not self.reconnect_credentials:
                    self.workspace.lock()
                    return 'Ingrese para restablecer la sesión.'
                self.workspace.enable(*self.reconnect_credentials)
                self.reconnect_credentials = None
            rows=self.workspace.sync()
            totals={state:sum(row['state']==state for row in rows) for state in STATES}
            return f"{totals['synced']} sincronizados · {totals['pending']} pendientes · {totals['conflict']+totals['rejected']} por revisar."
        self.perform('Sincronizando. La cola permanece guardada…', sync, syncing=True)

    def close(self):
        if self.busy:
            self.status.set('Espere a que termine la operación para cerrar.')
            return
        if self.workspace:
            self.pool.submit(self.workspace.close).result()
        self.pool.shutdown(wait=False)
        self.probe_pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main(*, demo=False):
    import sys
    root = tk.Tk()
    root.withdraw()
    if not demo and sys.argv[1:] == ['--configurar-institucional']:
        try:
            from server_policy import require_admin
            require_admin()
            value = simpledialog.askstring('TEC-SGDEA · Administración', 'Servidor institucional HTTPS', parent=root)
            if value:
                configure_institutional(value)
                messagebox.showinfo('TEC-SGDEA', 'Configuración institucional guardada.', parent=root)
        except (ValueError, OSError, OfflineError) as error:
            messagebox.showerror('TEC-SGDEA', str(error), parent=root)
        finally:
            root.destroy()
        return
    try:
        server = HOSTINGER_DEMO if demo else configured_server()
    except (ValueError, OSError) as error:
        messagebox.showerror('TEC-SGDEA', str(error), parent=root)
        root.destroy()
        return
    local = Path(os.environ['LOCALAPPDATA'])
    if demo:
        profiles = {'Demostración Hostinger': (local/'TEC-SGDEA-Hostinger-Demo'/'workspace.sqlite3', server)}
        errors = []
    else:
        profiles, errors = discover(local)
    if errors:
        messagebox.showwarning('TEC-SGDEA', 'No se pudo copiar: '+', '.join(errors)+
                               '. Los almacenes originales se conservan.', parent=root)
    profile = next(iter(profiles))
    if len(profiles) > 1:
        picker = tk.Toplevel(root)
        picker.title('TEC-SGDEA | Espacio local')
        picker.geometry('450x170')
        choice = tk.StringVar(value=profile)
        accepted = tk.BooleanVar(value=False)
        panel = ttk.Frame(picker, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Seleccione el espacio local que desea abrir.').pack(anchor='w')
        dropdown = ttk.Combobox(panel, values=tuple(profiles), textvariable=choice, state='readonly')
        dropdown.pack(fill='x', pady=8)
        dropdown.focus_set()
        def open_profile(_=None):
            accepted.set(True)
            picker.destroy()
        ttk.Button(panel, text='Abrir espacio', command=open_profile).pack(anchor='e')
        picker.bind('<Return>', open_profile)
        root.wait_window(picker)
        if not accepted.get():
            root.destroy()
            return
        profile = choice.get()
    database, _ = profiles[profile]
    Desktop(root, database, server, profile)
    root.deiconify()
    root.mainloop()


if __name__ == '__main__':
    main()
