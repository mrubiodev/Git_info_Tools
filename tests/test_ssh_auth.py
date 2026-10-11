import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from git_info.core import ssh_auth
from git_info.gui.credentials import CredentialPrompter

DENIED = "git@example.com: Permission denied (publickey).\nfatal: Could not read from remote repository."


class SshAuthTests(unittest.TestCase):
    def test_detects_ssh_key_error(self):
        self.assertTrue(ssh_auth.is_ssh_key_error(DENIED))
        self.assertFalse(ssh_auth.is_ssh_key_error("fatal: repository not found"))
        self.assertFalse(ssh_auth.is_ssh_key_error(None))

    @unittest.skipUnless(shutil.which("ssh-keygen") and shutil.which("git"), "requiere OpenSSH y Git")
    def test_load_keys_with_wrong_and_right_passphrase(self):
        try:
            ssh_auth._git_tool("ssh-agent")
            ssh_auth._git_tool("ssh-add")
        except ssh_auth.SshAuthError:
            self.skipTest("sin ssh-agent de Git")
        with tempfile.TemporaryDirectory() as folder:
            key = os.path.join(folder, "id_ed25519")
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "secreto123", "-f", key, "-C", "t"],
                           check=True, stdin=subprocess.DEVNULL, capture_output=True)
            try:
                with self.assertRaisesRegex(ssh_auth.SshAuthError, "passphrase"):
                    ssh_auth.load_keys("mala", [key])
                self.assertEqual(ssh_auth.load_keys("secreto123", [key]), [key])
                self.assertIn("SSH_AUTH_SOCK", os.environ)
            finally:
                ssh_auth.stop_agent()
            self.assertFalse(ssh_auth.agent_active())


class CredentialPrompterTests(unittest.TestCase):
    def make(self):
        app = MagicMock()
        prompter = CredentialPrompter(app)
        return app, prompter

    def test_ignores_other_errors(self):
        _, prompter = self.make()
        with patch.object(prompter, "prompt") as prompt:
            self.assertFalse(prompter.handle(["timeout"]))
        prompt.assert_not_called()

    def test_prompts_and_retries_after_loading(self):
        app, prompter = self.make()
        retry = MagicMock()
        app.runner.submit.side_effect = lambda fn, on_success, on_error: on_success(["k"])
        with patch.object(ssh_auth, "default_keys", return_value=["k"]), \
                patch("git_info.gui.credentials.simpledialog.askstring", return_value="pw"):
            self.assertTrue(prompter.handle([DENIED], retry=retry))
        retry.assert_called_once()
        self.assertEqual(prompter.loaded, ["k"])

    def test_cancel_stops_automatic_prompts_but_not_manual(self):
        _, prompter = self.make()
        with patch.object(ssh_auth, "default_keys", return_value=["k"]), \
                patch("git_info.gui.credentials.simpledialog.askstring", return_value=None) as ask:
            self.assertTrue(prompter.handle(DENIED, retry=MagicMock()))
            self.assertTrue(prompter.declined)
            self.assertFalse(prompter.handle(DENIED, retry=MagicMock()))
            self.assertTrue(prompter.handle(DENIED, retry=MagicMock(), manual=True))
        self.assertEqual(ask.call_count, 2)


if __name__ == "__main__":
    unittest.main()
