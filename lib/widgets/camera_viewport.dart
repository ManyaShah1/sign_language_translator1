import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import '../../models/landmark_data.dart';
import '../../services/camera_service.dart';
import 'skeleton_painter.dart';

class CameraViewport extends StatelessWidget {
  final CameraService cameraService;
  final TrackingMode trackingMode;
  final List<Map<String, double>> simulatedPoints;
  final double fps;
  final int packetsSent;
  final bool isConnected;
  final Function(Offset localPosition) onPointerUpdated;

  const CameraViewport({
    super.key,
    required this.cameraService,
    required this.trackingMode,
    required this.simulatedPoints,
    required this.fps,
    required this.packetsSent,
    required this.isConnected,
    required this.onPointerUpdated,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return GestureDetector(
      onPanUpdate: (details) {
        if (trackingMode == TrackingMode.cursor) onPointerUpdated(details.localPosition);
      },
      onPanDown: (details) {
        if (trackingMode == TrackingMode.cursor) onPointerUpdated(details.localPosition);
      },
      child: Container(
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
            (cameraService.isInitialized && cameraService.controller != null)
                ? CameraPreview(cameraService.controller!)
                : _buildMockCameraFeedback(isDark),
            if (isConnected) CustomPaint(painter: HandSkeletonPainter(points: simulatedPoints, isDark: isDark)),
            Positioned(
              top: 16, left: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(color: Colors.black.withOpacity(0.6), borderRadius: BorderRadius.circular(12)),
                child: Text(
                  trackingMode == TrackingMode.simulator ? "VIRTUAL AUTO-WAVE ACTIVE" : "TRACKING INTERACTIVE",
                  style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
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
          Icon(Icons.camera_alt_outlined, size: 48, color: const Color(0xff18b8b5).withOpacity(0.4)),
          const SizedBox(height: 12),
          const Text("Camera Feed Offline", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
        ],
      ),
    );
  }
}