import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import '../hand_landmarker_stub.dart'
    if (dart.library.io) 'package:hand_landmarker/hand_landmarker.dart';

class CameraService {
  CameraController? controller;
  bool isInitialized = false;
  
  HandLandmarkerPlugin? _handLandmarker;
  bool isProcessingFrame = false;

  Future<void> initialize(
    List<CameraDescription> cameras,
    VoidCallback onInitialized,
    Function(CameraImage) onImageStream,
  ) async {
    if (cameras.isEmpty) {
      debugPrint("CameraService: No cameras available.");
      return;
    }

    // Try to find the front-facing camera for kiosk users
    final frontCamera = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.front,
      orElse: () => cameras.first,
    );

    controller = CameraController(
      frontCamera,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    // Initialize native MediaPipe HandLandmarker with robust GPU/CPU fallback
    try {
      try {
        _handLandmarker = HandLandmarkerPlugin.create(
          numHands: 2, // Only need 1 hand for single hand ASL translation kiosk
          minHandDetectionConfidence: 0.6, // Set slightly lower for better stream tracking
          delegate: HandLandmarkerDelegate.GPU,
        );
        debugPrint("MediaPipe HandLandmarker initialized successfully with GPU delegate.");
      } catch (gpuError) {
        debugPrint("GPU Landmarker initialization failed: $gpuError. Falling back to CPU.");
        _handLandmarker = HandLandmarkerPlugin.create(
          numHands: 2,
          minHandDetectionConfidence: 0.6,
          delegate: HandLandmarkerDelegate.CPU,
        );
        debugPrint("MediaPipe HandLandmarker initialized successfully with CPU delegate.");
      }
    } catch (e) {
      debugPrint("MediaPipe HandLandmarker initialization bypassed (unsupported platform): $e");
    }

    try {
      await controller!.initialize();
      isInitialized = true;
      onInitialized();
    } catch (e) {
      debugPrint("CameraService: Failed to initialize camera controller: $e");
    }
  }

  Future<List<Map<String, double>>> processLiveFrame(CameraImage image, int sensorOrientation) async {
    if (isProcessingFrame) return [];
    isProcessingFrame = true;

    try {
      if (_handLandmarker == null) {
        isProcessingFrame = false;
        return [];
      }

      final List<Hand> hands = _handLandmarker!.detect(image, sensorOrientation);
      final List<Map<String, double>> extractedPoints = [];

      if (hands.isNotEmpty) {
        final Hand hand = hands.first;
        final lensDirection = controller?.description.lensDirection ?? CameraLensDirection.front;

        for (final Landmark landmark in hand.landmarks) {
          // Translate coordinate system from raw sensor space to upright screen space.
          // 1. Shift origin to center relative [-0.5, 0.5]
          double nx = landmark.x - 0.5;
          double ny = landmark.y - 0.5;

          // 2. Rotate by sensorOrientation degrees (convert to radians)
          double rad = sensorOrientation * math.pi / 180.0;
          double rx = nx * math.cos(rad) - ny * math.sin(rad);
          double ry = nx * math.sin(rad) + ny * math.cos(rad);

          // 3. Mirror the horizontal axis for the front camera to match mirrored preview
          if (lensDirection == CameraLensDirection.front) {
            rx = -rx;
          }

          // 4. Shift origin back to [0.0, 1.0]
          double finalX = rx + 0.5;
          double finalY = ry + 0.5;

          extractedPoints.add({
            "x": finalX,
            "y": finalY,
            "z": landmark.z,
          });
        }
      }

      isProcessingFrame = false;
      return extractedPoints;
    } catch (e) {
      debugPrint("CameraService: Error processing live frame: $e");
      isProcessingFrame = false;
      return [];
    }
  }

  void dispose() {
    controller?.dispose();
    controller = null;
    isInitialized = false;
    _handLandmarker?.dispose();
    _handLandmarker = null;
  }
}