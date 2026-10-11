"""Formato compartible de configuración, sin historial ni ejecución al importar."""
import json
import sqlite3

from .gitcmd import compile_regex
from .repo_automations import LOCAL_CHANGE_MODES, RepositoryAutomationStore, inspect_repository
from .saved_searches import SavedSearchStore, validate_fetch_failure

FORMAT = "git-info-automations"
FIELDS = {
    "repo": ("name", "repo_path", "branch", "remote", "remote_branch", "auto_sync",
             "interval_minutes", "local_changes", "restore_stash", "fetch_failure"),
    "search": ("name", "repo_path", "scope", "path_regex", "branch_regex", "ignore_case",
               "selected_paths", "dest_dir", "layout", "overwrite_local", "fetch_before",
               "auto_sync", "interval_minutes", "fetch_failure"),
}
REQUIRED = {
    "repo": ("name", "repo_path", "branch", "remote", "remote_branch"),
    "search": ("name", "repo_path", "scope", "dest_dir", "layout"),
}


def validate_record(record):
    if not isinstance(record, dict) or set(record) != {"type", "config"}:
        raise ValueError("Cada automatización debe contener type y config.")
    kind, config = record["type"], record["config"]
    if not isinstance(kind, str) or kind not in FIELDS or not isinstance(config, dict):
        raise ValueError("Tipo o configuración de automatización no válido.")
    if set(config) - set(FIELDS[kind]):
        raise ValueError("La configuración contiene campos no admitidos.")
    for field in REQUIRED[kind]:
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError(f"Falta un valor de texto para {field}.")
    if config["name"].strip().isdigit():
        raise ValueError("El nombre no puede ser solo numérico.")
    validate_fetch_failure(config.get("fetch_failure", "stop"))
    for field in ("auto_sync", "restore_stash", "ignore_case", "overwrite_local", "fetch_before"):
        if field in config and type(config[field]) is not bool:
            raise ValueError(f"{field} debe ser booleano.")
    interval = config.get("interval_minutes", 15)
    if type(interval) is not int or not 1 <= interval <= 1440:
        raise ValueError("El intervalo debe estar entre 1 y 1440 minutos.")
    if kind == "repo":
        mode = config.get("local_changes", "block")
        if not isinstance(mode, str) or mode not in LOCAL_CHANGE_MODES:
            raise ValueError("La política de cambios locales no es válida.")
    else:
        if config["scope"] not in ("local", "remote", "all") or config["layout"] not in ("repo", "branch"):
            raise ValueError("Ámbito o estructura de destino no válida.")
        for field in ("path_regex", "branch_regex"):
            value = config.get(field, "")
            if not isinstance(value, str):
                raise ValueError(f"{field} debe ser texto.")
            compile_regex(value, config.get("ignore_case", True))
        paths = config.get("selected_paths")
        if paths is not None and (not isinstance(paths, list) or
                                  any(not isinstance(path, str) or not path for path in paths)):
            raise ValueError("La selección debe ser una lista de rutas o null.")
    return {"type": kind, "config": dict(config)}


def export_automations(path, records):
    entries = [validate_record({"type": kind, "config": {
        key: item[key] for key in FIELDS[kind] if key in item
    }}) for kind, item in records]
    if not entries:
        raise ValueError("Selecciona al menos una automatización para exportar.")
    with open(path, "w", encoding="utf-8") as file:
        json.dump({"format": FORMAT, "version": 1, "automations": entries},
                  file, ensure_ascii=False, indent=2)
        file.write("\n")


def read_automations(path):
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    if (not isinstance(data, dict) or data.get("format") != FORMAT or
            type(data.get("version")) is not int or data["version"] != 1 or
            not isinstance(data.get("automations"), list)):
        raise ValueError("No es un archivo de automatizaciones compatible (versión 1).")
    return [validate_record(record) for record in data["automations"]]


def import_automations(repository_store, search_store, records):
    """Importa todo o nada; nunca reemplaza tareas existentes ni ejecuta Git pull."""
    entries = [validate_record(record) for record in records]
    if not entries:
        raise ValueError("Selecciona al menos una automatización para importar.")
    if repository_store.db_path != search_store.db_path:
        raise ValueError("Las automatizaciones deben compartir la misma base de datos.")
    connection = repository_store._connect()
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            stores = {
                "repo": RepositoryAutomationStore(repository_store.db_path, connection),
                "search": SavedSearchStore(search_store.db_path, connection),
            }
            imported = []
            for record in entries:
                kind, config = record["type"], record["config"]
                store = stores[kind]
                name = config["name"].strip()
                if store.get(name) is not None:
                    raise ValueError(f"Ya existe una automatización de tipo {kind} llamada '{name}'.")
                if kind == "search":
                    inspect_repository(config["repo_path"])
                imported.append((kind, store.save(dict(config, name=name))))
            return imported
    except sqlite3.IntegrityError as error:
        raise ValueError("Hay automatizaciones duplicadas; no se ha importado ninguna.") from error
    finally:
        connection.close()
