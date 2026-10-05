import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from git_info.gui.app import GitBranchInfoApp
from git_info.gui.automations_tab import RepositoryAutomationDialog


class AutomationsGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tkinter no dispone de pantalla: {error}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = GitBranchInfoApp(self.root, os.path.join(self.temp.name, "gui.db"))
        self.tab = self.app.automations_tab
        self.repo = os.path.join(self.temp.name, "selected")
        self.other_repo = os.path.join(self.temp.name, "other")
        for name, path in (("Selected", self.repo), ("Other", self.other_repo)):
            self.app.automation_store._execute("""
                INSERT INTO repository_automations
                (name, repo_path, branch, remote, remote_branch, created_at)
                VALUES (?, ?, 'main', 'origin', 'main', '2026-10-04 10:00:00')
            """, (name, path))
        self.search = self.app.saved_store.save({
            "name": "Saved search", "repo_path": self.other_repo, "scope": "local",
            "dest_dir": os.path.join(self.temp.name, "destination"), "layout": "tree",
        })

    def test_view_updates_with_selected_folder_and_all_includes_saved_searches(self):
        self.assertEqual(len(self.tab.records), 0)
        self.app.set_repo_path(self.repo)
        self.assertEqual(len(self.tab.records), 1)
        self.assertEqual(next(iter(self.tab.records.values()))[1]["name"], "Selected")
        self.tab.scope.set("Todas")
        self.tab.refresh()
        self.assertEqual(len(self.tab.records), 3)
        self.app.set_repo_path(self.other_repo)
        self.assertEqual(len(self.tab.records), 3)
        self.tab.scope.set("Carpeta seleccionada")
        self.tab.refresh()
        self.assertEqual(len(self.tab.records), 2)

    def test_scheduler_runs_hidden_automatic_repositories(self):
        self.app.set_repo_path(self.repo)
        with patch.object(self.tab, "run") as run:
            self.tab.tick()
        self.assertEqual({call.args[0]["name"] for call in run.call_args_list}, {"Selected", "Other"})
        self.assertEqual(len(self.tab.records), 1)

    def test_saved_search_runs_through_existing_scheduler_and_actions_persist(self):
        self.tab.scope.set("Todas")
        self.tab.refresh()
        self.tab.table.tree.selection_set(f"search:{self.search['id']}")
        with patch.object(self.app.latest_tab.saved_panel, "run") as run:
            self.tab.run_selected()
            run.assert_called_once()
            self.assertTrue(run.call_args.kwargs["force"])
        self.tab.toggle()
        self.assertTrue(self.app.saved_store.get(self.search["id"])["auto_sync"])
        with patch("git_info.gui.automations_tab.simpledialog.askinteger", return_value=7):
            self.tab.change_interval()
        self.assertEqual(self.app.saved_store.get(self.search["id"])["interval_minutes"], 7)
        self.tab.table.tree.selection_set("repo:1")
        self.tab.running[1] = Mock()
        with patch("git_info.gui.automations_tab.messagebox.showinfo") as info:
            self.tab.delete()
            info.assert_called_once()
        self.tab.running.clear()
        with patch("git_info.gui.automations_tab.messagebox.askyesno", return_value=True):
            self.tab.delete()
        self.assertIsNone(self.app.automation_store.get(1))

    def test_configuration_dialog_proposes_upstream_and_saves_selected_branch(self):
        metadata = {"repo_path": self.repo, "branches": ["main", "feature"],
                    "current": "main", "remotes": ["origin", "upstream"],
                    "upstream": {"main": ("origin", "main"),
                                 "feature": ("upstream", "release")}}
        store = Mock()
        with patch("git_info.gui.automations_tab.inspect_repository", return_value=metadata), \
                patch.object(RepositoryAutomationDialog, "wait_visibility"), \
                patch.object(RepositoryAutomationDialog, "wait_window"):
            dialog = RepositoryAutomationDialog(self.root, store, self.repo)
        try:
            self.assertEqual((dialog.branch.get(), dialog.remote.get()), ("main", "origin"))
            dialog.branch.set("feature")
            dialog.apply_upstream()
            self.assertEqual((dialog.remote.get(), dialog.remote_branch.get()), ("upstream", "release"))
            self.assertTrue(dialog.validate())
            saved = store.save.call_args.args[0]
            self.assertEqual(saved["interval_minutes"], 15)
            self.assertEqual(saved["branch"], "feature")
            self.assertEqual(saved["remote_branch"], "release")
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
