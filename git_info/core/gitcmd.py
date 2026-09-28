"""Utilidades de bajo nivel para invocar el ejecutable `git`."""
import os
import re
import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class GitError(Exception):
    pass


class Cancelled(Exception):
    pass


def git_args(repo_path, *args):
    return ["git", "-C", repo_path, "-c", "core.quotepath=false", *args]


def git_env():
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # nunca bloquearse pidiendo credenciales
    return env


def run_git(repo_path, *args, timeout=None):
    proc = subprocess.run(
        git_args(repo_path, *args),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=git_env(), creationflags=NO_WINDOW, timeout=timeout,
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(msg or f"git {' '.join(args)} ha fallado (código {proc.returncode})")
    return proc.stdout


def popen_git(repo_path, *args, stdin=subprocess.DEVNULL):
    return subprocess.Popen(
        git_args(repo_path, *args),
        stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=git_env(), creationflags=NO_WINDOW,
    )


def fetch_all(repo_path, timeout=600):
    run_git(repo_path, "fetch", "--all", "--prune", timeout=timeout)


def check_cancel(cancel):
    if cancel is not None and cancel():
        raise Cancelled()


def compile_regex(pattern, ignore_case=True):
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as e:
        raise ValueError(f"Expresión regular no válida '{pattern}': {e}")


_C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def unquote_path(path):
    """Deshace el entrecomillado estilo C que usa Git para rutas con caracteres especiales."""
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    s = path[1:-1]
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _C_ESCAPES:
                out.append(_C_ESCAPES[nxt])
                i += 2
                continue
            octal = s[i + 1:i + 4]
            if re.fullmatch(r"[0-7]{3}", octal):
                out.append(int(octal, 8))
                i += 4
                continue
        out.extend(c.encode("utf-8"))
        i += 1
    return out.decode("utf-8", "replace")
