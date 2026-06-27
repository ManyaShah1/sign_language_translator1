import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import '../../services/websocket_service.dart';
import '../../services/camera_service.dart';
import '../../widgets/camera_viewport.dart';
import '../../widgets/translation_panel.dart';


class TranslatorTab extends StatefulWidget {
  final List<CameraDescription> cameras;
  const TranslatorTab({super.key, required this.cameras});

  @override
  State<TranslatorTab> createState() => _TranslatorTabState();
}

class _TranslatorTabState extends State<TranslatorTab> {
  late WebSocketService _webSocketService;
  final CameraService _cameraService = CameraService();
  final TextEditingController serverIpController = TextEditingController(text: "ws://192.168.1.42:8768");


  String _currentTranslation = "System ready. Press Connect and start signing.";
  String _translationStatus = "Idle";
  double _confidence = 0.0;
  double _velocity = 0.0;
  double _fps = 0.0;
  int _fpsCount = 0;

  List<Map<String, double>> _simulatedHandPoints = [];
  final List<String> _translationHistory = [];
  String _activeTranslationMode = "spelling";

  Timer? _fpsTimer;
  bool _isStreaming = false;
  bool _isDisposed = false;

  @override
  void initState() {
    super.initState();
    _webSocketService = WebSocketService(
      onTranslationReceived: (trans, conf, status, vel) {
        if (!mounted || _isDisposed) return;
        setState(() {
          _currentTranslation = trans;
          _confidence = conf;
          _translationStatus = status;
          _velocity = vel;
          if (status.contains("Finalized") || status.contains("Completed")) {
            _translationHistory.insert(0, "${DateTime.now().hour.toString().padLeft(2, '0')}:${DateTime.now().minute.toString().padLeft(2, '0')} - $trans");
          }
        });
      },
      onDisconnected: (reason) {
        if (mounted && !_isDisposed) {
          setState(() => _currentTranslation = reason);
        }
      },
      onPacketSent: () {
        if (mounted && !_isDisposed) {
          setState(() => _fpsCount++);
        }
      },
    );


    _initializeHardwareCamera();


    _fpsTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _fps = _fpsCount.toDouble();
        _fpsCount = 0;
      });
    });
  }

  void _initializeHardwareCamera() {
    if (kIsWeb) {
      // Bypassed on Web: JS MediaPipe will manage camera initialization directly
      return;
    }
    _cameraService.initialize(widget.cameras, () {
      setState(() {});
      _manageImageStreamingPipeline();
    }, (image) {});
  }

  void _manageImageStreamingPipeline() {
    if (_cameraService.controller == null || !_cameraService.isInitialized) return;

    if (_isStreaming) return;
    _isStreaming = true;

    _cameraService.controller!.startImageStream((image) async {
      if (_cameraService.isProcessingFrame) return;

      final int sensorOrientation = _cameraService.controller!.description.sensorOrientation;
      final List<Map<String, double>> points = await _cameraService.processLiveFrame(image, sensorOrientation);

      if (mounted && !_isDisposed) {
        setState(() {
          _simulatedHandPoints = points;
        });

        if (_webSocketService.isConnected) {
          final int packetId = DateTime.now().millisecondsSinceEpoch;
          final payload = {
            "type": "coordinates",
            "mode": _activeTranslationMode,
            "timestamp": packetId,
            "landmarks": points,
          };
          _webSocketService.sendRawPayload(payload);
        }
      }
    });
  }


  void _clearTranslationBuffer() {
    setState(() {
      _currentTranslation = "";
    });
    if (_webSocketService.isConnected) {
      _webSocketService.sendRawPayload({"type": "clear_buffer"});
    }
  }

  void _backspaceTranslationBuffer() {
    if (_webSocketService.isConnected) {
      _webSocketService.sendRawPayload({"type": "backspace"});
    }
  }

  void _spaceTranslationBuffer() {
    if (_webSocketService.isConnected) {
      _webSocketService.sendRawPayload({"type": "space"});
    }
  }

  @override
  Widget build(BuildContext context) {
    final bool isDark = Theme.of(context).brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildHeroBanner(),
        const SizedBox(height: 24),
        _buildConfigCard(isDark),

        const SizedBox(height: 24),
        LayoutBuilder(
          builder: (context, constraints) {
            return constraints.maxWidth > 900
                ? Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 5, child: CameraViewport(cameraService: _cameraService, simulatedPoints: _simulatedHandPoints, fps: _fps, packetsSent: _webSocketService.packetsSent, isConnected: _webSocketService.isConnected, onWebLandmarks: _handleWebLandmarks, activeMode: _activeTranslationMode, onModeChanged: (mode) => setState(() => _activeTranslationMode = mode))),
                const SizedBox(width: 24),
                Expanded(flex: 4, child: TranslationPanel(currentTranslation: _currentTranslation, confidence: _confidence, status: _translationStatus, history: _translationHistory, latency: _webSocketService.serverLatency, fps: _fps, packetsSent: _webSocketService.packetsSent, packetsRecv: _webSocketService.packetsReceived, velocity: _velocity, onClear: _clearTranslationBuffer, onBackspace: _backspaceTranslationBuffer, onSpace: _spaceTranslationBuffer)),
              ],
            )
                : Column(
              children: [
                CameraViewport(cameraService: _cameraService, simulatedPoints: _simulatedHandPoints, fps: _fps, packetsSent: _webSocketService.packetsSent, isConnected: _webSocketService.isConnected, onWebLandmarks: _handleWebLandmarks, activeMode: _activeTranslationMode, onModeChanged: (mode) => setState(() => _activeTranslationMode = mode)),
                const SizedBox(height: 24),
                TranslationPanel(currentTranslation: _currentTranslation, confidence: _confidence, status: _translationStatus, history: _translationHistory, latency: _webSocketService.serverLatency, fps: _fps, packetsSent: _webSocketService.packetsSent, packetsRecv: _webSocketService.packetsReceived, velocity: _velocity, onClear: _clearTranslationBuffer, onBackspace: _backspaceTranslationBuffer, onSpace: _spaceTranslationBuffer),
              ],
            );
          },
        ),
      ],
    );
  }

  Widget _buildHeroBanner() {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: const Color(0xff18b8b5),
        borderRadius: BorderRadius.circular(25),
        boxShadow: [
          BoxShadow(
            color: const Color(0xff18b8b5).withOpacity(0.3),
            blurRadius: 15,
            offset: const Offset(0, 8),
          )
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.2),
              borderRadius: BorderRadius.circular(15),
            ),
            child: const Text(
              "Local Inference Architecture",
              style: TextStyle(
                color: Colors.white,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            "100% Free & Unlimited Translation",
            style: TextStyle(
              color: Colors.white,
              fontSize: 26,
              fontWeight: FontWeight.w600,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            "Extract arm/hand skeleton coordinate arrays locally, then stream them to a local server to translate continuous ASL sentences. No cloud latency, no subscription bills, no limits.",
            style: TextStyle(
              color: Color(0xffddf5f4),
              fontSize: 14,
              fontWeight: FontWeight.w300,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConfigCard(bool isDark) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isDark ? const Color(0xff242424) : Colors.black.withOpacity(0.05),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: serverIpController,
              enabled: !_webSocketService.isConnected && !_webSocketService.isConnecting,
              decoration: InputDecoration(
                labelText: "Local Inference Server Address",
                labelStyle: const TextStyle(color: Color(0xff18b8b5)),
                hintText: "ws://192.168.1.42:8768",
                prefixIcon: const Icon(Icons.lan, color: Color(0xff18b8b5)),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(15),
                  borderSide: BorderSide(
                    color: const Color(0xff18b8b5).withOpacity(0.4),
                  ),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(15),
                  borderSide: const BorderSide(color: Color(0xff18b8b5), width: 2),
                ),
              ),
            ),
          ),
          const SizedBox(width: 16),
          ElevatedButton(
            onPressed: _webSocketService.isConnecting
                ? null
                : (_webSocketService.isConnected
                    ? () {
                        _webSocketService.disconnect("Disconnected by user.");
                        setState(() {});
                      }
                    : () {
                        _webSocketService.connect(serverIpController.text);
                        setState(() {});
                      }),
            style: ElevatedButton.styleFrom(
              backgroundColor: _webSocketService.isConnected ? Colors.red : const Color(0xff18b8b5),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(15),
              ),
              elevation: 0,
            ),
            child: _webSocketService.isConnecting
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                  )
                : Text(
                    _webSocketService.isConnected ? "Disconnect" : "Connect",
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
          ),
        ],
      ),
    );
  }

  void _handleWebLandmarks(String jsonLandmarks) {
    if (!mounted || _isDisposed) return;
    try {
      final dynamic decoded = json.decode(jsonLandmarks);
      
      // Check for webcam errors returned by JS MediaPipe client
      if (decoded is Map && decoded.containsKey("error")) {
        setState(() {
          _currentTranslation = "Webcam Error: ${decoded["message"] ?? "Access denied"}";
          _translationStatus = "Error";
        });
        return;
      }
      
      final List<dynamic> landmarkList = decoded as List<dynamic>;
      final List<Map<String, double>> points = landmarkList.map((item) {
        return {
          "x": (item["x"] as num).toDouble(),
          "y": (item["y"] as num).toDouble(),
          "z": (item["z"] as num).toDouble(),
        };
      }).toList();

      setState(() {
        _fpsCount++;
      });

      if (_webSocketService.isConnected) {
        final int packetId = DateTime.now().millisecondsSinceEpoch;
        final payload = {
          "type": "coordinates",
          "mode": _activeTranslationMode,
          "timestamp": packetId,
          "landmarks": points,
        };
        _webSocketService.sendRawPayload(payload);
      }
    } catch (e) {
      debugPrint("Error parsing web landmarks: $e");
    }
  }

  @override
  void dispose() {
    _isDisposed = true;
    _fpsTimer?.cancel();
    _webSocketService.disconnect("Dashboard context exit.");
    _cameraService.dispose();
    serverIpController.dispose();
    super.dispose();
  }
}