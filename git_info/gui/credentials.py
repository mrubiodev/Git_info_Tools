"""Petición de credenciales SSH desde la GUI cuando un fetch falla por autenticación."""
from tkinter import messagebox, simpledialog

from ..core import ssh_auth


class CredentialPrompter:
    """Pide la passphrase una vez, carga la clave en el agente de la sesión y reintenta.

    Las ejecuciones automáticas no vuelven a preguntar si el usuario canceló o si
    la clave ya cargada sigue sin tener acceso; las manuales siempre preguntan.
    """

    def __init__(self, app):
        self.app = app
        self.pending = []
        self.prompting = False
        self.declined = False
        self.loaded = []

    def handle(self, texts, retry=None, manual=False):
        """Devuelve True si `texts` contiene un fallo de clave SSH y se gestiona aquí."""
        if isinstance(texts, str):
            texts = [texts]
        if not any(ssh_auth.is_ssh_key_error(text) for text in texts or []):
            return False
        if not ssh_auth.default_keys():
            self.app.log("Credenciales SSH: el servidor rechazó la conexión y no hay claves en ~/.ssh.")
            return False
        if self.prompting:
            if retry:
                self.pending.append(retry)
            return True
        if not manual and (self.declined or self.loaded):
            return False
        if retry:
            self.pending.append(retry)
        self.prompt()
        return True

    def prompt(self, reason=None):
        self.prompting = True
        keys = ssh_auth.default_keys()
        if not keys:
            self.prompting = False
            messagebox.showwarning("Credenciales SSH", "No hay claves SSH en ~/.ssh.", parent=self.app.root)
            return
        names = ", ".join(key.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for key in keys)
        message = reason or ("Git no ha podido autenticarse por SSH (Permission denied (publickey)).\n"
                             "La clave está protegida con passphrase y la aplicación no tiene consola "
                             "para pedirla.")
        passphrase = simpledialog.askstring(
            "Credenciales SSH",
            f"{message}\n\nClaves: {names}\nIntroduce la passphrase (se guarda solo en memoria "
            "durante esta sesión):", show="*", parent=self.app.root)
        if passphrase is None:
            self.prompting = False
            self.declined = True
            self.pending.clear()
            self.app.log("Credenciales SSH: cancelado. Las ejecuciones automáticas no volverán a "
                         "preguntar; usa 'Credenciales SSH...' en Automatizaciones para introducirlas.")
            return
        self.app.log("Credenciales SSH: cargando clave en el agente de la sesión...")
        self.app.runner.submit(lambda progress, cancel: ssh_auth.load_keys(passphrase, keys),
                               on_success=self._loaded, on_error=self._failed)

    def _loaded(self, keys):
        self.prompting = False
        self.declined = False
        self.loaded = keys
        self.app.log(f"Credenciales SSH: {len(keys)} clave(s) cargada(s). Reintentando operaciones pendientes...")
        pending, self.pending = self.pending, []
        for retry in pending:
            try:
                retry()
            except Exception as error:
                self.app.log(f"Credenciales SSH: error al reintentar: {error}")

    def _failed(self, error):
        self.app.log(f"Credenciales SSH: {error}")
        self.prompt(f"{error}\n\nVuelve a intentarlo o cancela.")

    def request(self):
        """Carga manual de credenciales (botón de la GUI)."""
        if not self.prompting:
            self.prompt("Carga la clave SSH para que Git pueda hacer fetch sin consola.")
