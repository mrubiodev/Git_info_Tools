"""Pestaña de búsqueda combinada sobre el historial de ramas en SQLite."""
import tkinter as tk
from tkinter import messagebox

from ..core.formatting import format_branch_details, repo_short_name, status_text, truncate, type_short
from .widgets import ScrolledTree, attach_context_menu, copy_rows, export_rows_dialog, show_text_window

HEADERS = ["ID", "Repositorio", "Rama", "Tipo", "Hash", "Fecha Commit",
           "Autor", "Mensaje", "Archivos Modificados", "Estado"]
COLUMNS = [("id", "ID", 40, "center"), ("repo", "Repositorio", 150), ("branch", "Rama", 150),
           ("type", "Tipo", 120), ("hash", "Hash", 80), ("date", "Fecha Commit", 130),
           ("author", "Autor", 100), ("message", "Mensaje", 200),
           ("files", "Archivos Modificados", 250), ("status", "Estado", 80, "center")]
EXCEL_WIDTHS = [8, 25, 30, 15, 12, 18, 20, 40, 50, 12]


def table_row(row):
    row_id, repo_path, branch_name, branch_type, commit_hash, commit_date, message, author, files, status = row
    return (row_id, repo_short_name(repo_path), branch_name, type_short(branch_type), commit_hash,
            commit_date, author or "", truncate(message, 50), truncate(files, 60), status_text(status))


class SearchTab:
    def __init__(self, app, notebook, store):
        self.app = app
        self.store = store
        self.frame = tk.Frame(notebook)
        notebook.add(self.frame, text="Búsqueda en Base de Datos")
        self.frame.grid_rowconfigure(1, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        self._build_controls()

        self.table = ScrolledTree(self.frame, COLUMNS)
        self.table.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.tree = self.table.tree

        self.label_results = tk.Label(self.frame, text="Resultados: 0", font=("Arial", 9))
        self.label_results.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.tree.bind("<Double-1>", self.show_details)
        attach_context_menu(self.tree, [
            ("Copiar fila", self.copy_selection),
            ("Copiar todas las filas visibles", self.copy_all_visible),
            None,
            ("Ver detalles", lambda: self.show_details(None)),
        ])

    def _build_controls(self):
        controls = tk.Frame(self.frame, relief=tk.GROOVE, borderwidth=2, padx=10, pady=10)
        controls.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        controls.grid_columnconfigure(1, weight=1)

        tk.Label(controls, text="Buscar por:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(0, 10), sticky="w")
        self.entry_search_branch = self._labeled_entry(controls, "Rama:", 1)
        self.entry_search_path = self._labeled_entry(controls, "Repositorio:", 2)
        self.entry_search_file = self._labeled_entry(controls, "Archivo:", 3)

        buttons = tk.Frame(controls)
        buttons.grid(row=4, column=0, columnspan=2, pady=10)
        for text, command in (("Buscar", self.perform_search), ("Limpiar Filtros", self.clear_search),
                              ("Ver Todos", self.view_all_records), ("Exportar Excel", self.export_to_excel),
                              ("Copiar Selección", self.copy_selection)):
            tk.Button(buttons, text=text, command=command, width=12).pack(side=tk.LEFT, padx=5)

    @staticmethod
    def _labeled_entry(parent, label, row):
        tk.Label(parent, text=label).grid(row=row, column=0, padx=5, pady=5, sticky="w")
        entry = tk.Entry(parent, width=30)
        entry.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        return entry

    def perform_search(self):
        branch_name = self.entry_search_branch.get().strip()
        repo_path = self.entry_search_path.get().strip()
        file_name = self.entry_search_file.get().strip()
        if not branch_name and not repo_path and not file_name:
            messagebox.showwarning("Advertencia", "Por favor, ingresa al menos un criterio de búsqueda.")
            return
        try:
            self.app.log(f"Ejecutando búsqueda con criterios: Rama='{branch_name}', Repo='{repo_path}', Archivo='{file_name}'")
            results = self.store.search(branch_name, repo_path, file_name)
            self.app.log(f"Se encontraron {len(results)} resultados.")
            self.populate(results)
        except Exception as e:
            messagebox.showerror("Error", f"Error al realizar la búsqueda: {e}")
            self.app.log(f"Error en búsqueda: {e}")

    def view_all_records(self):
        try:
            results = self.store.all()
            self.app.log(f"Cargando todos los registros: {len(results)} encontrados.")
            self.populate(results)
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar registros: {e}")
            self.app.log(f"Error al cargar registros: {e}")

    def clear_search(self):
        for entry in (self.entry_search_branch, self.entry_search_path, self.entry_search_file):
            entry.delete(0, tk.END)
        self.table.clear()
        self.label_results.config(text="Resultados: 0")

    def populate(self, results):
        self.table.clear()
        if not results:
            self.label_results.config(text="Resultados: 0 - No se encontraron registros")
            messagebox.showinfo("Búsqueda", "No se encontraron registros con los criterios especificados.")
            return
        for row in results:
            try:
                self.table.insert(table_row(row))
            except Exception as e:
                self.app.log(f"Error al procesar fila: {e}")
        self.label_results.config(text=f"Resultados: {len(results)}")
        self.app.select_tab(self.frame)

    def show_details(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        details = self.store.get_details(self.tree.item(selection[0])['values'][0])
        if details:
            show_text_window(self.app.root, f"Detalles: {details['branch_name']}", format_branch_details(details))

    def copy_selection(self):
        copy_rows(self.app.root, HEADERS, self.table.selected_rows(),
                  "Por favor, selecciona al menos una fila.")

    def copy_all_visible(self):
        copy_rows(self.app.root, HEADERS, self.table.rows(), "No hay datos para copiar.")

    def export_to_excel(self):
        export_rows_dialog(self.table.rows(), "Búsqueda de Ramas", HEADERS, EXCEL_WIDTHS, log=self.app.log)
