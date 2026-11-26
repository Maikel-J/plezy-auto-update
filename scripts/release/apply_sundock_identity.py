#!/usr/bin/env python3
"""Apply draft Sundock Android identity after exact upstream release preparation.

This prototype must not be signed or distributed: the full asset and inherited
service audit is not finished. The existing Plezy feed is never a fallback.
"""
from pathlib import Path

APP_ID = "io.github.maikelj.sundock"
APP_NAME = "autoPlez"
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


def update_runtime_identity() -> None:
    dart = "lib/services/deep_links/deep_link.dart"
    kt = "android/app/src"
    native = f"{kt}/main/kotlin/com/edde746/plezy"
    test_native = f"{kt}/test/kotlin/com/edde746/plezy"
    replace(dart, "static const scheme = 'plezy';", f"static const scheme = '{SCHEME}';")
    replace(f"{native}/deeplink/DeepLinkPlugin.kt", 'private const val SCHEME = "plezy"',
            f'private const val SCHEME = "{SCHEME}"')
    shelf = f"{native}/watchnext/WatchNextProvider.kt"
    replace(shelf, 'uri.scheme != "plezy"', f'uri.scheme != "{SCHEME}"')
    replace(shelf, '.scheme("plezy")', f'.scheme("{SCHEME}")')

    # Android rejects side-by-side installation when provider authorities collide,
    # even if the APKs have different application IDs.
    manifest = f"{kt}/main/AndroidManifest.xml"
    for suffix, consumers in {
        "fileprovider": [f"{native}/ExternalPlayerChannel.kt"],
        "systemshelf.artwork": [
            f"{native}/watchnext/SystemShelfArtworkProvider.kt",
            f"{test_native}/watchnext/SystemShelfArtworkManifestTest.kt",
        ],
    }.items():
        old, new = f"com.edde746.plezy.{suffix}", f"{APP_ID}.{suffix}"
        for path in [manifest, *consumers]:
            replace(path, old, new)

    for directory, pattern in (("lib", "*.dart"), ("test", "*.dart"), (kt, "*.kt")):
        for path in Path(directory).rglob(pattern):
            # Leave the method channel and stored content IDs unchanged.
            source = path.read_text()
            updated = (source.replace("plezy://", f"{SCHEME}://")
                       .replace("PLEZY://", f"{SCHEME.upper()}://")
                       .replace("Plezy://", f"{SCHEME}://"))
            if source != updated:
                path.write_text(updated)

    dart_test = "test/services/deep_links/deep_link_test.dart"
    replace(dart_test, "void main() {", """void main() {
  test('the legacy app link scheme is not claimed', () {
    expect(DeepLink.tryParse('plezy://open'), isNull);
    expect(DeepLink.tryParse('sundockmedia://open'), isA<OpenLink>());
  });
""")
    kotlin_test = f"{test_native}/deeplink/DeepLinkPluginTest.kt"
    replace(kotlin_test, "assertNull(DeepLinkPlugin.linkFrom(null))",
            'assertNull(DeepLinkPlugin.linkFrom(null))\n    assertNull(DeepLinkPlugin.linkFrom(viewIntent("plezy://open")))')


def apply_about_brand() -> None:
    en = Path("lib/i18n/en.i18n.json")
    for source in sorted(en.parent.glob("*.i18n.json")):
        if '"title": "Plezy"' in source.read_text():
            replace(str(source), '"title": "Plezy"', f'"title": "{APP_NAME}"')
    if f'"title": "{APP_NAME}"' not in en.read_text():
        raise ValueError("Missing rebranded app title")

    about = "lib/screens/settings/about_screen.dart"
    replace(about, "import 'package:flutter/material.dart';",
            "import 'package:flutter/material.dart';\nimport 'package:flutter_svg/flutter_svg.dart';")
    replace(about, "Image.asset('assets/plezy.png', width: 80, height: 80)",
            "SvgPicture.asset('assets/sundock_brand.svg', width: 80, height: 80)")
    auth = "lib/screens/auth_screen.dart"
    replace(auth, "import 'package:flutter/material.dart';",
            "import 'package:flutter/material.dart';\nimport 'package:flutter_svg/flutter_svg.dart';")
    for path, old, new in [
        (auth, "Image.asset('assets/plezy.png',", "SvgPicture.asset('assets/sundock_brand.svg',"),
        ("lib/main.dart", "SvgPicture.asset('assets/plezy_adaptive_foreground.svg',",
         "SvgPicture.asset('assets/sundock_brand.svg',"),
    ]:
        source = Path(path).read_text()
        if source.count(old) != 2:
            raise ValueError(f"Unexpected number of visible logo references in {path}")
        Path(path).write_text(source.replace(old, new))
    replace("pubspec.yaml", "    - assets/plezy.png", "    - assets/sundock_brand.svg")
    replace("pubspec.yaml", "    - assets/plezy_adaptive_foreground.svg\n", "")
    Path("assets/sundock_brand.svg").write_text("""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="18" fill="#102B34"/>
  <path d="M33 58A17 17 0 0 1 67 58Z" fill="#F4B857"/>
  <path d="M24 63H76V70H24Z M34 75H66V80H34Z" fill="#83DBCF"/>
</svg>
""")


def apply_identity() -> None:
    gradle = "android/app/build.gradle.kts"
    manifest = "android/app/src/main/AndroidManifest.xml"
    updates = "lib/services/update_service.dart"
    replace(gradle, 'applicationId = "com.edde746.plezy"', f'applicationId = "{APP_ID}"')
    replace(manifest, 'android:label="Plezy"', f'android:label="{APP_NAME}"')
    replace(manifest, 'android:scheme="plezy"', f'android:scheme="{SCHEME}"')
    replace(manifest, 'android:icon="@mipmap/ic_launcher"', 'android:icon="@drawable/sundock_launcher"')
    replace(manifest, 'android:banner="@drawable/tv_banner"', 'android:banner="@drawable/sundock_tv_banner"')
    replace(updates,
            f"const String.fromEnvironment('ANDROID_UPDATE_REPOSITORY', defaultValue: '{OLD_FEED}')",
            "sundockAndroidRepository")
    replace(updates, "class UpdateService {",
            f"class UpdateService {{\n  static const String sundockAndroidRepository = '{FEED}';")
    update_test = "test/services/update_service_test.dart"
    replace(update_test, "void main() {", """void main() {
  test('the Android updater is pinned to the independent Sundock repository', () {
    expect(UpdateService.sundockAndroidRepository, 'Maikel-J/sundock-media');
  });
""")
    update_runtime_identity()
    apply_about_brand()
    for name, dimensions in (("sundock_launcher", (108, 108, 100)), ("sundock_tv_banner", (320, 180, 178))):
        output = Path("android/app/src/main/res/drawable") / f"{name}.xml"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(drawable(*dimensions))


if __name__ == "__main__":
    apply_identity()
