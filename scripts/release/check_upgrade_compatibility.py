"""Fail closed if signed 2.24.0 APKs cannot update the published 2.23.0 APKs."""
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
BASELINE_URL = f"https://github.com/{REPOSITORY}/releases/download/v2.23.0%2Bandroid.1"
BASELINE_HASHES = {
    "arm64-v8a": "fbec8a8a9429dc2d4e4ce881573a4f24d64b9c5001824531e7601b9f89dd9659",
    "armeabi-v7a": "bbd1fa15f8d44f6bdf29128afae09cd6f04f179ab2a3a87f82b74062dcdc91cb",
    "x86_64": "8f3a9d770e7041e519b4d0982e4b0d86ba289d29e2fa76df8246c8602cf6c36d",
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


def verify_224(assets: Path, apksigner: str, apkanalyzer: str) -> None:
    plan = json.loads((assets / "upstream-release.json").read_text())
    if plan.get("version") != "2.24.0":
        print("Pinned 2.23.0 comparison applies to the 2.24.0 recovery release only.")
        return
    if plan.get("repository") != REPOSITORY or plan.get("release_tag") != "v2.24.0+android.1":
        raise ValueError("Unexpected 2.24.0 recovery plan")
    with tempfile.TemporaryDirectory() as tmp:
        for abi, expected in BASELINE_HASHES.items():
            name = f"plezy-android-{abi}.apk"
            baseline = Path(tmp) / name
            run(
                "curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                "--proto-redir", "=https", "--max-time", "120", "--retry", "2",
                "--output", str(baseline), f"{BASELINE_URL}/{name}",
            )
            with baseline.open("rb") as apk:
                if hashlib.file_digest(apk, "sha256").hexdigest() != expected:
                    raise ValueError(f"Published 2.23.0 baseline checksum mismatch: {abi}")
            old_code, new_code = check_pair(baseline, assets / name, apksigner, apkanalyzer)
            print(f"{abi}: verified same signing certificate set and version code {old_code} -> {new_code}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--apksigner", required=True)
    parser.add_argument("--apkanalyzer", required=True)
    args = parser.parse_args()
    verify_224(args.assets, args.apksigner, args.apkanalyzer)


if __name__ == "__main__":
    main()
