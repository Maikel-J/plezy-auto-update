import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

/// A standalone (not an AAB or split APK set) GitHub release asset.
class AndroidUpdateAsset {
  final Uri url;
  final int size;
  final String? sha256Digest;

  const AndroidUpdateAsset({required this.url, required this.size, this.sha256Digest});

  static AndroidUpdateAsset? select(List<dynamic> assets, List<String> abis, String repository) {
    // Exact names avoid accidentally selecting another ABI, a debug APK, or a
    // bundle that Android cannot install on its own. Prefer the device ABI order.
    for (final name in [...abis.map((abi) => 'plezy-android-$abi.apk'), 'plezy-android-universal.apk']) {
      for (final asset in assets.whereType<Map>()) {
        if (asset['name'] != name) continue;
        final downloadUrl = asset['browser_download_url'];
        if (downloadUrl is! String) continue;
        final url = Uri.tryParse(downloadUrl);
        final size = asset['size'];
        if (url == null || !isTrustedUrl(url, repository) || size is! int || size <= 0 || size > maxSize) continue;
        final digest = asset['digest'];
        if (digest != null && (digest is! String || !RegExp(r'^sha256:[a-fA-F0-9]{64}$').hasMatch(digest))) continue;
        return AndroidUpdateAsset(url: url, size: size, sha256Digest: (digest as String?)?.substring(7).toLowerCase());
      }
    }
    return null;
  }

  static const maxSize = 512 * 1024 * 1024;

  static bool isTrustedUrl(Uri url, String repository) =>
      url.scheme == 'https' &&
      url.host == 'github.com' &&
      url.port == 443 &&
      url.userInfo.isEmpty &&
      !url.hasQuery &&
      !url.hasFragment &&
      url.path.startsWith('/$repository/releases/download/') &&
      url.path.endsWith('.apk');
}

class UpdateDownloadCancelled implements Exception {}

/// One dialog owns one download. Closing it aborts the HTTP request; only a
/// complete, verified file is ever passed to Android's package installer.
class AndroidUpdateService {
  static const channel = MethodChannel('com.plezy/app_update');
  static bool _active = false;
  final http.Client _client;
  bool _cancelled = false;

  AndroidUpdateService({http.Client? client}) : _client = client ?? http.Client();

  static Future<List<String>> supportedAbis() async =>
      await channel.invokeListMethod<String>('getSupportedAbis') ?? <String>[];

  void cancel() {
    _cancelled = true;
    _client.close();
  }

  void _checkCancelled() {
    if (_cancelled) throw UpdateDownloadCancelled();
  }

  Future<void> downloadAndInstall(
    AndroidUpdateAsset asset, {
    required String repository,
    required void Function(double progress) onProgress,
  }) async {
    if (_active) {
      _client.close();
      throw StateError('An update is already in progress');
    }
    _active = true;
    File? partial;
    File? apk;
    var installerOpened = false;
    try {
      _checkCancelled();
      if (!AndroidUpdateAsset.isTrustedUrl(asset.url, repository) ||
          asset.size <= 0 ||
          asset.size > AndroidUpdateAsset.maxSize) {
        throw const FormatException('Invalid update asset');
      }
      // Ask before downloading, then continue automatically when the user
      // returns from Android's "Allow from this source" screen.
      final allowed = await channel.invokeMethod<bool>('requestInstallPermission');
      _checkCancelled();
      if (allowed != true) throw PlatformException(code: 'INSTALL_PERMISSION_DENIED');
      final directory = await channel.invokeMethod<String>('prepareUpdateDirectory');
      if (directory == null) throw StateError('Update cache unavailable');
      partial = File('$directory/update.apk.part');
      apk = File('$directory/update.apk');
      await _download(asset, partial, onProgress);
      _checkCancelled();
      await partial.rename(apk.path);
      _checkCancelled();
      await channel.invokeMethod<void>('installUpdate', {'path': apk.path});
      installerOpened = true;
    } catch (_) {
      if (_cancelled) throw UpdateDownloadCancelled();
      rethrow;
    } finally {
      _client.close();
      try {
        if (partial != null && await partial.exists()) await partial.delete();
        // Keep the completed APK until the next attempt: the external installer
        // may still be reading it after the channel method returns.
        if (!installerOpened && apk != null && await apk.exists()) await apk.delete();
      } finally {
        _active = false;
      }
    }
  }

  Future<void> _download(AndroidUpdateAsset asset, File target, void Function(double) onProgress) async {
    _checkCancelled();
    final request = http.Request('GET', asset.url);
    final response = await _client.send(request).timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) throw HttpException('APK download failed (${response.statusCode})');
    if (response.contentLength != null && response.contentLength != asset.size) {
      throw const FormatException('APK download size does not match the release');
    }
    final sink = target.openWrite();
    // Attach an error handler immediately so filesystem failures cannot become
    // unhandled async errors before close() is awaited.
    final sinkDone = sink.done;
    unawaited(sinkDone.catchError((Object _) {}));
    var received = 0;
    try {
      await for (final chunk in response.stream.timeout(const Duration(seconds: 30))) {
        _checkCancelled();
        received += chunk.length;
        if (received > asset.size) throw const FormatException('APK exceeds the release size');
        sink.add(chunk);
        // Bound memory even if storage is much slower than the network.
        await sink.flush();
        onProgress(received / asset.size);
      }
    } finally {
      await sink.close();
      await sinkDone;
    }
    if (received != asset.size) throw const FormatException('Incomplete APK download');
    if (asset.sha256Digest != null) {
      final digest = await sha256.bind(target.openRead()).first;
      if (digest.toString() != asset.sha256Digest) throw const FormatException('APK checksum mismatch');
    }
    _checkCancelled();
  }
}
