import os
import sqlite3
import subprocess
import tempfile
import unittest

from git_info.core.saved_searches import SavedSearchStore
from git_info.core.sync import run_saved_search
from git_info.gui.saved_searches_panel import format_search_details


class SavedSearchDetailsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = os.path.join(self.temp.name, "repo")
        self.dest = os.path.join(self.temp.name, "download")
        os.mkdir(self.repo)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        os.mkdir(os.path.join(self.repo, "src"))
        with open(os.path.join(self.repo, "src", "file.txt"), "w", encoding="utf-8") as file:
            file.write("content")
        self.git("add", "src/file.txt")
        self.git("commit", "-m", "Add file")
        self.store = SavedSearchStore(os.path.join(self.temp.name, "searches.db"))
        self.store.init()
        self.search = self.store.save({
            "name": "Archivos", "repo_path": self.repo, "scope": "local",
            "dest_dir": self.dest, "layout": "branch", "fetch_before": False,
        })

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, *args], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_manual_run_records_download_source_and_no_change_run(self):
        result = run_saved_search(self.store, self.search, force=True)
        record = self.store.get(self.search["id"])
        self.assertEqual(len(result["written"]), 1)
        self.assertEqual(record["last_details"]["downloaded"][0]["target"], "main/src/file.txt")
        self.assertEqual(record["last_details"]["downloaded"][0]["branch"], "main")
        self.assertTrue(record["last_details"]["downloaded"][0]["commit"])
        self.assertIn("src/file.txt", format_search_details(record))
        self.assertIn("main", format_search_details(record))

        unchanged = run_saved_search(self.store, record)
        self.assertFalse(unchanged["changed"])
        self.assertEqual(self.store.get(record["id"])["last_details"]["note"],
                         "No hubo descargas en esta ejecución.")

    def test_file_conflict_and_errors_are_visible_in_details(self):
        self.store.update(self.search["id"], last_run="2026-10-01 12:00:00",
                          last_result="1 error", last_details={
                              "downloaded": [], "unchanged": [],
                              "conflicts": ["main/src/file.txt"], "missing": ["old.txt"],
                              "errors": ["src/broken.txt: acceso denegado"],
                              "warnings": ["fetch falló"],
                          })
        text = format_search_details(self.store.get(self.search["id"]))
        for message in ("main/src/file.txt", "old.txt",
                        "src/broken.txt: acceso denegado", "fetch falló"):
            self.assertIn(message, text)

    def test_failure_records_detail(self):
        self.store.update(self.search["id"], last_details={"downloaded": [{"target": "old"}]})
        self.search["repo_path"] = os.path.join(self.temp.name, "does-not-exist")
        with self.assertRaises(Exception):
            run_saved_search(self.store, self.search, force=True)
        record = self.store.get(self.search["id"])
        self.assertIn("error", record["last_details"])
        self.assertNotIn("downloaded", record["last_details"])
        self.assertIn("Error de ejecución", format_search_details(record))

    def test_existing_database_is_migrated(self):
        legacy = os.path.join(self.temp.name, "legacy.db")
        conn = sqlite3.connect(legacy)
        try:
            conn.execute("CREATE TABLE saved_searches (id INTEGER PRIMARY KEY, name TEXT)")
            conn.commit()
        finally:
            conn.close()
        migrated = SavedSearchStore(legacy)
        migrated.init()
        conn = sqlite3.connect(legacy)
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(saved_searches)")]
        finally:
            conn.close()
        self.assertIn("last_details", columns)


if __name__ == "__main__":
    unittest.main()
