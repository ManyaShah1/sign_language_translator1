
class InferenceVitals {
  final int serverLatency;
  final double fps;
  final int packetsSent;
  final int packetsReceived;
  final double movementVelocity;

  InferenceVitals({
    required this.serverLatency,
    required this.fps,
    required this.packetsSent,
    required this.packetsReceived,
    required this.movementVelocity,
  });
}