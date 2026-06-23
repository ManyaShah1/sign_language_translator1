import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class TranslationPanel extends StatelessWidget {
  final String currentTranslation;
  final double confidence;
  final String status;
  final List<String> history;
  final int latency;
  final double fps;
  final int packetsSent;
  final int packetsRecv;
  final double velocity;
  final VoidCallback onClear;

  const TranslationPanel({
    super.key,
    required this.currentTranslation,
    required this.confidence,
    required this.status,
    required this.history,
    required this.latency,
    required this.fps,
    required this.packetsSent,
    required this.packetsRecv,
    required this.velocity,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xff1b1a1f) : Colors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: isDark ? const Color(0xff242424) : Colors.black.withOpacity(0.05)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text("Live Translation", style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: Color(0xff18b8b5))),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(color: const Color(0xffffcc00).withOpacity(0.15), borderRadius: BorderRadius.circular(10)),
                    child: Text("Confidence: ${(confidence * 100).toStringAsFixed(1)}%", style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Color(0xffd4aa00))),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              SelectableText(currentTranslation, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, height: 1.4)),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => Clipboard.setData(ClipboardData(text: currentTranslation)),
                      icon: const Icon(Icons.copy, size: 14),
                      label: const Text("Copy"),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: OutlinedButton.icon(onPressed: onClear, icon: const Icon(Icons.clear_all, size: 14), label: const Text("Clear"))),
                ],
              )
            ],
          ),
        ),
        const SizedBox(height: 24),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xff18b8b5).withOpacity(0.05),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xff18b8b5).withOpacity(0.15)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text("Local Inference Diagnostics (Vitals)", style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: Color(0xff18b8b5))),
              const SizedBox(height: 16),
              GridView.count(
                crossAxisCount: 2, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 2.2, crossAxisSpacing: 12, mainAxisSpacing: 12,
                children: [
                  _buildVitalCard("Server Latency", "$latency ms", Icons.speed),
                  _buildVitalCard("Landmarks FPS", "${fps.toStringAsFixed(0)} FPS", Icons.analytics_outlined),
                  _buildVitalCard("Frames Sent/Recv", "$packetsSent / $packetsRecv", Icons.upload_file),
                  _buildVitalCard("Movement Velocity", velocity.toStringAsFixed(4), Icons.show_chart),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildVitalCard(String label, String value, IconData icon) {
    return Builder(builder: (context) {
      final isDark = Theme.of(context).brightness == Brightness.dark;
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xff1b1a1f) : Colors.white,
          borderRadius: BorderRadius.circular(15),
          border: Border.all(color: const Color(0xff18b8b5).withOpacity(0.1)),
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
                  Text(label, style: const TextStyle(fontSize: 9, color: Colors.grey, overflow: TextOverflow.ellipsis)),
                  Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ],
        ),
      );
    });
  }
}