"""Versión ligera de la GUI: solo automatizaciones (repositorios y búsquedas guardadas).

Pensada para dejarla abierta en segundo plano: ejecuta el planificador, permite
gestionar las automatizaciones y muestra un registro, sin las pestañas de análisis.
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .. import DEFAULT_DB_PATH, __author__, __proyect__, __version__
from ..core.repo_automations import RepositoryAutomationStore
from ..core.saved_searches import SavedSearchStore
from .automations_tab import AutomationsTab
from .background import BackgroundRunner
from .console_tab import ConsoleTab
from .credentials import CredentialPrompter
from .saved_searches_panel import SavedSearchesPanel
from .widgets import ToolTip, browse_into


class _SavedSearchesHost:
    """Sustituye a la pestaña «Últimas versiones»: solo aporta el ejecutor de búsquedas guardadas."""

    def __init__(self, app, parent, store):
        self.app = app
        # Panel sin mostrar: reutiliza su ejecución y su planificador automático.
        self.saved_panel = SavedSearchesPanel(parent, app, store, on_load=self.load_saved)

    def load_saved(self, search):
        messagebox.showinfo(
            "Búsqueda guardada",
            f"La edición de filtros y destino de '{search['name']}' está en la versión completa "
            "(pestaña «Explorar y descargar»).\n\nAquí puedes ejecutarla, activar/desactivar auto, "
            "cambiar el intervalo, la política si falla fetch o eliminarla.",
            parent=self.app.root)


class LiteAutomationsApp:
    def __init__(self, root, db_path=DEFAULT_DB_PATH):
        self.root = root
        self.root.title(f"{__proyect__} Lite - Automatizaciones - v{__version__} by {__author__}")
        self.root.geometry("1250x650")
        self.db_path = db_path
        self.saved_store = SavedSearchStore(db_path)
        self.automation_store = RepositoryAutomationStore(db_path)
        self.saved_store.init()
        self.automation_store.init()
        self.runner = BackgroundRunner(root)
        self.credentials = CredentialPrompter(self)
        self.parallel_var = tk.BooleanVar(value=False)
        self.workers_var = tk.IntVar(value=4)

        self._build_top_bar()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        hidden = tk.Frame(root)
        self.console = ConsoleTab(self.notebook)
        self.latest_tab = _SavedSearchesHost(self, hidden, self.saved_store)
        self.automations_tab = AutomationsTab(self, self.notebook, self.automation_store, self.saved_store)
        self.automations_tab.scope.set("Todas")
        self.automations_tab.refresh()
        self.notebook.insert(0, self.automations_tab.frame)
        self.notebook.select(self.automations_tab.frame)
        if sys.platform == "win32":
            icon = Path(__file__).resolve().parents[2] / "res" / "app_icon.ico"
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError as error:
                self.log(f"No se pudo cargar el icono de la aplicación: {error}")
        self.log(f"Modo Lite iniciado. Base de datos: {db_path}")

    def _build_top_bar(self):
        top = tk.Frame(self.root, padx=10, pady=8)
        top.pack(fill="x")
        top.grid_columnconfigure(1, weight=1)
        tk.Label(top, text="Carpeta (filtro y alta):").grid(row=0, column=0, padx=5, sticky="w")
        self.repo_path_var = tk.StringVar()
        self.entry_path = tk.Entry(top, textvariable=self.repo_path_var)
        self.entry_path.grid(row=0, column=1, padx=5, sticky="ew")
        browse = tk.Button(top, text="Examinar", command=lambda: browse_into(self.entry_path))
        browse.grid(row=0, column=2, padx=5)
        ToolTip(self.entry_path, "Carpeta usada al añadir un repositorio y por el filtro «Carpeta seleccionada».")

    # ---- API común que usan las pestañas reutilizadas
    def display_message(self, message, append=False):
        self.console.write(message, append)

    def log(self, message):
        self.display_message(message, append=True)

    def repo_path(self):
        return self.entry_path.get().strip()

    def set_repo_path(self, path):
        self.repo_path_var.set(path)

    def select_tab(self, frame):
        self.notebook.select(frame)

    def set_status(self, text, timeout=5000):
        self.log(text)


def run_lite_gui(db_path=DEFAULT_DB_PATH):
    if sys.platform == "win32":
        import ctypes
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "mrubiodev.GitBranchInfoRecovery.Lite")
        if result < 0:
            raise OSError(f"No se pudo establecer la identidad de la aplicación: {result}")
    root = tk.Tk()
    LiteAutomationsApp(root, db_path)
    root.mainloop()
