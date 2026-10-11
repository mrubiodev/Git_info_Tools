import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import sys

from git_info.gui.app import GitBranchInfoApp
from git_info.gui.automations_tab import (AutomationImportDialog, ImportAdjustmentDialog,
                                          RepositoryAutomationDialog)
from git_info.core.saved_searches import FETCH_FAILURE_MODES
from git_info.gui.dialogs import SaveSearchDialog


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
        with patch.object(self.root, "iconbitmap", wraps=self.root.iconbitmap) as icon_call:
            self.app = GitBranchInfoApp(self.root, os.path.join(self.temp.name, "gui.db"))
        self.icon_call = icon_call
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

    @unittest.skipUnless(sys.platform == "win32", "El icono ICO usa Tkinter de Windows.")
    def test_application_icon_is_set_for_root_and_child_windows(self):
        import ctypes
        icon = str(Path(__file__).resolve().parents[1] / "res" / "app_icon.ico")
        self.icon_call.assert_called_once_with(default=icon)
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [ctypes.c_void_p]
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetClassLongPtrW.restype = ctypes.c_void_p
        def native_icons(window):
            window.update_idletasks()
            handle = user32.GetParent(window.winfo_id())
            return tuple(user32.GetClassLongPtrW(handle, index) for index in (-14, -34))
        self.root.deiconify()
        self.root.update()
        root_icons = native_icons(self.root)
        self.assertTrue(all(root_icons))
        child = tk.Toplevel(self.root)
        try:
            self.assertEqual(native_icons(child), root_icons)
        finally:
            child.destroy()

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
            self.assertEqual(saved["local_changes"], "sync")
            self.assertFalse(saved["restore_stash"])
            self.assertEqual(saved["fetch_failure"], "stop")
            dialog.fetch_failure.set(FETCH_FAILURE_MODES["local"])
            dialog.local_changes.set("Guardar cambios locales en stash y actualizar")
            dialog.update_policy()
            dialog.restore_stash.set(True)
            self.assertTrue(dialog.validate())
            self.assertEqual(store.save.call_args.args[0]["local_changes"], "stash")
            self.assertTrue(store.save.call_args.args[0]["restore_stash"])
            self.assertEqual(store.save.call_args.args[0]["fetch_failure"], "local")
        finally:
            dialog.destroy()

    def test_multi_selection_exports_both_types_and_single_actions_require_one(self):
        self.tab.scope.set("Todas")
        self.tab.refresh()
        self.tab.table.tree.selection_set(("repo:1", f"search:{self.search['id']}"))
        self.tab.refresh()
        self.assertEqual(len(self.tab.table.tree.selection()), 2)
        with patch("git_info.gui.automations_tab.filedialog.asksaveasfilename", return_value="tasks.json"), \
                patch("git_info.gui.automations_tab.export_automations") as export, \
                patch("git_info.gui.automations_tab.messagebox.showinfo"), \
                patch("git_info.gui.automations_tab.messagebox.showwarning") as warning:
            self.tab.export_selected()
            self.assertEqual([kind for kind, _ in export.call_args.args[1]], ["repo", "search"])
            self.assertIsNone(self.tab.selected())
            warning.assert_called_once()

    def test_import_preview_selects_only_requested_tasks_and_cancel_does_not_save(self):
        records = [{"type": "repo", "config": {"name": "Shared", "repo_path": self.repo,
                    "branch": "main", "remote": "origin", "remote_branch": "main", "auto_sync": True}},
                   {"type": "search", "config": dict(self.search)}]
        with patch.object(AutomationImportDialog, "wait_visibility"), \
                patch.object(AutomationImportDialog, "wait_window"), \
                patch("git_info.gui.automations_tab.import_automations") as importer:
            dialog = AutomationImportDialog(self.root, self.app.automation_store,
                                             self.app.saved_store, records)
            try:
                importer.assert_not_called()
                dialog.table.tree.selection_set("0")
                self.assertTrue(dialog.validate())
                self.assertEqual(importer.call_args.args[2], records[:1])
            finally:
                dialog.destroy()

    def test_import_adjustments_preserve_auto_and_allow_local_paths(self):
        record = {"type": "repo", "config": {"name": "Shared", "repo_path": self.repo,
                  "branch": "main", "remote": "origin", "remote_branch": "main",
                  "auto_sync": True, "interval_minutes": 10, "local_changes": "stash",
                  "restore_stash": True}}
        with patch.object(ImportAdjustmentDialog, "wait_visibility"), \
                patch.object(ImportAdjustmentDialog, "wait_window"):
            dialog = ImportAdjustmentDialog(self.root, record)
        try:
            dialog.variables["repo_path"].set(self.other_repo)
            self.assertTrue(dialog.validate())
            self.assertEqual(dialog.result["config"]["repo_path"], self.other_repo)
            self.assertTrue(dialog.result["config"]["auto_sync"])
            self.assertTrue(dialog.result["config"]["restore_stash"])
            self.assertEqual(record["config"]["repo_path"], self.repo)
            self.assertEqual(dialog.result["config"]["fetch_failure"], "stop")
            dialog.fetch_failure.set(FETCH_FAILURE_MODES["local"])
            self.assertTrue(dialog.validate())
            self.assertEqual(dialog.result["config"]["fetch_failure"], "local")
        finally:
            dialog.destroy()

    def test_fetch_policy_button_updates_each_type_and_details(self):
        self.tab.scope.set("Todas")
        self.tab.refresh()
        for iid, store, key in (("repo:1", self.app.automation_store, 1),
                                (f"search:{self.search['id']}", self.app.saved_store, self.search["id"])):
            self.tab.table.tree.selection_set(iid)
            with patch("git_info.gui.automations_tab.FetchFailureDialog") as dialog:
                dialog.return_value.result = "local"
                self.tab.change_fetch_failure()
            self.assertEqual(store.get(key)["fetch_failure"], "local")
        panel = self.app.latest_tab.saved_panel
        panel.refresh()
        panel.table.tree.selection_set(str(self.search["id"]))
        with patch("git_info.gui.saved_searches_panel.FetchFailureDialog") as dialog:
            dialog.return_value.result = "stop"
            panel.change_fetch_failure()
        self.assertEqual(self.app.saved_store.get(self.search["id"])["fetch_failure"], "stop")

    def test_save_search_dialog_preserves_explicit_fetch_policy(self):
        dialog = SaveSearchDialog(self.root, default_name="Policy", fetch_failure="local")
        try:
            self.assertEqual(dialog.fetch_failure.get(), FETCH_FAILURE_MODES["local"])
            dialog._accept()
            self.assertEqual(dialog.result["fetch_failure"], "local")
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_search_import_adjustment_exposes_fetch_policy(self):
        record = {"type": "search", "config": {
            "name": "Search", "repo_path": self.repo, "scope": "all",
            "dest_dir": self.other_repo, "layout": "repo", "fetch_failure": "local"}}
        with patch.object(ImportAdjustmentDialog, "wait_visibility"), \
                patch.object(ImportAdjustmentDialog, "wait_window"):
            dialog = ImportAdjustmentDialog(self.root, record)
        try:
            self.assertEqual(dialog.fetch_failure.get(), FETCH_FAILURE_MODES["local"])
            dialog.fetch_failure.set(FETCH_FAILURE_MODES["stop"])
            self.assertTrue(dialog.validate())
            self.assertEqual(dialog.result["config"]["fetch_failure"], "stop")
        finally:
            dialog.destroy()

    def test_import_file_errors_are_reported_without_opening_preview(self):
        with patch("git_info.gui.automations_tab.filedialog.askopenfilename", return_value="bad.json"), \
                patch("git_info.gui.automations_tab.read_automations", side_effect=ValueError("Invalid")), \
                patch("git_info.gui.automations_tab.AutomationImportDialog") as dialog, \
                patch("git_info.gui.automations_tab.messagebox.showerror") as error:
            self.tab.import_file()
            dialog.assert_not_called()
            error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
