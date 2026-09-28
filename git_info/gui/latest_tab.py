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
from .widgets import ScrolledTree, attach_context_menu, browse_into, copy_rows, export_rows_dialog

CHECKED, UNCHECKED = "☑", "☐"
MARK_ALL = object()
SCOPE_LABELS = {"Remotas": latest_scan.SCOPE_REMOTE, "Locales": latest_scan.SCOPE_LOCAL,
                "Todas": latest_scan.SCOPE_ALL}
SCOPE_BY_VALUE = {v: k for k, v in SCOPE_LABELS.items()}

COLUMNS = [("sel", CHECKED, 34, "center"), ("path", "Fichero", 360), ("branch", "Rama más reciente", 200),
           ("date", "Fecha", 130), ("commit", "Commit", 80), ("author", "Autor", 120),
           ("message", "Mensaje", 220), ("same", "Idéntico en", 200), ("count", "Nº ramas", 70, "center")]
HEADERS = ["Fichero", "Rama más reciente", "Fecha", "Commit", "Autor", "Mensaje",
           "Idéntico en", "Nº ramas con el fichero", "Marcado"]
EXCEL_WIDTHS = [60, 30, 18, 42, 20, 40, 40, 12, 10]


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
        self.scan_params = None    # parámetros del último escaneo correcto
        self.task = None

        self.frame = tk.Frame(notebook)
        notebook.add(self.frame, text="Últimas versiones")
        paned = ttk.PanedWindow(self.frame, orient=tk.VERTICAL)
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        top = tk.Frame(paned)
        self.saved_panel = SavedSearchesPanel(paned, app, saved_store, on_load=self.load_saved)
        paned.add(top, weight=3)
        paned.add(self.saved_panel.frame, weight=1)

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
        ttk.Combobox(box, textvariable=self.scope_var, values=list(SCOPE_LABELS), state="readonly",
                     width=10).grid(row=0, column=1, sticky="w", padx=5)
        tk.Label(box, text="Regex ramas:").grid(row=0, column=2, sticky="e")
        self.entry_branch_regex = tk.Entry(box)
        self.entry_branch_regex.grid(row=0, column=3, sticky="ew", padx=5)
        self.fetch_var = tk.BooleanVar(value=True)
        tk.Checkbutton(box, text="Hacer fetch antes", variable=self.fetch_var).grid(row=0, column=4, sticky="w")
        self.icase_var = tk.BooleanVar(value=True)
        tk.Checkbutton(box, text="Ignorar mayúsculas", variable=self.icase_var).grid(row=0, column=5, sticky="w")

        tk.Label(box, text="Regex ficheros:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.entry_path_regex = tk.Entry(box)
        self.entry_path_regex.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=(5, 0))
        self.entry_path_regex.bind("<Return>", lambda e: self.scan())
        self.button_scan = tk.Button(box, text="Escanear ramas", width=15, command=self.scan)
        self.button_scan.grid(row=1, column=4, pady=(5, 0))
        self.button_cancel = tk.Button(box, text="Cancelar", width=10, command=self.cancel, state="disabled")
        self.button_cancel.grid(row=1, column=5, pady=(5, 0))

        tk.Label(box, fg="#555555",
                 text=r"Ejemplos: \.py$   ^src/.*\.(cs|xml)$   config   (vacío = todos los ficheros). "
                      "Clic en ☐ o Espacio para marcar.").grid(row=2, column=0, columnspan=6, sticky="w")

    def _build_results(self, parent):
        self.table = ScrolledTree(parent, COLUMNS, sortable=True)
        self.table.pack(fill="both", expand=True)
        self.tree = self.table.tree
        self.tree.heading("sel", text=CHECKED, command=self.toggle_all)
        self.tree.bind("<Button-1>", self._on_click, add="+")
        self.tree.bind("<space>", lambda e: self.toggle_rows(self.tree.selection()))
        attach_context_menu(self.tree, [
            ("Marcar/desmarcar filas seleccionadas", lambda: self.toggle_rows(self.tree.selection())),
            ("Copiar filas seleccionadas", self.copy_selection),
            ("Copiar todo el listado", self.copy_all),
        ])

    def _build_marking(self, parent):
        bar = tk.Frame(parent)
        bar.pack(fill="x", pady=(5, 0))
        tk.Label(bar, text="Marcar por regex:").pack(side=tk.LEFT)
        self.entry_mark_regex = tk.Entry(bar, width=30)
        self.entry_mark_regex.pack(side=tk.LEFT, padx=5)
        for text, command in (("Marcar coincidentes", lambda: self.mark_regex(True)),
                              ("Desmarcar coincidentes", lambda: self.mark_regex(False)),
                              ("Marcar todo", lambda: self.set_all(True)),
                              ("Desmarcar todo", lambda: self.set_all(False))):
            tk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=2)
        self.label_count = tk.Label(bar, text="0 ficheros, 0 marcados")
        self.label_count.pack(side=tk.RIGHT)

    def _build_destination(self, parent):
        box = tk.LabelFrame(parent, text="Descarga a carpeta local", padx=8, pady=6)
        box.pack(fill="x", pady=5)
        box.grid_columnconfigure(1, weight=1)

        tk.Label(box, text="Carpeta destino:").grid(row=0, column=0, sticky="w")
        self.entry_dest = tk.Entry(box)
        self.entry_dest.grid(row=0, column=1, sticky="ew", padx=5)
        tk.Button(box, text="Examinar", command=lambda: browse_into(self.entry_dest)).grid(row=0, column=2)

        options = tk.Frame(box)
        options.grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self.layout_var = tk.StringVar(value=exporter.LAYOUT_REPO)
        tk.Radiobutton(options, text="Misma estructura que el repositorio", variable=self.layout_var,
                       value=exporter.LAYOUT_REPO).pack(side=tk.LEFT)
        tk.Radiobutton(options, text="Una subcarpeta por rama", variable=self.layout_var,
                       value=exporter.LAYOUT_BRANCH).pack(side=tk.LEFT, padx=10)
        self.overwrite_var = tk.BooleanVar(value=False)
        tk.Checkbutton(options, text="Sobrescribir ficheros modificados localmente",
                       variable=self.overwrite_var).pack(side=tk.LEFT, padx=10)

        actions = tk.Frame(box)
        actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        for text, command in (("Descargar marcados", lambda: self.download(checked_only=True)),
                              ("Descargar todos", lambda: self.download(checked_only=False)),
                              ("Exportar listado Excel", self.export_excel),
                              ("Guardar búsqueda...", self.save_search)):
            tk.Button(actions, text=text, width=20, command=command).pack(side=tk.LEFT, padx=3)

    def _build_status(self, parent):
        bar = tk.Frame(parent)
        bar.pack(fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT)
        self.label_status = tk.Label(bar, text="Listo.", anchor="w")
        self.label_status.pack(side=tk.LEFT, fill="x", expand=True)

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
            self.table.insert((CHECKED if entry["path"] in self.checked else UNCHECKED, entry["path"],
                               entry["branch"], entry["date"], entry["commit"][:8], entry["author"],
                               entry["message"], ", ".join(entry["same_in"]), entry["branch_count"]), iid=iid)
        self._update_count()

    # ------------------------------------------------------------- marcado
    def _update_count(self):
        self.label_count.config(text=f"{len(self.results)} ficheros, {len(self.checked)} marcados")

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
        return (e["path"], e["branch"], e["date"], e["commit"], e["author"], e["message"],
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
                    lambda summary: self._on_download_done(dest, summary), "Descargando ficheros...")

    def _on_download_done(self, dest, summary):
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
        self.scan(mark=MARK_ALL if paths is None else paths)
