import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from git_info.cli import build_parser
from git_info.gui.lite_app import LiteAutomationsApp


class LiteAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tkinter no dispone de pantalla: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = LiteAutomationsApp(self.root, os.path.join(self.temp.name, "lite.db"))
        self.repo = os.path.join(self.temp.name, "repo")
        self.app.automation_store._execute("""
            INSERT INTO repository_automations
            (name, repo_path, branch, remote, remote_branch, created_at)
            VALUES ('Repo', ?, 'main', 'origin', 'main', '2026-10-08 10:00:00')
        """, (self.repo,))
        self.app.saved_store.save({"name": "Search", "repo_path": self.repo, "scope": "local",
                                   "dest_dir": os.path.join(self.temp.name, "dest"), "layout": "tree"})

    def test_only_automations_and_console_tabs(self):
        tabs = [self.app.notebook.tab(tab, "text") for tab in self.app.notebook.tabs()]
        self.assertEqual(tabs, ["Automatizaciones", "Consola"])
        self.assertEqual(self.app.automations_tab.scope.get(), "Todas")

    def test_lists_repository_and_saved_search_automations(self):
        self.app.automations_tab.refresh()
        kinds = sorted(kind for kind, _ in self.app.automations_tab.records.values())
        self.assertEqual(kinds, ["repo", "search"])

    def test_editing_saved_search_explains_full_version(self):
        self.app.automations_tab.refresh()
        iid = next(iid for iid, (kind, _) in self.app.automations_tab.records.items() if kind == "search")
        self.app.automations_tab.table.tree.selection_set(iid)
        with patch("git_info.gui.lite_app.messagebox.showinfo") as info:
            self.app.automations_tab.edit()
        info.assert_called_once()

    def test_saved_search_scheduler_runs_without_latest_tab(self):
        panel = self.app.latest_tab.saved_panel
        with patch.object(panel, "run") as run, \
                patch("git_info.gui.saved_searches_panel.due_searches", return_value=["s"]):
            panel._tick()
        run.assert_called_once_with("s")

    def test_cli_lite_flag(self):
        self.assertTrue(build_parser().parse_args(["--lite"]).lite)


if __name__ == "__main__":
    unittest.main()
