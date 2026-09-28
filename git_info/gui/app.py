"""Ventana principal: compone las pestañas y el flujo de análisis de ramas."""
import tkinter as tk
from tkinter import messagebox, ttk

from git import InvalidGitRepositoryError, NoSuchPathError

# Prefer package-relative imports, but allow running this file directly as a script.
try:
    from .. import DEFAULT_DB_PATH, __author__, __proyect__, __version__
    from ..core import branch_scanner
    from ..core.branch_store import BranchStore
    from ..core.formatting import format_branch_report
    from ..core.saved_searches import SavedSearchStore
    from .background import BackgroundRunner
    from .batch_tab import BatchTab
    from .console_tab import ConsoleTab, FetchProgress
    from .latest_tab import LatestFilesTab
    from .search_tab import SearchTab
    from .widgets import browse_into, ToolTip
except Exception:
    # Running as a script (python git_info/gui/app.py) can make relative imports fail.
    # Insert the repo root into sys.path and use absolute imports as a fallback.
    import os, sys
    _this_dir = os.path.dirname(__file__)
    _repo_root = os.path.abspath(os.path.join(_this_dir, "..", ".."))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from git_info import DEFAULT_DB_PATH, __author__, __proyect__, __version__
    from git_info.core import branch_scanner
    from git_info.core.branch_store import BranchStore
    from git_info.core.formatting import format_branch_report
    from git_info.core.saved_searches import SavedSearchStore
    from git_info.gui.background import BackgroundRunner
    from git_info.gui.batch_tab import BatchTab
    from git_info.gui.console_tab import ConsoleTab, FetchProgress
    from git_info.gui.latest_tab import LatestFilesTab
    from git_info.gui.search_tab import SearchTab
    from git_info.gui.widgets import browse_into, ToolTip
 


class GitBranchInfoApp:
    def __init__(self, root, db_path=DEFAULT_DB_PATH):
        self.root = root
        self.root.title(f"{__proyect__} - v{__version__} by {__author__}")
        self.root.geometry("1400x900")
        self.db_path = db_path
        self.branch_store = BranchStore(db_path)
        self.saved_store = SavedSearchStore(db_path)
        self.runner = BackgroundRunner(root)

        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self._build_top_bar()

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.console = ConsoleTab(self.notebook)
        self._init_database()
        self.search_tab = SearchTab(self, self.notebook, self.branch_store)
        self.batch_tab = BatchTab(self, self.notebook, self.branch_store)
        self.latest_tab = LatestFilesTab(self, self.notebook, self.saved_store)
        # Keyboard shortcuts for navigation
        try:
            self.root.bind_all("<Control-f>", lambda e: self.search_tab.focus_search())
            self.root.bind_all("<Control-Tab>", lambda e: self._cycle_tab(1))
            self.root.bind_all("<Control-Shift-Tab>", lambda e: self._cycle_tab(-1))
        except Exception:
            pass

    def _build_top_bar(self):
        top = tk.Frame(self.root, padx=10, pady=10)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        tk.Label(top, text="Ruta del Repositorio Git:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_path = tk.Entry(top, width=70)
        self.entry_path.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        # Browse button (keep a reference for tooltip)
        browse_btn = tk.Button(top, text="Examinar", command=lambda: browse_into(self.entry_path))
        browse_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")
        # Action button
        getinfo_btn = tk.Button(top, text="Obtener Información y Registrar", command=self.get_all_branch_info)
        getinfo_btn.grid(row=1, column=0, columnspan=3, pady=10)

        # Status label to improve understandability of what's happening
        self.status_label = tk.Label(top, text="", font=("Arial", 9), fg="gray")
        self.status_label.grid(row=2, column=0, columnspan=3, sticky="w", padx=5, pady=(2, 0))

        # Panel de opciones (paralelismo)
        self.parallel_var = tk.BooleanVar(value=False)
        self.workers_var = tk.IntVar(value=4)
        chk = tk.Checkbutton(top, text="Escaneo paralelo", variable=self.parallel_var)
        chk.grid(row=0, column=3, padx=5, pady=5)
        spin = tk.Spinbox(top, from_=1, to=32, textvariable=self.workers_var, width=3)
        spin.grid(row=0, column=4, padx=5, pady=5, sticky="w")

        # Tooltips
        try:
            ToolTip(self.entry_path, "Ruta al repositorio Git. Puede pegar una carpeta o usar 'Examinar'.")
            ToolTip(browse_btn, "Abrir selector de carpetas")
            ToolTip(getinfo_btn, "Analiza el repositorio seleccionado y registra ramas en la base de datos")
            ToolTip(chk, "Usar escaneo paralelo para acelerar búsquedas (experimental). Desactivado por defecto.")
            ToolTip(spin, "Número de hilos a usar cuando el escaneo paralelo está activado")
        except Exception:
            pass

    def _init_database(self):
        for message in self.branch_store.init():
            self.display_message(message, append=False)
        self.saved_store.init()

    # ---- API común para las pestañas
    def display_message(self, message, append=False):
        self.console.write(message, append)

    def log(self, message):
        self.display_message(message, append=True)

    def repo_path(self):
        return self.entry_path.get().strip()

    def set_repo_path(self, path):
        self.entry_path.delete(0, tk.END)
        self.entry_path.insert(0, path)

    def select_tab(self, frame):
        self.notebook.select(frame)

    def set_status(self, text, timeout=5000):
        """Muestra un texto temporal en la barra de estado superior."""
        try:
            self.status_label.config(text=text)
            if hasattr(self, '_status_after_id') and self._status_after_id:
                try:
                    self.root.after_cancel(self._status_after_id)
                except Exception:
                    pass
            if timeout:
                self._status_after_id = self.root.after(timeout, lambda: self.status_label.config(text=""))
            else:
                self._status_after_id = None
        except Exception:
            pass

    def _cycle_tab(self, delta):
        try:
            tabs = list(self.notebook.tabs())
            if not tabs:
                return
            current = self.notebook.index(self.notebook.select())
            new = (current + delta) % len(tabs)
            self.notebook.select(new)
        except Exception:
            pass

    # ---- Análisis de ramas remotas y recuperables
    def _show_report(self, branches, title, recoverable=False):
        for block in format_branch_report(branches, title, recoverable):
            self.log(block)

    def get_all_branch_info(self):
        repo_path = self.entry_path.get()
        if not repo_path:
            messagebox.showwarning("Advertencia", "Por favor, selecciona la ruta del repositorio Git.")
            return
        self.display_message("Obteniendo información de ramas y registrando en la base de datos...", append=False)
        try:
            repo = branch_scanner.open_repo(repo_path)
            remote = branch_scanner.scan_remote_branches(
                repo, repo_path, self.branch_store, self.log, FetchProgress(self.console.text_output))
            self._show_report(remote, "Ramas Remotas Existentes")

            self.log("\n\n--- Buscando Ramas Potencialmente Recuperables en el Reflog Local ---")
            recoverable = branch_scanner.scan_recoverable_branches(
                repo, repo_path, self.branch_store, remote, self.log)
            self._show_report(recoverable, "Ramas Potencialmente Recuperables (Reflog)", recoverable=True)

            self.log("\nProceso completado. La información ha sido registrada en la base de datos.")
        except InvalidGitRepositoryError:
            messagebox.showerror("Error", "La carpeta seleccionada no es un repositorio Git válido.")
            self.display_message("Error: La carpeta seleccionada no es un repositorio Git válido.", append=False)
        except NoSuchPathError:
            messagebox.showerror("Error", "La ruta especificada no existe.")
            self.display_message("Error: La ruta especificada no existe.", append=False)
        except Exception as e:
            messagebox.showerror("Error Inesperado", f"Ocurrió un error: {e}")
            self.display_message(f"Error inesperado: {e}", append=False)


def run_gui(db_path=DEFAULT_DB_PATH):
    root = tk.Tk()
    GitBranchInfoApp(root, db_path)
    root.mainloop()
