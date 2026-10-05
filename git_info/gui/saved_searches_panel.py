"""Panel de búsquedas guardadas y planificador de sincronización automática."""
import tkinter as tk
from tkinter import messagebox, simpledialog

from ..core.formatting import repo_short_name
from ..core.saved_searches import describe_filter, describe_selection
from ..core.sync import due_searches, run_saved_search
from .widgets import ScrolledTree, ToolTip, attach_context_menu, show_text_window

COLUMNS = [("name", "Nombre", 220), ("repo", "Repositorio", 170),
           ("auto", "Auto", 65, "center"), ("last_run", "Última ejecución", 150),
           ("last_result", "Resultado", 350)]


def format_search_details(search):
    details = search["last_details"]
    lines = [
        f"Búsqueda: {search['name']}",
        f"Repositorio: {search['repo_path']}",
        f"Ámbito: {search['scope']}",
        f"Filtro: {describe_filter(search)}",
        f"Selección: {describe_selection(search)}",
        f"Destino: {search['dest_dir']}",
        f"Estructura: {search['layout']}",
        f"Automática: {'Sí' if search['auto_sync'] else 'No'} (cada {search['interval_minutes']} min)",
        f"Última ejecución: {search['last_run'] or 'Nunca'}",
        f"Resultado: {search['last_result'] or 'Sin ejecutar'}",
    ]
    if details is None:
        return "\n".join(lines + ["", "No hay detalles de ejecución registrados."])
    if details.get("error"):
        lines.extend(["", "Error de ejecución:", details["error"]])
    if details.get("note"):
        lines.extend(["", details["note"]])
    groups = (
        ("Ficheros descargados", "downloaded"),
        ("Sin cambios", "unchanged"),
        ("Conflictos locales (no sobrescritos)", "conflicts"),
        ("Ficheros ya no presentes", "missing"),
        ("Errores por fichero", "errors"),
        ("Avisos", "warnings"),
    )
    for label, key in groups:
        items = details.get(key, [])
        if items:
            lines.extend(["", f"{label} ({len(items)}):"])
            for item in items:
                if key == "downloaded":
                    lines.append(
                        f"  {item['target']}  ←  {item['path']} "
                        f"[{item['branch']}, commit {item['commit']}]")
                else:
                    lines.append(f"  {item}")
    return "\n".join(lines)


class SavedSearchesPanel:
    TICK_MS = 30_000
    FIRST_TICK_MS = 5_000

    def __init__(self, parent, app, store, on_load):
        self.app = app
        self.store = store
        self.on_load = on_load
        self.running = {}   # id de búsqueda -> Task
        self.searches = {}  # iid -> búsqueda

        self.frame = tk.LabelFrame(parent, text="Búsquedas guardadas y sincronización automática", padx=5, pady=5)
        self.table = ScrolledTree(self.frame, COLUMNS, selectmode="browse", height=5)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<Double-1>", self.show_details)
        self.context_menu = attach_context_menu(self.table.tree, [
            ("Ver detalles y ficheros descargados", self.show_details),
            ("Ejecutar ahora", self.run_selected),
            ("Cargar en pantalla", self.load_selected),
        ])
        self.table.tree.bind("<Button-3>", self._show_context_menu)
        ToolTip(self.table.tree, "Doble clic o clic derecho: resultado completo, origen de las descargas y errores.")

        buttons = tk.Frame(self.frame)
        buttons.pack(fill="x", pady=(5, 0))
        for text, command, tooltip in (
                ("Ejecutar ahora", self.run_selected,
                 "Ejecuta la búsqueda seleccionada en cualquier momento, aunque las ramas no hayan cambiado."),
                ("Ver detalles", self.show_details,
                 "Muestra opciones, ficheros descargados y su origen, conflictos y errores de la última ejecución."),
                ("Activar/Desactivar auto", self.toggle_auto,
                 "Activa o pausa la sincronización periódica de la búsqueda seleccionada."),
                ("Cambiar intervalo", self.change_interval,
                 "Cambia cuántos minutos espera la aplicación entre sincronizaciones automáticas."),
                ("Cargar en pantalla", self.load_selected,
                 "Copia sus filtros y destino a «Explorar y descargar» para revisarlos."),
                ("Eliminar", self.delete_selected,
                 "Elimina la búsqueda guardada; no elimina los ficheros ya descargados."),
                ("Refrescar", self.refresh,
                 "Vuelve a leer de la base de datos las búsquedas y sus últimos resultados.")):
            button = tk.Button(buttons, text=text, command=command)
            button.pack(side=tk.LEFT, padx=3)
            ToolTip(button, tooltip)
        self.auto_help = tk.Label(
            buttons, fg="#555555",
            text="Auto funciona con la app abierta; sin abrirla: main.py --sync-all")
        self.auto_help.pack(side=tk.RIGHT)
        ToolTip(self.auto_help, "Para sincronizar sin la interfaz, programa «python main.py --sync-all» en el Programador de tareas de Windows.")

        self.refresh()
        self.app.root.after(self.FIRST_TICK_MS, self._tick)

    def refresh(self):
        selected = self._selected(warn=False)
        self.table.clear()
        self.searches = {}
        try:
            searches = self.store.list()
        except Exception as e:
            self.app.log(f"Error al cargar las búsquedas guardadas: {e}")
            return
        for search in searches:
            iid = str(search["id"])
            self.searches[iid] = search
            result = "(ejecutándose...)" if search["id"] in self.running else (search["last_result"] or "")
            self.table.insert((search["name"], repo_short_name(search["repo_path"]),
                               "Sí" if search["auto_sync"] else "No",
                               search["last_run"] or "", result), iid=iid)
        if selected and str(selected["id"]) in self.searches:
            self.table.tree.selection_set(str(selected["id"]))

    def _selected(self, warn=True):
        selection = self.table.tree.selection()
        if not selection:
            if warn:
                messagebox.showwarning("Advertencia", "Selecciona una búsqueda guardada.")
            return None
        return self.searches.get(selection[0])

    def run_selected(self):
        search = self._selected()
        if search:
            self.run(search, force=True, manual=True)

    def _show_context_menu(self, event):
        iid = self.table.tree.identify_row(event.y)
        if not iid:
            return
        self.table.tree.selection_set(iid)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def show_details(self, event=None):
        if event is not None:
            iid = self.table.tree.identify_row(event.y)
            if iid:
                self.table.tree.selection_set(iid)
        search = self._selected()
        if search:
            show_text_window(self.app.root, f"Búsqueda guardada: {search['name']}",
                             format_search_details(search), geometry="950x600")

    def run(self, search, force=False, manual=False):
        if search["id"] in self.running:
            if manual:
                messagebox.showinfo("En ejecución", f"'{search['name']}' ya se está ejecutando.")
            return
        name = search["name"]
        self.app.log(f"[Sincronización '{name}'] iniciada{' (forzada)' if force else ''}...")
        self.running[search["id"]] = self.app.runner.submit(
            lambda progress, cancel: run_saved_search(
                self.store, search, force, progress, cancel,
                parallel=getattr(self.app, 'parallel_var', tk.BooleanVar(value=False)).get(),
                max_workers=getattr(self.app, 'workers_var', tk.IntVar(value=4)).get()
            ),
            on_success=lambda summary: self._report(search, summary, manual),
            on_error=lambda e: self._failed(search, e, manual),
            on_finally=lambda: self._finished(search["id"]),
        )
        self.refresh()

    def _report(self, search, summary, manual):
        name = search["name"]
        self.app.log(f"[Sincronización '{name}'] {summary['text']}")
        for item in summary.get("downloaded", []):
            self.app.log(f"    Descargado: {item['target']} ← {item['branch']} ({item['commit']})")
        for label, key in (("Con cambios locales", "conflicts"), ("Ya no existen", "missing"),
                           ("Errores", "errors")):
            for item in summary.get(key, [])[:20]:
                self.app.log(f"    {label}: {item}")
        if manual:
            self.refresh()
            self.table.tree.selection_set(str(search["id"]))
            self.show_details()

    def _failed(self, search, error, manual):
        name = search["name"]
        self.app.log(f"[Sincronización '{name}'] Error: {error}")
        if manual:
            messagebox.showerror("Sincronización", f"{name}:\n{error}")

    def _finished(self, search_id):
        self.running.pop(search_id, None)
        self.refresh()

    def _tick(self):
        try:
            for search in due_searches(self.store):
                self.run(search)
        except Exception as e:
            self.app.log(f"Error en el planificador de sincronización: {e}")
        finally:
            self.app.root.after(self.TICK_MS, self._tick)

    def toggle_auto(self):
        search = self._selected()
        if search:
            self.store.update(search["id"], auto_sync=not search["auto_sync"])
            self.refresh()

    def change_interval(self):
        search = self._selected()
        if not search:
            return
        value = simpledialog.askinteger("Intervalo", f"Comprobar '{search['name']}' cada (minutos):",
                                        initialvalue=search["interval_minutes"], minvalue=1, maxvalue=1440,
                                        parent=self.app.root)
        if value:
            self.store.update(search["id"], interval_minutes=value)
            self.refresh()

    def load_selected(self):
        search = self._selected()
        if search:
            self.on_load(search)

    def delete_selected(self):
        search = self._selected()
        if search and messagebox.askyesno("Eliminar", f"¿Eliminar la búsqueda guardada '{search['name']}'?\n"
                                                      "Los ficheros ya descargados no se borran."):
            self.store.delete(search["id"])
            self.refresh()
