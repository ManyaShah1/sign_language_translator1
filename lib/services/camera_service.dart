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
        final lensDirection = controller?.description.lensDirection ?? CameraLensDirection.front;

        List<Map<String, double>> getProcessedHand(Hand hand, CameraLensDirection lensDir) {
          final List<Map<String, double>> processedLandmarks = [];
          for (final Landmark landmark in hand.landmarks) {
            double nx = landmark.x - 0.5;
            double ny = landmark.y - 0.5;
            double rad = sensorOrientation * math.pi / 180.0;
            double rx = nx * math.cos(rad) - ny * math.sin(rad);
            double ry = nx * math.sin(rad) + ny * math.cos(rad);
            if (lensDir == CameraLensDirection.front) {
              rx = -rx;
            }
            double finalX = rx + 0.5;
            double finalY = ry + 0.5;
            processedLandmarks.add({
              "x": finalX,
              "y": finalY,
              "z": landmark.z,
            });
          }

          final List<Map<String, double>> normalized = [];
          if (processedLandmarks.isNotEmpty) {
            final wrist = processedLandmarks[0];
            final double wx = wrist["x"]!;
            final double wy = wrist["y"]!;
            final double wz = wrist["z"]!;
            final double layoutWidth = image.width.toDouble();
            final double layoutHeight = image.height.toDouble();

            for (final Map<String, double> lm in processedLandmarks) {
              normalized.add({
                "x": (lm["x"]! - wx) / layoutWidth,
                "y": (lm["y"]! - wy) / layoutHeight,
                "z": lm["z"]! - wz,
              });
            }
          }
          return normalized;
        }

        // 1. Add 4 dummy pose joints (shoulders, elbows)
        for (int i = 0; i < 4; i++) {
          extractedPoints.add({"x": 0.0, "y": 0.0, "z": 0.0});
        }

        // 2. Add Hand 1 (Left hand slot)
        final hand1Points = getProcessedHand(hands[0], lensDirection);
        extractedPoints.addAll(hand1Points);
        if (hand1Points.length < 21) {
          for (int i = hand1Points.length; i < 21; i++) {
            extractedPoints.add({"x": 0.0, "y": 0.0, "z": 0.0});
          }
        }

        // 3. Add Hand 2 (Right hand slot)
        if (hands.length > 1) {
          final hand2Points = getProcessedHand(hands[1], lensDirection);
          extractedPoints.addAll(hand2Points);
          if (hand2Points.length < 21) {
            for (int i = hand2Points.length; i < 21; i++) {
              extractedPoints.add({"x": 0.0, "y": 0.0, "z": 0.0});
            }
          }
        } else {
          for (int i = 0; i < 21; i++) {
            extractedPoints.add({"x": 0.0, "y": 0.0, "z": 0.0});
          }
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