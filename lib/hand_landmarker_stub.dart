import 'package:camera/camera.dart';

class Landmark {
  final double x;
  final double y;
  final double z;
  Landmark(this.x, this.y, this.z);
}

class Hand {
  final List<Landmark> landmarks;
  Hand(this.landmarks);
}

enum HandLandmarkerDelegate {
  CPU,
  GPU,
}

class HandLandmarkerPlugin {
  static HandLandmarkerPlugin create({
    int numHands = 2,
    double minHandDetectionConfidence = 0.5,
    HandLandmarkerDelegate delegate = HandLandmarkerDelegate.GPU,
  }) {
    throw UnsupportedError("HandLandmarkerPlugin is not supported on this platform.");
  }

  List<Hand> detect(CameraImage image, int sensorOrientation) {
    return [];
  }

  void dispose() {}
}
