"""Localiza, para cada fichero, la rama donde está su versión más reciente."""
import hashlib

from .commit_info import format_timestamp
from .gitcmd import check_cancel, compile_regex, popen_git, run_git, unquote_path

SCOPE_REMOTE = "remote"
SCOPE_LOCAL = "local"
SCOPE_ALL = "all"
SCOPES = {
    SCOPE_REMOTE: ["refs/remotes"],
    SCOPE_LOCAL: ["refs/heads"],
    SCOPE_ALL: ["refs/heads", "refs/remotes"],
}


def list_branches(repo_path, scope=SCOPE_REMOTE, branch_regex=None, ignore_case=True):
    """[{'ref', 'name', 'sha'}] de las ramas del ámbito, filtradas por regex opcional."""
    if scope not in SCOPES:
        raise ValueError(f"Ámbito de ramas desconocido: {scope}")
    rx = compile_regex(branch_regex, ignore_case)
    out = run_git(repo_path, "for-each-ref",
                  "--format=%(refname)%00%(refname:short)%00%(objectname)", *SCOPES[scope])
    branches = []
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\0")
        if len(parts) != 3 or parts[0].endswith("/HEAD"):
            continue
        ref, name, sha = parts
        if rx and not rx.search(name):
            continue
        branches.append({"ref": ref, "name": name, "sha": sha})
    return branches


def refs_signature(branches):
    """Huella de las puntas de las ramas: cambia si alguna rama avanza, aparece o desaparece."""
    joined = "\n".join(f"{b['ref']} {b['sha']}" for b in sorted(branches, key=lambda b: b["ref"]))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def tip_files(repo_path, sha):
    """{ruta: blob} de todos los ficheros que existen en el commit `sha`."""
    out = run_git(repo_path, "ls-tree", "-r", "-z", "--full-tree", sha)
    files = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        fields = meta.split()
        if len(fields) == 3 and fields[1] == b"blob":  # ignora submódulos
            files[path.decode("utf-8", "replace")] = fields[2].decode("ascii")
    return files


def last_commits(repo_path, sha, wanted, cancel=None):
    """{ruta: (hash, timestamp, autor, asunto)} del último commit que tocó cada ruta.

    Lee `git log` en streaming y se detiene en cuanto resuelve todas las rutas.
    """
    proc = popen_git(repo_path, "log", "--no-renames", "--name-only",
                     "--format=%x1e%H%x1f%ct%x1f%an%x1f%s", sha, "--")
    remaining = set(wanted)
    result = {}
    first = current = None
    try:
        for n, raw in enumerate(proc.stdout):
            if n % 2000 == 0:
                check_cancel(cancel)
            line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
            if line.startswith("\x1e"):
                fields = (line[1:].split("\x1f", 3) + ["", "", "", ""])[:4]
                current = (fields[0], int(fields[1] or 0), fields[2], fields[3])
                first = first or current
                continue
            if not line or current is None:
                continue
            path = unquote_path(line)
            if path in remaining:
                result[path] = current
                remaining.discard(path)
                if not remaining:
                    break
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.stdout.close()
        proc.wait()
    # Historial incompleto (p. ej. clon superficial): se atribuye al commit de la punta.
    if first is not None:
        for path in remaining:
            result[path] = first
    return result


def _pick_latest(entries):
    entries.sort(key=lambda e: (-e["timestamp"], e["branch"]))
    best = dict(entries[0])
    best["date"] = format_timestamp(best["timestamp"])
    best["same_in"] = [e["branch"] for e in entries[1:] if e["blob"] == best["blob"]]
    best["branch_count"] = len(entries)
    return best


def scan_latest(repo_path, scope=SCOPE_REMOTE, path_regex="", branch_regex="", ignore_case=True,
                progress=None, cancel=None, branches=None):
    """Devuelve (resultados, ramas analizadas).

    Cada resultado describe la versión más reciente de un fichero: la rama cuyo
    último commit sobre ese fichero tiene la fecha más reciente. Solo cuentan
    los ficheros que existen en la punta de cada rama.
    """
    prx = compile_regex(path_regex, ignore_case)
    if branches is None:
        branches = list_branches(repo_path, scope, branch_regex, ignore_case)
    candidates = {}
    commits_by_tip = {}
    for i, branch in enumerate(branches, 1):
        check_cancel(cancel)
        if progress:
            progress(f"Analizando rama {i}/{len(branches)}: {branch['name']}")
        files = tip_files(repo_path, branch["sha"])
        if prx:
            files = {p: b for p, b in files.items() if prx.search(p)}
        if not files:
            continue
        if branch["sha"] not in commits_by_tip:
            commits_by_tip[branch["sha"]] = last_commits(repo_path, branch["sha"], files.keys(), cancel)
        commits = commits_by_tip[branch["sha"]]
        for path, blob in files.items():
            commit_hash, ts, author, message = commits.get(path, ("", 0, "", ""))
            candidates.setdefault(path, []).append({
                "path": path, "branch": branch["name"], "ref": branch["ref"], "blob": blob,
                "commit": commit_hash, "timestamp": ts, "author": author, "message": message,
            })
    results = [_pick_latest(entries) for entries in candidates.values()]
    results.sort(key=lambda e: e["path"].lower())
    return results, branches
