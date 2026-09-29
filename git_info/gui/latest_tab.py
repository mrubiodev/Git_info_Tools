"""Pestaña "Últimas versiones": última versión de cada fichero entre ramas.

Permite escanear, filtrar con expresiones regulares, marcar ficheros,
descargarlos a una carpeta local, exportar el listado y guardar la búsqueda.
"""
import os
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from ..core import exporter, latest_scan
from ..core.gitcmd import Cancelled, GitError, compile_regex, fetch_all
from .dialogs import SAVE_SELECTION, SaveSearchDialog
from .saved_searches_panel import SavedSearchesPanel
from .widgets import (ScrolledTree, ToolTip, attach_context_menu, browse_into, copy_rows,
                      export_rows_dialog, show_text_window)

CHECKED, UNCHECKED = "☑", "☐"
MARK_ALL = object()
SCOPE_LABELS = {"Remotas": latest_scan.SCOPE_REMOTE, "Locales": latest_scan.SCOPE_LOCAL,
                "Todas": latest_scan.SCOPE_ALL}
SCOPE_BY_VALUE = {v: k for k, v in SCOPE_LABELS.items()}

COLUMNS = [("sel", CHECKED, 38, "center"), ("path", "Fichero", 520),
           ("branch", "Rama más reciente", 230), ("status", "Estado local", 190)]
HEADERS = ["Fichero", "Rama más reciente", "Estado local", "Fecha", "Commit", "Autor", "Mensaje",
           "Idéntico en", "Nº ramas con el fichero", "Marcado"]
EXCEL_WIDTHS = [60, 30, 24, 18, 42, 20, 40, 40, 12, 10]


def scan_job(params, progress, cancel):
    """Trabajo en segundo plano: fetch opcional + escaneo. Devuelve (resultados, ramas, aviso)."""
    warning = None
    if params["fetch"]:
        progress("git fetch --all --prune ...")
        try:
            fetch_all(params["repo_path"])
        except (GitError, subprocess.TimeoutExpired) as e:
            warning = f"fetch falló, se usan las referencias locales: {e}"
    results, branches = latest_scan.scan_latest(
        params["repo_path"], params["scope"], params["path_regex"], params["branch_regex"],
        params["ignore_case"], progress=progress, cancel=cancel,
        db_path=params.get("db_path"), parallel=params.get("parallel", False),
        max_workers=params.get("workers", 4))
    return results, branches, warning


class LatestFilesTab:
    def __init__(self, app, notebook, saved_store):
        self.app = app
        self.saved_store = saved_store
        self.results = []
        self.entries = {}          # iid -> resultado
        self.checked = set()       # rutas marcadas
        self.local_statuses = {}
        self.status_signature = None
        self.status_refresh_id = None
        self.scan_params = None    # parámetros del último escaneo correcto
        self.task = None

        self.frame = tk.Frame(notebook)
        notebook.add(self.frame, text="Últimas versiones")
        self.workflow_tabs = ttk.Notebook(self.frame)
        self.workflow_tabs.pack(fill="both", expand=True, padx=5, pady=5)
        top = tk.Frame(self.workflow_tabs)
        self.workflow_tabs.add(top, text="Explorar y descargar")
        self.saved_panel = SavedSearchesPanel(
            self.workflow_tabs, app, saved_store, on_load=self.load_saved)
        self.workflow_tabs.add(self.saved_panel.frame, text="Búsquedas guardadas")
        ToolTip(self.workflow_tabs, "Explora ficheros en la primera pestaña y administra las sincronizaciones guardadas en la segunda.")

        self._build_filters(top)
        self._build_results(top)
        self._build_marking(top)
        self._build_destination(top)
        self._build_status(top)

    # ------------------------------------------------------------------ UI
    def _build_filters(self, parent):
        box = tk.LabelFrame(parent, text="Buscar la última versión de cada fichero en todas las ramas",
                            padx=8, pady=6)
        box.pack(fill="x", pady=(0, 5))
        box.grid_columnconfigure(3, weight=1)

        tk.Label(box, text="Ramas:").grid(row=0, column=0, sticky="w")
        self.scope_var = tk.StringVar(value="Remotas")
        self.scope_combo = ttk.Combobox(box, textvariable=self.scope_var, values=list(SCOPE_LABELS),
                                        state="readonly", width=10)
        self.scope_combo.grid(row=0, column=1, sticky="w", padx=5)
        tk.Label(box, text="Regex ramas:").grid(row=0, column=2, sticky="e")
        self.entry_branch_regex = tk.Entry(box)
        self.entry_branch_regex.grid(row=0, column=3, sticky="ew", padx=5)
        self.fetch_var = tk.BooleanVar(value=True)
        self.fetch_check = tk.Checkbutton(box, text="Hacer fetch antes", variable=self.fetch_var)
        self.fetch_check.grid(row=0, column=4, sticky="w")
        self.icase_var = tk.BooleanVar(value=True)
        self.icase_check = tk.Checkbutton(box, text="Ignorar mayúsculas", variable=self.icase_var)
        self.icase_check.grid(row=0, column=5, sticky="w")

        tk.Label(box, text="Regex ficheros:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.entry_path_regex = tk.Entry(box)
        self.entry_path_regex.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=(5, 0))
        self.entry_path_regex.bind("<Return>", lambda e: self.scan())
        self.button_scan = tk.Button(box, text="Escanear ramas", width=15, command=self.scan)
        self.button_scan.grid(row=1, column=4, pady=(5, 0))
        self.button_cancel = tk.Button(box, text="Cancelar", width=10, command=self.cancel, state="disabled")
        self.button_cancel.grid(row=1, column=5, pady=(5, 0))

        self.filter_help = tk.Label(
            box, fg="#555555",
            text="1. Filtra y escanea   2. Marca los ficheros   3. Elige destino y descarga")
        self.filter_help.grid(row=2, column=0, columnspan=6, sticky="w")
        ToolTip(self.scope_combo, "Elige si buscar en ramas remotas, locales o en ambas.")
        ToolTip(self.entry_branch_regex, "Limita las ramas por expresión regular. Vacío significa todas las ramas del ámbito elegido.")
        ToolTip(self.fetch_check, "Actualiza las referencias remotas antes de escanear. Requiere conexión al servidor Git.")
        ToolTip(self.icase_check, "Aplica la búsqueda de expresiones regulares sin distinguir mayúsculas y minúsculas.")
        ToolTip(self.entry_path_regex, r"Filtra rutas con una expresión regular; por ejemplo, \.py$ o ^src/.*\.xml$. Vacío incluye todos los ficheros.")
        ToolTip(self.button_scan, "Busca en las puntas de las ramas dónde está la versión más reciente de cada fichero.")
        ToolTip(self.button_cancel, "Solicita cancelar el escaneo, la comprobación o la descarga en curso.")
        ToolTip(self.filter_help, "Flujo recomendado: escanea, revisa/selecciona los resultados y descárgalos en la carpeta indicada.")

    def _build_results(self, parent):
        self.table = ScrolledTree(parent, COLUMNS)
        self.table.pack(fill="both", expand=True)
        self.tree = self.table.tree
        self.tree.heading("sel", text=CHECKED, command=self.toggle_all)
        self.tree.bind("<Button-1>", self._on_click, add="+")
        self.tree.bind("<space>", lambda e: self.toggle_rows(self.tree.selection()))
        self.tree.bind("<Double-1>", self.show_selected_details)
        for tag, color in (("status_up_to_date", "#e6f4ea"),
                           ("status_update", "#fff4ce"),
                           ("status_local", "#fde7e9"),
                           ("status_missing", "#eeeeee"),
                           ("status_untracked", "#f0e8ff"),
                           ("status_error", "#ffd9d9")):
            self.tree.tag_configure(tag, background=color)
        attach_context_menu(self.tree, [
            ("Ver detalles del fichero", self.show_selected_details),
            ("Marcar/desmarcar filas seleccionadas", lambda: self.toggle_rows(self.tree.selection())),
            ("Copiar filas seleccionadas", self.copy_selection),
            ("Copiar todo el listado", self.copy_all),
        ])
        ToolTip(
            self.tree,
            "☐/☑ marca ficheros para descargar. Doble clic o clic derecho permite consultar todos sus detalles.\n"
            "Estados: Al día = mismo contenido; Actualización disponible = descarga antigua intacta;\n"
            "Modificado localmente = hay ediciones locales; Sin seguimiento = no figura en el manifiesto.")

    def _build_marking(self, parent):
        bar = tk.Frame(parent)
        bar.pack(fill="x", pady=(5, 0))
        tk.Label(bar, text="Marcar por regex:").pack(side=tk.LEFT)
        self.entry_mark_regex = tk.Entry(bar, width=30)
        self.entry_mark_regex.pack(side=tk.LEFT, padx=5)
        self.mark_buttons = []
        for text, command, tooltip in (
                ("Marcar coincidentes", lambda: self.mark_regex(True),
                 "Marca las rutas que coinciden con la expresión regular escrita."),
                ("Desmarcar coincidentes", lambda: self.mark_regex(False),
                 "Desmarca las rutas que coinciden con la expresión regular escrita."),
                ("Marcar todo", lambda: self.set_all(True), "Marca todos los ficheros del resultado actual."),
                ("Desmarcar todo", lambda: self.set_all(False), "Quita la marca de todos los ficheros.")):
            button = tk.Button(bar, text=text, command=command)
            button.pack(side=tk.LEFT, padx=2)
            self.mark_buttons.append(button)
            ToolTip(button, tooltip)
        self.label_count = tk.Label(bar, text="0 ficheros, 0 marcados")
        self.label_count.pack(side=tk.RIGHT)
        ToolTip(self.entry_mark_regex, "Expresión regular aplicada a la ruta del fichero para marcar o desmarcar resultados.")
        ToolTip(self.label_count, "Número de resultados encontrados y cuántos están marcados para descarga.")

    def _build_destination(self, parent):
        box = tk.LabelFrame(parent, text="Descarga a carpeta local", padx=8, pady=6)
        box.pack(fill="x", pady=5)
        box.grid_columnconfigure(1, weight=1)

        tk.Label(box, text="Carpeta destino:").grid(row=0, column=0, sticky="w")
        self.dest_var = tk.StringVar()
        self.entry_dest = tk.Entry(box, textvariable=self.dest_var)
        self.entry_dest.grid(row=0, column=1, sticky="ew", padx=5)
        self.dest_var.trace_add("write", lambda *_: self._schedule_status_refresh())
        self.button_browse = tk.Button(box, text="Examinar", command=lambda: browse_into(self.entry_dest))
        self.button_browse.grid(row=0, column=2)

        options = tk.Frame(box)
        options.grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self.layout_var = tk.StringVar(value=exporter.LAYOUT_REPO)
        self.layout_var.trace_add("write", lambda *_: self._schedule_status_refresh())
        self.layout_repo = tk.Radiobutton(
            options, text="Misma estructura que el repositorio", variable=self.layout_var,
            value=exporter.LAYOUT_REPO)
        self.layout_repo.pack(side=tk.LEFT)
        self.layout_branch = tk.Radiobutton(
            options, text="Una subcarpeta por rama", variable=self.layout_var,
            value=exporter.LAYOUT_BRANCH)
        self.layout_branch.pack(side=tk.LEFT, padx=10)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.overwrite_check = tk.Checkbutton(
            options, text="Sobrescribir ficheros modificados localmente",
            variable=self.overwrite_var)
        self.overwrite_check.pack(side=tk.LEFT, padx=10)

        actions = tk.Frame(box)
        actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.button_check = tk.Button(actions, text="Comprobar estado local", width=22,
                                      command=self.check_destination, state="disabled")
        self.button_check.pack(side=tk.LEFT, padx=3)
        self.button_details = tk.Button(actions, text="Ver detalles", width=14,
                                        command=self.show_selected_details)
        self.button_details.pack(side=tk.LEFT, padx=3)
        self.action_buttons = []
        for text, command, tooltip in (
                ("Descargar marcados", lambda: self.download(checked_only=True),
                 "Descarga únicamente los ficheros marcados. Los cambios locales se protegen según la opción elegida."),
                ("Descargar todos", lambda: self.download(checked_only=False),
                 "Descarga todos los ficheros del resultado actual."),
                ("Exportar listado Excel", self.export_excel,
                 "Exporta el listado completo, incluidos autor, commit, fecha, mensaje y ramas con contenido idéntico."),
                ("Guardar búsqueda...", self.save_search,
                 "Guarda los filtros y el destino para repetir la búsqueda o sincronizarla automáticamente.")):
            button = tk.Button(actions, text=text, width=20, command=command)
            button.pack(side=tk.LEFT, padx=3)
            self.action_buttons.append(button)
            ToolTip(button, tooltip)
        ToolTip(self.entry_dest, "Carpeta donde se guardarán los ficheros, respetando la estructura seleccionada.")
        ToolTip(self.button_browse, "Selecciona la carpeta destino mediante el explorador.")
        ToolTip(self.layout_repo, "Guarda cada fichero usando la ruta relativa original del repositorio.")
        ToolTip(self.layout_branch, "Crea una subcarpeta por rama para separar ficheros con el mismo nombre.")
        ToolTip(self.overwrite_check, "Si está desmarcado, los ficheros editados localmente no se sobrescriben.")
        ToolTip(self.button_check, "Compara cada fichero del destino con la versión actual y el manifiesto de descargas.")
        ToolTip(self.button_details, "Muestra fecha, commit, autor, mensaje y ramas donde existe el mismo contenido.")

    def _build_status(self, parent):
        bar = tk.Frame(parent)
        bar.pack(fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT)
        self.label_status = tk.Label(bar, text="Listo.", anchor="w")
        self.label_status.pack(side=tk.LEFT, fill="x", expand=True)
        ToolTip(self.progress, "Indicador de que hay una operación ejecutándose en segundo plano.")
        ToolTip(self.label_status, "Progreso, resultado o aviso de la última operación.")

    # ------------------------------------------------------- tareas en fondo
    def _set_status(self, text):
        self.label_status.config(text=text)

    def _start(self, fn, on_success, status):
        if self.task:
            messagebox.showinfo("Ocupado", "Ya hay una operación en curso en esta pestaña.")
            return
        self._set_status(status)
        self.button_scan.config(state="disabled")
        self.button_cancel.config(state="normal")
        self.button_check.config(state="disabled")
        self.progress.start(12)
        self.task = self.app.runner.submit(fn, on_success=on_success, on_error=self._on_error,
                                           on_progress=self._set_status, on_finally=self._on_finished)

    def _on_error(self, error):
        if isinstance(error, Cancelled):
            self._set_status("Operación cancelada.")
            self.app.log("Operación cancelada por el usuario.")
            return
        self._set_status(f"Error: {error}")
        self.app.log(f"Error en Últimas versiones: {error}")
        messagebox.showerror("Error", str(error))

    def _on_finished(self):
        self.task = None
        self.progress.stop()
        self.button_scan.config(state="normal")
        self.button_cancel.config(state="disabled")
        self.button_check.config(state="normal" if self.scan_params and self.results else "disabled")

    def cancel(self):
        if self.task:
            self.task.cancel()
            self._set_status("Cancelando...")

    # -------------------------------------------------------------- escaneo
    def _current_params(self):
        return {
            "repo_path": self.app.repo_path(),
            "scope": SCOPE_LABELS[self.scope_var.get()],
            "path_regex": self.entry_path_regex.get().strip(),
            "branch_regex": self.entry_branch_regex.get().strip(),
            "ignore_case": self.icase_var.get(),
            "fetch": self.fetch_var.get(),
            "db_path": getattr(self.app, 'db_path', None),
            "parallel": getattr(self.app, 'parallel_var', tk.BooleanVar(value=False)).get(),
            "workers": getattr(self.app, 'workers_var', tk.IntVar(value=4)).get(),
        }

    def scan(self, mark=None):
        """`mark`: rutas a marcar tras el escaneo, MARK_ALL para todas o None para ninguna."""
        params = self._current_params()
        if not params["repo_path"]:
            messagebox.showwarning("Advertencia", "Por favor, selecciona la ruta del repositorio Git.")
            return
        if not os.path.isdir(params["repo_path"]):
            messagebox.showerror("Error", "La ruta especificada no existe.")
            return
        try:
            compile_regex(params["path_regex"], params["ignore_case"])
            compile_regex(params["branch_regex"], params["ignore_case"])
        except ValueError as e:
            messagebox.showerror("Expresión regular", str(e))
            return
        self.app.log(f"\nEscaneando últimas versiones en '{params['repo_path']}' "
                     f"(ramas: {self.scope_var.get()}, ficheros: '{params['path_regex'] or '*'}', "
                     f"regex ramas: '{params['branch_regex'] or '*'}')...")
        self._start(lambda progress, cancel: scan_job(params, progress, cancel),
                    lambda result: self._on_scan_done(params, result, mark), "Escaneando ramas...")

    def _on_scan_done(self, params, result, mark=None):
        results, branches, warning = result
        self.scan_params = params
        self.results = results
        self.local_statuses = {}
        self.status_signature = None
        paths = {r["path"] for r in results}
        if mark is MARK_ALL:
            self.checked = paths
        else:
            self.checked = set(mark) & paths if mark else set()
        self._populate()
        text = f"{len(results)} ficheros encontrados en {len(branches)} ramas."
        if warning:
            text += f" Aviso: {warning}"
            self.app.log(f"Aviso: {warning}")
        self._set_status(text)
        self.app.log(text)
        self.app.select_tab(self.frame)

    def _populate(self):
        self.table.clear()
        self.entries = {}
        for i, entry in enumerate(self.results):
            iid = str(i)
            self.entries[iid] = entry
            status = self._status_for(entry["path"])
            status_tag = self._status_tag(status)
            self.table.insert(
                (CHECKED if entry["path"] in self.checked else UNCHECKED, entry["path"],
                 entry["branch"], status), iid=iid,
                tags=(status_tag,) if status_tag else ())
        self._update_count()

    @staticmethod
    def _status_tag(status):
        return {
            exporter.STATUS_UP_TO_DATE: "status_up_to_date",
            exporter.STATUS_UPDATE_AVAILABLE: "status_update",
            exporter.STATUS_LOCAL_MODIFIED: "status_local",
            exporter.STATUS_MISSING: "status_missing",
            exporter.STATUS_UNTRACKED: "status_untracked",
            exporter.STATUS_ERROR: "status_error",
        }.get(status, "")

    def _current_status_signature(self, dest=None, layout=None):
        dest = self.entry_dest.get().strip() if dest is None else dest
        layout = self.layout_var.get() if layout is None else layout
        normalized = os.path.normcase(os.path.abspath(dest)) if dest else ""
        return normalized, layout

    def _status_for(self, path):
        if self.status_signature != self._current_status_signature():
            return exporter.STATUS_UNCHECKED
        return self.local_statuses.get(path, exporter.STATUS_UNCHECKED)

    def _refresh_status_column(self):
        for iid, entry in self.entries.items():
            status = self._status_for(entry["path"])
            self.tree.set(iid, "status", status)
            status_tag = self._status_tag(status)
            self.tree.item(iid, tags=(status_tag,) if status_tag else ())
        if self.status_signature is not None and self.status_signature != self._current_status_signature():
            self._set_status("Estado local pendiente de comprobar para este destino y estructura.")

    def _schedule_status_refresh(self):
        if self.status_refresh_id:
            self.app.root.after_cancel(self.status_refresh_id)
        self.status_refresh_id = self.app.root.after(200, self._run_status_refresh)

    def _run_status_refresh(self):
        self.status_refresh_id = None
        self._refresh_status_column()

    def check_destination(self):
        if not self.scan_params or not self.results:
            messagebox.showwarning("Advertencia", "Primero escanea las ramas.")
            return
        dest = self.entry_dest.get().strip()
        if not dest:
            messagebox.showwarning("Advertencia", "Selecciona la carpeta destino.")
            return
        layout = self.layout_var.get()
        signature = self._current_status_signature(dest, layout)
        self._start(
            lambda progress, cancel: exporter.inspect_entries(
                dest, self.results, layout, progress=progress, cancel=cancel),
            lambda result: self._on_status_checked(signature, result),
            "Comprobando versiones en la carpeta destino...")

    def _on_status_checked(self, signature, result):
        if signature != self._current_status_signature():
            self._set_status("La carpeta o estructura cambió durante la comprobación; vuelve a comprobar.")
            return
        self.local_statuses = result["statuses"]
        self.status_signature = signature
        self._refresh_status_column()
        counts = {}
        for status in self.local_statuses.values():
            counts[status] = counts.get(status, 0) + 1
        summary = ", ".join(f"{count} {status.lower()}" for status, count in counts.items())
        self._set_status(summary or "No hay ficheros para comprobar.")
        for error in result["errors"]:
            self.app.log(f"Error al comprobar fichero: {error}")

    # ------------------------------------------------------------- marcado
    def _update_count(self):
        self.label_count.config(text=f"{len(self.results)} ficheros, {len(self.checked)} marcados")

    def show_selected_details(self, event=None):
        selection = self.tree.selection()
        if not selection and event is not None:
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
                selection = (iid,)
        if not selection:
            messagebox.showwarning("Detalles", "Selecciona un fichero para ver sus detalles.")
            return

        entry = self.entries[selection[0]]
        same_in = ", ".join(entry["same_in"]) or "Ninguna otra rama"
        details = (
            f"Fichero: {entry['path']}\n"
            f"Rama con la versión más reciente: {entry['branch']}\n"
            f"Estado local: {self._status_for(entry['path'])}\n"
            f"Fecha del último cambio: {entry['date']}\n"
            f"Commit: {entry['commit']}\n"
            f"Autor: {entry['author']}\n"
            f"Mensaje: {entry['message']}\n"
            f"Contenido idéntico en: {same_in}\n"
            f"Ramas donde existe: {entry['branch_count']}")
        show_text_window(self.app.root, f"Detalles del fichero: {entry['path']}", details,
                         geometry="900x420")

    def _refresh_marks(self, iids=None):
        for iid in (self.entries if iids is None else iids):
            path = self.entries[iid]["path"]
            self.tree.set(iid, "sel", CHECKED if path in self.checked else UNCHECKED)
        self._update_count()

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            iid = self.tree.identify_row(event.y)
            if iid:
                self.toggle_rows([iid])
                return "break"
        return None

    def toggle_rows(self, iids):
        for iid in iids:
            path = self.entries[iid]["path"]
            self.checked.symmetric_difference_update({path})
        self._refresh_marks(iids)

    def set_all(self, value):
        self.checked = {e["path"] for e in self.results} if value else set()
        self._refresh_marks()

    def toggle_all(self):
        self.set_all(len(self.checked) < len(self.results))

    def mark_regex(self, value):
        try:
            rx = compile_regex(self.entry_mark_regex.get().strip(), self.icase_var.get())
        except ValueError as e:
            messagebox.showerror("Expresión regular", str(e))
            return
        if rx is None:
            messagebox.showwarning("Advertencia", "Escribe una expresión regular para marcar.")
            return
        matched = {e["path"] for e in self.results if rx.search(e["path"])}
        if value:
            self.checked |= matched
        else:
            self.checked -= matched
        self._refresh_marks()
        self._set_status(f"{len(matched)} ficheros coinciden con la expresión.")

    # ------------------------------------------------------------ acciones
    def _row(self, iid):
        e = self.entries[iid]
        return (e["path"], e["branch"], self._status_for(e["path"]), e["date"], e["commit"],
                e["author"], e["message"],
                ", ".join(e["same_in"]), e["branch_count"], "Sí" if e["path"] in self.checked else "No")

    def copy_selection(self):
        copy_rows(self.app.root, HEADERS, [self._row(i) for i in self.tree.selection()],
                  "Por favor, selecciona al menos una fila.")

    def copy_all(self):
        copy_rows(self.app.root, HEADERS, [self._row(i) for i in self.tree.get_children()],
                  "No hay datos para copiar.")

    def export_excel(self):
        export_rows_dialog([self._row(i) for i in self.tree.get_children()], "Últimas versiones",
                           HEADERS, EXCEL_WIDTHS, log=self.app.log,
                           log_message="Listado de últimas versiones exportado a: {path}")

    def _validated_destination(self):
        dest = self.entry_dest.get().strip()
        if not dest:
            messagebox.showwarning("Advertencia", "Selecciona la carpeta destino.")
            return None
        if exporter.is_inside(dest, self.scan_params["repo_path"]) and not messagebox.askyesno(
                "Carpeta destino", "La carpeta destino está dentro del repositorio analizado.\n"
                                   "Los ficheros aparecerán como cambios en ese repositorio. ¿Continuar?"):
            return None
        return dest

    def download(self, checked_only):
        if not self.scan_params:
            messagebox.showwarning("Advertencia", "Primero escanea las ramas.")
            return
        entries = [e for e in self.results if e["path"] in self.checked] if checked_only else list(self.results)
        if not entries:
            messagebox.showwarning("Advertencia", "No hay ficheros marcados." if checked_only
                                   else "No hay ficheros en el listado.")
            return
        dest = self._validated_destination()
        if not dest:
            return
        repo, layout, overwrite = self.scan_params["repo_path"], self.layout_var.get(), self.overwrite_var.get()
        self.app.log(f"Descargando {len(entries)} ficheros a '{dest}'...")
        self._start(lambda progress, cancel: exporter.export_entries(repo, entries, dest, layout, overwrite,
                                                                     progress, cancel),
                    lambda summary: self._on_download_done(dest, layout, summary),
                    "Descargando ficheros...")

    def _on_download_done(self, dest, layout, summary):
        text = exporter.summary_text(summary)
        self._set_status(text)
        self.app.log(f"Descarga en '{dest}': {text}")
        details = []
        for label, key in (("Con cambios locales (no sobrescritos)", "conflicts"), ("Errores", "errors")):
            items = summary.get(key, [])
            for item in items[:20]:
                self.app.log(f"    {label}: {item}")
            if items:
                details.append(f"\n{label}:\n  " + "\n  ".join(items[:10]) +
                               (f"\n  ... (+{len(items) - 10} más, ver Consola)" if len(items) > 10 else ""))
        messagebox.showinfo("Descarga completada", f"{text}\n\nDestino: {dest}" + "".join(details))
        signature = self._current_status_signature(dest, layout)
        self.app.root.after_idle(
            lambda: self.check_destination()
            if signature == self._current_status_signature() else None)

    # ---------------------------------------------------- búsquedas guardadas
    def save_search(self):
        if not self.scan_params:
            messagebox.showwarning("Advertencia", "Primero escanea las ramas para definir la búsqueda.")
            return
        dest = self._validated_destination()
        if not dest:
            return
        answer = SaveSearchDialog.ask(self.app.root, total=len(self.results), checked=len(self.checked))
        if not answer:
            return
        if self.saved_store.get(answer["name"]) and not messagebox.askyesno(
                "Guardar búsqueda", f"Ya existe una búsqueda '{answer['name']}'. ¿Reemplazarla?"):
            return
        params = self.scan_params
        search = self.saved_store.save({
            "name": answer["name"], "repo_path": params["repo_path"], "scope": params["scope"],
            "path_regex": params["path_regex"], "branch_regex": params["branch_regex"],
            "ignore_case": params["ignore_case"], "fetch_before": params["fetch"],
            "selected_paths": sorted(self.checked) if answer["mode"] == SAVE_SELECTION else None,
            "dest_dir": dest, "layout": self.layout_var.get(), "overwrite_local": self.overwrite_var.get(),
            "auto_sync": answer["auto_sync"], "interval_minutes": answer["interval_minutes"],
        })
        self.app.log(f"Búsqueda guardada: '{search['name']}' ({'auto cada ' + str(search['interval_minutes']) + ' min' if search['auto_sync'] else 'manual'}).")
        self.saved_panel.refresh()

    def load_saved(self, search):
        self.app.set_repo_path(search["repo_path"])
        self.scope_var.set(SCOPE_BY_VALUE.get(search["scope"], "Remotas"))
        for entry, value in ((self.entry_path_regex, search["path_regex"]),
                             (self.entry_branch_regex, search["branch_regex"]),
                             (self.entry_dest, search["dest_dir"])):
            entry.delete(0, tk.END)
            entry.insert(0, value or "")
        self.icase_var.set(search["ignore_case"])
        self.fetch_var.set(search["fetch_before"])
        self.layout_var.set(search["layout"])
        self.overwrite_var.set(search["overwrite_local"])
        paths = search["selected_paths"]
        self.workflow_tabs.select(0)
        self.scan(mark=MARK_ALL if paths is None else paths)
