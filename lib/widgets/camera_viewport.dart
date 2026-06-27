import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:camera/camera.dart';
import '../../services/camera_service.dart';
import 'skeleton_painter.dart';
import 'web_camera_view.dart';

class CameraViewport extends StatelessWidget {
  final CameraService cameraService;
  final List<Map<String, double>> simulatedPoints;
  final double fps;
  final int packetsSent;
  final bool isConnected;
  final Function(String jsonLandmarks)? onWebLandmarks;
  
  // Active mode state and callback for the hybrid dual-toggle
  final String activeMode;
  final ValueChanged<String> onModeChanged;

  const CameraViewport({
    super.key,
    required this.cameraService,
    required this.simulatedPoints,
    required this.fps,
    required this.packetsSent,
    required this.isConnected,
    this.onWebLandmarks,
    required this.activeMode,
    required this.onModeChanged,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Container(
      height: 480,
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(25),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.03), blurRadius: 12, offset: const Offset(0, 4))],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          kIsWeb
              ? WebCameraView(onLandmarks: onWebLandmarks ?? (_) {})
              : (cameraService.isInitialized && cameraService.controller != null)
                  ? CameraPreview(cameraService.controller!)
                  : _buildMockCameraFeedback(isDark),
          if (simulatedPoints.isNotEmpty) CustomPaint(painter: HandSkeletonPainter(points: simulatedPoints, isDark: isDark)),
          
          // Left status label
          Positioned(
            top: 16, left: 16,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(color: Colors.black.withOpacity(0.6), borderRadius: BorderRadius.circular(12)),
              child: const Text(
                "TRACKING INTERACTIVE",
                style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
              ),
            ),
          ),
          
          // Right sliding mode toggle button
          Positioned(
            top: 12, right: 16,
            child: Container(
              padding: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.6),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildToggleTab("spelling", "Spelling Mode", activeMode == "spelling"),
                  const SizedBox(width: 4),
                  _buildToggleTab("word", "Word Mode", activeMode == "word"),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildToggleTab(String modeKey, String label, bool isActive) {
    return GestureDetector(
      onTap: () => onModeChanged(modeKey),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xff18b8b5) : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isActive ? Colors.white : Colors.white70,
            fontSize: 10,
            fontWeight: FontWeight.bold,
          ),
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
          Icon(Icons.camera_alt_outlined, size: 48, color: const Color(0xff18b8b5).withOpacity(0.4)),
          const SizedBox(height: 12),
          const Text("Camera Feed Offline", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
        ],
      ),
    );
  }
}