"""Persistencia SQLite del historial de ramas analizadas."""
import datetime
import sqlite3

TABLE_COLUMNS = ("id", "repo_path", "branch_name", "branch_type", "last_commit_hash", "commit_date",
                 "commit_message", "commit_author", "modified_files", "status")
DETAIL_COLUMNS = ("repo_path", "branch_name", "branch_type", "last_commit_hash", "commit_date",
                  "commit_message", "commit_author", "modified_files", "first_seen_date",
                  "last_updated_date", "status")
BATCH_COLUMNS = ("id", "repo_path", "branch_name", "branch_type", "last_commit_hash",
                 "commit_date", "modified_files")

BATCH_BY_BRANCH = "branch"
BATCH_BY_FILE = "file"


def parse_terms(text):
    """Separa términos por líneas y/o comas, sin duplicados y manteniendo el orden."""
    terms = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if ',' in line:
            terms.extend(t.strip() for t in line.split(',') if t.strip())
        else:
            terms.append(line)
    return list(dict.fromkeys(terms))


class BranchStore:
    def __init__(self, db_path):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init(self):
        """Crea/migra las tablas. Devuelve los mensajes informativos generados."""
        messages = []
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS branches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_path TEXT NOT NULL,
                    branch_name TEXT NOT NULL,
                    branch_type TEXT NOT NULL, -- 'remote_existing', 'local_existing', 'reflog_recoverable'
                    last_commit_hash TEXT,
                    commit_date TEXT,
                    commit_message TEXT,
                    commit_author TEXT,
                    modified_files TEXT, -- Lista de archivos modificados separados por comas
                    first_seen_date TEXT,
                    last_updated_date TEXT,
                    status TEXT, -- 'new', 'updated_commit', 'seen'
                    UNIQUE(repo_path, branch_name, branch_type)
                )
            """)
            cursor.execute("PRAGMA table_info(branches)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'modified_files' not in columns:
                cursor.execute("ALTER TABLE branches ADD COLUMN modified_files TEXT DEFAULT ''")
                messages.append("Base de datos actualizada: columna 'modified_files' agregada.")
            conn.commit()
        finally:
            conn.close()
        messages.append(f"Base de datos SQLite '{self.db_path}' inicializada.")
        return messages

    def record(self, repo_path, info):
        """Inserta o actualiza una rama. Devuelve 'new', 'updated_commit' o 'seen'."""
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        key = (repo_path, info['name'], info['type'])
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_commit_hash FROM branches
                WHERE repo_path = ? AND branch_name = ? AND branch_type = ?
            """, key)
            existing = cursor.fetchone()
            if existing is None:
                status = "new"
                cursor.execute("""
                    INSERT INTO branches (repo_path, branch_name, branch_type, last_commit_hash, commit_date,
                                         commit_message, commit_author, modified_files, first_seen_date, last_updated_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (*key, info['hash'], info['date'], info['message'], info['author'],
                      info.get('files', ''), now, now, status))
            elif existing[0] != info['hash']:
                status = "updated_commit"
                cursor.execute("""
                    UPDATE branches
                    SET last_commit_hash = ?, commit_date = ?, commit_message = ?, commit_author = ?,
                        modified_files = ?, last_updated_date = ?, status = ?
                    WHERE repo_path = ? AND branch_name = ? AND branch_type = ?
                """, (info['hash'], info['date'], info['message'], info['author'],
                      info.get('files', ''), now, status, *key))
            else:
                status = "seen"
                cursor.execute("""
                    UPDATE branches SET last_updated_date = ?, status = ?
                    WHERE repo_path = ? AND branch_name = ? AND branch_type = ?
                """, (now, status, *key))
            conn.commit()
        finally:
            conn.close()
        return status

    def _fetchall(self, query, params=()):
        conn = self._connect()
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def search(self, branch_name="", repo_path="", file_name=""):
        query = f"SELECT {', '.join(TABLE_COLUMNS)} FROM branches WHERE 1=1"
        params = []
        for column, value in (("branch_name", branch_name), ("repo_path", repo_path),
                              ("modified_files", file_name)):
            if value:
                query += f" AND {column} LIKE ?"
                params.append(f"%{value}%")
        query += " ORDER BY commit_date DESC"
        return self._fetchall(query, params)

    def all(self):
        return self._fetchall(f"SELECT {', '.join(TABLE_COLUMNS)} FROM branches ORDER BY commit_date DESC")

    def _details(self, where, params):
        rows = self._fetchall(f"SELECT {', '.join(DETAIL_COLUMNS)} FROM branches WHERE {where}", params)
        return dict(zip(DETAIL_COLUMNS, rows[0])) if rows else None

    def get_details(self, row_id):
        return self._details("id = ?", (row_id,))

    def latest_details_by_name(self, branch_name):
        return self._details("branch_name = ? ORDER BY commit_date DESC LIMIT 1", (branch_name,))

    def batch_search(self, terms, kind=BATCH_BY_BRANCH):
        """[(término, [filas])] buscando por nombre de rama o por fichero modificado."""
        column = "branch_name" if kind == BATCH_BY_BRANCH else "modified_files"
        query = (f"SELECT {', '.join(BATCH_COLUMNS)} FROM branches "
                 f"WHERE {column} LIKE ? ORDER BY commit_date DESC")
        conn = self._connect()
        try:
            return [(term, conn.execute(query, (f"%{term}%",)).fetchall()) for term in terms]
        finally:
            conn.close()
