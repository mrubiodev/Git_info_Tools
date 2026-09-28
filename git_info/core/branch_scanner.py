"""Análisis de ramas remotas existentes y candidatas recuperables del reflog.

Las funciones informan del progreso a través de `log(mensaje)`, de modo que
puedan usarse tanto desde la GUI como desde otros contextos.
"""
import re
import subprocess

from git import Repo, GitCommandError

from .commit_info import commit_summary, modified_files, summarize_files
from .gitcmd import NO_WINDOW

REFLOG_PATTERNS = [
    re.compile(r"HEAD@\{\d+\}:\s*(?:checkout|branch|merge|rebase\s+\(finish\)|rebase\s+\(pick\)|rebase\s+\(start\)):.*(?:from|to)\s+([^\s]+)$"),
    re.compile(r"HEAD@\{\d+\}:\s*commit(?:\s+\(initial\))?:.*refs/heads/([^\s]+)$"),
    re.compile(r"HEAD@\{\d+\}:\s*merge\s+([^\s]+):.*"),
    re.compile(r"HEAD@\{\d+\}:\s*reset:.*to\s+([^\s]+)$"),
]
_HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _noop(_message):
    pass


def open_repo(repo_path):
    return Repo(repo_path)


def fetch_remotes(repo, log=_noop, progress=None):
    """`fetch --prune` de todos los remotos. Devuelve False si no hay remotos."""
    log("Realizando 'git fetch --prune origin' para actualizar la información remota...")
    if not repo.remotes:
        log("Error: El repositorio no tiene remotos configurados.")
        return False
    for remote in repo.remotes:
        try:
            remote.fetch(prune=True, progress=progress)
            log(f"Fetch completado para remoto: {remote.name}")
        except GitCommandError as e:
            log(f"Advertencia: No se pudo hacer fetch para el remoto '{remote.name}': {e}")
        except Exception as e:
            log(f"Advertencia: Error inesperado durante fetch para '{remote.name}': {e}")
    return True


def remote_branches(repo, log=_noop):
    """Información del último commit de cada rama del remoto predeterminado."""
    branches = []
    for remote_branch in repo.remote().refs:
        if remote_branch.name.endswith('/HEAD'):
            continue
        branch_name = remote_branch.name.split('/', 1)[1]
        try:
            last_commit = remote_branch.commit
            commit_hash = last_commit.hexsha[:7]
            message, date, author = commit_summary(last_commit)
            files = []
            try:
                files = modified_files(repo.commit(last_commit.hexsha))
                log(f"  Rama remota '{branch_name}': {len(files)} archivos modificados encontrados")
            except Exception as e:
                log(f"Advertencia: No se pudieron obtener archivos modificados para '{branch_name}' (commit {commit_hash}): {e}")
            branches.append({
                "type": "remote_existing",
                "name": branch_name,
                "hash": commit_hash,
                "date": date,
                "message": message,
                "author": author,
                "files": summarize_files(files),
            })
        except Exception as e:
            log(f"Advertencia: No se pudo obtener información para la rama remota '{branch_name}': {e}")
    return branches


def read_reflog(repo):
    result = subprocess.run(
        ['git', 'reflog', '--all'], cwd=repo.working_dir, capture_output=True,
        text=True, check=True, encoding='utf-8', creationflags=NO_WINDOW,
    )
    return result.stdout


def _normalize_candidate(name):
    name = name.strip()
    for prefix in ("refs/heads/", "refs/remotes/origin/", "refs/remotes/"):
        name = name.replace(prefix, "")
    return name


def _is_valid_candidate(name, existing, processed):
    return (bool(name)
            and name not in existing
            and not name.startswith("HEAD")
            and not _HASH_RE.match(name)
            and not name.startswith("origin/")
            and name not in processed)


def reflog_candidates(repo, existing_branch_names, log=_noop):
    """Ramas que aparecen en el reflog local pero ya no existen."""
    log("Analizando el reflog local para encontrar ramas borradas...")
    existing = set(existing_branch_names)
    existing.update(h.name for h in repo.heads)
    try:
        reflog_output = read_reflog(repo)
    except subprocess.CalledProcessError as e:
        log(f"Error al ejecutar 'git reflog --all': {e.stderr}")
        return []
    except Exception as e:
        log(f"Error inesperado al obtener el reflog: {e}")
        return []

    candidates = []
    processed = set()
    for line in reflog_output.splitlines():
        match_hash = re.match(r"^([0-9a-f]{7,40})\s+.*", line)
        if not match_hash:
            continue
        commit_hash = match_hash.group(1)
        for pattern in REFLOG_PATTERNS:
            match_branch = pattern.search(line)
            if not match_branch:
                continue
            name = _normalize_candidate(match_branch.group(1))
            if _is_valid_candidate(name, existing, processed):
                try:
                    commit_obj = repo.commit(commit_hash)
                    message, date, author = commit_summary(commit_obj)
                    files = []
                    try:
                        files = modified_files(commit_obj)
                        log(f"  Rama '{name}': {len(files)} archivos modificados encontrados")
                    except Exception as e:
                        log(f"  Advertencia: Error al obtener archivos de '{name}': {e}")
                    candidates.append({
                        "type": "reflog_recoverable",
                        "name": name,
                        "hash": commit_hash,
                        "date": date,
                        "message": message,
                        "author": author,
                        "files": summarize_files(files),
                    })
                    processed.add(name)
                except Exception as e:
                    # El commit puede no ser accesible (p. ej. ya eliminado por el GC)
                    log(f"Advertencia: No se pudo obtener información del commit '{commit_hash}' para la rama '{name}': {e}")
            break
    return candidates


def record_all(store, repo_path, branches):
    """Registra cada rama en la base de datos y le añade su 'status'."""
    for info in branches:
        info['status'] = store.record(repo_path, info)
    return branches


def scan_remote_branches(repo, repo_path, store, log=_noop, fetch_progress=None):
    if not fetch_remotes(repo, log, fetch_progress):
        return []
    return record_all(store, repo_path, remote_branches(repo, log))


def scan_recoverable_branches(repo, repo_path, store, existing_branches, log=_noop):
    names = [b['name'] for b in existing_branches]
    return record_all(store, repo_path, reflog_candidates(repo, names, log))
