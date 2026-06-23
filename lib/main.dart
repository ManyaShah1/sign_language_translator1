import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:flutter/services.dart';
import 'hand_landmarker_stub.dart'
    if (dart.library.io) 'package:hand_landmarker/hand_landmarker.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  List<CameraDescription> cameras = [];
  try {
    cameras = await availableCameras();
  } catch (e) {
    debugPrint("Failed to initialize cameras: $e");
  }

  runApp(MyApp(cameras: cameras));
}

class MyApp extends StatefulWidget {
  final List<CameraDescription> cameras;
  const MyApp({super.key, required this.cameras});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  ThemeMode _themeMode = ThemeMode.system;

  void toggleTheme() {
    setState(() {
      _themeMode = _themeMode == ThemeMode.light ? ThemeMode.dark : ThemeMode.light;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Swayam Health - ASL Translator',
      debugShowCheckedModeBanner: false,
      themeMode: _themeMode,
      theme: ThemeData(
        brightness: Brightness.light,
        scaffoldBackgroundColor: const Color(0xffeaeaec),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff18b8b5),
          primary: const Color(0xff18b8b5),
          secondary: const Color(0xffffcc00),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        fontFamily: 'Poppins',
      ),
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xff141316),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff18b8b5),
          primary: const Color(0xff18b8b5),
          secondary: const Color(0xffffcc00),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        fontFamily: 'Poppins',
      ),
      home: TranslatorDashboard(
        cameras: widget.cameras,
        isDark: _themeMode == ThemeMode.dark,
        onThemeToggle: toggleTheme,
      ),
    );
  }
}

class TranslatorDashboard extends StatefulWidget {
  final List<CameraDescription> cameras;
  final bool isDark;
  final VoidCallback onThemeToggle;

  const TranslatorDashboard({
    super.key,
    required this.cameras,
    required this.isDark,
    required this.onThemeToggle,
  });

  @override
  State<TranslatorDashboard> createState() => _TranslatorDashboardState();
}

enum TrackingMode { simulator, cursor, cameraMotion, mediaPipe }

class _TranslatorDashboardState extends State<TranslatorDashboard> with TickerProviderStateMixin {
  // Camera variables
  CameraController? _cameraController;
  int _selectedCameraIndex = 0;
  bool _isCameraInitialized = false;
  bool _isStreaming = false;

  // WebSocket variables
  WebSocketChannel? _channel;
  bool _isConnected = false;
  bool _isConnecting = false;
  final TextEditingController _serverIpController = TextEditingController(text: "ws://localhost:8768");
  StreamSubscription? _webSocketListener;

  // Translation stats & state
  String _currentTranslation = "System ready. Press Connect and start signing.";
  String _translationStatus = "Idle";
  double _confidence = 0.0;
  double _velocity = 0.0;
  int _packetsSent = 0;
  int _packetsReceived = 0;
  int _serverLatency = 0; // in milliseconds
  double _fps = 0.0;
  
  // Timers and animations
  Timer? _fpsTimer;
  Timer? _coordinatesTimer;
  int _fpsCount = 0;
  final List<String> _translationHistory = [];
  final Map<int, DateTime> _sentTimestamps = {};

  // Swayam UI navigation
  int _activeTab = 0; // 0: Translator, 1: About Swayam Health, 2: Technical FAQ

  // Tracking details
  TrackingMode _trackingMode = TrackingMode.simulator;
  double _trackedHandX = 0.5;
  double _trackedHandY = 0.5;
  bool _isProcessingFrame = false;
  List<int>? _prevLuma;
  final GlobalKey _cameraContainerKey = GlobalKey();

  // MediaPipe details
  HandLandmarkerPlugin? _handLandmarker;
  bool _isMediaPipeSupported = false;

  // Simulation variables (for hand landmarks overlay)
  List<Map<String, double>> _simulatedHandPoints = [];
  double _simTime = 0.0;

  @override
  void initState() {
    super.initState();
    _initializeCamera();
    _startSimulatedHandTracking();
    _startPerformanceTracker();
  }

  @override
  void dispose() {
    _cameraController?.dispose();
    _webSocketListener?.cancel();
    _channel?.sink.close();
    _fpsTimer?.cancel();
    _coordinatesTimer?.cancel();
    _serverIpController.dispose();
    _handLandmarker?.dispose();
    super.dispose();
  }

  // --- CAMERA PIPELINE ---
  void _initializeCamera() async {
    if (widget.cameras.isEmpty) {
      debugPrint("No available cameras found.");
      return;
    }

    _cameraController = CameraController(
      widget.cameras[_selectedCameraIndex],
      ResolutionPreset.medium,
      enableAudio: false,
    );

    // Try to initialize native MediaPipe HandLandmarker
    try {
      _handLandmarker = HandLandmarkerPlugin.create(
        numHands: 2,
        minHandDetectionConfidence: 0.7,
        delegate: HandLandmarkerDelegate.GPU,
      );
      _isMediaPipeSupported = true;
      debugPrint("MediaPipe HandLandmarker initialized successfully.");
    } catch (e) {
      _isMediaPipeSupported = false;
      debugPrint("MediaPipe HandLandmarker initialization bypassed (unsupported platform): $e");
    }

    try {
      await _cameraController!.initialize();
      if (mounted) {
        setState(() {
          _isCameraInitialized = true;
        });
        _toggleCameraImageStream();
      }
    } catch (e) {
      debugPrint("Camera initialization failed: $e");
    }
  }

  void _toggleCamera() {
    if (widget.cameras.length < 2) return;
    setState(() {
      _isCameraInitialized = false;
      _selectedCameraIndex = (_selectedCameraIndex + 1) % widget.cameras.length;
    });
    _initializeCamera();
  }

  void _toggleCameraImageStream() {
    if (_cameraController == null || !_isCameraInitialized) {
      if (_trackingMode == TrackingMode.cameraMotion || _trackingMode == TrackingMode.mediaPipe) {
        _initializeCamera();
      }
      return;
    }
    
    if (_trackingMode == TrackingMode.cameraMotion || _trackingMode == TrackingMode.mediaPipe) {
      try {
        _cameraController!.startImageStream((CameraImage image) {
          if (_trackingMode != TrackingMode.cameraMotion && _trackingMode != TrackingMode.mediaPipe) {
            _cameraController!.stopImageStream();
            return;
          }
          if (_isProcessingFrame) return;
          _isProcessingFrame = true;
          
          if (_trackingMode == TrackingMode.mediaPipe && _isMediaPipeSupported && _handLandmarker != null) {
            _processMediaPipeFrame(image);
          } else {
            _processCameraImageFrame(image);
          }
        });
      } catch (e) {
        debugPrint("Image stream start failed: $e");
      }
    } else {
      try {
        _cameraController!.stopImageStream();
      } catch (e) {
        // ignore
      }
    }
  }

  void _processMediaPipeFrame(CameraImage image) {
    try {
      final hands = _handLandmarker!.detect(
        image,
        _cameraController!.description.sensorOrientation,
      );
      
      if (hands.isNotEmpty && mounted) {
        final List<Map<String, double>> points = [];
        for (var landmark in hands.first.landmarks) {
          points.add({
            "x": landmark.x,
            "y": landmark.y,
            "z": landmark.z,
          });
        }
        
        setState(() {
          _simulatedHandPoints = points;
          if (points.isNotEmpty) {
            _trackedHandX = points[0]["x"]!;
            _trackedHandY = points[0]["y"]!;
          }
        });
      }
    } catch (e) {
      debugPrint("Error running MediaPipe: $e");
    } finally {
      _isProcessingFrame = false;
    }
  }

  void _processCameraImageFrame(CameraImage image) {
    try {
      if (image.planes.isEmpty) {
        _isProcessingFrame = false;
        return;
      }
      
      final plane = image.planes[0];
      final bytes = plane.bytes;
      final int width = image.width;
      final int height = image.height;
      
      const int gridX = 24;
      const int gridY = 18;
      
      int stepX = width ~/ gridX;
      int stepY = height ~/ gridY;
      if (stepX < 1) stepX = 1;
      if (stepY < 1) stepY = 1;
      
      List<int> currLuma = [];
      for (int y = 0; y < gridY; y++) {
        for (int x = 0; x < gridX; x++) {
          int index = (y * stepY) * width + (x * stepX);
          if (index < bytes.length) {
            currLuma.add(bytes[index]);
          } else {
            currLuma.add(0);
          }
        }
      }
      
      if (_prevLuma != null && _prevLuma!.length == currLuma.length) {
        double sumX = 0;
        double sumY = 0;
        double totalMotion = 0;
        
        for (int i = 0; i < currLuma.length; i++) {
          int diff = (currLuma[i] - _prevLuma![i]).abs();
          if (diff > 25) { 
            int gx = i % gridX;
            int gy = i ~/ gridX;
            sumX += gx * diff;
            sumY += gy * diff;
            totalMotion += diff;
          }
        }
        
        if (totalMotion > 400 && mounted) {
          double normX = (sumX / totalMotion) / gridX;
          double normY = (sumY / totalMotion) / gridY;
          
          setState(() {
            _trackedHandX = (1.0 - normX) * 0.35 + _trackedHandX * 0.65;
            _trackedHandY = normY * 0.35 + _trackedHandY * 0.65;
          });
        }
      }
      
      _prevLuma = currLuma;
    } catch (e) {
      debugPrint("Error in frame analysis: $e");
    } finally {
      _isProcessingFrame = false;
    }
  }

  void _updatePointerCoordinates(Offset localPosition) {
    final RenderBox? renderBox = _cameraContainerKey.currentContext?.findRenderObject() as RenderBox?;
    if (renderBox != null) {
      final size = renderBox.size;
      setState(() {
        _trackedHandX = (localPosition.dx / size.width).clamp(0.0, 1.0);
        _trackedHandY = (localPosition.dy / size.height).clamp(0.0, 1.0);
      });
    }
  }

  // --- WEBSOCKET COMMUNICATION ---
  void _connectWebSocket() {
    if (_isConnected || _isConnecting) return;

    setState(() {
      _isConnecting = true;
      _currentTranslation = "Connecting to local inference server...";
    });

    try {
      _channel = WebSocketChannel.connect(Uri.parse(_serverIpController.text));
      
      _webSocketListener = _channel!.stream.listen(
        (message) {
          _handleWebSocketMessage(message);
        },
        onDone: () {
          _handleDisconnect("Connection closed by server.");
        },
        onError: (error) {
          _handleDisconnect("Failed to connect: Ensure server is running at ${_serverIpController.text}");
        },
      );

      // Verify connection by sending a ping
      _channel!.sink.add(json.encode({"type": "ping"}));
      
      setState(() {
        _isConnected = true;
        _isConnecting = false;
        _currentTranslation = "Connected to inference server. Start signing!";
        _translationStatus = "Connected";
      });
      
      _startDataStreaming();
    } catch (e) {
      _handleDisconnect("Connection error: $e");
    }
  }

  void _disconnectWebSocket() {
    _channel?.sink.close();
    _handleDisconnect("Disconnected by user.");
  }

  void _handleDisconnect(String reason) {
    _webSocketListener?.cancel();
    _coordinatesTimer?.cancel();
    setState(() {
      _isConnected = false;
      _isConnecting = false;
      _isStreaming = false;
      _translationStatus = "Disconnected";
      _currentTranslation = reason;
      _confidence = 0.0;
    });
  }

  void _handleWebSocketMessage(dynamic message) {
    try {
      final data = json.decode(message);
      final msgType = data["type"];

      if (msgType == "pong") {
        debugPrint("[WS] Pong received.");
      } else if (msgType == "translation_result") {
        setState(() {
          _packetsReceived++;
          _currentTranslation = data["translation"] ?? "";
          _confidence = (data["confidence"] as num?)?.toDouble() ?? 0.0;
          _translationStatus = data["status"] ?? "Translating";
          _velocity = (data["velocity"] as num?)?.toDouble() ?? 0.0;

          // Latency Calculation
          final int? originalTimestamp = data["timestamp"];
          if (originalTimestamp != null && _sentTimestamps.containsKey(originalTimestamp)) {
            final sentTime = _sentTimestamps[originalTimestamp]!;
            _serverLatency = DateTime.now().difference(sentTime).inMilliseconds;
            // Clean up old timestamps to prevent leak
            _sentTimestamps.remove(originalTimestamp);
          }

          // Add to history if stabilized
          if (_translationStatus.contains("Finalized") || _translationStatus.contains("Completed")) {
            if (_translationHistory.isEmpty || _translationHistory.first != _currentTranslation) {
              _translationHistory.insert(0, "${DateTime.now().hour.toString().padLeft(2, '0')}:${DateTime.now().minute.toString().padLeft(2, '0')} - $_currentTranslation");
              if (_translationHistory.length > 10) {
                _translationHistory.removeLast();
              }
            }
          }
        });
      }
    } catch (e) {
      debugPrint("Error parsing websocket message: $e");
    }
  }

  // --- LANDMARK COORDINATES STREAMING ---
  void _startDataStreaming() {
    _coordinatesTimer?.cancel();
    
    // Stream coordinates at 30 FPS (~33ms intervals)
    _coordinatesTimer = Timer.periodic(const Duration(milliseconds: 33), (timer) {
      if (!_isConnected) {
        timer.cancel();
        return;
      }

      // 1. Generate Coordinates (MediaPipe output simulator)
      final List<Map<String, double>> landmarks = _getCurrentLandmarks();
      
      // 2. Wrap and send to Local Python Inference Server
      final int packetId = DateTime.now().millisecondsSinceEpoch;
      _sentTimestamps[packetId] = DateTime.now();

      final payload = {
        "type": "coordinates",
        "timestamp": packetId,
        "landmarks": landmarks,
      };

      try {
        _channel!.sink.add(json.encode(payload));
        _fpsCount++;
        setState(() {
          _packetsSent++;
          _isStreaming = true;
        });
      } catch (e) {
        debugPrint("Error sending packet: $e");
      }
    });
  }

  // Generate real/mock coordinates depending on setup
  List<Map<String, double>> _getCurrentLandmarks() {
    // We generate standard 21-landmark hand configuration coordinates.
    // In a full ML implementation, these points are populated via native MediaPipe/MLKit integration.
    // Since we want this to be 100% stable across all platforms, we simulate a hand gesture path.
    return _simulatedHandPoints;
  }

  // Simulation engine to create realistic movement trajectories
  void _startSimulatedHandTracking() {
    Timer.periodic(const Duration(milliseconds: 30), (timer) {
      _simTime += 0.05;
      
      // Simulate 21 hand joints using mathematical paths
      final List<Map<String, double>> joints = [];
      
      double wristX;
      double wristY;
      
      if (_trackingMode == TrackingMode.simulator) {
        wristX = 0.5 + 0.15 * math.sin(_simTime * 1.2);
        wristY = 0.6 + 0.10 * math.cos(_simTime * 0.8);
      } else {
        wristX = _trackedHandX;
        wristY = _trackedHandY;
      }
      
      double wristZ = 0.0 + 0.05 * math.sin(_simTime * 2.0);
      joints.add({"x": wristX, "y": wristY, "z": wristZ});
      
      // Simulate 5 fingers (4 joints each) branching from wrist
      for (int f = 0; f < 5; f++) {
        double angle = -0.5 + (f * 0.25); // finger spread angle
        double length = 0.06;
        
        double prevX = wristX;
        double prevY = wristY;
        double prevZ = wristZ;
        
        for (int j = 0; j < 4; j++) {
          // Add rhythmic joint curl simulation
          double curl = math.sin(_simTime * 1.5 + f * 0.5) * 0.08;
          double jointX = prevX + length * math.sin(angle + curl);
          double jointY = prevY - length * math.cos(angle + curl);
          double jointZ = prevZ + 0.01 * math.sin(_simTime + j);
          
          joints.add({"x": jointX, "y": jointY, "z": jointZ});
          prevX = jointX;
          prevY = jointY;
          prevZ = jointZ;
        }
      }

      if (mounted) {
        setState(() {
          _simulatedHandPoints = joints;
        });
      }
    });
  }

  // Trigger preset gestures instantly to the server for fast verification
  void _simulatePresetGesture(String gestureName, int index) {
    if (!_isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Please connect the local server first!"),
          backgroundColor: Color(0xff18b8b5),
        ),
      );
      return;
    }

    final int packetId = DateTime.now().millisecondsSinceEpoch;
    final payload = {
      "type": "gesture_select",
      "timestamp": packetId,
      "gesture": gestureName,
      "index": index
    };
    
    _sentTimestamps[packetId] = DateTime.now();
    _channel!.sink.add(json.encode(payload));
  }

  void _startPerformanceTracker() {
    _fpsTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          _fps = _fpsCount.toDouble();
          _fpsCount = 0;
        });
      }
    });
  }

  // --- UI WIDGET BUILDERS ---

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 1. Navigation Header (Swayam Styled)
                _buildHeader(isDark),
                const SizedBox(height: 20),

                // 2. Active Tab View
                if (_activeTab == 0) _buildTranslatorTab(isDark)
                else if (_activeTab == 1) _buildAboutTab(isDark)
                else _buildFaqTab(isDark),

                const SizedBox(height: 40),
                // 3. Footer
                _buildFooter(isDark),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // Beautiful header with Swayam brand styles
  Widget _buildHeader(bool isDark) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(25),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.04),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Brand Logo / Title
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: const BoxDecoration(
                  color: Color(0xff18b8b5),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.gesture,
                  color: Colors.white,
                  size: 20,
                ),
              ),
              const SizedBox(width: 10),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  RichText(
                    text: TextSpan(
                      text: "swayam",
                      style: TextStyle(
                        fontFamily: 'Poppins',
                        fontWeight: FontWeight.w600,
                        fontSize: 18,
                        color: isDark ? Colors.white : const Color(0xff242424),
                      ),
                      children: const [
                        TextSpan(
                          text: "health",
                          style: TextStyle(
                            color: Color(0xff18b8b5),
                            fontWeight: FontWeight.w300,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Text(
                    "ASL local translation",
                    style: TextStyle(
                      fontSize: 10,
                      color: Colors.grey,
                      fontWeight: FontWeight.w400,
                    ),
                  )
                ],
              ),
            ],
          ),

          // Tabs Options (Desktop-like Nav)
          Row(
            children: [
              _buildTabButton("Translate", 0),
              const SizedBox(width: 8),
              _buildTabButton("About Kiosk", 1),
              const SizedBox(width: 8),
              _buildTabButton("Local FAQ", 2),
            ],
          ),

          // Theme / Settings toggles
          Row(
            children: [
              IconButton(
                icon: Icon(widget.isDark ? Icons.light_mode : Icons.dark_mode),
                onPressed: widget.onThemeToggle,
                color: const Color(0xff18b8b5),
              ),
              const SizedBox(width: 5),
              // Server status pill
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: _isConnected
                      ? const Color(0xff18b8b5).withOpacity(0.15)
                      : Colors.red.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: _isConnected ? const Color(0xff18b8b5) : Colors.red,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      _isConnected ? "ONLINE" : "OFFLINE",
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: _isConnected ? const Color(0xff18b8b5) : Colors.red,
                      ),
                    )
                  ],
                ),
              ),
            ],
          )
        ],
      ),
    );
  }

  Widget _buildTabButton(String label, int index) {
    bool isActive = _activeTab == index;
    return InkWell(
      onTap: () => setState(() => _activeTab = index),
      borderRadius: BorderRadius.circular(15),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xff18b8b5).withOpacity(0.1) : Colors.transparent,
          borderRadius: BorderRadius.circular(15),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
            color: isActive ? const Color(0xff18b8b5) : Colors.grey,
          ),
        ),
      ),
    );
  }

  Widget _buildTrackingModeSelector(bool isDark) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isDark ? const Color(0xff242424) : Colors.black.withOpacity(0.05),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.tune, color: Color(0xff18b8b5), size: 20),
              const SizedBox(width: 8),
              Text(
                "Landmark Input Source",
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                  color: isDark ? Colors.white : const Color(0xff242424),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            "Choose how hand landmarks are extracted. Live Camera Motion tracks the physical hand centroid in front of your camera in real time.",
            style: TextStyle(
              fontSize: 11,
              color: Colors.grey.shade500,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _buildModeButton(
                  "Virtual Auto-Wave",
                  TrackingMode.simulator,
                  Icons.smart_toy_outlined,
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _buildModeButton(
                  "Interactive Touch",
                  TrackingMode.cursor,
                  Icons.touch_app_outlined,
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _buildModeButton(
                  "Live Camera Motion",
                  TrackingMode.cameraMotion,
                  Icons.motion_photos_on_outlined,
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _buildModeButton(
                  "Live MediaPipe Tracking",
                  TrackingMode.mediaPipe,
                  Icons.fingerprint,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildModeButton(String label, TrackingMode mode, IconData icon) {
    bool isActive = _trackingMode == mode;
    return InkWell(
      onTap: () {
        setState(() {
          _trackingMode = mode;
          _toggleCameraImageStream();
        });
      },
      borderRadius: BorderRadius.circular(15),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xff18b8b5).withOpacity(0.12) : Colors.transparent,
          borderRadius: BorderRadius.circular(15),
          border: Border.all(
            color: isActive ? const Color(0xff18b8b5) : Colors.grey.withOpacity(0.2),
            width: isActive ? 1.5 : 1.0,
          ),
        ),
        child: Column(
          children: [
            Icon(
              icon,
              color: isActive ? const Color(0xff18b8b5) : Colors.grey,
              size: 22,
            ),
            const SizedBox(height: 8),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 10,
                fontWeight: isActive ? FontWeight.bold : FontWeight.w500,
                color: isActive ? const Color(0xff18b8b5) : Colors.grey,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // --- TAB 1: TRANSLATOR WORKSPACE ---
  Widget _buildTranslatorTab(bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Hero Banner
        _buildHeroBanner(isDark),
        const SizedBox(height: 24),

        // Settings / IP Input card
        _buildConnectionConfig(isDark),
        const SizedBox(height: 24),

        // Tracking Mode Selection
        _buildTrackingModeSelector(isDark),
        const SizedBox(height: 24),

        // Main translation viewport layout
        LayoutBuilder(
          builder: (context, constraints) {
            bool isDesktop = constraints.maxWidth > 900;
            return isDesktop
                ? Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(flex: 5, child: _buildCameraContainer(isDark)),
                      const SizedBox(width: 24),
                      Expanded(flex: 4, child: _buildTranslationPanel(isDark)),
                    ],
                  )
                : Column(
                    children: [
                      _buildCameraContainer(isDark),
                      const SizedBox(height: 24),
                      _buildTranslationPanel(isDark),
                    ],
                  );
          },
        ),

        const SizedBox(height: 24),
        // Interactive preset gesture triggers for easy testing
        _buildGestureTestingPanel(isDark),
      ],
    );
  }

  Widget _buildHeroBanner(bool isDark) {
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

  Widget _buildConnectionConfig(bool isDark) {
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
              controller: _serverIpController,
              enabled: !_isConnected && !_isConnecting,
              decoration: InputDecoration(
                labelText: "Local Inference Server Address",
                labelStyle: const TextStyle(color: Color(0xff18b8b5)),
                hintText: "ws://localhost:8765",
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
            onPressed: _isConnecting
                ? null
                : (_isConnected ? _disconnectWebSocket : _connectWebSocket),
            style: ElevatedButton.styleFrom(
              backgroundColor: _isConnected ? Colors.red : const Color(0xff18b8b5),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(15),
              ),
              elevation: 0,
            ),
            child: _isConnecting
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                  )
                : Text(
                    _isConnected ? "Disconnect" : "Connect",
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildCameraContainer(bool isDark) {
    return GestureDetector(
      key: _cameraContainerKey,
      onPanUpdate: (details) {
        if (_trackingMode == TrackingMode.cursor) {
          _updatePointerCoordinates(details.localPosition);
        }
      },
      onPanDown: (details) {
        if (_trackingMode == TrackingMode.cursor) {
          _updatePointerCoordinates(details.localPosition);
        }
      },
      child: Container(
        height: 480,
        decoration: BoxDecoration(
          color: isDark ? const Color(0xff1b1a1f) : Colors.white,
          borderRadius: BorderRadius.circular(25),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.03),
              blurRadius: 12,
              offset: const Offset(0, 4),
            )
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 1. Camera Viewport or Mock Simulator
            (_isCameraInitialized && _cameraController != null)
                ? CameraPreview(_cameraController!)
                : _buildMockCameraFeedback(isDark),

            // 2. Custom Painter Landmark Overlay (MediaPipe Simulation)
            if (_isStreaming || _isConnected)
              CustomPaint(
                painter: HandSkeletonPainter(
                  points: _simulatedHandPoints,
                  isDark: isDark,
                ),
              ),

            // 3. Floating Overlay Indicators
            Positioned(
              top: 16,
              left: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: _isStreaming ? const Color(0xff18b8b5) : Colors.grey,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      _trackingMode == TrackingMode.simulator
                          ? "VIRTUAL AUTO-WAVE ACTIVE"
                          : (_trackingMode == TrackingMode.cursor
                              ? "INTERACTIVE POINTER ACTIVE"
                              : "CAMERA MOTION TRACKING ACTIVE"),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Camera toggle (Front/Back)
            if (widget.cameras.length > 1)
              Positioned(
                top: 16,
                right: 16,
                child: InkWell(
                  onTap: _toggleCamera,
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.6),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.switch_camera,
                      color: Colors.white,
                      size: 18,
                    ),
                  ),
                ),
              ),

            // Stream Details Watermark
            Positioned(
              bottom: 16,
              left: 16,
              right: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.55),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      _trackingMode == TrackingMode.simulator
                          ? "Source: Virtual Wave Pattern"
                          : (_trackingMode == TrackingMode.cursor
                              ? "Source: Drag Finger/Pointer"
                              : "Source: Camera Luminance Pixel Motion"),
                      style: const TextStyle(color: Colors.white70, fontSize: 10),
                    ),
                    Text(
                      "FPS: ${_fps.toStringAsFixed(0)} | Pkts: $_packetsSent",
                      style: const TextStyle(color: Colors.white70, fontSize: 10),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMockCameraFeedback(bool isDark) {
    return Container(
      color: isDark ? const Color(0xff0d0c0e) : const Color(0xfff0f4f4),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.camera_alt_outlined,
            size: 48,
            color: const Color(0xff18b8b5).withOpacity(0.4),
          ),
          const SizedBox(height: 12),
          const Text(
            "Physical Camera Uninitialized",
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              "Using on-device simulator. Coordinates are generated dynamically using mathematical curves to allow end-to-end local inference testing.",
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey.shade500,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTranslationPanel(bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Translation display box
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xff1b1a1f) : Colors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: isDark ? const Color(0xff242424) : Colors.black.withOpacity(0.05),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    "Live Translation",
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      color: Color(0xff18b8b5),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xffffcc00).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      "Confidence: ${(_confidence * 100).toStringAsFixed(1)}%",
                      style: const TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        color: Color(0xffd4aa00),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              SelectableText(
                _currentTranslation,
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        Clipboard.setData(ClipboardData(text: _currentTranslation));
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text("Translation copied to clipboard!")),
                        );
                      },
                      icon: const Icon(Icons.copy, size: 14),
                      label: const Text("Copy"),
                      style: OutlinedButton.styleFrom(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        setState(() {
                          _currentTranslation = "System cleared. Ready for next gesture.";
                          _confidence = 0.0;
                        });
                      },
                      icon: const Icon(Icons.clear_all, size: 14),
                      label: const Text("Clear"),
                      style: OutlinedButton.styleFrom(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                ],
              )
            ],
          ),
        ),
        const SizedBox(height: 24),

        // Vitals Dashboard (inspired by Swayam Health ATM UI)
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xff18b8b5).withOpacity(0.04) : const Color(0xff18b8b5).withOpacity(0.05),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: const Color(0xff18b8b5).withOpacity(0.15),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                "Local Inference Diagnostics (Vitals)",
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                  color: Color(0xff18b8b5),
                ),
              ),
              const SizedBox(height: 16),
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 2.2,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                children: [
                  _buildVitalCard("Server Latency", "$_serverLatency ms", Icons.speed),
                  _buildVitalCard("Landmarks FPS", "${_fps.toStringAsFixed(0)} FPS", Icons.analytics_outlined),
                  _buildVitalCard("Frames Sent/Recv", "$_packetsSent / $_packetsReceived", Icons.upload_file),
                  _buildVitalCard("Movement Velocity", _velocity.toStringAsFixed(4), Icons.show_chart),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // Translation History
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xff1b1a1f) : Colors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: isDark ? const Color(0xff242424) : Colors.black.withOpacity(0.05),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                "Translation History",
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                  color: Colors.grey,
                ),
              ),
              const SizedBox(height: 12),
              _translationHistory.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Text(
                        "No history segments recorded yet.",
                        style: TextStyle(color: Colors.grey, fontSize: 12),
                      ),
                    )
                  : ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _translationHistory.length,
                      separatorBuilder: (c, idx) => const Divider(height: 12),
                      itemBuilder: (c, idx) {
                        return Text(
                          _translationHistory[idx],
                          style: TextStyle(
                            fontSize: 12,
                            color: isDark ? Colors.white70 : Colors.black87,
                          ),
                        );
                      },
                    ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildVitalCard(String label, String value, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(
          color: const Color(0xff18b8b5).withOpacity(0.1),
        ),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: const Color(0xff18b8b5)),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: const TextStyle(fontSize: 9, color: Colors.grey, overflow: TextOverflow.ellipsis),
                ),
                Text(
                  value,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGestureTestingPanel(bool isDark) {
    // Quick buttons that stream predefined coordinate flows to mock standard ASL motions.
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isDark ? const Color(0xff242424) : Colors.black.withOpacity(0.05),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.terminal, color: Color(0xff18b8b5), size: 18),
              SizedBox(width: 8),
              Text(
                "Interactive Inference Simulator",
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            "Trigger standard gesture tracks directly. These mock structural data coordinates and feed them to the local server to verify the CTC decoding sentence mapping.",
            style: TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.w300),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _buildGestureTriggerButton("Wave Hand (Greeting)", 0),
              _buildGestureTriggerButton("Medical Cross (Assistance)", 1),
              _buildGestureTriggerButton("Circle Path (Doctor Room)", 2),
              _buildGestureTriggerButton("Heart Path (Vitals Check)", 3),
              _buildGestureTriggerButton("Swipe Down (Thank You)", 4),
              _buildGestureTriggerButton("Shake Left/Right (Feeling Weak)", 5),
              _buildGestureTriggerButton("Double Loop (Health Report)", 6),
              _buildGestureTriggerButton("Thumbs Up (Finished)", 7),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildGestureTriggerButton(String name, int index) {
    return ElevatedButton(
      onPressed: () => _simulatePresetGesture(name, index),
      style: ElevatedButton.styleFrom(
        backgroundColor: const Color(0xff18b8b5).withOpacity(0.1),
        foregroundColor: const Color(0xff18b8b5),
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: Color(0xff18b8b5), width: 0.5),
        ),
      ),
      child: Text(name, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }

  // --- TAB 2: ABOUT THE SWAYAM HEALTH ECOSYSTEM ---
  Widget _buildAboutTab(bool isDark) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(25),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            "About Swayam Health ATM Kiosks",
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: Color(0xff18b8b5),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            "Empowering decentralized point-of-care medical testing & diagnostics.",
            style: TextStyle(fontSize: 14, color: Colors.grey, fontWeight: FontWeight.w300),
          ),
          const Divider(height: 32),
          
          const Text(
            "Swayam Health is the premier smart health kiosk network (Health ATMs) approved by CDSCO. It integrates a clinical-grade diagnostics suite that processes over 100 physiological metrics (blood pressure, ECG, glucose, urine, vitals) and delivers digital health reports instantly.",
            style: TextStyle(fontSize: 14, height: 1.6),
          ),
          const SizedBox(height: 24),
          
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _buildInfoCard(
                  "Swayam AHM Kiosk",
                  "Stationary diagnostic cabin deployed in public centers, offices, and clinics containing automatic testing modules.",
                  Icons.monitor_heart,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _buildInfoCard(
                  "Swandook Case",
                  "A highly portable, compact suitcase carrying critical diagnostic kits designed for remote rural checkups.",
                  Icons.business_center,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          
          const Text(
            "Integration with Sign Language",
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text(
            "By incorporating local hand-tracking and ASL sentence translation directly onto the kiosk system, non-verbal patients and deaf/mute individuals can seamlessly run diagnostics and engage in real-time telemedicine consultations without any communication barriers.",
            style: TextStyle(fontSize: 14, height: 1.6),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoCard(String title, String desc, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xff0d0c0e) : const Color(0xfff0f4f4),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xff18b8b5).withOpacity(0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 28, color: const Color(0xff18b8b5)),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
          const SizedBox(height: 8),
          Text(desc, style: const TextStyle(fontSize: 12, color: Colors.grey, height: 1.5)),
        ],
      ),
    );
  }

  // --- TAB 3: LOCAL INFERENCE TECHNICAL FAQ ---
  Widget _buildFaqTab(bool isDark) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(25),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            "Technical FAQ & Architecture",
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: Color(0xff18b8b5),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            "Understanding the 100% free, local machine learning translation stack.",
            style: TextStyle(fontSize: 14, color: Colors.grey, fontWeight: FontWeight.w300),
          ),
          const Divider(height: 32),

          _buildFaqItem(
            "Why use Local Inference instead of commercial APIs?",
            "Cloud-based sign language models charge high rates per minute of video feed and enforce strict limits. By running model inference on your local hardware (or a dedicated on-site server), we ensure the translator remains 100% free, private, and unlimited.",
          ),
          _buildFaqItem(
            "How does the Flutter app connect to the Python server?",
            "The Flutter app initializes a WebSocket connection (using `web_socket_channel`) to a local Python daemon running on port 8765. The app continuously streams lightweight hand-coordinate JSON payloads (21 keypoints * X/Y/Z) at 30 packets per second, causing negligible network overhead.",
          ),
          _buildFaqItem(
            "What is a CTC Network and how does it translate sentences?",
            "A Connectionist Temporal Classification (CTC) network is a type of neural network output layer designed for sequence tasks (like speech or sign language). Unlike simple letter classifiers, a continuous CTC model evaluates frames over a temporal timeline, capturing dynamic transitions between signs to output cohesive English sentences.",
          ),
          _buildFaqItem(
            "How do I setup and execute the Python Server?",
            "Navigate to the `python_server/` directory and run 'pip install websockets' followed by 'python server.py'. This sets up the WebSocket endpoint. You can view input streams and model prediction reports directly in your shell terminal.",
          ),
        ],
      ),
    );
  }

  Widget _buildFaqItem(String question, String answer) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: widget.isDark ? const Color(0xff1c1b22) : const Color(0xffeaeaec).withOpacity(0.5),
          borderRadius: BorderRadius.circular(15),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              question,
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Color(0xff18b8b5)),
            ),
            const SizedBox(height: 8),
            Text(
              answer,
              style: TextStyle(
                fontSize: 13,
                height: 1.5,
                color: widget.isDark ? Colors.white70 : Colors.black87,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFooter(bool isDark) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.shield, size: 14, color: const Color(0xff18b8b5).withOpacity(0.6)),
              const SizedBox(width: 6),
              const Text(
                "Secure, Private, Local Machine Learning System",
                style: TextStyle(fontSize: 10, color: Colors.grey, fontWeight: FontWeight.w400),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            "© ${DateTime.now().year} Sanskritech Smart Solutions. Swayam Health Ecosystem.",
            style: const TextStyle(fontSize: 10, color: Colors.grey),
          ),
        ],
      ),
    );
  }
}

// --- CUSTOM PAINTER: OVERLAYS SKELETON POINTS ---
class HandSkeletonPainter extends CustomPainter {
  final List<Map<String, double>> points;
  final bool isDark;

  HandSkeletonPainter({required this.points, required this.isDark});

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;

    final paintJoint = Paint()
      ..color = const Color(0xffffcc00)
      ..style = PaintingStyle.fill;

    final paintLine = Paint()
      ..color = const Color(0xff18b8b5)
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    // Convert normalized [0, 1] coordinates to viewport coordinates
    List<Offset> offsets = [];
    List<double> scales = [];
    for (var pt in points) {
      double x = pt["x"] ?? 0.0;
      double y = pt["y"] ?? 0.0;
      double z = pt["z"] ?? 0.0;
      double scale = 1.0 + (z * 0.5);
      offsets.add(Offset(x * size.width, y * size.height));
      scales.add(scale);
    }

    // 1. Draw connections (skeleton segments)
    // Hand model: joint 0 is wrist. Fingers 1-5, each having 4 joints.
    // Indexing: 
    // Wrist: 0
    // Finger 1 (Thumb): 1,2,3,4
    // Finger 2 (Index): 5,6,7,8
    // Finger 3 (Middle): 9,10,11,12
    // Finger 4 (Ring): 13,14,15,16
    // Finger 5 (Pinky): 17,18,19,20
    
    // Connect fingers to wrist
    for (int f = 0; f < 5; f++) {
      int baseIdx = 1 + f * 4;
      if (offsets.length > baseIdx) {
        canvas.drawLine(offsets[0], offsets[baseIdx], paintLine);
      }
      
      // Connect joints within each finger
      for (int j = 0; j < 3; j++) {
        int idx1 = baseIdx + j;
        int idx2 = baseIdx + j + 1;
        if (offsets.length > idx2) {
          canvas.drawLine(offsets[idx1], offsets[idx2], paintLine);
        }
      }
    }

    // 2. Draw joint points
    for (int i = 0; i < offsets.length; i++) {
      final offset = offsets[i];
      final scale = scales[i];
      canvas.drawCircle(offset, 4.0 * scale, paintJoint);
      // Small outer ring for depth
      canvas.drawCircle(offset, 6.0 * scale, Paint()
        ..color = const Color(0xff18b8b5).withOpacity(0.3)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0 * scale
      );
    }
  }

  @override
  bool shouldRepaint(covariant HandSkeletonPainter oldDelegate) {
    return true; // Repaint every frame for smooth tracking animation
  }
}
