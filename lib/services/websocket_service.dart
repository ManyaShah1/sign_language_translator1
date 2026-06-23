import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class WebSocketService {
  WebSocketChannel? _channel;
  StreamSubscription? _listener;
  Timer? _streamTimer;

  bool isConnected = false;
  bool isConnecting = false;

  final Map<int, DateTime> sentTimestamps = {};
  int packetsSent = 0;
  int packetsReceived = 0;
  int serverLatency = 0;

  // Callbacks to pass state up to the UI view model or view
  final Function(String message, double confidence, String status, double velocity) onTranslationReceived;
  final Function(String disconnectReason) onDisconnected;
  final Function() onPacketSent;

  WebSocketService({
    required this.onTranslationReceived,
    required this.onDisconnected,
    required this.onPacketSent,
  });

  void connect(String url) {
    if (isConnected || isConnecting) return;
    isConnecting = true;

    try {
      _channel = WebSocketChannel.connect(Uri.parse(url));

      _listener = _channel!.stream.listen(
            (message) => _handleIncomingMessage(message),
        onDone: () => disconnect("Connection closed by server."),
        onError: (error) => disconnect("Failed to connect to inference server."),
      );

      _channel!.sink.add(json.encode({"type": "ping"}));
      isConnected = true;
      isConnecting = false;
    } catch (e) {
      disconnect("Connection error: $e");
    }
  }

  void startStreamingCoordinates(List<Map<String, double>> Function() getCurrentLandmarks) {
    _streamTimer?.cancel();
    _streamTimer = Timer.periodic(const Duration(milliseconds: 33), (timer) {
      if (!isConnected) {
        timer.cancel();
        return;
      }

      final List<Map<String, double>> landmarks = getCurrentLandmarks();
      final int packetId = DateTime.now().millisecondsSinceEpoch;
      sentTimestamps[packetId] = DateTime.now();

      final payload = {
        "type": "coordinates",
        "timestamp": packetId,
        "landmarks": landmarks,
      };

      try {
        _channel!.sink.add(json.encode(payload));
        packetsSent++;
        onPacketSent();
      } catch (e) {
        debugPrint("Error sending frame packet: $e");
      }
    });
  }

  void sendPresetGesture(String gestureName, int index) {
    if (!isConnected) return;
    final int packetId = DateTime.now().millisecondsSinceEpoch;
    sentTimestamps[packetId] = DateTime.now();

    final payload = {
      "type": "gesture_select",
      "timestamp": packetId,
      "gesture": gestureName,
      "index": index
    };
    _channel!.sink.add(json.encode(payload));
  }

  void _handleIncomingMessage(dynamic message) {
    try {
      final data = json.decode(message);
      if (data["type"] == "translation_result") {
        packetsReceived++;
        final String translation = data["translation"] ?? "";
        final double confidence = (data["confidence"] as num?)?.toDouble() ?? 0.0;
        final String status = data["status"] ?? "Translating";
        final double velocity = (data["velocity"] as num?)?.toDouble() ?? 0.0;

        final int? originalTimestamp = data["timestamp"];
        if (originalTimestamp != null && sentTimestamps.containsKey(originalTimestamp)) {
          serverLatency = DateTime.now().difference(sentTimestamps[originalTimestamp]!).inMilliseconds;
          sentTimestamps.remove(originalTimestamp);
        }

        onTranslationReceived(translation, confidence, status, velocity);
      }
    } catch (e) {
      debugPrint("Error parsing incoming socket message: $e");
    }
  }

  void sendRawPayload(Map<String, dynamic> payload) {
    if (!isConnected || _channel == null) return;
    try {
      _channel!.sink.add(json.encode(payload));
      packetsSent++;
      onPacketSent();
    } catch (e) {
      debugPrint("Error sending raw payload: $e");


    }
  }

  void disconnect(String reason) {
    _streamTimer?.cancel();
    _listener?.cancel();
    _channel?.sink.close();
    isConnected = false;
    isConnecting = false;
    onDisconnected(reason);
  }
}
