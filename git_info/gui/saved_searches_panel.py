"""Panel de búsquedas guardadas y planificador de sincronización automática."""
import tkinter as tk
from tkinter import messagebox, simpledialog

from ..core.formatting import repo_short_name
from ..core.saved_searches import describe_filter, describe_selection
from ..core.sync import due_searches, run_saved_search
from .widgets import ScrolledTree, ToolTip

COLUMNS = [("name", "Nombre", 150), ("repo", "Repositorio", 130), ("filter", "Filtro", 220),
           ("selection", "Selección", 90), ("dest", "Destino", 220), ("auto", "Auto", 50, "center"),
           ("interval", "Cada (min)", 75, "center"), ("last_run", "Última ejecución", 130),
           ("last_result", "Resultado", 320)]


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
        self.table.tree.bind("<Double-1>", lambda e: self.load_selected())
        ToolTip(self.table.tree, "Selecciona una búsqueda para ejecutar, editar sus opciones, cargar sus filtros o eliminarla.")

        buttons = tk.Frame(self.frame)
        buttons.pack(fill="x", pady=(5, 0))
        for text, command, tooltip in (
                ("Ejecutar ahora", self.run_selected,
                 "Ejecuta ahora la búsqueda seleccionada y actualiza sus ficheros en destino."),
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
            self.table.insert((search["name"], repo_short_name(search["repo_path"]), describe_filter(search),
                               describe_selection(search), search["dest_dir"],
                               "Sí" if search["auto_sync"] else "No", search["interval_minutes"],
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
            on_success=lambda summary: self._report(name, summary, manual),
            on_error=lambda e: self._failed(name, e, manual),
            on_finally=lambda: self._finished(search["id"]),
        )
        self.refresh()

    def _report(self, name, summary, manual):
        self.app.log(f"[Sincronización '{name}'] {summary['text']}")
        for label, key in (("Con cambios locales", "conflicts"), ("Ya no existen", "missing"),
                           ("Errores", "errors")):
            for item in summary.get(key, [])[:20]:
                self.app.log(f"    {label}: {item}")
        if manual:
            messagebox.showinfo("Sincronización", f"{name}:\n{summary['text']}")

    def _failed(self, name, error, manual):
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
