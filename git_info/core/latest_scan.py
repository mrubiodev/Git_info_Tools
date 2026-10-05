"""Localiza, para cada fichero, la rama donde está su versión más reciente."""
import hashlib

from .commit_info import format_timestamp
from .gitcmd import GitError, check_cancel, compile_regex, popen_git, run_git, unquote_path
from .repo_cache import RepoCache

SCOPE_REMOTE = "remote"
SCOPE_LOCAL = "local"
SCOPE_ALL = "all"
SCOPES = {
    SCOPE_REMOTE: ["refs/remotes"],
    SCOPE_LOCAL: ["refs/heads"],
    SCOPE_ALL: ["refs/heads", "refs/remotes"],
}


def list_branches(repo_path, scope=SCOPE_REMOTE, branch_regex=None, ignore_case=True, db_path=None, use_cache=True):
    """[{'ref', 'name', 'sha'}] de las ramas del ámbito, filtradas por regex opcional."""
    if scope not in SCOPES:
        raise ValueError(f"Ámbito de ramas desconocido: {scope}")
    rx = compile_regex(branch_regex, ignore_case)

    # Las referencias son baratas de consultar y deben leerse siempre en vivo:
    # una caché compartida entre ámbitos podía ocultar main o devolver ramas
    # eliminadas justo después de un fetch.
    out = run_git(repo_path, "for-each-ref",
                  "--format=%(refname)%00%(refname:short)%00%(objectname)", *SCOPES[scope])
    default_refs = _default_branch_refs(repo_path)
    branches = []
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\0")
        if len(parts) != 3 or parts[0].endswith("/HEAD"):
            continue
        ref, name, sha = parts
        if rx and not rx.search(name):
            continue
        branches.append({
            "ref": ref,
            "name": name,
            "sha": sha,
            "is_default": ref in default_refs,
        })
    if not any(branch["is_default"] for branch in branches):
        for preferred in ("main", "master"):
            matches = [branch for branch in branches
                       if branch["name"] == preferred or branch["name"].endswith("/" + preferred)]
            if matches:
                matches[0]["is_default"] = True
                break

    # Store into cache for later runs (best-effort)
    if db_path:
        try:
            cache = RepoCache(db_path)
            cache.set_branches(repo_path, refs_signature(branches), branches)
        except Exception:
            pass
    return branches


def _default_branch_refs(repo_path):
    """Referencias local y remota de la rama predeterminada, si está configurada."""
    try:
        remote_ref = run_git(
            repo_path, "symbolic-ref", "--quiet",
            "refs/remotes/origin/HEAD").decode("utf-8", "replace").strip()
    except GitError:
        return set()
    branch_name = remote_ref.rsplit("/", 1)[-1]
    return {remote_ref, f"refs/heads/{branch_name}"}


def refs_signature(branches):
    """Huella de las puntas de las ramas: cambia si alguna rama avanza, aparece o desaparece."""
    joined = "\n".join(f"{b['ref']} {b['sha']}" for b in sorted(branches, key=lambda b: b["ref"]))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def tip_files(repo_path, sha, db_path=None):
    """{ruta: blob} de todos los ficheros que existen en el commit `sha`."""
    # Try cache first
    if db_path:
        try:
            cache = RepoCache(db_path)
            cached = cache.get_tip_files(repo_path, sha)
            if cached is not None:
                return cached
        except Exception:
            pass

    out = run_git(repo_path, "ls-tree", "-r", "-z", "--full-tree", sha)
    files = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        fields = meta.split()
        if len(fields) == 3 and fields[1] == b"blob":  # ignora submódulos
            files[path.decode("utf-8", "replace")] = fields[2].decode("ascii")

    # Store in cache (best-effort)
    if db_path:
        try:
            cache = RepoCache(db_path)
            cache.set_tip_files(repo_path, sha, files)
        except Exception:
            pass

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
    entries.sort(key=lambda e: (-e["timestamp"], not e.get("is_default", False), e["branch"]))
    best = dict(entries[0])
    best["date"] = format_timestamp(best["timestamp"])
    best["same_in"] = [e["branch"] for e in entries if e is not entries[0] and e["blob"] == best["blob"]]
    best["branch_count"] = len(entries)
    return best


def file_history(repo_path, path, branches, max_commits=100):
    """Historial del fichero agrupado por rama para mostrarlo como árbol."""
    history = []
    for branch in branches:
        out = run_git(
            repo_path, "log", f"--max-count={max_commits}", "--date-order",
            "--format=%H%x00%ct%x00%an%x00%s", branch["ref"], "--", path)
        commits = []
        for line in out.decode("utf-8", "replace").splitlines():
            fields = line.split("\0", 3)
            if len(fields) != 4:
                continue
            commit_hash, timestamp, author, message = fields
            commits.append({
                "commit": commit_hash,
                "timestamp": int(timestamp or 0),
                "date": format_timestamp(int(timestamp or 0)),
                "author": author,
                "message": message,
            })
        history.append({
            "ref": branch["ref"],
            "branch": branch["name"],
            "is_default": branch.get("is_default", False),
            "commits": commits,
        })
    history.sort(key=lambda item: (not item["is_default"], item["branch"].lower()))
    return history


def scan_latest(repo_path, scope=SCOPE_REMOTE, path_regex="", branch_regex="", ignore_case=True,
                progress=None, cancel=None, branches=None, db_path=None, parallel=False, max_workers=4):
    """Devuelve (resultados, ramas analizadas).

    Cada resultado describe la versión más reciente de un fichero: la rama cuyo
    último commit sobre ese fichero tiene la fecha más reciente. Solo cuentan
    los ficheros que existen en la punta de cada rama.
    """
    prx = compile_regex(path_regex, ignore_case)
    if branches is None:
        branches = list_branches(repo_path, scope, branch_regex, ignore_case, db_path=db_path, use_cache=True)
    candidates = {}
    commits_by_tip = {}

    # If parallel requested, process unique SHAs concurrently: fetch tip_files then last_commits.
    if parallel:
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
        except Exception:
            parallel = False

    if parallel:
        # Unique SHAs preserving order
        unique_shas = []
        seen = set()
        for b in branches:
            if b["sha"] not in seen:
                seen.add(b["sha"]) 
                unique_shas.append(b["sha"])

        # Fetch tip_files in parallel
        sha_to_files = {}
        total = len(unique_shas)
        if progress:
            progress(f"Recuperando listados de ficheros de {total} puntas (paralelo={max_workers})")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sha = {executor.submit(tip_files, repo_path, sha, db_path): sha for sha in unique_shas}
            completed = 0
            for fut in as_completed(future_to_sha):
                sha = future_to_sha[fut]
                completed += 1
                try:
                    files = fut.result()
                except Exception:
                    files = {}
                if prx:
                    try:
                        files = {p: b for p, b in files.items() if prx.search(p)}
                    except Exception:
                        files = {}
                sha_to_files[sha] = files
                if progress:
                    progress(f"Listados recuperados: {completed}/{total} (SHA {sha[:7]})")

        # For SHAs that have files, fetch last_commits in parallel
        if progress:
            progress(f"Obteniendo commits por SHA (paralelo={max_workers})")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sha = {}
            for sha, files in sha_to_files.items():
                if not files:
                    continue
                # last_commits expects an iterable of paths
                future_to_sha[executor.submit(last_commits, repo_path, sha, files.keys(), cancel)] = sha
            completed = 0
            total = len(future_to_sha)
            for fut in as_completed(future_to_sha):
                sha = future_to_sha[fut]
                completed += 1
                try:
                    commits = fut.result()
                except Exception:
                    commits = {}
                commits_by_tip[sha] = commits
                if progress:
                    progress(f"Commits obtenidos: {completed}/{total} (SHA {sha[:7]})")

        # Build candidates
        for branch in branches:
            check_cancel(cancel)
            files = sha_to_files.get(branch["sha"], {})
            if not files:
                continue
            commits = commits_by_tip.get(branch["sha"], {})
            for path, blob in files.items():
                commit_hash, ts, author, message = commits.get(path, ("", 0, "", ""))
                candidates.setdefault(path, []).append({
                    "path": path, "branch": branch["name"], "ref": branch["ref"], "blob": blob,
                    "commit": commit_hash, "timestamp": ts, "author": author, "message": message,
                    "is_default": branch.get("is_default", False),
                })
    else:
        for i, branch in enumerate(branches, 1):
            check_cancel(cancel)
            if progress:
                progress(f"Analizando rama {i}/{len(branches)}: {branch['name']}")
            files = tip_files(repo_path, branch["sha"], db_path=db_path)
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
                    "is_default": branch.get("is_default", False),
                })
    results = [_pick_latest(entries) for entries in candidates.values()]
    results.sort(key=lambda e: e["path"].lower())
    return results, branches
