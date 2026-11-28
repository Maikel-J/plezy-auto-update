"""Fail closed if signed recovery APKs cannot upgrade their pinned baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

REPOSITORY = "Maikel-J/plezy-auto-update"
APPLICATION_ID = "com.edde746.plezy"
BASELINES = {
    "2.24.0": ("2.23.0", {
        "arm64-v8a": "fbec8a8a9429dc2d4e4ce881573a4f24d64b9c5001824531e7601b9f89dd9659",
        "armeabi-v7a": "bbd1fa15f8d44f6bdf29128afae09cd6f04f179ab2a3a87f82b74062dcdc91cb",
        "x86_64": "8f3a9d770e7041e519b4d0982e4b0d86ba289d29e2fa76df8246c8602cf6c36d",
    }),
    "2.26.0": ("2.25.0", {
        "arm64-v8a": "367565d4c73e5ccff41c3c7f9863ad1921615d633bb5f375c56d913f9ae8f797",
        "armeabi-v7a": "437f8ec34a558270383999cb50c7f80597d922713f566e0bc9a2fabbf4ccc2b7",
        "x86_64": "b148d6bf0bb562e7060cf3b450fc1a26a9827825550318a06b5aedc3813f84c3",
    }),
}
CERT_LINE = re.compile(r"^Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})$", re.MULTILINE)


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE).stdout


def signer_set(output: str) -> set[str]:
    signers = {digest.lower() for digest in CERT_LINE.findall(output)}
    if not signers:
        raise ValueError("No verified APK signer fingerprints were returned")
    return signers


def check_pair(baseline: Path, candidate: Path, apksigner: str, apkanalyzer: str) -> tuple[int, int]:
    for apk in (baseline, candidate):
        if run(apkanalyzer, "manifest", "application-id", str(apk)).strip() != APPLICATION_ID:
            raise ValueError(f"Unexpected Android application ID: {apk.name}")
    old_signers, new_signers = (
        signer_set(run(apksigner, "verify", "--print-certs", str(apk))) for apk in (baseline, candidate)
    )
    if new_signers != old_signers:
        raise ValueError(f"Signing certificate mismatch: {candidate.name}")
    old_code, new_code = (
        int(run(apkanalyzer, "manifest", "version-code", str(apk)).strip()) for apk in (baseline, candidate)
    )
    if new_code <= old_code:
        raise ValueError(f"Android version code did not increase: {candidate.name} ({old_code} -> {new_code})")
    return old_code, new_code


def verify_upgrade(assets: Path, apksigner: str, apkanalyzer: str) -> None:
    plan = json.loads((assets / "upstream-release.json").read_text())
    version = plan.get("version")
    if version not in BASELINES:
        print("No pinned upgrade baseline for this release.")
        return
    if plan.get("repository") != REPOSITORY or plan.get("release_tag") != f"v{version}+android.1":
        raise ValueError(f"Unexpected {version} recovery plan")
    baseline_version, hashes = BASELINES[version]
    baseline_url = f"https://github.com/{REPOSITORY}/releases/download/v{baseline_version}%2Bandroid.1"
    print(f"Comparing signed {version} APKs to published {baseline_version}.")
    with tempfile.TemporaryDirectory() as tmp:
        for abi, expected in hashes.items():
            name = f"plezy-android-{abi}.apk"
            baseline = Path(tmp) / name
            run(
                "curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                "--proto-redir", "=https", "--max-time", "120", "--retry", "2",
                "--output", str(baseline), f"{baseline_url}/{name}",
            )
            with baseline.open("rb") as apk:
                if hashlib.file_digest(apk, "sha256").hexdigest() != expected:
                    raise ValueError(f"Published {baseline_version} baseline checksum mismatch: {abi}")
            old_code, new_code = check_pair(baseline, assets / name, apksigner, apkanalyzer)
            print(f"{abi}: verified same signing certificate set and version code {old_code} -> {new_code}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--apksigner", required=True)
    parser.add_argument("--apkanalyzer", required=True)
    args = parser.parse_args()
    verify_upgrade(args.assets, args.apksigner, args.apkanalyzer)


if __name__ == "__main__":
    main()
