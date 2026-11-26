import tempfile
import unittest
from pathlib import Path

from course_workspace import (
    load_course_workspace,
    load_user_profile,
    save_course_workspace,
    save_media_upload,
    save_user_profile,
)


class CourseWorkspaceTests(unittest.TestCase):
    def test_workspace_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "course_workspace.json"
            workspace, error = load_course_workspace(path)
            self.assertEqual(error, "")
            self.assertEqual(
                workspace,
                {"confirmed": [], "notes": {}, "week_one_mondays": {}},
            )

            expected = {
                "confirmed": ["1151::CS101-A"],
                "week_one_mondays": {"1151": "2026-09-07"},
                "notes": {
                    "1151::CS101-A": {
                        "text": "Remember the first lecture.",
                        "attachments": [],
                    }
                },
            }
            self.assertEqual(save_course_workspace(expected, path), "")
            loaded, error = load_course_workspace(path)
            self.assertEqual(error, "")
            self.assertEqual(loaded, expected)

    def test_media_upload_is_saved_and_identical_upload_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_directory = Path(temporary_directory) / "media"
            existing = []
            content = b"\x89PNG\r\n\x1a\nimage"
            attachment, duplicated, error = save_media_upload(
                content,
                "../../lecture.png",
                "image/png",
                media_directory,
                existing,
            )
            self.assertEqual(error, "")
            self.assertFalse(duplicated)
            self.assertEqual(Path(attachment["file"]).name, attachment["file"])
            self.assertEqual(attachment["name"], "lecture.png")
            self.assertEqual(
                (media_directory / attachment["file"]).read_bytes(),
                content,
            )

            duplicate, duplicated, error = save_media_upload(
                content,
                "lecture.png",
                "image/png",
                media_directory,
                [attachment],
            )
            self.assertEqual(error, "")
            self.assertTrue(duplicated)
            self.assertIsNone(duplicate)

    def test_rejects_unsupported_media_type(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            attachment, duplicated, error = save_media_upload(
                b"content",
                "note.txt",
                "text/plain",
                temporary_directory,
                [],
            )
            self.assertIsNone(attachment)
            self.assertFalse(duplicated)
            self.assertIn("不支援", error)

    def test_user_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "course_profile.json"
            profile = {
                "department": "資訊工程學系",
                "grade": "大二",
                "target_credits": 18,
                "preferred_days": ["二", "四"],
                "preferred_time_slots": ["二|540"],
            }
            self.assertEqual(save_user_profile(profile, path), "")
            loaded, error = load_user_profile(path)
            self.assertEqual(error, "")
            self.assertEqual(loaded, profile)


if __name__ == "__main__":
    unittest.main()
