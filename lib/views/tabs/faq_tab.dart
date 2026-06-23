import 'package:flutter/material.dart';

class FaqTab extends StatelessWidget {
  final bool isDark;
  const FaqTab({super.key, required this.isDark});

  @override
  Widget build(BuildContext context) {
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
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Color(0xff18b8b5)),
          ),
          const SizedBox(height: 8),
          const Text(
            "Understanding the 100% free, local machine learning translation stack.",
            style: TextStyle(fontSize: 14, color: Colors.grey, fontWeight: FontWeight.w300),
          ),
          const Divider(height: 32),
          _buildFaqItem("Why use Local Inference instead of commercial APIs?", "Cloud-based sign language models charge high rates per minute of video feed and enforce strict limits. Running model inference locally ensures the translator remains 100% free, private, and unlimited."),
          _buildFaqItem("How does the Flutter app connect to the Python server?", "The Flutter app initializes a WebSocket connection to a local Python daemon running on port 8768, streaming lightweight hand-coordinate JSON payloads at 30 packets per second."),
          _buildFaqItem("What is a CTC Network and how does it translate sentences?", "A Connectionist Temporal Classification (CTC) network is designed for sequence tasks. It evaluates frames over a temporal timeline, capturing dynamic transitions between signs to output cohesive English sentences."),
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
          color: isDark ? const Color(0xff1c1b22) : const Color(0xffeaeaec).withOpacity(0.5),
          borderRadius: BorderRadius.circular(15),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(question, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Color(0xff18b8b5))),
            const SizedBox(height: 8),
            Text(answer, style: TextStyle(fontSize: 13, height: 1.5, color: isDark ? Colors.white70 : Colors.black87)),
          ],
        ),
      ),
    );
  }
}