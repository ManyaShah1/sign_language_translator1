import 'dart:async';
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

    // Initialize native MediaPipe HandLandmarker
    try {
      _handLandmarker = HandLandmarkerPlugin.create(
        numHands: 1, // Only need 1 hand for single hand ASL translation kiosk
        minHandDetectionConfidence: 0.5,
        delegate: HandLandmarkerDelegate.GPU,
      );
      debugPrint("MediaPipe HandLandmarker initialized successfully.");
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
        for (final Landmark landmark in hand.landmarks) {
          extractedPoints.add({
            "x": landmark.x,
            "y": landmark.y,
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