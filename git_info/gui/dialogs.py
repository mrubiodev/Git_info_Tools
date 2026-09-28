"""Diálogos modales reutilizables."""
import tkinter as tk
from tkinter import messagebox

SAVE_ALL = "all"
SAVE_SELECTION = "selection"


class SaveSearchDialog(tk.Toplevel):
    """Pide nombre, alcance (todo el filtro o solo lo marcado) y sincronización automática."""

    def __init__(self, parent, default_name="", total=0, checked=0, auto_sync=False, interval=15):
        super().__init__(parent)
        self.title("Guardar búsqueda")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        body = tk.Frame(self, padx=12, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Nombre:").grid(row=0, column=0, sticky="w")
        self.entry_name = tk.Entry(body, width=45)
        self.entry_name.insert(0, default_name)
        self.entry_name.grid(row=0, column=1, sticky="ew", pady=4)

        self.mode = tk.StringVar(value=SAVE_SELECTION if checked else SAVE_ALL)
        tk.Label(body, text="Guardar:").grid(row=1, column=0, sticky="nw", pady=(8, 0))
        modes = tk.Frame(body)
        modes.grid(row=1, column=1, sticky="w", pady=(8, 0))
        tk.Radiobutton(modes, variable=self.mode, value=SAVE_ALL,
                       text=f"Búsqueda completa: todo lo que cumpla el filtro ({total} ahora, incluye ficheros nuevos)"
                       ).pack(anchor="w")
        tk.Radiobutton(modes, variable=self.mode, value=SAVE_SELECTION,
                       text=f"Solo los ficheros marcados ({checked})",
                       state="normal" if checked else "disabled").pack(anchor="w")

        self.auto_var = tk.BooleanVar(value=auto_sync)
        tk.Checkbutton(body, variable=self.auto_var,
                       text="Descargar automáticamente cuando cambien las ramas").grid(
            row=2, column=1, sticky="w", pady=(8, 0))
        interval_frame = tk.Frame(body)
        interval_frame.grid(row=3, column=1, sticky="w")
        tk.Label(interval_frame, text="Comprobar cada (minutos):").pack(side=tk.LEFT)
        self.interval = tk.Spinbox(interval_frame, from_=1, to=1440, width=6)
        self.interval.delete(0, tk.END)
        self.interval.insert(0, str(interval))
        self.interval.pack(side=tk.LEFT, padx=5)

        buttons = tk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        tk.Button(buttons, text="Guardar", width=12, command=self._accept).pack(side=tk.LEFT, padx=5)
        tk.Button(buttons, text="Cancelar", width=12, command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._accept())
        self.bind("<Escape>", lambda e: self.destroy())
        self.entry_name.focus_set()
        self.grab_set()

    def _accept(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("Advertencia", "Indica un nombre para la búsqueda.", parent=self)
            return
        try:
            interval = int(self.interval.get())
            if interval < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Advertencia", "El intervalo debe ser un número entero de minutos (≥ 1).",
                                   parent=self)
            return
        self.result = {"name": name, "mode": self.mode.get(), "auto_sync": self.auto_var.get(),
                       "interval_minutes": interval}
        self.destroy()

    @classmethod
    def ask(cls, parent, **kwargs):
        dialog = cls(parent, **kwargs)
        parent.wait_window(dialog)
        return dialog.result
