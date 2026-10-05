"""Actualización periódica de repositorios, sin descartar trabajo local."""
import contextlib
import json
import os
import sqlite3

from .gitcmd import GitError, check_cancel, run_git
from .saved_searches import SavedSearchStore, is_due, now_text

COLUMNS = ("id", "name", "repo_path", "branch", "remote", "remote_branch",
           "auto_sync", "interval_minutes", "created_at", "last_run",
           "last_result", "last_details")


def normalized_path(path):
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def in_selected_folder(repo_path, selected_path):
    if not selected_path.strip():
        return False
    repo, folder = normalized_path(repo_path), normalized_path(selected_path)
    try:
        return os.path.commonpath([repo, folder]) == folder
    except ValueError:
        return False  # Distintas unidades.


def git_text(repo, *args):
    return run_git(repo, *args, timeout=30).decode("utf-8", "replace").strip()


def inspect_repository(path):
    if not path.strip():
        raise ValueError("Indica la carpeta del repositorio.")
    repo = normalized_path(path)
    if git_text(repo, "rev-parse", "--is-inside-work-tree") != "true":
        raise ValueError("Selecciona un repositorio con carpeta de trabajo, no un repositorio bare.")
    repo = normalized_path(git_text(repo, "rev-parse", "--show-toplevel"))
    branches = git_text(repo, "for-each-ref", "--format=%(refname:strip=2)", "refs/heads/").splitlines()
    current = git_text(repo, "branch", "--show-current")
    remotes = git_text(repo, "remote").splitlines()
    upstream = {}
    for line in run_git(repo, "for-each-ref",
                        "--format=%(refname:strip=2)%09%(upstream:remotename)%09%(upstream:remoteref)",
                        "refs/heads/", timeout=30).decode("utf-8", "replace").splitlines():
        branch, remote, ref = line.split("\t")
        if remote and remote != "." and ref.startswith("refs/heads/"):
            upstream[branch] = (remote, ref[len("refs/heads/"):])
    return {"repo_path": repo, "branches": branches, "current": current,
            "remotes": remotes, "upstream": upstream}


class RepositoryAutomationStore(SavedSearchStore):
    """Tabla independiente; comparte únicamente las utilidades SQLite existentes."""

    def init(self):
        self._execute("""
            CREATE TABLE IF NOT EXISTS repository_automations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                repo_path TEXT NOT NULL UNIQUE,
                branch TEXT NOT NULL,
                remote TEXT NOT NULL,
                remote_branch TEXT NOT NULL,
                auto_sync INTEGER NOT NULL DEFAULT 1,
                interval_minutes INTEGER NOT NULL DEFAULT 15,
                created_at TEXT NOT NULL,
                last_run TEXT,
                last_result TEXT,
                last_details TEXT
            )
        """)

    @staticmethod
    def _to_dict(row):
        data = dict(zip(COLUMNS, row))
        data["auto_sync"] = bool(data["auto_sync"])
        data["last_details"] = json.loads(data["last_details"]) if data["last_details"] else None
        return data

    def list(self):
        rows = self._execute(f"SELECT {', '.join(COLUMNS)} FROM repository_automations ORDER BY name")
        return [self._to_dict(row) for row in rows]

    def get(self, key):
        by_id = str(key).isdigit()
        rows = self._execute(f"SELECT {', '.join(COLUMNS)} FROM repository_automations WHERE "
                             f"{'id' if by_id else 'name'} = ?", (int(key) if by_id else key,))
        return self._to_dict(rows[0]) if rows else None

    def save(self, automation, automation_id=None):
        if automation_id is not None and self.get(automation_id) is None:
            raise ValueError("La automatización ya no existe.")
        name = automation["name"].strip()
        if not name or name.isdigit():
            raise ValueError("El nombre no puede estar vacío ni ser solo numérico.")
        interval = int(automation.get("interval_minutes", 15))
        if not 1 <= interval <= 1440:
            raise ValueError("El intervalo debe estar entre 1 y 1440 minutos.")
        info = inspect_repository(automation["repo_path"])
        branch = automation["branch"].strip()
        remote = automation["remote"].strip()
        remote_branch = automation["remote_branch"].strip()
        if branch not in info["branches"]:
            raise ValueError("La rama local elegida no existe.")
        if remote not in info["remotes"] or remote.startswith("-"):
            raise ValueError("El remoto elegido no existe o su nombre no es válido.")
        if remote_branch.startswith("-"):
            raise ValueError("La rama remota no puede comenzar por un guion.")
        git_text(info["repo_path"], "check-ref-format", f"refs/heads/{remote_branch}")
        values = (name, info["repo_path"], branch, remote, remote_branch,
                  int(automation.get("auto_sync", True)), interval)
        try:
            if automation_id is None:
                self._execute("""
                    INSERT INTO repository_automations
                    (name, repo_path, branch, remote, remote_branch, auto_sync, interval_minutes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (*values, now_text()))
            else:
                self._execute("""
                    UPDATE repository_automations SET name=?, repo_path=?, branch=?, remote=?,
                        remote_branch=?, auto_sync=?, interval_minutes=?,
                        last_run=NULL, last_result=NULL, last_details=NULL WHERE id=?
                """, (*values, automation_id))
        except sqlite3.IntegrityError as error:
            raise ValueError("Ya existe una automatización con ese nombre o repositorio.") from error
        return self.get(automation_id) if automation_id is not None else self.get(name)

    def update(self, automation_id, **fields):
        allowed = {"auto_sync", "interval_minutes", "last_run", "last_result", "last_details"}
        if set(fields) - allowed:
            raise ValueError("Campo de automatización no actualizable.")
        if "interval_minutes" in fields and not 1 <= int(fields["interval_minutes"]) <= 1440:
            raise ValueError("El intervalo debe estar entre 1 y 1440 minutos.")
        if "last_details" in fields and fields["last_details"] is not None:
            fields["last_details"] = json.dumps(fields["last_details"], ensure_ascii=False)
        fields = {key: int(value) if isinstance(value, bool) else value for key, value in fields.items()}
        if fields:
            self._execute(f"UPDATE repository_automations SET "
                          f"{', '.join(key + '=?' for key in fields)} WHERE id=?",
                          (*fields.values(), automation_id))

    def delete(self, automation_id):
        self._execute("DELETE FROM repository_automations WHERE id=?", (automation_id,))


@contextlib.contextmanager
def repository_lock(repo):
    # El bloqueo del SO se libera también al morir el proceso. No se borra el
    # fichero: borrarlo permitiría bloquear dos inodos distintos simultáneamente.
    common = git_text(repo, "rev-parse", "--git-common-dir")
    path = os.path.join(repo, common, "git_info_automation.lock")
    with open(path, "a+b") as lock:
        if os.path.getsize(path) == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise GitError("Este repositorio ya está siendo actualizado por otra automatización.") from error
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _blocked_reason(repo, branch):
    for state in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD",
                  "REVERT_HEAD", "BISECT_LOG", "sequencer"):
        path = git_text(repo, "rev-parse", "--git-path", state)
        if os.path.exists(os.path.join(repo, path)):
            return f"Hay una operación Git en curso ({state})."
    current = git_text(repo, "branch", "--show-current")
    if current != branch:
        return f"La rama activa es '{current or 'HEAD separado'}'; se esperaba '{branch}'. No se cambia de rama."
    status = run_git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                     "--ignore-submodules=none", timeout=30)
    if status:
        return "Hay cambios locales o ficheros sin seguimiento. No se modifica la carpeta de trabajo."
    return None


def _run_update(automation, progress, cancel):
    repo, branch = automation["repo_path"], automation["branch"]
    info = inspect_repository(repo)
    if normalized_path(repo) != info["repo_path"]:
        raise ValueError("La ruta registrada ya no es la raíz del repositorio.")
    with repository_lock(repo):
        check_cancel(cancel)
        reason = _blocked_reason(repo, branch)
        if reason:
            return {"status": "blocked", "text": f"Bloqueada: {reason}"}
        remote, remote_branch = automation["remote"], automation["remote_branch"]
        if remote not in info["remotes"] or remote.startswith("-"):
            raise ValueError("El remoto configurado ya no existe o no es válido.")
        git_text(repo, "check-ref-format", f"refs/heads/{remote_branch}")
        ref = f"refs/remotes/{remote}/{remote_branch}"
        if progress:
            progress(f"[{automation['name']}] Descargando {remote}/{remote_branch}...")
        run_git(repo, "fetch", "--no-tags", "--no-recurse-submodules", "--", remote,
                f"+refs/heads/{remote_branch}:{ref}", timeout=600)
        check_cancel(cancel)
        target = git_text(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
        before = git_text(repo, "rev-parse", "--verify", "HEAD")
        ahead, behind = map(int, git_text(repo, "rev-list", "--left-right", "--count",
                                         f"{before}...{target}").split())
        details = {"before": before, "target": target, "ahead": ahead, "behind": behind}
        if ahead:
            return dict(details, status="blocked",
                        text=f"Bloqueada: {ahead} commit(s) locales y {behind} remotos pendientes. "
                             "No se hace merge ni se publican commits.")
        if not behind:
            return dict(details, status="unchanged", after=before, text="Al día; sin cambios.")
        # Fetch puede tardar: revisar de nuevo antes de tocar el working tree.
        reason = _blocked_reason(repo, branch)
        if reason or git_text(repo, "rev-parse", "HEAD") != before:
            return dict(details, status="blocked",
                        text=f"Bloqueada: {reason or 'HEAD cambió durante la descarga.'}")
        check_cancel(cancel)
        run_git(repo, "-c", "merge.autostash=false", "-c", "submodule.recurse=false",
                "merge", "--ff-only", "--no-autostash", "--no-squash", "--no-edit",
                "--no-overwrite-ignore", target, timeout=120)
        after = git_text(repo, "rev-parse", "HEAD")
        if after != target:
            raise GitError("La actualización no terminó en el commit remoto esperado.")
        return dict(details, status="updated", after=after,
                    text=f"Actualizada: {behind} commit(s) incorporados por fast-forward.")


def run_repository_automation(store, automation, progress=None, cancel=None):
    try:
        result = _run_update(automation, progress, cancel)
    except Exception as error:
        store.update(automation["id"], last_run=now_text(), last_result=f"Error: {error}",
                     last_details={"status": "error", "error": str(error)})
        raise
    store.update(automation["id"], last_run=now_text(), last_result=result["text"], last_details=result)
    return result


def due_automations(store, now=None):
    return [automation for automation in store.list() if is_due(automation, now)]
