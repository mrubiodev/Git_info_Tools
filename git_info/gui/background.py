"""Ejecución de tareas en segundo plano sin bloquear Tkinter.

Los hilos de trabajo nunca tocan widgets: publican en una cola que el hilo de
la interfaz procesa periódicamente.
"""
import queue
import threading
import traceback


class Task:
    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()


class BackgroundRunner:
    def __init__(self, root, poll_ms=100):
        self.root = root
        self.poll_ms = poll_ms
        self._queue = queue.Queue()
        self.root.after(poll_ms, self._poll)

    def submit(self, fn, on_success=None, on_error=None, on_progress=None, on_finally=None):
        """Ejecuta `fn(progress, cancelled)` en un hilo; los callbacks corren en el hilo de la GUI."""
        task = Task()

        def progress(message):
            if on_progress:
                self._queue.put((on_progress, (message,)))

        def work():
            try:
                result = fn(progress, lambda: task.cancelled)
            except Exception as e:
                self._queue.put((on_error, (e,)))
            else:
                self._queue.put((on_success, (result,)))
            finally:
                self._queue.put((on_finally, ()))

        threading.Thread(target=work, daemon=True).start()
        return task

    def _poll(self):
        try:
            while True:
                callback, args = self._queue.get_nowait()
                if callback:
                    try:
                        callback(*args)
                    except Exception:
                        traceback.print_exc()
        except queue.Empty:
            pass
        self.root.after(self.poll_ms, self._poll)
