import unittest
import os
import tempfile
from unittest.mock import patch

from git_info.core import latest_scan


class LatestScanTests(unittest.TestCase):
    @patch("git_info.core.latest_scan.run_git")
    def test_list_branches_reads_live_refs_and_marks_main(self, run_git):
        run_git.side_effect = [
            (
                b"refs/remotes/origin/feature\x00origin/feature\x00aaa\n"
                b"refs/remotes/origin/main\x00origin/main\x00bbb\n"
            ),
            b"refs/remotes/origin/main\n",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            branches = latest_scan.list_branches(
                "repo", latest_scan.SCOPE_REMOTE,
                db_path=os.path.join(temp_dir, "cache.sqlite"), use_cache=True)

        self.assertEqual([branch["name"] for branch in branches],
                         ["origin/feature", "origin/main"])
        self.assertFalse(branches[0]["is_default"])
        self.assertTrue(branches[1]["is_default"])

    def test_identical_inherited_version_is_attributed_to_default_branch(self):
        best = latest_scan._pick_latest([
            {
                "branch": "origin/feature", "timestamp": 10, "blob": "same",
                "commit": "abc", "is_default": False,
            },
            {
                "branch": "origin/main", "timestamp": 10, "blob": "same",
                "commit": "abc", "is_default": True,
            },
        ])

        self.assertEqual(best["branch"], "origin/main")
        self.assertEqual(best["same_in"], ["origin/feature"])

    def test_newer_local_commit_wins_over_remote_branch(self):
        best = latest_scan._pick_latest([
            {
                "branch": "feature", "timestamp": 20, "blob": "new",
                "commit": "local", "is_default": False,
            },
            {
                "branch": "origin/feature", "timestamp": 10, "blob": "old",
                "commit": "remote", "is_default": False,
            },
        ])

        self.assertEqual(best["branch"], "feature")
        self.assertEqual(best["commit"], "local")

    @patch("git_info.core.latest_scan.run_git")
    def test_file_history_groups_commits_by_branch(self, run_git):
        run_git.side_effect = [
            b"aaa\x0010\x00Mario\x00Feature change\nbbb\x005\x00Mario\x00Initial\n",
            b"bbb\x005\x00Mario\x00Initial\n",
        ]
        branches = [
            {"ref": "refs/remotes/origin/feature", "name": "origin/feature",
             "sha": "feature", "is_default": False},
            {"ref": "refs/remotes/origin/main", "name": "origin/main",
             "sha": "main", "is_default": True},
        ]

        history = latest_scan.file_history("repo", "src/file.py", branches)

        self.assertEqual(history[0]["branch"], "origin/main")
        self.assertEqual(history[0]["commits"][0]["commit"], "bbb")
        self.assertEqual(history[1]["commits"][0]["commit"], "aaa")


if __name__ == "__main__":
    unittest.main()
