"""Punto de entrada: GUI por defecto o sincronización sin interfaz.

Ejemplos (p. ej. desde el Programador de tareas de Windows):
    python main.py --list
    python main.py --sync "Mi búsqueda"
    python main.py --sync-all
"""
import argparse
import sys

from . import DEFAULT_DB_PATH


def build_parser():
    parser = argparse.ArgumentParser(description="Git Branch Info & Recovery")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Ruta de la base de datos SQLite")
    parser.add_argument("--parallel", action="store_true",
                        help="Habilita escaneo paralelo (experimental)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Número de hilos para escaneo paralelo")
    parser.add_argument("--list", action="store_true", help="Lista las búsquedas guardadas")
    parser.add_argument("--sync", action="append", metavar="NOMBRE_O_ID",
                        help="Ejecuta una búsqueda guardada (se puede repetir)")
    parser.add_argument("--sync-all", action="store_true",
                        help="Ejecuta todas las búsquedas con sincronización automática activada")
    parser.add_argument("--force", action="store_true",
                        help="Escanea y descarga aunque las ramas no hayan cambiado")
    parser.add_argument("--list-automations", action="store_true",
                        help="Lista automatizaciones de repositorios y búsquedas guardadas")
    parser.add_argument("--update-repo", action="append", metavar="NOMBRE_O_ID",
                        help="Actualiza un repositorio registrado solo por fast-forward (repetible)")
    parser.add_argument("--update-repos", action="store_true",
                        help="Ejecuta todos los repositorios con actualización automática activada")
    return parser


def _list(store):
    from .core.saved_searches import describe_filter, describe_selection
    for s in store.list():
        auto = f"auto cada {s['interval_minutes']} min" if s["auto_sync"] else "manual"
        print(f"[{s['id']}] {s['name']} | {s['repo_path']} | {describe_filter(s)} | "
              f"{describe_selection(s)} -> {s['dest_dir']} | {auto} | {s['last_run'] or '-'}: {s['last_result'] or '-'}")
    return 0


def _sync(store, searches, force, parallel=False, workers=4):
    from .core.sync import run_saved_search
    exit_code = 0
    for search in searches:
        try:
            summary = run_saved_search(store, search, force=force, progress=print,
                                       parallel=parallel, max_workers=workers)
            print(f"[{search['name']}] {summary['text']}")
            if summary["errors"]:
                exit_code = 1
        except Exception as e:
            print(f"[{search['name']}] Error: {e}", file=sys.stderr)
            exit_code = 1
    return exit_code


def run_cli(args):
    from .core.saved_searches import SavedSearchStore
    from .core.repo_automations import RepositoryAutomationStore, run_repository_automation
    store = SavedSearchStore(args.db)
    store.init()
    automations = RepositoryAutomationStore(args.db)
    automations.init()
    if args.list_automations:
        for item in automations.list():
            print(f"[repo:{item['id']}] {item['name']} | {item['repo_path']} | "
                  f"{item['branch']} <- {item['remote']}/{item['remote_branch']} | "
                  f"{'auto' if item['auto_sync'] else 'manual'} cada {item['interval_minutes']} min | "
                  f"{item['last_run'] or '-'}: {item['last_result'] or '-'}")
        return _list(store)
    if args.list:
        return _list(store)
    repositories = []
    for key in args.update_repo or []:
        automation = automations.get(key)
        if automation is None:
            print(f"No existe la automatización de repositorio '{key}'.", file=sys.stderr)
            return 2
        if automation not in repositories:
            repositories.append(automation)
    if args.update_repos:
        repositories += [item for item in automations.list()
                         if item["auto_sync"] and item not in repositories]
    searches = []
    for key in args.sync or []:
        search = store.get(key)
        if search is None:
            print(f"No existe la búsqueda guardada '{key}'.", file=sys.stderr)
            return 2
        searches.append(search)
    if args.sync_all:
        searches += [s for s in store.list() if s["auto_sync"] and s not in searches]
    exit_code = 0
    for automation in repositories:
        try:
            result = run_repository_automation(automations, automation, progress=print)
            print(f"[{automation['name']}] {result['text']}")
            if result["status"] == "blocked":
                exit_code = 1
        except Exception as error:
            print(f"[{automation['name']}] Error: {error}", file=sys.stderr)
            exit_code = 1
    return max(exit_code, _sync(store, searches, args.force,
                                parallel=args.parallel, workers=args.workers))


def main(argv=None):
    args = build_parser().parse_args(argv)
    if (args.list or args.sync or args.sync_all or args.list_automations
            or args.update_repo or args.update_repos):
        return run_cli(args)
    from .gui.app import run_gui
    run_gui(args.db)
    return 0
