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


def remove_legacy_launcher_art(manifest: str) -> None:
    path = Path(manifest)
    source = path.read_text()
    begin = "        <!-- Alternate icons (AppIconChannel): disabled until chosen. Ids are permanent. -->"
    end = "        <!-- END generated app icon aliases -->\n"
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError("Launcher alias boundaries changed")
    first = source.index(begin)
    last = source.index(end, first) + len(end)
    if source[first:last].count('android:name=".appicon.') != 23:
        raise ValueError("Unexpected legacy launcher alias inventory")
    path.write_text(source[:first] + source[last:])
    replace("android/app/src/main/res/drawable/splash_icon.xml",
            'android:drawable="@drawable/ic_launcher_foreground"',
            'android:drawable="@drawable/sundock_launcher"')
    replace("pubspec.yaml",
            "    # App icon picker thumbnails; scripts/codegen/generate_app_icons.py renders them from\n"
            "    # assets/app_icons/source, which stays out of the bundle.\n"
            "    - assets/app_icons/previews/\n", "")
    res = Path("android/app/src/main/res")
    legacy = [f for f in res.glob("*/*") if f.is_file() and f.name.startswith(("ic_launcher", "tv_banner"))]
    if len(legacy) != 287:
        raise ValueError(f"Unexpected legacy launcher resource inventory: {len(legacy)}")
    for file in legacy:
        file.unlink()



def isolate_diagnostics() -> None:
    service = "lib/services/log_upload_service.dart"
    replace(service, "import 'plezy_server.dart';\n", "")
    replace(service,
            "/// Plezy server endpoint that returns a short, quotable Log ID.\n"
            "const String logUploadEndpoint = '$plezyServerBaseUrl/logs';",
            "/// No hosted diagnostics endpoint is configured for this build.\n"
            "const String logUploadEndpoint = '';\n"
            "const bool diagnosticsUploadAvailable = logUploadEndpoint != '';")
    replace(service, "  final response = await (client ?? httpClient).post(",
            """  if (!diagnosticsUploadAvailable) {
    throw UnsupportedError('Hosted diagnostics are disabled in this build.');
  }
  final response = await (client ?? httpClient).post(""")
    logs = "lib/screens/settings/logs_screen.dart"
    replace(logs, "                              FocusableAction(\n"
                  "                                icon: Symbols.upload_rounded,",
            "                              if (diagnosticsUploadAvailable)\n"
            "                                FocusableAction(\n"
            "                                  icon: Symbols.upload_rounded,")
    startup = "lib/widgets/startup_failure_view.dart"
    replace(startup, "                  FocusableButton(\n"
                     "                    onPressed: enabled ? () => _uploadDetails() : null,",
            "                  if (diagnosticsUploadAvailable)\n"
            "                    FocusableButton(\n"
            "                      onPressed: enabled ? () => _uploadDetails() : null,")
    main = Path("lib/main.dart")
    main_source = main.read_text()
    dsn = [line for line in main_source.splitlines() if line.startswith("const String _sentryDsn = ")]
    if len(dsn) != 1 or "@bugs.plezy.app/" not in dsn[0]:
        raise ValueError("Unexpected upstream crash reporting configuration")
    replace(str(main), dsn[0], "const String _sentryDsn = '';")
    replace(str(main), "const bool _enableSentry = bool.fromEnvironment('ENABLE_SENTRY', defaultValue: false);",
            "const bool _enableSentry = false;")

    path = Path("test/screens/settings/logs_screen_test.dart")
    tests = path.read_text()
    begin = tests.index("  testWidgets('long upload capability displays and copies at narrow width'")
    end = tests.index("  group('previous startup failure'", begin)
    block = tests[begin:end]
    block = block.replace("long upload capability displays and copies at narrow width",
                          "diagnostics stay local and Copy works at narrow width")
    decl = block.index("    const capability")
    stop = block.index("    String? clipboardText;", decl)
    block = block[:decl] + "    var networkRequests = 0;\n" + block[stop:]
    mock = block.index("        uploadedRequest = request;")
    mock_end = block.index("      }),", mock)
    block = block[:mock] + """        networkRequests++;
        return http.Response('', 500);
""" + block[mock_end:]
    actions = block.index("    await tester.tap(find.byTooltip(t.logs.uploadLogs));")
    block = block[:actions] + """    expect(find.byTooltip(t.logs.uploadLogs), findsNothing);
    await tester.tap(find.byTooltip(t.logs.copyLogs));
    await tester.pumpAndSettle();
    expect(clipboardText, contains('widget upload seed'));
    await expectLater(uploadDiagnosticText('test-only', client: client), throwsUnsupportedError);
    expect(networkRequests, 0);
    expect(tester.takeException(), isNull);
  });

"""
    path.write_text(tests[:begin] + block + tests[end:])
    replace(str(path), "enables upload and copy with a record but an empty log buffer",
            "enables copy with a record but an empty log buffer")
    replace(str(path), "[t.logs.uploadLogs, t.logs.copyLogs, t.logs.clearLogs]",
            "[t.logs.copyLogs, t.logs.clearLogs]")
    replace(str(path), "startsWith('Plezy')", "startsWith('${t.app.title} v')")
    replace(str(path), "find.textContaining('Plezy', findRichText: true)",
            "find.textContaining('${t.app.title} v', findRichText: true)")
    replace("test/widgets/startup_failure_view_test.dart",
            "    // The diagnostic actions stay, because a stuck user still needs them out.",
            "    // Local diagnostic copy stays available even when storage is gated.")
    replace("test/widgets/startup_failure_view_test.dart",
            "expect(find.byKey(startupFailureUploadKey), findsOneWidget);",
            "expect(find.byKey(startupFailureUploadKey), findsNothing);")
    replace("test/widgets/startup_failure_view_test.dart",
            "    expect(find.byKey(startupFailureRestartKey), findsNothing);",
            "    expect(find.byKey(startupFailureRestartKey), findsNothing);\n"
            "    expect(find.byKey(startupFailureUploadKey), findsNothing);\n"
            "    expect(find.byKey(startupFailureCopyKey), findsOneWidget);")



def isolate_updater_asset_names() -> None:
    service = Path("lib/services/android_update_service.dart")
    tests = Path("test/services/android_update_service_test.dart")
    old = "plezy-android-"
    new = "autoplez-android-"
    source = service.read_text()
    if source.count(old) != 2:
        raise ValueError("Unexpected updater asset name patterns")
    service.write_text(source.replace(old, new))
    test_source = tests.read_text()
    if test_source.count(old) < 5:
        raise ValueError("Missing updater asset test fixtures")
    tests.write_text(test_source.replace(old, new))
    replace(str(tests), "import 'dart:async';", "import 'dart:async';\nimport 'dart:convert';")
    replace(str(tests), f"const repository = '{OLD_FEED}';", f"const repository = '{FEED}';")
    replace(str(tests), "  group('release asset selection', () {", """  group('release asset selection', () {
    test('rejects legacy asset names and Flutter build filenames', () {
      for (final name in ['plezy-android-arm64-v8a.apk', 'app-arm64-v8a-release.apk']) {
        expect(AndroidUpdateAsset.select([
          {...releaseAsset('arm64-v8a'), 'name': name},
        ], ['arm64-v8a'], repository), isNull);
      }
    });

    final manifestPath = Platform.environment['AUTOPLEZ_REHEARSAL_ASSET_JSON'];
    if (manifestPath != null) {
      test('all three staged release names resolve from the publication metadata', () {
        final manifest = jsonDecode(File(manifestPath).readAsStringSync()) as Map<String, dynamic>;
        final assets = manifest['assets'] as List<dynamic>;
        expect(assets, hasLength(3));
        for (final abi in ['arm64-v8a', 'armeabi-v7a', 'x86_64']) {
          final asset = AndroidUpdateAsset.select(assets, [abi], repository)!;
          expect(asset.url.pathSegments.last, 'autoplez-android-$abi.apk');
          expect(asset.size, greaterThan(0));
          expect(asset.sha256Digest, matches(r'^[0-9a-f]{64}$'));
        }
        expect(AndroidUpdateAsset.select(assets, ['arm64-v8a'], 'Maikel-J/plezy-auto-update'), isNull);
      });
    }
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
    remove_legacy_launcher_art(manifest)
    isolate_diagnostics()
    isolate_updater_asset_names()
    for name, dimensions in (("sundock_launcher", (108, 108, 100)), ("sundock_tv_banner", (320, 180, 178))):
        output = Path("android/app/src/main/res/drawable") / f"{name}.xml"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(drawable(*dimensions))


if __name__ == "__main__":
    apply_identity()
