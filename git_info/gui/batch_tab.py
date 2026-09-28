"""Pestaña de búsqueda en lote por nombres de rama o ficheros modificados."""
import tkinter as tk
from tkinter import messagebox

from ..core import excel
from ..core.branch_store import BATCH_BY_BRANCH, BATCH_BY_FILE, parse_terms
from ..core.formatting import format_branch_details, repo_short_name, truncate, type_short
from .widgets import ScrolledTree, attach_context_menu, copy_rows, export_rows_dialog, show_text_window

FOUND, NOT_FOUND = "✓ SÍ", "✗ NO"
HEADERS = ["Búsqueda", "Encontrado", "Repositorio", "Rama", "Tipo", "Hash", "Fecha", "Archivos"]
COLUMNS = [("item", "Búsqueda", 200), ("found", "Encontrado", 80, "center"), ("repo", "Repositorio", 120),
           ("branch", "Rama", 150), ("type", "Tipo", 100), ("hash", "Hash", 80),
           ("date", "Fecha", 130), ("files", "Archivos", 250)]
EXCEL_WIDTHS = [35, 12, 25, 30, 15, 12, 18, 50]


def _row_color(values):
    return excel.FOUND_COLOR if values[1] == FOUND else excel.NOT_FOUND_COLOR


class BatchTab:
    def __init__(self, app, notebook, store):
        self.app = app
        self.store = store
        self.frame = tk.Frame(notebook)
        notebook.add(self.frame, text="Búsqueda en Lote")
        self.frame.grid_rowconfigure(2, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        tk.Label(self.frame, text="Pega múltiples nombres de ramas o archivos (uno por línea o separados por comas)",
                 font=("Arial", 10, "bold"), pady=10).grid(row=0, column=0, sticky="ew", padx=10)

        type_frame = tk.Frame(self.frame)
        type_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        tk.Label(type_frame, text="Buscar por:").pack(side=tk.LEFT, padx=5)
        self.batch_search_type = tk.StringVar(value=BATCH_BY_BRANCH)
        tk.Radiobutton(type_frame, text="Nombres de Ramas", variable=self.batch_search_type,
                       value=BATCH_BY_BRANCH).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(type_frame, text="Archivos Modificados", variable=self.batch_search_type,
                       value=BATCH_BY_FILE).pack(side=tk.LEFT, padx=10)

        self._build_input()
        self._build_buttons()
        self._build_results()

    def _build_input(self):
        frame = tk.Frame(self.frame)
        frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tk.Label(frame, text="Lista de búsqueda:", anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.batch_text_input = tk.Text(frame, height=10, wrap="word", font=("Consolas", 10))
        self.batch_text_input.grid(row=1, column=0, sticky="nsew")
        scroll = tk.Scrollbar(frame, command=self.batch_text_input.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.batch_text_input.config(yscrollcommand=scroll.set)

    def _build_buttons(self):
        frame = tk.Frame(self.frame)
        frame.grid(row=3, column=0, pady=10)
        for text, command, width in (("Buscar en Lote", self.perform_batch_search, 15),
                                     ("Limpiar", self.clear_batch_search, 12),
                                     ("Exportar Excel", self.export_batch_to_excel, 12),
                                     ("Copiar Resultados", self.copy_batch_selection, 12)):
            tk.Button(frame, text=text, command=command, width=width, height=2).pack(side=tk.LEFT, padx=5)

    def _build_results(self):
        frame = tk.Frame(self.frame)
        frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=5)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tk.Label(frame, text="Resultados:", anchor="w", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        self.table = ScrolledTree(frame, COLUMNS)
        self.table.grid(row=1, column=0, sticky="nsew")
        self.batch_tree = self.table.tree
        self.batch_tree.tag_configure("found", background="#d4edda")
        self.batch_tree.tag_configure("not_found", background="#f8d7da")
        self.label_batch_results = tk.Label(frame, text="Esperando búsqueda...", font=("Arial", 9))
        self.label_batch_results.grid(row=3, column=0, sticky="w", pady=5)

        self.batch_tree.bind("<Double-1>", self.show_batch_details)
        attach_context_menu(self.batch_tree, [
            ("Copiar fila", self.copy_batch_selection),
            ("Copiar todos los resultados", self.copy_all_batch),
            None,
            ("Ver detalles", lambda: self.show_batch_details(None)),
        ])

    def perform_batch_search(self):
        input_text = self.batch_text_input.get("1.0", tk.END).strip()
        if not input_text:
            messagebox.showwarning("Advertencia", "Por favor, ingresa términos de búsqueda.")
            return
        self.table.clear()
        terms = parse_terms(input_text)
        if not terms:
            messagebox.showwarning("Advertencia", "No se encontraron términos válidos de búsqueda.")
            return

        self.app.log(f"\nIniciando búsqueda en lote de {len(terms)} términos...")
        self.label_batch_results.config(text=f"Buscando {len(terms)} términos...")
        self.app.root.update_idletasks()
        try:
            found = 0
            for term, rows in self.store.batch_search(terms, self.batch_search_type.get()):
                if rows:
                    found += 1
                    for _id, repo_path, branch_name, branch_type, commit_hash, commit_date, files in rows:
                        self.table.insert((term, FOUND, repo_short_name(repo_path), branch_name,
                                           type_short(branch_type), commit_hash, commit_date,
                                           truncate(files, 40)), tags=("found",))
                else:
                    self.table.insert((term, NOT_FOUND, "-", "-", "-", "-", "-", "-"), tags=("not_found",))
            self.label_batch_results.config(
                text=f"Búsqueda completada: {found} encontrados, {len(terms) - found} no encontrados (Total: {len(terms)})")
            self.app.log(f"Búsqueda en lote completada: {found}/{len(terms)} términos encontrados")
            self.app.select_tab(self.frame)
        except Exception as e:
            messagebox.showerror("Error", f"Error en búsqueda en lote: {e}")
            self.app.log(f"Error en búsqueda en lote: {e}")

    def clear_batch_search(self):
        self.batch_text_input.delete("1.0", tk.END)
        self.table.clear()
        self.label_batch_results.config(text="Esperando búsqueda...")

    def show_batch_details(self, event=None):
        selection = self.batch_tree.selection()
        if not selection:
            return
        values = self.batch_tree.item(selection[0])['values']
        if values[1] == NOT_FOUND:
            messagebox.showinfo("No encontrado", f"El término '{values[0]}' no se encontró en la base de datos.")
            return
        try:
            details = self.store.latest_details_by_name(str(values[3]))
            if details:
                show_text_window(self.app.root, f"Detalles: {details['branch_name']}",
                                 format_branch_details(details))
        except Exception as e:
            messagebox.showerror("Error", f"Error al obtener detalles: {e}")

    def copy_batch_selection(self):
        copy_rows(self.app.root, HEADERS, self.table.selected_rows(),
                  "Por favor, selecciona al menos una fila.")

    def copy_all_batch(self):
        copy_rows(self.app.root, HEADERS, self.table.rows(), "No hay datos para copiar.")

    def export_batch_to_excel(self):
        export_rows_dialog(self.table.rows(), "Búsqueda en Lote", HEADERS, EXCEL_WIDTHS, _row_color,
                           log=self.app.log, log_message="Datos de búsqueda en lote exportados a: {path}")
