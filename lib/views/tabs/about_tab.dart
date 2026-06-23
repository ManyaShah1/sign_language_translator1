import 'package:flutter/material.dart';

class AboutTab extends StatelessWidget {
  final bool isDark;
  const AboutTab({super.key, required this.isDark});

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
            "About Swayam Health ATM Kiosks",
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Color(0xff18b8b5)),
          ),
          const SizedBox(height: 8),
          const Text(
            "Empowering decentralized point-of-care medical testing & diagnostics.",
            style: TextStyle(fontSize: 14, color: Colors.grey, fontWeight: FontWeight.w300),
          ),
          const Divider(height: 32),
          const Text(
            "Swayam Health is the premier smart health kiosk network (Health ATMs) approved by CDSCO. It integrates a clinical-grade diagnostics suite that processes over 100 physiological metrics and delivers digital health reports instantly.",
            style: TextStyle(fontSize: 14, height: 1.6),
          ),
          const SizedBox(height: 24),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _buildInfoCard(
                  "Swayam AHM Kiosk",
                  "Stationary diagnostic cabin deployed in public centers, offices, and clinics containing automatic testing modules.",
                  Icons.monitor_heart,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _buildInfoCard(
                  "Swandook Case",
                  "A highly portable, compact suitcase carrying critical diagnostic kits designed for remote rural checkups.",
                  Icons.business_center,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          const Text(
            "Integration with Sign Language",
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text(
            "By incorporating local hand-tracking and ASL sentence translation directly onto the kiosk system, non-verbal patients and deaf/mute individuals can seamlessly run diagnostics and engage in real-time telemedicine consultations without any communication barriers.",
            style: TextStyle(fontSize: 14, height: 1.6),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoCard(String title, String desc, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff0d0c0e) : const Color(0xfff0f4f4),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xff18b8b5).withOpacity(0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 28, color: const Color(0xff18b8b5)),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
          const SizedBox(height: 8),
          Text(desc, style: const TextStyle(fontSize: 12, color: Colors.grey, height: 1.5)),
        ],
      ),
    );
  }
}