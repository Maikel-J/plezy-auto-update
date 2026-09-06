import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:plezy/services/android_update_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const repository = 'Maikel-J/plezy-auto-update';
  final url = Uri.parse('https://github.com/$repository/releases/download/v2.19.0/plezy-android-arm64-v8a.apk');
  final bytes = [1, 2, 3, 4];

  Map<String, dynamic> releaseAsset(String abi) => {
    'name': 'plezy-android-$abi.apk',
    'browser_download_url': 'https://github.com/$repository/releases/download/v2.19.0/plezy-android-$abi.apk',
    'size': 4,
    'digest': 'sha256:${sha256.convert(bytes)}',
  };

  group('release asset selection', () {
    test('selects exact APK name in the device ABI preference order', () {
      final asset = AndroidUpdateAsset.select(
        [releaseAsset('armeabi-v7a'), releaseAsset('arm64-v8a')],
        ['arm64-v8a', 'armeabi-v7a'],
        repository,
      );
      expect(asset?.url, url);
      expect(asset?.sha256Digest, sha256.convert(bytes).toString());
    });

    test('uses universal fallback but never an incompatible ABI or archive', () {
      final candidates = [releaseAsset('x86_64'), releaseAsset('universal')];
      expect(
        AndroidUpdateAsset.select(candidates, ['armeabi-v7a'], repository)?.url.path,
        endsWith('plezy-android-universal.apk'),
      );
      expect(AndroidUpdateAsset.select([releaseAsset('x86_64')], ['arm64-v8a'], repository), isNull);
      expect(
        AndroidUpdateAsset.select(
          [
            {...releaseAsset('arm64-v8a'), 'name': 'plezy-android-arm64-v8a.tar.gz'},
          ],
          ['arm64-v8a'],
          repository,
        ),
        isNull,
      );
    });

    test('rejects untrusted URLs, invalid digests, and unbounded sizes', () {
      for (final changes in <Map<String, dynamic>>[
        {'browser_download_url': 'http://github.com/$repository/releases/download/v1/a.apk'},
        {'browser_download_url': 'https://github.com/another/repo/releases/download/v1/a.apk'},
        {'browser_download_url': 'https://github.com.evil.example/$repository/releases/download/v1/a.apk'},
        {'size': 0},
        {'size': AndroidUpdateAsset.maxSize + 1},
        {'digest': 'sha256:invalid'},
      ]) {
        expect(
          AndroidUpdateAsset.select(
            [
              {...releaseAsset('arm64-v8a'), ...changes},
            ],
            ['arm64-v8a'],
            repository,
          ),
          isNull,
          reason: '$changes',
        );
      }
    });

    test('older GitHub assets without a digest still use Android signature verification', () {
      expect(
        AndroidUpdateAsset.select(
          [
            {...releaseAsset('arm64-v8a'), 'digest': null},
          ],
          ['arm64-v8a'],
          repository,
        ),
        isNotNull,
      );
    });
  });

  group('download and installer handoff', () {
    late Directory directory;
    late List<MethodCall> calls;
    var permission = true;
    PlatformException? installerError;
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

    setUp(() async {
      directory = await Directory.systemTemp.createTemp('plezy-update-test-');
      calls = [];
      permission = true;
      installerError = null;
      messenger.setMockMethodCallHandler(AndroidUpdateService.channel, (call) async {
        calls.add(call);
        switch (call.method) {
          case 'requestInstallPermission':
            return permission;
          case 'prepareUpdateDirectory':
            return directory.path;
          case 'getSupportedAbis':
            return ['arm64-v8a'];
          case 'installUpdate':
            if (installerError != null) throw installerError!;
            expect(await File(call.arguments['path'] as String).readAsBytes(), bytes);
            return null;
          default:
            fail('Unexpected channel call: ${call.method}');
        }
      });
    });

    tearDown(() async {
      messenger.setMockMethodCallHandler(AndroidUpdateService.channel, null);
      await directory.delete(recursive: true);
    });

    AndroidUpdateAsset asset({String? digest, int? size}) => AndroidUpdateAsset(
      url: url,
      size: size ?? bytes.length,
      sha256Digest: digest ?? sha256.convert(bytes).toString(),
    );

    test('reads native ABI list', () async {
      expect(await AndroidUpdateService.supportedAbis(), ['arm64-v8a']);
    });

    test('verifies download, reports progress, and retains APK for the installer', () async {
      final service = AndroidUpdateService(client: MockClient((_) async => http.Response.bytes(bytes, 200)));
      final progress = <double>[];
      await service.downloadAndInstall(asset(), repository: repository, onProgress: progress.add);
      expect(progress.last, 1);
      expect(calls.map((call) => call.method), ['requestInstallPermission', 'prepareUpdateDirectory', 'installUpdate']);
      expect(await File('${directory.path}/update.apk').exists(), isTrue);
      expect(await File('${directory.path}/update.apk.part').exists(), isFalse);
    });

    test('denied permission does not download or install', () async {
      permission = false;
      final service = AndroidUpdateService(client: MockClient((_) async => throw StateError('Must not download')));
      await expectLater(
        service.downloadAndInstall(asset(), repository: repository, onProgress: (_) {}),
        throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'INSTALL_PERMISSION_DENIED')),
      );
      expect(calls.map((call) => call.method), ['requestInstallPermission']);
    });

    for (final failure in ['http', 'truncated', 'oversized', 'checksum', 'network']) {
      test('$failure download never invokes installer and removes partial files', () async {
        final client = MockClient.streaming((_, _) async {
          if (failure == 'network') throw const SocketException('offline');
          final body = failure == 'truncated'
              ? [1]
              : failure == 'oversized'
              ? [1, 2, 3, 4, 5]
              : bytes;
          return http.StreamedResponse(Stream.value(body), failure == 'http' ? 503 : 200);
        });
        final service = AndroidUpdateService(client: client);
        await expectLater(
          service.downloadAndInstall(
            asset(digest: failure == 'checksum' ? '0' * 64 : null),
            repository: repository,
            onProgress: (_) {},
          ),
          throwsA(isA<Exception>()),
        );
        expect(calls.any((call) => call.method == 'installUpdate'), isFalse);
        expect(await directory.list().toList(), isEmpty);
      });
    }

    test('cancel during a streamed download removes partial file without installing', () async {
      late AndroidUpdateService service;
      service = AndroidUpdateService(
        client: MockClient.streaming(
          (_, _) async => http.StreamedResponse(
            Stream.fromIterable([
              [1, 2],
              [3, 4],
            ]),
            200,
          ),
        ),
      );
      await expectLater(
        service.downloadAndInstall(asset(), repository: repository, onProgress: (_) => service.cancel()),
        throwsA(isA<UpdateDownloadCancelled>()),
      );
      expect(calls.any((call) => call.method == 'installUpdate'), isFalse);
      expect(await directory.list().toList(), isEmpty);
    });

    test('native validation errors delete the APK and release the single-flight guard', () async {
      installerError = PlatformException(code: 'SIGNATURE_MISMATCH');
      final service = AndroidUpdateService(client: MockClient((_) async => http.Response.bytes(bytes, 200)));
      await expectLater(
        service.downloadAndInstall(asset(), repository: repository, onProgress: (_) {}),
        throwsA(isA<PlatformException>()),
      );
      expect(await directory.list().toList(), isEmpty);
      installerError = null;
      final retry = AndroidUpdateService(client: MockClient((_) async => http.Response.bytes(bytes, 200)));
      await retry.downloadAndInstall(asset(), repository: repository, onProgress: (_) {});
      expect(await File('${directory.path}/update.apk').exists(), isTrue);
    });

    test('rejects overlapping update attempts', () async {
      final response = Completer<http.Response>();
      final started = Completer<void>();
      final first = AndroidUpdateService(
        client: MockClient((_) {
          started.complete();
          return response.future;
        }),
      );
      final pending = first.downloadAndInstall(asset(), repository: repository, onProgress: (_) {});
      await started.future;
      final second = AndroidUpdateService(client: MockClient((_) async => http.Response.bytes(bytes, 200)));
      await expectLater(
        second.downloadAndInstall(asset(), repository: repository, onProgress: (_) {}),
        throwsStateError,
      );
      second.cancel();
      response.complete(http.Response.bytes(bytes, 200));
      await pending;
    });
  });
}
