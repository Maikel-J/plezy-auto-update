import hashlib
import json
import tempfile
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


    def test_226_compares_all_abis_to_225(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "upstream-release.json").write_text(json.dumps({
                "version": "2.26.0",
                "repository": compat.REPOSITORY,
                "release_tag": "v2.26.0+android.1",
            }))
            downloads = []

            def download(*args):
                downloads.append(args[-1])
                Path(args[-2]).write_bytes(b"verified baseline fixture")

            digest = hashlib.sha256(b"verified baseline fixture").hexdigest()
            fake_baseline = {
                "2.26.0": ("2.25.0", dict.fromkeys(compat.BASELINES["2.26.0"][1], digest))
            }
            with patch.object(compat, "BASELINES", fake_baseline), patch.object(
                compat, "run", side_effect=download
            ), patch.object(compat, "check_pair", return_value=(2158, 2161)) as compared:
                compat.verify_upgrade(assets, "apksigner", "apkanalyzer")
            self.assertEqual(compared.call_count, 3)
            self.assertEqual(len(downloads), 3)
            self.assertTrue(all("/releases/download/v2.25.0%2Bandroid.1/" in url for url in downloads))

    def test_226_rejects_wrong_release_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "upstream-release.json").write_text(json.dumps({
                "version": "2.26.0",
                "repository": compat.REPOSITORY,
                "release_tag": "v2.25.0+android.1",
            }))
            with self.assertRaisesRegex(ValueError, "Unexpected 2.26.0 recovery plan"):
                compat.verify_upgrade(assets, "apksigner", "apkanalyzer")


if __name__ == "__main__":
    unittest.main()
