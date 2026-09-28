"""Widgets y utilidades de interfaz reutilizables entre pestañas."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..core import excel


def _sort_key(value):
    try:
        return (0, float(value))
    except (TypeError, ValueError):
        return (1, str(value).lower())


class ScrolledTree(tk.Frame):
    """Treeview de columnas con barras de desplazamiento.

    `columns`: lista de tuplas (id, cabecera, ancho[, anchor]).
    """

    def __init__(self, parent, columns, selectmode="extended", sortable=False, height=None):
        super().__init__(parent)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        options = {"height": height} if height else {}
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings",
                                 selectmode=selectmode, **options)
        self._descending = {}
        for column in columns:
            cid, heading, width = column[:3]
            anchor = column[3] if len(column) > 3 else "w"
            if sortable:
                self.tree.heading(cid, text=heading, command=lambda c=cid: self.sort_by(c))
            else:
                self.tree.heading(cid, text=heading)
            self.tree.column(cid, width=width, anchor=anchor)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll_y = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

    def clear(self):
        self.tree.delete(*self.tree.get_children())

    def insert(self, values, iid=None, tags=()):
        return self.tree.insert("", "end", iid=iid, values=values, tags=tags)

    def rows(self, items=None):
        items = self.tree.get_children() if items is None else items
        return [self.tree.item(i)['values'] for i in items]

    def selected_rows(self):
        return self.rows(self.tree.selection())

    def sort_by(self, column):
        descending = not self._descending.get(column, True)
        items = [(self.tree.set(i, column), i) for i in self.tree.get_children()]
        items.sort(key=lambda t: _sort_key(t[0]), reverse=descending)
        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)
        self._descending[column] = descending


def attach_context_menu(widget, entries):
    """`entries`: lista de (etiqueta, comando) o None para un separador."""
    menu = tk.Menu(widget, tearoff=0)
    for entry in entries:
        if entry is None:
            menu.add_separator()
        else:
            menu.add_command(label=entry[0], command=entry[1])

    def popup(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", popup)
    return menu


def copy_rows(root, headers, rows, empty_message):
    """Copia filas al portapapeles separadas por tabuladores."""
    if not rows:
        messagebox.showwarning("Advertencia", empty_message)
        return False
    lines = ["\t".join(headers)] + ["\t".join(str(v) for v in row) for row in rows]
    root.clipboard_clear()
    root.clipboard_append("\n".join(lines))
    root.update()
    messagebox.showinfo("Copiado", f"{len(rows)} fila(s) copiada(s) al portapapeles.")
    return True


def export_rows_dialog(rows, sheet_title, headers, widths=None, row_color=None, log=None,
                       log_message="Datos exportados a: {path}"):
    """Pide destino y guarda las filas como XLSX, informando al usuario."""
    if not rows:
        messagebox.showwarning("Advertencia", "No hay datos para exportar.")
        return None
    path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                        filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                                        title="Guardar como Excel")
    if not path:
        return None
    try:
        excel.write_table(path, sheet_title, headers, rows, widths, row_color)
        messagebox.showinfo("Éxito", f"Datos exportados exitosamente a:\n{path}")
        if log:
            log(log_message.format(path=path))
        return path
    except Exception as e:
        messagebox.showerror("Error", f"Error al exportar a Excel: {e}")
        if log:
            log(f"Error al exportar: {e}")
        return None


def show_text_window(root, title, text, geometry="800x600"):
    window = tk.Toplevel(root)
    window.title(title)
    window.geometry(geometry)
    text_widget = tk.Text(window, wrap="word", font=("Consolas", 10))
    text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    scrollbar = tk.Scrollbar(window, command=text_widget.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.config(yscrollcommand=scrollbar.set)
    text_widget.insert("1.0", text)
    text_widget.config(state="disabled")
    return window


def browse_into(entry, **options):
    """Abre el selector de carpetas y escribe el resultado en `entry`."""
    directory = filedialog.askdirectory(**options)
    if directory:
        entry.delete(0, tk.END)
        entry.insert(0, directory)
    return directory
