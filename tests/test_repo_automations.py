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

    def test_sync_preserves_staged_unstaged_and_untracked_work(self):
        self.store.update(self.automation["id"], local_changes="sync")
        self.write(self.repo, "file.txt", "staged\n")
        self.git(self.repo, "add", "file.txt")
        self.write(self.repo, "file.txt", "unstaged\n")
        self.write(self.repo, "private.txt", "untracked\n")
        index = self.git(self.repo, "show", ":file.txt")
        target = self.publish("remote.txt", "new remote file\n")
        self.assertEqual(self.run_automation()["status"], "updated")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
        self.assertEqual(self.git(self.repo, "show", ":file.txt"), index)
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "unstaged\n")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "private.txt")))
        self.assertEqual(self.git(self.repo, "stash", "list"), "")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), self.git(self.source, "rev-parse", "HEAD"))

    def test_sync_blocks_overlapping_edits_and_untracked_collisions(self):
        self.store.update(self.automation["id"], local_changes="sync")
        self.write(self.repo, "file.txt", "local work\n")
        before = self.git(self.repo, "rev-parse", "HEAD")
        self.publish()
        self.assertEqual(self.run_automation()["status"], "blocked")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "local work\n")
        self.git(self.repo, "restore", "file.txt")
        self.write(self.repo, "new.txt", "private\n")
        self.publish("new.txt", "published\n")
        self.assertEqual(self.run_automation()["status"], "blocked")
        with open(os.path.join(self.repo, "new.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "private\n")

    def test_stash_can_keep_work_for_manual_recovery(self):
        self.store.update(self.automation["id"], local_changes="stash")
        self.write(self.repo, "file.txt", "local work\n")
        self.git(self.repo, "add", "file.txt")
        self.write(self.repo, "private.txt", "untracked\n")
        target = self.publish()
        result = self.run_automation()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
        self.assertEqual(self.git(self.repo, "status", "--porcelain"), "")
        self.assertIn(result["stash"], self.git(self.repo, "stash", "list", "--format=%H"))
        self.assertEqual(self.git(self.repo, "show", f"{result['stash']}:file.txt"), "local work")
        self.assertEqual(self.git(self.repo, "show", f"{result['stash']}^3:private.txt"), "untracked")
        self.assertEqual(self.run_automation()["status"], "unchanged")
        self.assertEqual(len(self.git(self.repo, "stash", "list").splitlines()), 1)

    def test_stash_reapplies_index_and_preserves_older_stashes(self):
        self.write(self.repo, "old.txt", "older stash\n")
        self.git(self.repo, "stash", "push", "-u", "-m", "existing")
        previous = self.git(self.repo, "rev-parse", "refs/stash")
        self.store.update(self.automation["id"], local_changes="stash", restore_stash=True)
        self.write(self.repo, "file.txt", "staged\n")
        self.git(self.repo, "add", "file.txt")
        self.write(self.repo, "file.txt", "unstaged\n")
        self.write(self.repo, "private.txt", "untracked\n")
        target = self.publish("new.txt", "remote\n")
        result = self.run_automation()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
        self.assertEqual(self.git(self.repo, "show", ":file.txt"), "staged")
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "unstaged\n")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "private.txt")))
        self.assertEqual(self.git(self.repo, "stash", "list", "--format=%H"), previous)

    def test_stash_restore_conflicts_are_visible_and_keep_backup(self):
        self.store.update(self.automation["id"], local_changes="stash", restore_stash=True)
        self.write(self.repo, "file.txt", "local\n")
        target = self.publish()
        result = self.run_automation()
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), target)
        self.assertIn(result["stash"], self.git(self.repo, "stash", "list", "--format=%H"))
        self.assertEqual(self.store.get("Clone")["last_details"]["status"], "conflict")
        self.assertEqual(self.run_automation()["status"], "blocked")

    def test_stash_restores_work_if_fast_forward_fails(self):
        self.store.update(self.automation["id"], local_changes="stash")
        self.write(self.repo, "file.txt", "local\n")
        self.write(self.repo, "private.txt", "untracked\n")
        self.write(self.repo, "ignored.txt", "ignored private\n")
        self.write(self.source, "ignored.txt", "remote\n")
        self.git(self.source, "add", "-f", "ignored.txt")
        self.git(self.source, "commit", "-m", "Track ignored")
        self.git(self.source, "push", "origin", "main")
        before = self.git(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(GitError):
            self.run_automation()
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "local\n")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "private.txt")))
        self.assertEqual(self.git(self.repo, "stash", "list"), "")

    def test_stash_cancellation_after_saving_restores_local_work(self):
        self.store.update(self.automation["id"], local_changes="stash")
        self.write(self.repo, "file.txt", "local\n")
        self.publish()
        from git_info.core import repo_automations
        original = repo_automations.run_git
        cancelled = False

        def intercepted(repo, *args, **kwargs):
            nonlocal cancelled
            result = original(repo, *args, **kwargs)
            if args[:2] == ("stash", "push"):
                cancelled = True
            return result

        with patch.object(repo_automations, "run_git", side_effect=intercepted), self.assertRaises(Cancelled):
            run_repository_automation(self.store, self.store.get("Clone"), cancel=lambda: cancelled)
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "local\n")
        self.assertEqual(self.git(self.repo, "stash", "list"), "")

    def test_failed_stash_push_restores_backup_if_it_was_created(self):
        self.store.update(self.automation["id"], local_changes="stash")
        self.write(self.repo, "file.txt", "local\n")
        self.publish("new.txt", "remote\n")
        from git_info.core import repo_automations
        original = repo_automations.run_git

        def intercepted(repo, *args, **kwargs):
            result = original(repo, *args, **kwargs)
            if args[:2] == ("stash", "push"):
                raise GitError("Stash cleanup failed")
            return result

        before = self.git(self.repo, "rev-parse", "HEAD")
        with patch.object(repo_automations, "run_git", side_effect=intercepted), self.assertRaises(GitError):
            self.run_automation()
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "local\n")
        self.assertEqual(self.git(self.repo, "stash", "list"), "")

    def test_policy_persistence_and_old_database_migration(self):
        self.store.update(self.automation["id"], local_changes="stash", restore_stash=True)
        reopened = RepositoryAutomationStore(self.db)
        reopened.init()
        self.assertEqual(reopened.get("Clone")["local_changes"], "stash")
        self.assertTrue(reopened.get("Clone")["restore_stash"])
        with self.assertRaises(ValueError):
            reopened.update(self.automation["id"], local_changes="reset")
        old = RepositoryAutomationStore(os.path.join(self.temp.name, "old.db"))
        old._execute("""
            CREATE TABLE repository_automations (
                id INTEGER PRIMARY KEY, name TEXT, repo_path TEXT, branch TEXT, remote TEXT,
                remote_branch TEXT, auto_sync INTEGER, interval_minutes INTEGER, created_at TEXT,
                last_run TEXT, last_result TEXT, last_details TEXT)
        """)
        old._execute("""
            INSERT INTO repository_automations VALUES
            (1, 'Old', ?, 'main', 'origin', 'main', 1, 15, '2026-10-04', NULL, NULL, NULL)
        """, (self.repo,))
        old.init()
        self.assertEqual(old.get(1)["local_changes"], "block")
        self.assertFalse(old.get(1)["restore_stash"])
        self.assertEqual(old.get(1)["fetch_failure"], "stop")

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
        self.assertTrue(record["last_result"].startswith("REMOTO NO ACTUALIZADO"))

    def make_remote_unavailable(self):
        self.git(self.repo, "remote", "set-url", "origin", os.path.join(self.temp.name, "missing.git"))

    def test_local_fetch_fallback_fast_forwards_only_existing_ref_and_warns(self):
        target = self.publish()
        self.git(self.repo, "fetch", "origin")
        self.store.update(self.automation["id"], fetch_failure="local")
        self.make_remote_unavailable()
        result = self.run_automation()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["after"], target)
        self.assertFalse(result["remote_updated"])
        self.assertTrue(result["text"].startswith("REMOTO NO ACTUALIZADO"))
        self.assertTrue(result["warnings"])
        self.assertIn("AVISO", format_repository_details(self.store.get("Clone")))
        unchanged = self.run_automation()
        self.assertEqual(unchanged["status"], "unchanged")
        self.assertNotIn("Al día", unchanged["text"])
        self.assertTrue(unchanged["text"].startswith("REMOTO NO ACTUALIZADO"))
        with patch("builtins.print"):
            self.assertEqual(main(["--db", self.db, "--update-repo", "Clone"]), 1)

    def test_local_fetch_fallback_requires_configured_ref(self):
        before = self.git(self.repo, "rev-parse", "HEAD")
        self.store.update(self.automation["id"], fetch_failure="local")
        self.git(self.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.make_remote_unavailable()
        with self.assertRaisesRegex(GitError, "No existe la referencia local configurada"):
            self.run_automation()
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        self.assertTrue(self.store.get("Clone")["last_details"]["warnings"])

    def test_fallback_keeps_safety_checks_and_warning_on_later_error(self):
        self.store.update(self.automation["id"], fetch_failure="local", local_changes="sync")
        target = self.publish()
        self.git(self.repo, "fetch", "origin")
        self.write(self.repo, "file.txt", "local work\n")
        self.make_remote_unavailable()
        before = self.git(self.repo, "rev-parse", "HEAD")
        blocked = self.run_automation()
        self.assertEqual(blocked["status"], "blocked")
        self.assertTrue(blocked["text"].startswith("REMOTO NO ACTUALIZADO"))
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        self.assertNotEqual(before, target)
        self.git(self.repo, "restore", "file.txt")
        from git_info.core import repo_automations
        original = repo_automations.run_git

        def intercepted(repo, *args, **kwargs):
            if "merge" in args:
                raise GitError("merge failed")
            return original(repo, *args, **kwargs)

        with patch.object(repo_automations, "run_git", side_effect=intercepted):
            with self.assertRaisesRegex(GitError, "merge failed"):
                self.run_automation()
        record = self.store.get("Clone")
        self.assertTrue(record["last_result"].startswith("REMOTO NO ACTUALIZADO"))
        self.assertTrue(record["last_details"]["warnings"])
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)

    def test_fetch_policy_save_update_validation_and_cli_override(self):
        for value in ("ignore", None, [], True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.save(dict(self.automation, fetch_failure=value), self.automation["id"])
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.update(self.automation["id"], fetch_failure=value)
        saved = self.store.save(dict(self.automation, fetch_failure="local"), self.automation["id"])
        self.assertEqual(saved["fetch_failure"], "local")
        self.publish()
        self.git(self.repo, "fetch", "origin")
        before = self.git(self.repo, "rev-parse", "HEAD")
        self.make_remote_unavailable()
        with patch("builtins.print"):
            self.assertEqual(main(["--db", self.db, "--update-repo", "Clone",
                                   "--fetch-failure", "stop"]), 1)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(self.store.get("Clone")["fetch_failure"], "local")

    def test_fallback_uses_pre_fetch_ref_even_after_partial_fetch_timeout(self):
        cached = self.publish()
        self.git(self.repo, "fetch", "origin")
        newer = self.publish("next.txt", "not cached before fetch\n")
        self.store.update(self.automation["id"], fetch_failure="local")
        from git_info.core import repo_automations
        original = repo_automations.run_git

        def intercepted(repo, *args, **kwargs):
            result = original(repo, *args, **kwargs)
            if args[0] == "fetch":
                raise subprocess.TimeoutExpired("git fetch", 600)
            return result

        with patch.object(repo_automations, "run_git", side_effect=intercepted):
            result = self.run_automation()
        self.assertEqual(result["after"], cached)
        self.assertEqual(self.git(self.repo, "rev-parse", "origin/main"), newer)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "next.txt")))
        self.assertTrue(result["warnings"])

    def test_fallback_preserves_stash_mode_and_divergence_blocking(self):
        self.store.update(self.automation["id"], fetch_failure="local",
                          local_changes="stash", restore_stash=True)
        self.write(self.repo, "file.txt", "local work\n")
        cached = self.publish("new.txt", "remote\n")
        self.git(self.repo, "fetch", "origin")
        self.make_remote_unavailable()
        result = self.run_automation()
        self.assertEqual(result["after"], cached)
        self.assertTrue(result["warnings"])
        with open(os.path.join(self.repo, "file.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "local work\n")
        self.assertEqual(self.git(self.repo, "stash", "list"), "")
        self.git(self.repo, "add", "file.txt")
        self.git(self.repo, "commit", "-m", "Local")
        local_head = self.git(self.repo, "rev-parse", "HEAD")
        result = self.run_automation()
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["warnings"])
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), local_head)

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
