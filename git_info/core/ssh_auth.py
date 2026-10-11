"""Credenciales SSH para Git sin consola.

La aplicación lanza Git sin terminal, así que `ssh` no puede pedir la
passphrase de una clave cifrada y el fetch acaba en
"Permission denied (publickey)". Este módulo arranca un `ssh-agent` propio
(el incluido en Git for Windows) durante la sesión y carga en él las claves
con la passphrase que el usuario introduce en la GUI. Los procesos Git hijos
heredan `SSH_AUTH_SOCK`, por lo que la passphrase solo se pide una vez.
"""
import atexit
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEFAULT_KEYS = ("id_ed25519", "id_ecdsa", "id_rsa", "id_ed25519_sk", "id_ecdsa_sk", "id_dsa")

_lock = threading.Lock()
_agent = {}


class SshAuthError(Exception):
    pass


def is_ssh_key_error(text):
    return "permission denied (publickey" in (text or "").lower()


def _git_tool(name):
    """Herramienta OpenSSH del mismo Git que usa la app (compatible con su socket de agente)."""
    git = shutil.which("git")
    candidates = []
    if git:
        root = Path(git).resolve().parent.parent
        candidates += [root / "usr" / "bin" / f"{name}.exe", root.parent / "usr" / "bin" / f"{name}.exe"]
    candidates.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise SshAuthError(f"No se encontró {name}; instala Git for Windows o carga la clave en un agente SSH.")


def default_keys(ssh_dir=None):
    ssh_dir = Path(ssh_dir or Path.home() / ".ssh")
    return [str(ssh_dir / name) for name in DEFAULT_KEYS if (ssh_dir / name).is_file()]


def agent_active():
    return bool(_agent.get("sock"))


def _start_agent():
    proc = subprocess.run([_git_tool("ssh-agent"), "-s"], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, creationflags=NO_WINDOW, timeout=30)
    sock = re.search(r"SSH_AUTH_SOCK=([^;\s]+)", proc.stdout)
    pid = re.search(r"SSH_AGENT_PID=(\d+)", proc.stdout)
    if proc.returncode != 0 or not sock or not pid:
        raise SshAuthError(f"No se pudo iniciar ssh-agent: {proc.stderr.strip() or proc.stdout.strip()}")
    _agent.update(sock=sock.group(1), pid=pid.group(1))
    os.environ["SSH_AUTH_SOCK"] = _agent["sock"]
    os.environ["SSH_AGENT_PID"] = _agent["pid"]
    atexit.register(stop_agent)


def stop_agent():
    with _lock:
        if not _agent:
            return
        env = dict(os.environ, SSH_AUTH_SOCK=_agent["sock"], SSH_AGENT_PID=_agent["pid"])
        try:
            subprocess.run([_git_tool("ssh-agent"), "-k"], env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, creationflags=NO_WINDOW, timeout=15)
        except Exception:
            pass
        for name in ("SSH_AUTH_SOCK", "SSH_AGENT_PID"):
            if os.environ.get(name) == _agent.get("sock" if name == "SSH_AUTH_SOCK" else "pid"):
                os.environ.pop(name, None)
        _agent.clear()


def _add_key(key, passphrase, workdir):
    # Si la passphrase es incorrecta, ssh-add repite la pregunta ("Bad passphrase...")
    # indefinidamente; el askpass corta ahí para no entrar en bucle.
    script = Path(workdir) / "askpass.sh"
    script.write_text('#!/bin/sh\ncase "$1" in *[Bb]ad*) exit 1;; esac\n'
                      'printf \'%s\\n\' "$GIT_INFO_SSH_PASSPHRASE"\n', newline="\n")
    env = dict(os.environ, SSH_AUTH_SOCK=_agent["sock"], SSH_AGENT_PID=_agent["pid"],
               SSH_ASKPASS=script.as_posix(), SSH_ASKPASS_REQUIRE="force",
               DISPLAY=os.environ.get("DISPLAY", "git-info:0"), GIT_INFO_SSH_PASSPHRASE=passphrase)
    proc = subprocess.run([_git_tool("ssh-add"), key], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, creationflags=NO_WINDOW, timeout=60)
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def load_keys(passphrase, keys=None):
    """Carga en el agente de la sesión las claves que abre `passphrase`.

    Devuelve la lista de claves cargadas; lanza SshAuthError si ninguna se pudo abrir.
    """
    keys = list(keys) if keys else default_keys()
    if not keys:
        raise SshAuthError(f"No hay claves SSH en {Path.home() / '.ssh'}.")
    with _lock:
        if not agent_active():
            _start_agent()
        loaded, errors = [], []
        with tempfile.TemporaryDirectory(prefix="git-info-ssh-") as workdir:
            for key in keys:
                ok, message = _add_key(key, passphrase, workdir)
                (loaded.append(key) if ok else
                 errors.append(f"{Path(key).name}: {message or 'passphrase incorrecta'}"))
    if not loaded:
        raise SshAuthError("No se pudo cargar ninguna clave (¿passphrase incorrecta?).\n" + "\n".join(errors))
    return loaded
