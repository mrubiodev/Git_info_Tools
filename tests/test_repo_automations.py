import datetime
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from git_info.cli import main
from git_info.core.gitcmd import Cancelled, GitError
from git_info.core.repo_automations import (RepositoryAutomationStore, due_automations,
                                           in_selected_folder, inspect_repository,
                                           normalized_path, repository_lock,
                                           run_repository_automation)
from git_info.core.saved_searches import SavedSearchStore
from git_info.gui.automations_tab import format_repository_details, visible_automations


class RepositoryAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.remote = os.path.join(self.temp.name, "remote.git")
        self.source = os.path.join(self.temp.name, "publisher")
        self.repo = os.path.join(self.temp.name, "clone")
        self.git(self.temp.name, "init", "--bare", self.remote)
        self.git(self.temp.name, "init", "-b", "main", self.source)
        self.configure(self.source)
        self.write(self.source, "file.txt", "initial\n")
        self.write(self.source, ".gitignore", "ignored.txt\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "Initial")
        self.git(self.source, "remote", "add", "origin", self.remote)
        self.git(self.source, "push", "-u", "origin", "main")
        self.git(self.temp.name, "clone", "-b", "main", self.remote, self.repo)
        self.configure(self.repo)
        self.db = os.path.join(self.temp.name, "automations.db")
        self.store = RepositoryAutomationStore(self.db)
        self.store.init()
        self.automation = self.store.save({
            "name": "Clone", "repo_path": self.repo, "branch": "main",
            "remote": "origin", "remote_branch": "main",
        })

    def git(self, repo, *args):
        result = subprocess.run(["git", "-C", repo, *args], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode("utf-8", "replace").strip()

    def configure(self, repo):
        self.git(repo, "config", "user.name", "Test")
        self.git(repo, "config", "user.email", "test@example.com")
        self.git(repo, "config", "commit.gpgsign", "false")

    def write(self, repo, path, text):
        with open(os.path.join(repo, path), "w", encoding="utf-8") as file:
            file.write(text)

    def publish(self, path="file.txt", text="remote update\n", branch="main"):
        self.write(self.source, path, text)
        self.git(self.source, "add", "--", path)
        self.git(self.source, "commit", "-m", "Update")
        self.git(self.source, "push", "origin", branch)
        return self.git(self.source, "rev-parse", "HEAD")

    def run_automation(self):
        return run_repository_automation(self.store, self.store.get(self.automation["id"]))

    def test_fast_forward_downloads_changes_and_records_result(self):
        self.git(self.repo, "config", "branch.main.mergeOptions", "--squash --autostash")
        old = self.git(self.repo, "rev-parse", "HEAD")
        target = self.publish()
        result = self.run_automation()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["before"], old)
        self.assertEqual(result["after"], target)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "remote update\n")
        record = self.store.get("Clone")
        self.assertTrue(record["last_run"])
        self.assertIn(target, format_repository_details(record))
        self.assertEqual(self.run_automation()["status"], "unchanged")

    def test_deleted_remote_file_is_removed_by_fast_forward(self):
        self.git(self.source, "rm", "file.txt")
        self.git(self.source, "commit", "-m", "Remove")
        self.git(self.source, "push", "origin", "main")
        self.assertEqual(self.run_automation()["status"], "updated")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "file.txt")))

    def test_local_changes_and_untracked_files_block_without_fetch(self):
        self.publish()
        before = self.git(self.repo, "rev-parse", "HEAD")
        for path, staged in (("file.txt", False), ("file.txt", True), ("new.txt", False)):
            with self.subTest(path=path, staged=staged):
                self.write(self.repo, path, "local work\n")
                if staged:
                    self.git(self.repo, "add", path)
                result = self.run_automation()
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
                self.assertEqual(self.git(self.repo, "rev-parse", "origin/main"), before)
                with open(os.path.join(self.repo, path), encoding="utf-8") as file:
                    self.assertEqual(file.read(), "local work\n")
                if path == "file.txt":
                    self.git(self.repo, "restore", "--staged", "--worktree", path)
                else:
                    os.remove(os.path.join(self.repo, path))

    def test_local_commits_and_divergence_block(self):
        self.write(self.repo, "local.txt", "local commit\n")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-m", "Local")
        local_head = self.git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(self.run_automation()["status"], "blocked")
        self.publish()
        result = self.run_automation()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual((result["ahead"], result["behind"]), (1, 1))
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), local_head)
        self.assertEqual(self.git(self.repo, "stash", "list"), "")

    def test_different_branch_and_detached_head_block(self):
        self.publish()
        self.git(self.repo, "checkout", "-b", "other")
        self.assertEqual(self.run_automation()["status"], "blocked")
        self.assertEqual(self.git(self.repo, "branch", "--show-current"), "other")
        self.git(self.repo, "checkout", "--detach")
        result = self.run_automation()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("HEAD separado", result["text"])

    def test_in_progress_git_operation_blocks_even_when_clean(self):
        state = os.path.join(self.repo, ".git", "rebase-merge")
        os.mkdir(state)
        result = self.run_automation()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("rebase-merge", result["text"])

    def test_ignored_files_cannot_be_overwritten(self):
        self.write(self.repo, "ignored.txt", "private\n")
        self.write(self.source, "ignored.txt", "remote\n")
        self.git(self.source, "add", "-f", "ignored.txt")
        self.git(self.source, "commit", "-m", "Track ignored file")
        self.git(self.source, "push", "origin", "main")
        before = self.git(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(GitError):
            self.run_automation()
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        with open(os.path.join(self.repo, "ignored.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "private\n")
        self.assertEqual(self.store.get("Clone")["last_details"]["status"], "error")

    def test_fetch_failure_does_not_merge_cached_updates(self):
        self.publish()
        self.git(self.repo, "fetch", "origin")
        before = self.git(self.repo, "rev-parse", "HEAD")
        self.git(self.repo, "remote", "set-url", "origin", os.path.join(self.temp.name, "missing.git"))
        with self.assertRaises(GitError):
            self.run_automation()
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        record = self.store.get("Clone")
        self.assertIn("Error", record["last_result"])
        self.assertIn("error", record["last_details"])

    def test_remote_branch_removed_is_reported(self):
        self.git(self.source, "push", "origin", "--delete", "main")
        with self.assertRaises(GitError):
            self.run_automation()
        self.assertEqual(self.store.get("Clone")["last_details"]["status"], "error")

    def test_configurable_local_and_remote_branch_and_remote_name(self):
        self.git(self.source, "checkout", "-b", "release")
        target = self.publish(branch="release")
        self.git(self.repo, "remote", "rename", "origin", "upstream")
        self.git(self.repo, "checkout", "-b", "deployment")
        self.automation = self.store.save(dict(self.automation, branch="deployment",
                                               remote="upstream", remote_branch="release"),
                                           self.automation["id"])
        self.assertEqual(self.run_automation()["after"], target)
        self.assertEqual(self.git(self.repo, "branch", "--show-current"), "deployment")

    def test_local_changes_during_fetch_are_rechecked(self):
        self.publish()
        self.git(self.repo, "config", "merge.autostash", "true")
        from git_info.core import repo_automations
        original = repo_automations.run_git

        def intercepted(repo, *args, **kwargs):
            result = original(repo, *args, **kwargs)
            if args[0] == "fetch":
                self.write(self.repo, "file.txt", "written during fetch\n")
            return result

        before = self.git(self.repo, "rev-parse", "HEAD")
        with patch.object(repo_automations, "run_git", side_effect=intercepted):
            self.assertEqual(self.run_automation()["status"], "blocked")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(self.git(self.repo, "stash", "list"), "")

    def test_repository_lock_prevents_overlapping_runs(self):
        linked = os.path.join(self.temp.name, "linked")
        self.git(self.repo, "worktree", "add", "-b", "linked", linked)
        with repository_lock(self.repo):
            with self.assertRaises(GitError):
                self.run_automation()
            with self.assertRaises(GitError), repository_lock(linked):
                self.fail("El worktree debería compartir el bloqueo.")
            child = subprocess.run(
                [sys.executable, "-c",
                 "import sys; from git_info.core.repo_automations import repository_lock; "
                 "lock = repository_lock(sys.argv[1]); lock.__enter__()", self.repo],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(child.returncode, 0)
            self.assertIn("GitError", child.stderr.decode("utf-8", "replace"))
        with self.assertRaises(Cancelled):
            run_repository_automation(self.store, self.automation, cancel=lambda: True)
        self.assertEqual(self.store.get("Clone")["last_details"]["status"], "error")
        self.assertEqual(self.run_automation()["status"], "unchanged")

    def test_schedule_persistence_edit_pause_and_delete(self):
        self.assertEqual(len(due_automations(self.store)), 1)
        self.store.update(self.automation["id"], last_run="2026-10-04 10:00:00")
        self.assertEqual(due_automations(self.store, datetime.datetime(2026, 10, 4, 10, 14, 59)), [])
        self.assertEqual(len(due_automations(self.store, datetime.datetime(2026, 10, 4, 10, 15))), 1)
        self.store.update(self.automation["id"], auto_sync=False)
        self.assertEqual(due_automations(self.store), [])
        reopened = RepositoryAutomationStore(self.db)
        reopened.init()
        self.assertFalse(reopened.get("Clone")["auto_sync"])
        edited = reopened.save(dict(self.automation, name="Renamed", interval_minutes=3),
                               self.automation["id"])
        self.assertEqual(edited["interval_minutes"], 3)
        self.assertIsNone(edited["last_run"])
        reopened.delete(edited["id"])
        self.assertEqual(reopened.list(), [])

    def test_store_rejects_duplicates_empty_path_and_invalid_config(self):
        for changes in ({}, {"name": "Other"}, {"name": ""},
                        {"interval_minutes": 0}, {"branch": "absent"},
                        {"remote": "absent"}, {"remote_branch": "../invalid"},
                        {"repo_path": ""}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, GitError)):
                self.store.save(dict(self.automation, **changes))
        with self.assertRaises((ValueError, GitError)):
            inspect_repository(self.remote)

    def test_inspection_uses_upstream_and_canonical_root(self):
        info = inspect_repository(os.path.join(self.repo, ".git", ".."))
        self.assertEqual(info["repo_path"], normalized_path(self.repo))
        self.assertEqual(info["upstream"]["main"], ("origin", "main"))
        self.assertEqual(info["current"], "main")

    def test_scoped_view_includes_both_types_and_other_folders_only_in_all(self):
        searches = SavedSearchStore(self.db)
        searches.init()
        search = searches.save({"name": "Files", "repo_path": self.source, "scope": "local",
                                "dest_dir": os.path.join(self.temp.name, "export"), "layout": "tree"})
        self.assertEqual([(kind, item["id"]) for kind, item in
                          visible_automations(self.store, searches, self.repo)],
                         [("repo", self.automation["id"])])
        self.assertEqual(len(visible_automations(self.store, searches, self.temp.name)), 2)
        self.assertEqual(len(visible_automations(self.store, searches, self.repo, show_all=True)), 2)
        self.assertEqual(visible_automations(self.store, searches, ""), [])
        self.assertEqual(searches.get(search["id"])["name"], "Files")
        self.assertFalse(in_selected_folder(self.repo + "_other", self.repo))

    def test_cli_updates_only_enabled_repositories_and_reports_missing_or_blocked(self):
        target = self.publish()
        self.store.update(self.automation["id"], auto_sync=False)
        with patch("builtins.print"):
            self.assertEqual(main(["--db", self.db, "--update-repos"]), 0)
            self.assertNotEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
            self.assertEqual(main(["--db", self.db, "--update-repo", "Clone"]), 0)
            self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
            self.assertEqual(main(["--db", self.db, "--update-repo", "absent"]), 2)
            self.write(self.repo, "untracked.txt", "local\n")
            self.assertEqual(main(["--db", self.db, "--update-repo", "Clone", "--force"]), 1)

    def test_cli_lists_both_types_and_keeps_existing_sync_behavior(self):
        searches = SavedSearchStore(self.db)
        searches.init()
        search = searches.save({"name": "Files", "repo_path": self.repo, "scope": "local",
                                "dest_dir": os.path.join(self.temp.name, "export"),
                                "layout": "tree", "fetch_before": False})
        with patch("builtins.print") as output:
            self.assertEqual(main(["--db", self.db, "--list-automations"]), 0)
            printed = "\n".join(str(call.args[0]) for call in output.call_args_list)
            self.assertIn("[repo:", printed)
            self.assertIn("Files", printed)
            self.assertEqual(main(["--db", self.db, "--sync", "Files"]), 0)
        self.assertTrue(searches.get(search["id"])["last_run"])
        self.assertIsNone(self.store.get("Clone")["last_run"])


if __name__ == "__main__":
    unittest.main()
