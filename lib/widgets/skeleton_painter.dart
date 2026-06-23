// lib/views/widgets/skeleton_painter.dart
import 'package:flutter/material.dart';

class HandSkeletonPainter extends CustomPainter {
  final List<Map<String, double>> points;
  final bool isDark;

  HandSkeletonPainter({required this.points, required this.isDark});

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;

    final paintJoint = Paint()..color = const Color(0xffffcc00)..style = PaintingStyle.fill;
    final paintLine = Paint()
      ..color = const Color(0xff18b8b5)
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    List<Offset> offsets = [];
    List<double> scales = [];
    for (var pt in points) {
      double x = pt["x"] ?? 0.0;
      double y = pt["y"] ?? 0.0;
      double z = pt["z"] ?? 0.0;
      offsets.add(Offset(x * size.width, y * size.height));
      scales.add(1.0 + (z * 0.5));
    }

    // Draw lines connecting finger nodes to wrist and between nodes
    for (int f = 0; f < 5; f++) {
      int baseIdx = 1 + f * 4;
      if (offsets.length > baseIdx) {
        canvas.drawLine(offsets[0], offsets[baseIdx], paintLine);
      }
      for (int j = 0; j < 3; j++) {
        int idx1 = baseIdx + j;
        int idx2 = baseIdx + j + 1;
        if (offsets.length > idx2) {
          canvas.drawLine(offsets[idx1], offsets[idx2], paintLine);
        }
      }
    }

    // Draw physical nodes
    for (int i = 0; i < offsets.length; i++) {
      canvas.drawCircle(offsets[i], 4.0 * scales[i], paintJoint);
      canvas.drawCircle(offsets[i], 6.0 * scales[i], Paint()
        ..color = const Color(0xff18b8b5).withOpacity(0.3)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0 * scales[i]
      );
    }
  }

  @override
  bool shouldRepaint(covariant HandSkeletonPainter oldDelegate) => true;
}