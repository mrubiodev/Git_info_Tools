import json
import os
import tempfile
import unittest
from unittest.mock import patch

from git_info.core.automation_transfer import (FORMAT, export_automations, import_automations,
                                                read_automations, validate_record)
from git_info.core.repo_automations import RepositoryAutomationStore
from git_info.core.saved_searches import SavedSearchStore


class AutomationTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "tasks.db")
        self.repo_store = RepositoryAutomationStore(self.db)
        self.search_store = SavedSearchStore(self.db)
        self.repo_store.init()
        self.search_store.init()
        self.path = os.path.join(self.temp.name, "tasks.json")
        self.repo = {"name": "Repo", "repo_path": self.temp.name, "branch": "main",
                     "remote": "origin", "remote_branch": "main", "auto_sync": True,
                     "interval_minutes": 10, "local_changes": "stash", "restore_stash": True}
        self.search = {"name": "Search", "repo_path": self.temp.name, "scope": "all",
                       "dest_dir": os.path.join(self.temp.name, "downloads"), "layout": "repo",
                       "auto_sync": True, "selected_paths": ["src/file.py"], "path_regex": r"\.py$"}
        self.metadata = {"repo_path": self.temp.name, "branches": ["main"], "remotes": ["origin"]}

    def import_records(self, records):
        with patch("git_info.core.repo_automations.inspect_repository", return_value=self.metadata), \
                patch("git_info.core.repo_automations.git_text", return_value=""), \
                patch("git_info.core.automation_transfer.inspect_repository", return_value=self.metadata):
            return import_automations(self.repo_store, self.search_store, records)

    def test_roundtrip_exports_only_selected_configs_without_runtime_or_ids(self):
        export_automations(self.path, [("repo", dict(self.repo, id=42, last_result="private history")),
                                       ("search", dict(self.search, refs_signature="private"))])
        records = read_automations(self.path)
        self.assertEqual(records, [{"type": "repo", "config": self.repo},
                                   {"type": "search", "config": self.search}])
        imported = self.import_records(records)
        self.assertEqual(len(imported), 2)
        self.assertTrue(self.repo_store.get("Repo")["auto_sync"])
        self.assertTrue(self.repo_store.get("Repo")["restore_stash"])
        self.assertEqual(self.repo_store.get("Repo")["local_changes"], "stash")
        self.assertEqual(self.search_store.get("Search")["selected_paths"], ["src/file.py"])
        self.assertTrue(self.search_store.get("Search")["auto_sync"])
        self.assertIsNone(self.repo_store.get("Repo")["last_run"])
        self.assertIsNone(self.search_store.get("Search")["last_run"])

    def test_subset_export_and_subset_import(self):
        export_automations(self.path, [("search", self.search)])
        self.assertEqual(len(read_automations(self.path)), 1)
        self.import_records([{"type": "search", "config": self.search}])
        self.assertEqual(self.repo_store.list(), [])
        self.assertEqual(len(self.search_store.list()), 1)

    def test_duplicate_never_replaces_and_rolls_back_entire_import(self):
        original = self.search_store.save(self.search)
        with self.assertRaises(ValueError):
            self.import_records([{"type": "repo", "config": self.repo},
                                 {"type": "search", "config": dict(self.search, auto_sync=False)}])
        self.assertEqual(self.repo_store.list(), [])
        self.assertEqual(self.search_store.get("Search"), original)
        with self.assertRaises(ValueError):
            self.import_records([{"type": "repo", "config": self.repo},
                                 {"type": "repo", "config": dict(self.repo, name="Another")}])
        self.assertEqual(self.repo_store.list(), [])

    def test_invalid_records_are_rejected(self):
        for change in ({"local_changes": "reset"}, {"auto_sync": "yes"},
                       {"interval_minutes": 0}, {"interval_minutes": True},
                       {"repo_path": ""}, {"name": 5}, {"last_run": "private"},
                       {"local_changes": []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_record({"type": "repo", "config": dict(self.repo, **change)})
        for change in ({"scope": "invalid"}, {"layout": "tree"}, {"path_regex": "["},
                       {"selected_paths": [1]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_record({"type": "search", "config": dict(self.search, **change)})
        with self.assertRaises(ValueError):
            self.import_records([])

    def test_invalid_format_and_version_are_rejected(self):
        for data in ({}, [], {"format": FORMAT, "version": True, "automations": []},
                     {"format": FORMAT, "version": 2, "automations": []},
                     {"format": FORMAT, "version": 1, "automations": [{}]}):
            with self.subTest(data=data):
                with open(self.path, "w", encoding="utf-8") as file:
                    json.dump(data, file)
                with self.assertRaises(ValueError):
                    read_automations(self.path)

    def test_missing_local_repository_does_not_import_other_tasks(self):
        with patch("git_info.core.automation_transfer.inspect_repository", side_effect=ValueError("Missing")):
            with self.assertRaises(ValueError):
                import_automations(self.repo_store, self.search_store,
                                   [{"type": "search", "config": self.search}])
        self.assertEqual(self.search_store.list(), [])

    def test_fetch_policy_roundtrip_legacy_default_and_validation(self):
        export_automations(self.path, [("repo", dict(self.repo, fetch_failure="local")),
                                       ("search", dict(self.search, fetch_failure="local"))])
        records = read_automations(self.path)
        self.assertTrue(all(record["config"]["fetch_failure"] == "local" for record in records))
        self.import_records(records)
        self.assertEqual(self.repo_store.get("Repo")["fetch_failure"], "local")
        self.assertEqual(self.search_store.get("Search")["fetch_failure"], "local")
        legacy = dict(self.search, name="Legacy")
        self.import_records([{"type": "search", "config": legacy}])
        self.assertEqual(self.search_store.get("Legacy")["fetch_failure"], "stop")
        self.repo_store.delete(self.repo_store.get("Repo")["id"])
        self.import_records([{"type": "repo", "config": self.repo}])
        self.assertEqual(self.repo_store.get("Repo")["fetch_failure"], "stop")
        for kind, config in (("repo", self.repo), ("search", self.search)):
            for value in ("ignore", None, [], True):
                with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                    validate_record({"type": kind, "config": dict(config, fetch_failure=value)})


if __name__ == "__main__":
    unittest.main()
