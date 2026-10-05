"""Vista unificada de automatizaciones, independiente del filtro del planificador."""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..core.repo_automations import (due_automations, in_selected_folder,
                                     inspect_repository, run_repository_automation)
from .saved_searches_panel import format_search_details
from .widgets import ScrolledTree, ToolTip, browse_into, show_text_window

COLUMNS = [("type", "Tipo", 125), ("name", "Nombre", 180),
           ("repo", "Carpeta del repositorio", 320), ("branch", "Rama / filtro", 200),
           ("auto", "Auto", 55), ("interval", "Minutos", 65),
           ("last_run", "Última ejecución", 145), ("result", "Resultado", 350)]


def visible_automations(repository_store, search_store, selected_path, show_all=False):
    records = [("repo", item) for item in repository_store.list()]
    records += [("search", item) for item in search_store.list()]
    return [(kind, item) for kind, item in records
            if show_all or in_selected_folder(item["repo_path"], selected_path)]


def format_repository_details(automation):
    lines = [
        f"Automatización: {automation['name']}",
        f"Repositorio: {automation['repo_path']}",
        f"Rama local: {automation['branch']}",
        f"Origen: {automation['remote']}/{automation['remote_branch']}",
        f"Automática: {'Sí' if automation['auto_sync'] else 'No'}",
        f"Intervalo: {automation['interval_minutes']} min",
        f"Última ejecución: {automation['last_run'] or 'Nunca'}",
        f"Resultado: {automation['last_result'] or 'Sin ejecutar'}",
    ]
    details = automation["last_details"] or {}
    for key, label in (("before", "Commit anterior"), ("target", "Commit remoto"),
                       ("after", "Commit final"), ("ahead", "Commits locales"),
                       ("behind", "Commits remotos"), ("error", "Error")):
        if key in details:
            lines.append(f"{label}: {details[key]}")
    return "\n".join(lines)


class RepositoryAutomationDialog(simpledialog.Dialog):
    def __init__(self, parent, store, repo_path="", automation=None):
        self.store = store
        self.automation = automation
        self.initial_path = repo_path
        super().__init__(parent, "Editar automatización" if automation else "Nueva automatización de repositorio")

    def body(self, parent):
        data = self.automation or {}
        self.name = tk.StringVar(value=data.get("name", ""))
        self.path = tk.StringVar(value=data.get("repo_path", self.initial_path))
        self.branch = tk.StringVar(value=data.get("branch", ""))
        self.remote = tk.StringVar(value=data.get("remote", ""))
        self.remote_branch = tk.StringVar(value=data.get("remote_branch", ""))
        self.interval = tk.StringVar(value=str(data.get("interval_minutes", 15)))
        self.auto = tk.BooleanVar(value=data.get("auto_sync", True))
        parent.grid_columnconfigure(1, weight=1)
        fields = [("Nombre", self.name), ("Repositorio", self.path),
                  ("Rama local", self.branch), ("Remoto", self.remote),
                  ("Rama remota", self.remote_branch), ("Intervalo (minutos)", self.interval)]
        self.entries = {}
        for row, (label, variable) in enumerate(fields):
            tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)
            widget = (ttk.Combobox(parent, textvariable=variable, width=55)
                      if row in (2, 3) else tk.Entry(parent, textvariable=variable, width=58))
            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            self.entries[label] = widget
        tk.Button(parent, text="Examinar", command=lambda: browse_into(
            self.entries["Repositorio"], parent=self)).grid(row=1, column=2, padx=5)
        tk.Button(parent, text="Leer ramas y seguimiento",
                  command=self.read_repository).grid(row=6, column=1, sticky="w", padx=5)
        self.entries["Rama local"].bind("<<ComboboxSelected>>", self.apply_upstream)
        tk.Checkbutton(parent, text="Activar actualización automática",
                       variable=self.auto).grid(row=7, column=1, sticky="w")
        tk.Label(parent, text="Solo fast-forward; no cambia de rama, no hace stash ni reset.\n"
                             "La rama elegida debe estar activa para poder actualizarla.",
                 justify="left", fg="#555555").grid(row=8, column=0, columnspan=3, pady=8)
        self.info = None
        if self.path.get():
            self.read_repository()
        return self.entries["Nombre"]

    def read_repository(self):
        previous_path = self.info["repo_path"] if self.info else None
        try:
            self.info = inspect_repository(self.path.get().strip())
        except Exception as error:
            self.info = None
            messagebox.showerror("Repositorio", str(error), parent=self)
            return
        self.path.set(self.info["repo_path"])
        self.entries["Rama local"]["values"] = self.info["branches"]
        self.entries["Remoto"]["values"] = self.info["remotes"]
        if previous_path and previous_path != self.info["repo_path"]:
            self.branch.set(self.info["current"])
            self.remote.set("")
            self.remote_branch.set("")
        if not self.name.get():
            import os
            self.name.set(os.path.basename(self.info["repo_path"]))
        if not self.branch.get():
            self.branch.set(self.info["current"])
        if not self.remote.get() and not self.remote_branch.get():
            self.apply_upstream()

    def apply_upstream(self, event=None):
        if self.info:
            remote, branch = self.info["upstream"].get(
                self.branch.get(), ("origin" if "origin" in self.info["remotes"] else
                                    next(iter(self.info["remotes"]), ""), self.branch.get()))
            self.remote.set(remote)
            self.remote_branch.set(branch)

    def validate(self):
        try:
            self.result = self.store.save({
                "name": self.name.get(), "repo_path": self.path.get().strip(),
                "branch": self.branch.get(), "remote": self.remote.get(),
                "remote_branch": self.remote_branch.get(), "auto_sync": self.auto.get(),
                "interval_minutes": int(self.interval.get()),
            }, self.automation["id"] if self.automation else None)
        except Exception as error:
            messagebox.showerror("Automatización", str(error), parent=self)
            return False
        return True


class AutomationsTab:
    TICK_MS = 30_000

    def __init__(self, app, notebook, store, search_store):
        self.app, self.store, self.search_store = app, store, search_store
        self.running = {}
        self.records = {}
        self.frame = tk.Frame(notebook)
        notebook.add(self.frame, text="Automatizaciones")
        toolbar = tk.Frame(self.frame)
        toolbar.pack(fill="x", padx=5, pady=5)
        tk.Label(toolbar, text="Mostrar:").pack(side=tk.LEFT)
        self.scope = tk.StringVar(value="Carpeta seleccionada")
        selector = ttk.Combobox(toolbar, textvariable=self.scope,
                                values=["Carpeta seleccionada", "Todas"], state="readonly", width=22)
        selector.pack(side=tk.LEFT, padx=5)
        selector.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        ToolTip(selector, "Filtra solo la vista: carpeta seleccionada y repositorios dentro de ella, "
                          "o todas las automatizaciones. Las tareas ocultas siguen ejecutándose.")
        tk.Button(toolbar, text="Añadir repositorio", command=self.add).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Refrescar", command=self.refresh).pack(side=tk.LEFT, padx=5)
        self.table = ScrolledTree(self.frame, COLUMNS, selectmode="browse")
        self.table.pack(fill="both", expand=True, padx=5)
        self.table.tree.bind("<Double-1>", lambda event: self.details())
        buttons = tk.Frame(self.frame)
        buttons.pack(fill="x", padx=5, pady=5)
        for text, command in (("Ejecutar ahora", self.run_selected), ("Ver detalles", self.details),
                              ("Editar", self.edit), ("Activar/Desactivar auto", self.toggle),
                              ("Cambiar intervalo", self.change_interval), ("Eliminar", self.delete)):
            tk.Button(buttons, text=text, command=command).pack(side=tk.LEFT, padx=3)
        self.help = tk.Label(self.frame, anchor="w", fg="#555555")
        self.help.pack(fill="x", padx=8, pady=5)
        app.repo_path_var.trace_add("write", lambda *args: self.refresh())
        notebook.bind("<<NotebookTabChanged>>", lambda event: self.refresh(), add="+")
        self.refresh()
        app.root.after(5_000, self.tick)

    def refresh(self):
        selected = self.table.tree.selection()
        self.table.clear()
        self.records = {}
        try:
            records = visible_automations(self.store, self.search_store, self.app.repo_path(),
                                          self.scope.get() == "Todas")
        except Exception as error:
            self.app.log(f"Error al cargar automatizaciones: {error}")
            self.help.config(text=f"Error al cargar automatizaciones: {error}")
            return
        for kind, item in records:
            iid = f"{kind}:{item['id']}"
            self.records[iid] = (kind, item)
            running = (item["id"] in self.running if kind == "repo" else
                       item["id"] in self.app.latest_tab.saved_panel.running)
            branch = (f"{item['branch']} ← {item['remote']}/{item['remote_branch']}"
                      if kind == "repo" else item["branch_regex"] or "Todas")
            self.table.insert(("Repositorio" if kind == "repo" else "Búsqueda",
                               item["name"], item["repo_path"], branch,
                               "Sí" if item["auto_sync"] else "No", item["interval_minutes"],
                               item["last_run"] or "", "Ejecutándose..." if running else
                               item["last_result"] or "Sin ejecutar"), iid=iid)
        if selected and selected[0] in self.records:
            self.table.tree.selection_set(selected[0])
        self.help.config(text=f"{len(records)} automatización(es). El filtro solo afecta a la vista. "
                              "Auto: app abierta o CLI programada; las tareas fuera de esta carpeta siguen activas.")

    def selected(self):
        selection = self.table.tree.selection()
        if not selection:
            messagebox.showwarning("Automatizaciones", "Selecciona una automatización.")
            return None
        return self.records[selection[0]]

    def _busy(self, kind, item):
        running = self.running if kind == "repo" else self.app.latest_tab.saved_panel.running
        if item["id"] in running:
            messagebox.showinfo("En ejecución", "Espera a que termine la automatización.")
            return True
        return False

    def add(self):
        RepositoryAutomationDialog(self.app.root, self.store, self.app.repo_path())
        self.refresh()

    def edit(self):
        selected = self.selected()
        if not selected:
            return
        kind, item = selected
        if self._busy(kind, item):
            return
        if kind == "repo":
            RepositoryAutomationDialog(self.app.root, self.store, automation=item)
        else:
            self.app.latest_tab.load_saved(item)
        self.refresh()

    def details(self):
        selected = self.selected()
        if selected:
            kind, item = selected
            store = self.store if kind == "repo" else self.search_store
            item = store.get(item["id"])
            if item is None:
                messagebox.showwarning("Automatizaciones", "La automatización ya no existe.")
                self.refresh()
                return
            text = format_repository_details(item) if kind == "repo" else format_search_details(item)
            show_text_window(self.app.root, item["name"], text, geometry="950x600")

    def run_selected(self):
        selected = self.selected()
        if selected:
            kind, item = selected
            if kind == "repo":
                self.run(item, manual=True)
            else:
                self.app.latest_tab.saved_panel.run(item, force=True, manual=True)
            self.refresh()

    def run(self, item, manual=False):
        if item["id"] in self.running:
            if manual:
                self._busy("repo", item)
            return
        self.app.log(f"[Automatización '{item['name']}'] iniciada...")
        self.running[item["id"]] = self.app.runner.submit(
            lambda progress, cancel: run_repository_automation(self.store, item, progress, cancel),
            on_success=lambda result: self._report(item, result, manual),
            on_error=lambda error: self._failed(item, error, manual),
            on_progress=self.app.log,
            on_finally=lambda: self._finished(item["id"]))
        self.refresh()

    def _report(self, item, result, manual):
        self.app.log(f"[Automatización '{item['name']}'] {result['text']}")
        if manual:
            record = self.store.get(item["id"])
            if record:
                show_text_window(self.app.root, item["name"], format_repository_details(record))

    def _failed(self, item, error, manual):
        self.app.log(f"[Automatización '{item['name']}'] Error: {error}")
        if manual:
            messagebox.showerror("Automatización", str(error))

    def _finished(self, automation_id):
        self.running.pop(automation_id, None)
        self.refresh()

    def tick(self):
        try:
            for item in due_automations(self.store):
                self.run(item)
            self.refresh()
        except Exception as error:
            self.app.log(f"Error en el planificador de repositorios: {error}")
        finally:
            self.app.root.after(self.TICK_MS, self.tick)

    def toggle(self):
        selected = self.selected()
        if selected:
            kind, item = selected
            store = self.store if kind == "repo" else self.search_store
            store.update(item["id"], auto_sync=not item["auto_sync"])
            self.refresh()
            self.app.latest_tab.saved_panel.refresh()

    def change_interval(self):
        selected = self.selected()
        if not selected:
            return
        kind, item = selected
        value = simpledialog.askinteger("Intervalo", "Comprobar cada (minutos):",
                                        initialvalue=item["interval_minutes"], minvalue=1, maxvalue=1440,
                                        parent=self.app.root)
        if value is not None:
            store = self.store if kind == "repo" else self.search_store
            store.update(item["id"], interval_minutes=value)
            self.refresh()
            self.app.latest_tab.saved_panel.refresh()

    def delete(self):
        selected = self.selected()
        if not selected:
            return
        kind, item = selected
        if self._busy(kind, item):
            return
        if messagebox.askyesno("Eliminar", f"¿Eliminar '{item['name']}'?\nNo se borran carpetas ni ficheros."):
            store = self.store if kind == "repo" else self.search_store
            store.delete(item["id"])
            self.refresh()
            self.app.latest_tab.saved_panel.refresh()
