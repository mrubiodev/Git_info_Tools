"""Pestaña de consola de texto y visualizador del progreso de `fetch`."""
import tkinter as tk


class ConsoleTab:
    def __init__(self, notebook):
        self.frame = tk.Frame(notebook)
        notebook.add(self.frame, text="Consola")
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        self.text_output = tk.Text(self.frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.text_output.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(self.frame, command=self.text_output.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_output.config(yscrollcommand=scrollbar.set)

    def write(self, message, append=False):
        self.text_output.config(state="normal")
        if not append:
            self.text_output.delete(1.0, tk.END)
        self.text_output.insert(tk.END, message + "\n")
        self.text_output.see(tk.END)
        self.text_output.config(state="disabled")
        self.frame.update_idletasks()


class FetchProgress(object):
    """Callback de progreso de GitPython que reescribe una línea del Text."""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.current_line_start = None

    def __call__(self, op_code, cur_count, max_count=None, message=''):
        progress = f" ({cur_count}/{max_count})" if max_count else f" ({cur_count})"
        full_message = f"  {op_code} {message}{progress}"

        self.text_widget.config(state="normal")
        if self.current_line_start:
            self.text_widget.delete(self.current_line_start, tk.END)
        else:
            if self.text_widget.index(tk.END) != "1.0":
                self.text_widget.insert(tk.END, "\n")
            self.current_line_start = self.text_widget.index(tk.END)

        self.text_widget.insert(tk.END, full_message)
        self.text_widget.see(tk.END)
        self.text_widget.config(state="disabled")
        self.text_widget.update_idletasks()

        if max_count and cur_count == max_count:
            self.current_line_start = None
