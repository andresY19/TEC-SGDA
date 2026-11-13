"""Raster-only PDF viewing. Document bytes and rendered pages stay in memory."""
from contextlib import closing
import math
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk
import pypdfium2 as pdfium

from workspace import OfflineError


def center(window, parent, width, height):
    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    window.geometry(f'{width}x{height}{x:+d}{y:+d}')


def rasterize(data, index, pixels):
    try:
        with pdfium.PdfDocument(data) as document:
            total = len(document)
            if not 0 <= index < total:
                raise OfflineError('Página fuera del documento.')
            with closing(document[index]) as page:
                width, height = page.get_size()
                if not all(math.isfinite(x) and x > 0 for x in (width, height)):
                    raise OfflineError('Dimensiones de página inválidas.')
                scale = min(pixels, 1600) / max(width, height)
                with closing(page.render(scale=scale, draw_annots=False)) as bitmap:
                    return bitmap.to_pil().copy(), total
    except (pdfium.PdfiumError, ValueError, OverflowError) as error:
        raise OfflineError('PDF dañado, cifrado o incompatible con el visor.') from error


class PdfViewer:
    def __init__(self, parent, name, data):
        self.data, self.index, self.total, self.zoom = data, 0, 0, 800
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title('TEC-SGDEA | Visor PDF')
        center(self.window, parent, 850, 650)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', self.close)
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=name, wraplength=790).pack(anchor='w')
        controls = ttk.Frame(frame)
        controls.pack(fill='x', pady=5)
        self.previous = ttk.Button(controls, text='Anterior', command=lambda: self.step(-1))
        self.next = ttk.Button(controls, text='Siguiente', command=lambda: self.step(1))
        self.previous.pack(side='left')
        self.next.pack(side='left')
        ttk.Button(controls, text='Reducir', command=lambda: self.resize(-200)).pack(side='left')
        ttk.Button(controls, text='Ampliar', command=lambda: self.resize(200)).pack(side='left')
        ttk.Button(controls, text='Cerrar', command=self.close).pack(side='right')
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status).pack(anchor='w')
        self.canvas = tk.Canvas(frame, bg='#E5E8F4', highlightthickness=0)
        vertical = ttk.Scrollbar(frame, command=self.canvas.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)
        self.window.bind('<Left>', lambda _: self.step(-1))
        self.window.bind('<Right>', lambda _: self.step(1))
        self.canvas.bind('<MouseWheel>', lambda event: self.canvas.yview_scroll(-int(event.delta/120), 'units'))
        self.canvas.focus_set()
        self.render()

    def step(self, direction):
        if 0 <= self.index + direction < self.total:
            self.index += direction
            self.render()

    def resize(self, delta):
        self.zoom = max(400, min(1600, self.zoom + delta))
        self.render()

    def render(self):
        self.canvas.delete('all')
        self.image = None
        try:
            image, self.total = rasterize(self.data, self.index, self.zoom)
            self.image = ImageTk.PhotoImage(image, master=self.window)
            self.canvas.create_image(8, 8, image=self.image, anchor='nw')
            self.canvas.configure(scrollregion=(0, 0, image.width+16, image.height+16))
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.status.set(f'Página {self.index+1} de {self.total} · Vista local')
        except OfflineError as error:
            self.status.set(str(error))
        self.previous.state(['!disabled'] if self.index > 0 else ['disabled'])
        self.next.state(['!disabled'] if self.index+1 < self.total else ['disabled'])

    def close(self, _=None):
        self.data = self.image = None
        self.window.destroy()
        self.parent.grab_set()
        self.parent.focus_set()
