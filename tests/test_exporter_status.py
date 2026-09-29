import os
import tempfile
import unittest

from git_info.core import exporter


class InspectEntriesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dest_dir = self.temp_dir.name
        self.entry = {
            "path": "src/file.txt",
            "branch": "main",
            "blob": exporter.git_blob_id(b"latest"),
        }
        self.target = os.path.join(self.dest_dir, "src", "file.txt")
        os.makedirs(os.path.dirname(self.target))

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_target(self, content):
        with open(self.target, "wb") as file:
            file.write(content)

    def write_manifest(self, blob):
        exporter.save_manifest(self.dest_dir, {
            "version": 1,
            "files": {"src/file.txt": {"blob": blob}},
        })

    def test_reports_up_to_date_file(self):
        self.write_target(b"latest")
        self.write_manifest(exporter.git_blob_id(b"older"))

        result = exporter.inspect_entries(self.dest_dir, [self.entry])

        self.assertEqual(result["statuses"]["src/file.txt"], exporter.STATUS_UP_TO_DATE)

    def test_reports_available_update_for_unchanged_tracked_file(self):
        self.write_target(b"older")
        self.write_manifest(exporter.git_blob_id(b"older"))

        result = exporter.inspect_entries(self.dest_dir, [self.entry])

        self.assertEqual(result["statuses"]["src/file.txt"], exporter.STATUS_UPDATE_AVAILABLE)

    def test_reports_local_modification(self):
        self.write_target(b"local edit")
        self.write_manifest(exporter.git_blob_id(b"older"))

        result = exporter.inspect_entries(self.dest_dir, [self.entry])

        self.assertEqual(result["statuses"]["src/file.txt"], exporter.STATUS_LOCAL_MODIFIED)

    def test_reports_untracked_and_missing_files(self):
        self.write_target(b"older")
        result = exporter.inspect_entries(self.dest_dir, [self.entry])
        self.assertEqual(result["statuses"]["src/file.txt"], exporter.STATUS_UNTRACKED)

        os.remove(self.target)
        result = exporter.inspect_entries(self.dest_dir, [self.entry])
        self.assertEqual(result["statuses"]["src/file.txt"], exporter.STATUS_MISSING)


if __name__ == "__main__":
    unittest.main()
