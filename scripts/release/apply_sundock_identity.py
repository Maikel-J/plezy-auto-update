#!/usr/bin/env python3
"""Apply draft Sundock Android identity after exact upstream release preparation.

This prototype must not be signed or distributed: the full asset and inherited
service audit is not finished. The existing Plezy feed is never a fallback.
"""
from pathlib import Path

APP_ID = "io.github.maikelj.sundock"
APP_NAME = "Sundock Media"
SCHEME = "sundockmedia"
FEED = "Maikel-J/sundock-media"
OLD_FEED = "Maikel-J/plezy-auto-update"


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    source = file.read_text()
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one identity site in {path}: {old!r}")
    file.write_text(source.replace(old, new, 1))


def drawable(width: int, height: int, viewport: int) -> str:
    offset = (viewport - 100) // 2
    return f"""<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="{width}dp" android:height="{height}dp"
    android:viewportWidth="{viewport}" android:viewportHeight="100">
    <path android:fillColor="#102B34" android:pathData="M0,0H{viewport}V100H0Z"/>
    <group android:translateX="{offset}">
        <path android:fillColor="#F4B857"
            android:pathData="M33,58A17,17 0,0 1,67 58Z"/>
        <path android:fillColor="#83DBCF" android:pathData="M24,63H76V70H24Z M34,75H66V80H34Z"/>
    </group>
</vector>
"""


def apply_identity() -> None:
    gradle = "android/app/build.gradle.kts"
    manifest = "android/app/src/main/AndroidManifest.xml"
    updates = "lib/services/update_service.dart"
    replace(gradle, 'applicationId = "com.edde746.plezy"', f'applicationId = "{APP_ID}"')
    replace(manifest, 'android:label="Plezy"', f'android:label="{APP_NAME}"')
    replace(manifest, 'android:scheme="plezy"', f'android:scheme="{SCHEME}"')
    replace(manifest, 'android:icon="@mipmap/ic_launcher"', 'android:icon="@drawable/sundock_launcher"')
    replace(manifest, 'android:banner="@drawable/tv_banner"', 'android:banner="@drawable/sundock_tv_banner"')
    replace(updates, f"defaultValue: '{OLD_FEED}'", f"defaultValue: '{FEED}'")
    for name, dimensions in (("sundock_launcher", (108, 108, 100)), ("sundock_tv_banner", (320, 180, 178))):
        output = Path("android/app/src/main/res/drawable") / f"{name}.xml"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(drawable(*dimensions))


if __name__ == "__main__":
    apply_identity()
