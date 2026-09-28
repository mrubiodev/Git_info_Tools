"""Persistencia SQLite de las búsquedas de últimas versiones guardadas."""
import datetime
import json
import sqlite3

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

COLUMNS = ("id", "name", "repo_path", "scope", "path_regex", "branch_regex", "ignore_case",
           "selected_paths", "dest_dir", "layout", "overwrite_local", "fetch_before",
           "auto_sync", "interval_minutes", "created_at", "last_run", "last_result",
           "refs_signature")
_BOOL_COLUMNS = ("ignore_case", "overwrite_local", "fetch_before", "auto_sync")
_UPDATABLE = {"auto_sync", "interval_minutes", "last_run", "last_result", "refs_signature"}


def now_text():
    return datetime.datetime.now().strftime(TIME_FORMAT)


class SavedSearchStore:
    def __init__(self, db_path):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def _execute(self, query, params=()):
        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def init(self):
        self._execute("""
            CREATE TABLE IF NOT EXISTS saved_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                repo_path TEXT NOT NULL,
                scope TEXT NOT NULL,
                path_regex TEXT DEFAULT '',
                branch_regex TEXT DEFAULT '',
                ignore_case INTEGER DEFAULT 1,
                selected_paths TEXT, -- JSON con rutas concretas; NULL = todo lo que cumpla el filtro
                dest_dir TEXT NOT NULL,
                layout TEXT NOT NULL,
                overwrite_local INTEGER DEFAULT 0,
                fetch_before INTEGER DEFAULT 1,
                auto_sync INTEGER DEFAULT 0,
                interval_minutes INTEGER DEFAULT 15,
                created_at TEXT,
                last_run TEXT,
                last_result TEXT,
                refs_signature TEXT -- huella de las ramas en la última ejecución correcta
            )
        """)

    @staticmethod
    def _to_dict(row):
        data = dict(zip(COLUMNS, row))
        data["selected_paths"] = json.loads(data["selected_paths"]) if data["selected_paths"] else None
        for key in _BOOL_COLUMNS:
            data[key] = bool(data[key])
        return data

    def list(self):
        rows = self._execute(f"SELECT {', '.join(COLUMNS)} FROM saved_searches ORDER BY name")
        return [self._to_dict(r) for r in rows]

    def get(self, key):
        """Busca por id (numérico) o por nombre."""
        by_id = str(key).isdigit()
        rows = self._execute(f"SELECT {', '.join(COLUMNS)} FROM saved_searches WHERE "
                             f"{'id' if by_id else 'name'} = ?", (int(key) if by_id else key,))
        return self._to_dict(rows[0]) if rows else None

    def save(self, search):
        """Crea o reemplaza (por nombre) una búsqueda guardada."""
        selected = search.get("selected_paths")
        self._execute("""
            INSERT INTO saved_searches (name, repo_path, scope, path_regex, branch_regex, ignore_case,
                selected_paths, dest_dir, layout, overwrite_local, fetch_before, auto_sync,
                interval_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                repo_path = excluded.repo_path, scope = excluded.scope,
                path_regex = excluded.path_regex, branch_regex = excluded.branch_regex,
                ignore_case = excluded.ignore_case, selected_paths = excluded.selected_paths,
                dest_dir = excluded.dest_dir, layout = excluded.layout,
                overwrite_local = excluded.overwrite_local, fetch_before = excluded.fetch_before,
                auto_sync = excluded.auto_sync, interval_minutes = excluded.interval_minutes,
                refs_signature = NULL
        """, (
            search["name"], search["repo_path"], search["scope"], search.get("path_regex", ""),
            search.get("branch_regex", ""), int(search.get("ignore_case", True)),
            json.dumps(selected, ensure_ascii=False) if selected is not None else None,
            search["dest_dir"], search["layout"], int(search.get("overwrite_local", False)),
            int(search.get("fetch_before", True)), int(search.get("auto_sync", False)),
            int(search.get("interval_minutes", 15)), now_text(),
        ))
        return self.get(search["name"])

    def update(self, search_id, **fields):
        fields = {k: (int(v) if isinstance(v, bool) else v) for k, v in fields.items() if k in _UPDATABLE}
        if fields:
            assignments = ", ".join(f"{k} = ?" for k in fields)
            self._execute(f"UPDATE saved_searches SET {assignments} WHERE id = ?",
                          (*fields.values(), search_id))

    def delete(self, search_id):
        self._execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))


def is_due(search, now=None):
    """True si la búsqueda tiene sincronización automática y ya toca ejecutarla."""
    if not search["auto_sync"]:
        return False
    if not search["last_run"]:
        return True
    try:
        last = datetime.datetime.strptime(search["last_run"], TIME_FORMAT)
    except ValueError:
        return True
    elapsed = ((now or datetime.datetime.now()) - last).total_seconds()
    return elapsed >= max(1, int(search["interval_minutes"])) * 60


def describe_filter(search):
    parts = [f"ficheros: {search['path_regex']}" if search["path_regex"] else "todos los ficheros"]
    if search["branch_regex"]:
        parts.append(f"ramas: {search['branch_regex']}")
    return "; ".join(parts)


def describe_selection(search):
    paths = search["selected_paths"]
    return "Todos" if paths is None else f"{len(paths)} ficheros"
