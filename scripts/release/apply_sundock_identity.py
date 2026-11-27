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


def replace(path: str, old: str, new: str, *, expected: int = 1) -> None:
    file = Path(path)
    source = file.read_text()
    if source.count(old) != expected:
        raise ValueError(f"Expected {expected} matching site(s) in {path}: {old!r}")
    file.write_text(source.replace(old, new, expected))


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


def rebrand_media_server_identity() -> None:
    replace("lib/services/plex_auth_service.dart", "static const String _appName = 'Plezy';",
            f"static const String _appName = '{APP_NAME}';")
    replace("lib/models/plex/plex_config.dart", "product: product ?? 'Plezy',",
            f"product: product ?? '{APP_NAME}',")
    plex = "lib/services/plex_client.dart"
    replace(plex, "headers['X-Plex-Product'] = 'Plezy';",
            f"headers['X-Plex-Product'] = '{APP_NAME}';")
    replace(plex, "sanitizeHeaderValue(identity.deviceName) ?? 'Plezy';",
            f"sanitizeHeaderValue(identity.deviceName) ?? '{APP_NAME}';")
    replace("lib/services/plex_discover_client.dart", "'X-Plex-Product': 'Plezy',",
            f"'X-Plex-Product': '{APP_NAME}',")

    header = Path("lib/services/jellyfin_auth_header.dart")
    before = header.read_text()
    if before.count("'Plezy") != 5:
        raise ValueError("Unexpected Jellyfin/Emby client identity literals")
    header.write_text(before.replace("'Plezy", f"'{APP_NAME}"))
    test_header = Path("test/services/jellyfin_auth_header_test.dart")
    test_header.write_text(test_header.read_text().replace("Plezy", APP_NAME))
    test_urls = Path("test/services/jellyfin_client_urls_test.dart")
    u = test_urls.read_text()
    if u.count('Client="Plezy%20') != 3:
        raise ValueError("Unexpected MediaBrowser expected client headers")
    test_urls.write_text(u.replace('Client="Plezy%20', f'Client="{APP_NAME}%20'))

    plex_test = "test/services/plex_auth_service_test.dart"
    replace(plex_test, "  group('PlexAuthService', () {", """  group('PlexAuthService', () {
    test('browser authorization carries the new label and retains the installation identifier', () {
      final httpClient = MediaServerHttpClient(client: MockClient((_) async => throw StateError('Unexpected HTTP')));
      final auth = PlexAuthService.forTesting(http: httpClient, clientIdentifier: 'rehearsal-device');
      addTearDown(auth.dispose);
      final uri = Uri.parse(auth.getAuthUrl('test-pin'));
      final context = Uri.splitQueryString(uri.fragment.substring(1));
      expect(context['context[device][product]'], 'autoPlez');
      expect(context['clientID'], 'rehearsal-device');
    });
""")
    replace(plex_test, "          hosts.add(request.url.host);\n"
                       "          if (request.url.host == 'clients.plex.tv') {",
            "          hosts.add(request.url.host);\n"
            "          expect(request.headers.entries.singleWhere("
            "(e) => e.key.toLowerCase() == 'x-plex-product').value, 'autoPlez');\n"
            "          if (request.url.host == 'clients.plex.tv') {")


def isolate_watch_together_relays() -> None:
    # The SDK also supports a public network. This rehearsal deliberately
    # selects exactly one explicitly configured relay and never falls back.
    replace("lib/watch_together/services/watch_party_relays.dart",
            "String? canonicalRelayBaseUrl(String input) {\n  final trimmed = input.trim();",
            "String? canonicalRelayBaseUrl(String? input) {\n  final trimmed = input?.trim() ?? '';")
    replace("lib/watch_together/services/watch_party_relays.dart",
            "  final host = uri.host.toLowerCase();",
            "  final host = uri.host.toLowerCase();\n  final dnsHost = host.replaceFirst(RegExp(r'\\.+$'), '');\n  if (dnsHost == 'openwatch.party' || dnsHost.endsWith('.openwatch.party') ||\n      dnsHost == 'plezy.app' || dnsHost.endsWith('.plezy.app')) {\n    return null;\n  }")
    replace("lib/watch_together/services/watch_party_relays.dart",
            "/// The relays rooms live on: the public Open Watch Party relays, or the\n/// self-hosted one at [customBaseUrl].\nowp.Relays relaysFor(String? customBaseUrl) =>\n    customBaseUrl == null ? owp.Relays.public() : owp.Relays.at(customBaseUrl);",
            "/// Local app error; no request has been made.\nconst relayConfigurationRequired = 'autoplez_relay_configuration_required';\n\n/// Use exactly one explicitly configured independent relay, never a public fallback.\nowp.Relays relaysFor(String? customBaseUrl) {\n  final base = canonicalRelayBaseUrl(customBaseUrl);\n  if (base == null) {\n    throw const owp.PartyException(relayConfigurationRequired, 'No independent Watch Together relay configured');\n  }\n  return owp.Relays.at(base);\n}")
    replace("lib/watch_together/services/watch_party_relays.dart",
            "customBaseUrl == null ? 'public' : sha256.convert(utf8.encode(customBaseUrl)).toString();",
            "customBaseUrl == null ? 'unconfigured' : sha256.convert(utf8.encode(customBaseUrl)).toString();")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "_clientName = clientName ?? _plezyClientName",
            "_clientName = clientName ?? _appClientName")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "static String _defaultName() => 'Plezy';",
            "static String _defaultName() => 'autoPlez';")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "static Future<String> _plezyClientName() async {",
            "static Future<String> _appClientName() async {")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "return 'Plezy/${info.version}';",
            "return 'autoPlez/${info.version}';")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "    final base = _customRelayBaseUrl();",
            "    final base = customRelayBaseUrl;")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "String get relayScope => relayScopeOf(_customRelayBaseUrl());",
            "String get relayScope => relayScopeOf(customRelayBaseUrl);")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "  /// The self-hosted relay's base URL rooms use; null for the public relays.\n  String? get customRelayBaseUrl => _customRelayBaseUrl();",
            "  /// The configured independent relay, or null if the feature is unconfigured.\n  String? get customRelayBaseUrl => canonicalRelayBaseUrl(_customRelayBaseUrl());")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "    await _closeParty();\n    final name = _sanitizedName(_displayName());\n    final party = _partyFactory(relays: _currentRelays(),",
            "    final relays = _currentRelays();\n    await _closeParty();\n    final name = _sanitizedName(_displayName());\n    final party = _partyFactory(relays: relays,")
    replace("lib/watch_together/providers/watch_together_provider.dart",
            "        final relays = _customRelayBaseUrl() == null ? 'the public relays' : 'the custom relay';\n        appLogger.w('WatchTogether: $action failed on $relays: ${error.code}: ${error.message}');",
            "        appLogger.w('WatchTogether: $action failed on the configured relay: ${error.code}: ${error.message}');")
    replace("lib/watch_together/widgets/watch_labels.dart",
            "import '../models/watch_notice.dart';",
            "import '../models/watch_notice.dart';\nimport '../services/watch_party_relays.dart';")
    replace("lib/watch_together/widgets/watch_labels.dart",
            "  owp.ErrorCode.invalidCode =>",
            "  relayConfigurationRequired => t.watchTogether.relayRequired,\n  owp.ErrorCode.invalidCode =>")
    replace("lib/watch_together/screens/watch_together_screen.dart",
            "    final rooms = profileId == null\n",
            "    final relay = provider.customRelayBaseUrl;\n    final rooms = profileId == null || relay == null\n")
    replace("lib/watch_together/screens/watch_together_screen.dart",
            "    final relay = provider.customRelayBaseUrl;\n    return Column(",
            "    return Column(")
    replace("lib/watch_together/screens/watch_together_screen.dart",
            "onPressed: busy ? null : widget.onCreate,",
            "onPressed: busy || relay == null ? null : widget.onCreate,")
    replace("lib/watch_together/screens/watch_together_screen.dart",
            "onPressed: busy ? null : widget.onJoin,",
            "onPressed: busy || relay == null ? null : widget.onJoin,")
    replace("lib/watch_together/screens/watch_together_screen.dart",
            "t.watchTogether.relayPublic : t.watchTogether.relayCustom(url: relay)",
            "t.watchTogether.relayRequired : t.watchTogether.relayCustom(url: relay)")
    replace("lib/screens/settings/settings_screen.dart",
            "subtitle: t.settings.watchTogetherRelayDescription,",
            "subtitle: t.watchTogether.relayRequired,")
    replace("lib/screens/settings/settings_screen.dart",
            "errorText: _relayUrlInvalid ? t.settings.watchTogetherRelayInvalid : null,",
            "errorText: _relayUrlInvalid ? t.watchTogether.independentRelayInvalid : null,")
    replace("lib/screens/settings/settings_screen.dart",
            "DialogActionButton(onPressed: _reset, label: t.settings.resetToDefault),",
            "DialogActionButton(onPressed: _reset, label: t.watchTogether.clearRelay),")
    replace("lib/i18n/en.i18n.json",
            "    \"relayPublic\": \"Rooms use the public Open Watch Party relays.\",",
            "    \"relayPublic\": \"Rooms use the public Open Watch Party relays.\",\n    \"relayRequired\": \"Set your own relay in Settings → Watch Together Relay. Everyone in a room must use the same relay.\",\n    \"independentRelayInvalid\": \"Enter the HTTP or HTTPS base URL for your own relay.\",\n    \"clearRelay\": \"Clear relay\",")
    replace("test/watch_together/watch_party_relays_test.dart",
            "    test('null is the public relays', () {\n      final relays = relaysFor(null);\n      expect(relays.list, isNotEmpty);\n      expect(relays.list.every((relay) => relay.url.startsWith('wss://')), isTrue);\n    });",
            "    test('missing, malformed and inherited relay URLs fail without selecting a relay', () {\n      for (final input in [null, '', 'invalid', 'https://openwatch.party',\n        'https://EU.RELAY.OPENWATCH.PARTY./', 'https://relay.plezy.app']) {\n        expect(\n          () => relaysFor(input),\n          throwsA(isA<owp.PartyException>().having((e) => e.code, 'code', relayConfigurationRequired)),\n          reason: '$input',\n        );\n      }\n    });")
    replace("test/watch_together/watch_party_relays_test.dart",
            "public relays share one scope; each custom base has its own, stable one",
            "unconfigured is separate; each independent relay has a stable scope")
    replace("test/watch_together/watch_party_relays_test.dart",
            "expect(relayScopeOf(null), 'public');",
            "expect(relayScopeOf(null), 'unconfigured');")
    replace("test/test_helpers/watch_room_harness.dart",
            "/// The server the [WatchRoomHarness.host] shares its files from.",
            "const watchTestRelayBaseUrl = 'https://watch.example.test';\n\n/// The server the [WatchRoomHarness.host] shares its files from.")
    replace("test/test_helpers/watch_room_harness.dart",
            "  /// A participant named [name]. [relayBaseUrl] is the relay setting (null:\n  /// the public relays); the room is on [relay] either way.",
            "  /// A participant named [name]. The test relay is configured unless overridden.")
    replace("test/test_helpers/watch_room_harness.dart",
            "customRelayBaseUrl: () => relayBaseUrl,",
            "customRelayBaseUrl: () => relayBaseUrl ?? watchTestRelayBaseUrl,")
    replace("test/watch_together/watch_together_provider_test.dart",
            "    partyFactory: relay.party,",
            "    partyFactory: relay.party,\n    customRelayBaseUrl: () => 'https://watch.example.test',")
    replace("test/watch_together/watch_together_provider_test.dart",
            "presses left to the player, the public relays",
            "presses left to the player, no relay configured")
    replace("test/watch_together/watch_together_provider_test.dart",
            "      expect(h.provider.relayScope, relayScopeOf(null));",
            "      expect(h.provider.relayScope, relayScopeOf('https://watch.example.test'));")
    replace("test/watch_together/watch_together_provider_test.dart",
            "final rooms = RecentRoomsService.getRecentRooms(profileId: profile, relayScope: relayScopeOf(null));",
            "final rooms = RecentRoomsService.getRecentRooms(\n          profileId: profile, relayScope: relayScopeOf('https://watch.example.test'),\n        );")
    replace("test/watch_together/watch_together_provider_test.dart",
            "a display name without text is Plezy",
            "a display name without text is autoPlez")
    replace("test/watch_together/watch_together_provider_test.dart",
            "expect(h.provider.participants.single.name, 'Plezy');",
            "expect(h.provider.participants.single.name, 'autoPlez');")
    replace("test/watch_together/watch_together_provider_test.dart",
            "    test('a player opened outside a room is only remembered; another one releases it', () async {",
            "    test('create and join reject missing or inherited configuration before the party factory', () async {\n      for (final base in [null, ' ', 'nonsense', 'https://na.relay.openwatch.party']) {\n        final provider = WatchTogetherProvider(\n          customRelayBaseUrl: () => base,\n          clientName: () async => throw StateError('Client metadata must not be read'),\n          partyFactory: ({required relays, required client, required name, required resolver}) =>\n              throw StateError('Unexpected party factory'),\n        );\n        addTearDown(provider.dispose);\n        expect(provider.customRelayBaseUrl, isNull);\n        await expectLater(provider.createRoom(), _partyError(relayConfigurationRequired));\n        await expectLater(provider.joinRoom('K7M-Q2X'), _partyError(relayConfigurationRequired));\n        expect(provider.isInSession, isFalse);\n      }\n    });\n\n    test('a player opened outside a room is only remembered; another one releases it', () async {")
    replace("test/watch_together/watch_together_screen_test.dart",
            "List<RecentRoom> _recentRooms(String profileId, [String? relay])",
            "List<RecentRoom> _recentRooms(String profileId, [String? relay = watchTestRelayBaseUrl])")
    replace("test/watch_together/watch_together_screen_test.dart",
            "      await _openScreen(tester, host);\n      expect(find.text(t.watchTogether.relayPublic), findsOneWidget);\n",
            "      await _openScreen(tester, host);\n      expect(find.text(t.watchTogether.relayCustom(url: watchTestRelayBaseUrl)), findsOneWidget);\n")
    replace("test/watch_together/watch_together_screen_test.dart",
            "      await _openScreen(tester, world.guest(profileId: 'p1'));\n      expect(find.text(t.watchTogether.relayPublic), findsOneWidget);\n      expect(find.text('K7M-Q2X'), findsOneWidget);",
            "      await _openScreen(tester, world.guest(profileId: 'p1'));\n      expect(find.text(t.watchTogether.relayCustom(url: watchTestRelayBaseUrl)), findsOneWidget);\n      expect(find.text('K7M-Q2X'), findsOneWidget);")
    replace("test/watch_together/watch_together_screen_test.dart",
            "      await RecentRoomsService.addOrUpdateRoom('ABC234', profileId: 'p1', relayScope: relayScopeOf(null));",
            "      await RecentRoomsService.addOrUpdateRoom('ABC234', profileId: 'p1', relayScope: relayScopeOf(watchTestRelayBaseUrl));")
    replace("test/watch_together/watch_together_screen_test.dart",
            "      await RecentRoomsService.renameRoom('ABC234', 'Movie night', profileId: 'p1', relayScope: relayScopeOf(null));",
            "      await RecentRoomsService.renameRoom('ABC234', 'Movie night', profileId: 'p1', relayScope: relayScopeOf(watchTestRelayBaseUrl));")
    replace("test/watch_together/watch_together_screen_test.dart",
            "      expect(find.text(t.watchTogether.relayPublic), findsNothing);",
            "      expect(find.text(t.watchTogether.relayCustom(url: watchTestRelayBaseUrl)), findsNothing);")
    replace("test/watch_together/watch_together_screen_test.dart",
            "      expect(find.text('K7M-Q2X'), findsNothing, reason: 'that code belongs to the public relays');",
            "      expect(find.text('K7M-Q2X'), findsNothing, reason: 'that code belongs to a different relay');")
    replace("test/watch_together/watch_together_screen_test.dart",
            "  group('out of a room', () {",
            "  group('out of a room', () {\n    _screenTest('unconfigured relay disables room actions and hides old public rooms', (tester, world) async {\n      final provider = world.guest(profileId: 'p1', relayBaseUrl: '');\n      await RecentRoomsService.addOrUpdateRoom(FakeOwpRelay.code, profileId: 'p1', relayScope: 'public');\n      await _openScreen(tester, provider);\n      expect(find.text(t.watchTogether.relayRequired), findsOneWidget);\n      expect(_enabled(tester, t.watchTogether.createRoom), isFalse);\n      expect(_enabled(tester, t.watchTogether.joinRoom), isFalse);\n      expect(find.text('K7M-Q2X'), findsNothing);\n      expect(world.relay.sent('create'), isEmpty);\n      expect(world.relay.sent('join'), isEmpty);\n    });\n")
    replace("test/screens/settings/settings_screen_test.dart",
            "expect(find.text(t.settings.watchTogetherRelayInvalid), findsOneWidget);",
            "expect(find.text(t.watchTogether.independentRelayInvalid), findsOneWidget);")
    replace("test/watch_together/watch_together_screen_test.dart",
            "await RecentRoomsService.addOrUpdateRoom(FakeOwpRelay.code, profileId: 'p1', relayScope: relayScopeOf(null));",
            "await RecentRoomsService.addOrUpdateRoom(FakeOwpRelay.code, profileId: 'p1', relayScope: relayScopeOf(watchTestRelayBaseUrl));", expected=3)
    replace("test/test_helpers/fake_owp_relay.dart",
            "    relays: owp.Relays.at('http://relay.test'),",
            "    relays: relays,")
    replace("test/screens/settings/settings_screen_test.dart",
            "    await tester.enterText(find.byType(TextField), 'ws://opaque-user@relay.example.test/path?wrong=route');",
            "    await tester.enterText(find.byType(TextField), 'https://eu.relay.openwatch.party');")


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
    channel = "android/app/src/main/kotlin/com/edde746/plezy/AppUpdateChannel.kt"
    replace(channel, "Allow installs from Plezy in Android settings",
            f"Allow installs from {APP_NAME} in Android settings")
    replace(channel, 'ClipData.newRawUri("Plezy update", uri)',
            f'ClipData.newRawUri("{APP_NAME} update", uri)')
    update_test = "test/services/update_service_test.dart"
    # GitHub-facing discovery uses the numeric version, distinct from Android's version code.
    replace(update_test, "      ('v2.23.0+android.1', false),",
            "      ('v2.23.0+android.1', false),\n"
            "      ('v2.23.0+android.2', false),")
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
    rebrand_media_server_identity()
    isolate_watch_together_relays()
    for name, dimensions in (("sundock_launcher", (108, 108, 100)), ("sundock_tv_banner", (320, 180, 178))):
        output = Path("android/app/src/main/res/drawable") / f"{name}.xml"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(drawable(*dimensions))


if __name__ == "__main__":
    apply_identity()
