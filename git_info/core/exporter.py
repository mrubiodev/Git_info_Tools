"""Copia versiones concretas de ficheros del repositorio a una carpeta local.

Mantiene un manifiesto en la carpeta destino para saber qué se descargó y
detectar cambios locales, de forma que las sincronizaciones solo escriben lo
que ha cambiado y nunca pisan ediciones manuales salvo que se pida.
"""
import datetime
import hashlib
import json
import os
import re
import subprocess

from .commit_info import format_timestamp
from .gitcmd import Cancelled, GitError, check_cancel, popen_git

MANIFEST_NAME = ".git_latest_manifest.json"

LAYOUT_REPO = "repo"      # destino/<ruta en el repo>
LAYOUT_BRANCH = "branch"  # destino/<rama>/<ruta en el repo>

STATUS_UNCHECKED = "Sin comprobar"
STATUS_MISSING = "No descargado"
STATUS_UP_TO_DATE = "Al día"
STATUS_UPDATE_AVAILABLE = "Actualización disponible"
STATUS_LOCAL_MODIFIED = "Modificado localmente"
STATUS_UNTRACKED = "Sin seguimiento"
STATUS_ERROR = "Error"

_WINDOWS_INVALID = re.compile(r'[<>:"|?*\x00-\x1f]')


def git_blob_id(data, id_length=40):
    algo = hashlib.sha256 if id_length == 64 else hashlib.sha1
    return algo(b"blob %d\0" % len(data) + data).hexdigest()


def file_blob_id(path, id_length=40):
    with open(path, "rb") as f:
        return git_blob_id(f.read(), id_length)


def _safe_segment(segment):
    return _WINDOWS_INVALID.sub("_", segment).rstrip(" .") or "_"


def target_relpath(entry, layout=LAYOUT_REPO):
    parts = entry["path"].split("/")
    if layout == LAYOUT_BRANCH:
        parts = [_safe_segment(s) for s in entry["branch"].split("/")] + parts
    for p in parts:
        if p in ("", ".", "..") or p.lower() == ".git":
            raise ValueError(f"Ruta no permitida: {entry['path']}")
    return "/".join(parts)


def resolve_target(dest_dir, relpath):
    base = os.path.abspath(dest_dir)
    target = os.path.abspath(os.path.join(base, *relpath.split("/")))
    if os.path.commonpath([base, target]) != base:
        raise ValueError(f"Ruta fuera de la carpeta destino: {relpath}")
    return target


def is_inside(path, folder):
    try:
        a, b = os.path.abspath(path), os.path.abspath(folder)
        return os.path.commonpath([a, b]) == b
    except ValueError:  # distintas unidades en Windows
        return False


def load_manifest(dest_dir):
    try:
        with open(os.path.join(dest_dir, MANIFEST_NAME), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "files": {}}


def save_manifest(dest_dir, manifest):
    path = os.path.join(dest_dir, MANIFEST_NAME)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    os.replace(path + ".tmp", path)


class BlobReader:
    """Lee blobs a través de un único proceso `git cat-file --batch`."""

    def __init__(self, repo_path):
        self.proc = popen_git(repo_path, "cat-file", "--batch", stdin=subprocess.PIPE)

    def read(self, sha):
        self.proc.stdin.write(sha.encode("ascii") + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode("ascii", "replace").split()
        if len(header) < 3:
            raise GitError(f"Objeto no encontrado en el repositorio: {sha}")
        remaining = int(header[2])
        chunks = []
        while remaining > 0:
            chunk = self.proc.stdout.read(remaining)
            if not chunk:
                raise GitError(f"Lectura incompleta del objeto {sha}")
            chunks.append(chunk)
            remaining -= len(chunk)
        self.proc.stdout.read(1)  # salto de línea que sigue al contenido
        return b"".join(chunks)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        finally:
            self.proc.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _record(entry, st):
    return {
        "path": entry["path"], "branch": entry["branch"], "commit": entry["commit"],
        "blob": entry["blob"], "date": entry.get("date") or format_timestamp(entry.get("timestamp", 0)),
        "size": st.st_size, "mtime_ns": st.st_mtime_ns,
    }


def _local_state(target, prev, id_length):
    """Blob del fichero local; evita recalcularlo si no ha cambiado desde la última descarga."""
    st = os.stat(target)
    if prev and st.st_size == prev.get("size") and st.st_mtime_ns == prev.get("mtime_ns"):
        return prev["blob"], st
    return file_blob_id(target, id_length), st


def _write_atomic(target, data):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".gitlatest.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, target)


def export_entries(repo_path, entries, dest_dir, layout=LAYOUT_REPO, overwrite_local=False,
                   progress=None, cancel=None):
    """Copia a `dest_dir` la versión (blob) de cada entrada.

    Devuelve {'written', 'unchanged', 'conflicts', 'errors'}. Un fichero local
    distinto de lo último descargado es un conflicto y no se sobrescribe salvo
    `overwrite_local`.
    """
    os.makedirs(dest_dir, exist_ok=True)
    manifest = load_manifest(dest_dir)
    manifest["repo"] = os.path.abspath(repo_path)
    files = manifest["files"]
    summary = {"written": [], "written_details": [], "unchanged": [], "conflicts": [], "errors": []}
    total = len(entries)
    try:
        with BlobReader(repo_path) as reader:
            for i, entry in enumerate(entries, 1):
                check_cancel(cancel)
                if progress and (i == 1 or i % 25 == 0 or i == total):
                    progress(f"Exportando {i}/{total}: {entry['path']}")
                try:
                    rel = target_relpath(entry, layout)
                    target = resolve_target(dest_dir, rel)
                    prev = files.get(rel)
                    if os.path.isfile(target):
                        local_blob, st = _local_state(target, prev, len(entry["blob"]))
                        if local_blob == entry["blob"]:
                            files[rel] = _record(entry, st)
                            summary["unchanged"].append(rel)
                            continue
                        if not overwrite_local and (prev is None or local_blob != prev.get("blob")):
                            summary["conflicts"].append(rel)
                            continue
                    _write_atomic(target, reader.read(entry["blob"]))
                    files[rel] = _record(entry, os.stat(target))
                    summary["written"].append(rel)
                    summary["written_details"].append({
                        "target": rel, "path": entry["path"],
                        "branch": entry["branch"], "commit": entry["commit"],
                    })
                except Cancelled:
                    raise
                except Exception as e:
                    summary["errors"].append(f"{entry.get('path')}: {e}")
    finally:
        # Se guarda también si se cancela, para no perder lo ya descargado.
        manifest["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_manifest(dest_dir, manifest)
    return summary


def inspect_entries(dest_dir, entries, layout=LAYOUT_REPO, progress=None, cancel=None):
    """Compara los ficheros del destino con las versiones actuales y el manifiesto."""
    manifest = load_manifest(dest_dir)
    files = manifest["files"]
    statuses = {}
    errors = []
    for i, entry in enumerate(entries, 1):
        check_cancel(cancel)
        if progress and (i == 1 or i % 25 == 0 or i == len(entries)):
            progress(f"Comprobando {i}/{len(entries)}: {entry['path']}")
        try:
            rel = target_relpath(entry, layout)
            target = resolve_target(dest_dir, rel)
            if not os.path.isfile(target):
                statuses[entry["path"]] = STATUS_MISSING
                continue

            local_blob = file_blob_id(target, len(entry["blob"]))
            if local_blob == entry["blob"]:
                statuses[entry["path"]] = STATUS_UP_TO_DATE
                continue

            previous = files.get(rel)
            previous_blob = previous.get("blob") if isinstance(previous, dict) else None
            if previous_blob and local_blob == previous_blob:
                statuses[entry["path"]] = STATUS_UPDATE_AVAILABLE
            elif previous_blob:
                statuses[entry["path"]] = STATUS_LOCAL_MODIFIED
            else:
                statuses[entry["path"]] = STATUS_UNTRACKED
        except Cancelled:
            raise
        except Exception as e:
            statuses[entry["path"]] = STATUS_ERROR
            errors.append(f"{entry.get('path')}: {e}")
    return {"statuses": statuses, "errors": errors}


def summary_text(summary):
    parts = [f"{len(summary['written'])} descargados", f"{len(summary['unchanged'])} sin cambios"]
    if summary.get("conflicts"):
        parts.append(f"{len(summary['conflicts'])} con cambios locales (no sobrescritos)")
    if summary.get("missing"):
        parts.append(f"{len(summary['missing'])} ya no existen en ninguna rama")
    if summary.get("errors"):
        parts.append(f"{len(summary['errors'])} errores")
    return ", ".join(parts)
