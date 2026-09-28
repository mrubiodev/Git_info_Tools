"""Persistente simple para cachear metadatos de repositorios entre ejecuciones.

Guarda la lista de ramas (ref/name/sha) y los "tip files" (ls-tree de un SHA)
para evitar ejecutar git ls-tree y operaciones caras repetidamente.
"""
import json
import datetime
import sqlite3
import os


class RepoCache:
    def __init__(self, db_path):
        self.db_path = os.path.expanduser(db_path)
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        self._ensure_tables()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_tables(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS repo_cache (
                    repo_path TEXT PRIMARY KEY,
                    refs_signature TEXT,
                    branches_json TEXT,
                    updated_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS repo_tip_files (
                    repo_path TEXT,
                    commit_sha TEXT,
                    files_json TEXT,
                    updated_at TEXT,
                    PRIMARY KEY(repo_path, commit_sha)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def get_branches(self, repo_path):
        conn = self._connect()
        try:
            row = conn.execute("SELECT branches_json FROM repo_cache WHERE repo_path = ?",
                               (repo_path,)).fetchone()
            if not row or not row[0]:
                return None
            return json.loads(row[0])
        finally:
            conn.close()

    def get_refs_signature(self, repo_path):
        conn = self._connect()
        try:
            row = conn.execute("SELECT refs_signature FROM repo_cache WHERE repo_path = ?",
                               (repo_path,)).fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()

    def set_branches(self, repo_path, refs_signature, branches):
        conn = self._connect()
        try:
            now = datetime.datetime.now().isoformat()
            conn.execute("REPLACE INTO repo_cache (repo_path, refs_signature, branches_json, updated_at) VALUES (?, ?, ?, ?)",
                         (repo_path, refs_signature, json.dumps(branches, ensure_ascii=False), now))
            conn.commit()
        finally:
            conn.close()

    def get_tip_files(self, repo_path, commit_sha):
        conn = self._connect()
        try:
            row = conn.execute("SELECT files_json FROM repo_tip_files WHERE repo_path = ? AND commit_sha = ?",
                               (repo_path, commit_sha)).fetchone()
            if not row or not row[0]:
                return None
            return json.loads(row[0])
        finally:
            conn.close()

    def set_tip_files(self, repo_path, commit_sha, files_map):
        conn = self._connect()
        try:
            now = datetime.datetime.now().isoformat()
            conn.execute("REPLACE INTO repo_tip_files (repo_path, commit_sha, files_json, updated_at) VALUES (?, ?, ?, ?)",
                         (repo_path, commit_sha, json.dumps(files_map, ensure_ascii=False), now))
            conn.commit()
        finally:
            conn.close()
