import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'tabs/translator_tab.dart';
import 'tabs/about_tab.dart';
import 'tabs/faq_tab.dart';

class TranslatorDashboard extends StatefulWidget {
  final List<CameraDescription> cameras;
  final bool isDark;
  final VoidCallback onThemeToggle;

  const TranslatorDashboard({
    super.key,
    required this.cameras,
    required this.isDark,
    required this.onThemeToggle,
  });

  @override
  State<TranslatorDashboard> createState() => _TranslatorDashboardState();
}

class _TranslatorDashboardState extends State<TranslatorDashboard> {
  int _activeTab = 0;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildHeader(isDark),
                const SizedBox(height: 20),
                IndexedStack(
                  index: _activeTab,
                  children: [
                    TranslatorTab(cameras: widget.cameras),
                    AboutTab(isDark: isDark),
                    FaqTab(isDark: isDark),
                  ],
                ),
                const SizedBox(height: 40),
                _buildFooter(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(bool isDark) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xff1b1a1f) : Colors.white,
        borderRadius: BorderRadius.circular(25),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10, offset: const Offset(0, 4))],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 38, height: 38,
                decoration: const BoxDecoration(color: Color(0xff18b8b5), shape: BoxShape.circle),
                child: const Icon(Icons.gesture, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 10),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text.rich(
                    TextSpan(
                      text: "swayam",
                      style: TextStyle(fontFamily: 'Poppins', fontWeight: FontWeight.w600, fontSize: 18, color: isDark ? Colors.white : const Color(0xff242424)),
                      children: const [TextSpan(text: "health", style: TextStyle(color: Color(0xff18b8b5), fontWeight: FontWeight.w300))],
                    ),
                  ),
                  const Text("ASL local translation", style: TextStyle(fontSize: 10, color: Colors.grey))
                ],
              ),
            ],
          ),
          Flexible(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildTabButton("Translate", 0),
                  const SizedBox(width: 8),
                  _buildTabButton("About Kiosk", 1),
                  const SizedBox(width: 8),
                  _buildTabButton("Local FAQ", 2),
                ],
              ),
            ),
          ),
          IconButton(
            icon: Icon(widget.isDark ? Icons.light_mode : Icons.dark_mode),
            onPressed: widget.onThemeToggle,
            color: const Color(0xff18b8b5),
          ),
        ],
      ),

    );
  }

  Widget _buildTabButton(String label, int index) {
    bool isActive = _activeTab == index;
    return InkWell(
      onTap: () => setState(() => _activeTab = index),
      borderRadius: BorderRadius.circular(15),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xff18b8b5).withOpacity(0.1) : Colors.transparent,
          borderRadius: BorderRadius.circular(15),
        ),
        child: Text(label, style: TextStyle(fontSize: 12, fontWeight: isActive ? FontWeight.w600 : FontWeight.w400, color: isActive ? const Color(0xff18b8b5) : Colors.grey)),
      ),
    );
  }

  Widget _buildFooter() {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.shield, size: 14, color: const Color(0xff18b8b5).withOpacity(0.6)),
              const SizedBox(width: 6),
              const Text("Secure, Private, Local Machine Learning System", style: TextStyle(fontSize: 10, color: Colors.grey)),
            ],
          ),
          const SizedBox(height: 6),
          Text("© ${DateTime.now().year} Sanskritech Smart Solutions. Swayam Health Ecosystem.", style: const TextStyle(fontSize: 10, color: Colors.grey)),
        ],
      ),
    );
  }
}