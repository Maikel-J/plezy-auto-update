from pathlib import Path
import unittest
from unittest.mock import patch

import check_upgrade_compatibility as compat


class UpgradeCompatibilityTest(unittest.TestCase):
    def check(self, *, old_signer="a" * 64, new_signer="a" * 64, new_code=2156, new_id=compat.APPLICATION_ID):
        old, candidate = Path("previous.apk"), Path("candidate.apk")

        def tool(*args):
            current = args[-1] == str(candidate)
            if args[0] == "apksigner":
                signer = new_signer if current else old_signer
                return f"Signer #1 certificate SHA-256 digest: {signer}\n"
            if args[2] == "application-id":
                return new_id if current else compat.APPLICATION_ID
            return str(new_code if current else 2154)

        with patch.object(compat, "run", side_effect=tool):
            return compat.check_pair(old, candidate, "apksigner", "apkanalyzer")

    def test_same_signer_and_higher_version(self):
        self.assertEqual(self.check(), (2154, 2156))

    def test_rejects_changed_signer(self):
        with self.assertRaisesRegex(ValueError, "Signing certificate mismatch"):
            self.check(new_signer="b" * 64)

    def test_rejects_missing_signer(self):
        with self.assertRaisesRegex(ValueError, "No verified APK signer"):
            self.check(new_signer="")

    def test_rejects_equal_or_lower_version(self):
        for version in (2154, 2153):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "version code did not increase"):
                self.check(new_code=version)

    def test_rejects_changed_application_id(self):
        with self.assertRaisesRegex(ValueError, "Unexpected Android application ID"):
            self.check(new_id="com.example.other")


if __name__ == "__main__":
    unittest.main()
