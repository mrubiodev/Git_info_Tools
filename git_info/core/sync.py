"""Ejecución de búsquedas guardadas: detecta cambios en las ramas y descarga."""
import subprocess

from . import exporter, latest_scan
from .gitcmd import GitError, fetch_all
from .saved_searches import is_due, now_text


def _result(text, **extra):
    base = {"text": text, "changed": False, "written": [], "unchanged": [], "conflicts": [],
            "errors": [], "missing": [], "warnings": []}
    base.update(extra)
    return base


def _with_warnings(text, warnings):
    return text + (" (" + "; ".join(warnings) + ")" if warnings else "")


def run_saved_search(store, search, force=False, progress=None, cancel=None):
    """Ejecuta una búsqueda guardada y registra el resultado en `store`.

    Sin `force`, si las ramas no han cambiado desde la última ejecución
    correcta no se vuelve a escanear ni a descargar nada.
    """
    try:
        return _run(store, search, force, progress, cancel)
    except Exception as e:
        store.update(search["id"], last_run=now_text(), last_result=f"Error: {e}")
        raise


def _run(store, search, force, progress, cancel):
    repo = search["repo_path"]
    warnings = []
    if search["fetch_before"]:
        if progress:
            progress(f"[{search['name']}] git fetch --all --prune")
        try:
            fetch_all(repo)
        except (GitError, subprocess.TimeoutExpired) as e:
            warnings.append(f"fetch falló, se usan las referencias locales: {e}")

    branches = latest_scan.list_branches(repo, search["scope"], search["branch_regex"], search["ignore_case"])
    signature = latest_scan.refs_signature(branches)

    if not force and signature == search.get("refs_signature"):
        text = _with_warnings("Sin cambios en las ramas", warnings)
        store.update(search["id"], last_run=now_text(), last_result=text)
        return _result(text, warnings=warnings)

    results, _ = latest_scan.scan_latest(repo, search["scope"], search["path_regex"],
                                         search["branch_regex"], search["ignore_case"],
                                         progress=progress, cancel=cancel, branches=branches)
    missing = []
    if search["selected_paths"] is not None:
        wanted = set(search["selected_paths"])
        results = [r for r in results if r["path"] in wanted]
        missing = sorted(wanted - {r["path"] for r in results})

    summary = exporter.export_entries(repo, results, search["dest_dir"], search["layout"],
                                      search["overwrite_local"], progress=progress, cancel=cancel)
    summary.update(missing=missing, warnings=warnings, changed=True)
    summary["text"] = _with_warnings(exporter.summary_text(summary), warnings)
    # Con errores no se guarda la huella, para reintentar en la siguiente pasada.
    store.update(search["id"], last_run=now_text(), last_result=summary["text"],
                 refs_signature=None if summary["errors"] else signature)
    return summary


def due_searches(store, now=None):
    return [s for s in store.list() if is_due(s, now)]
