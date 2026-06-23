// lib/main.dart
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'views/dashboard_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  List<CameraDescription> cameras = [];
  try {
    cameras = await availableCameras();
  } catch (e) {
    debugPrint("Failed to initialize cameras: $e");
  }
  runApp(MyApp(cameras: cameras));
}

class MyApp extends StatefulWidget {
  final List<CameraDescription> cameras;
  const MyApp({super.key, required this.cameras});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  ThemeMode _themeMode = ThemeMode.system;

  void toggleTheme() {
    setState(() {
      _themeMode = _themeMode == ThemeMode.light ? ThemeMode.dark : ThemeMode.light;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Swayam Health - ASL Translator',
      debugShowCheckedModeBanner: false,
      themeMode: _themeMode,
      theme: _buildTheme(Brightness.light, const Color(0xffeaeaec)),
      darkTheme: _buildTheme(Brightness.dark, const Color(0xff141316)),
      home: TranslatorDashboard(
        cameras: widget.cameras,
        isDark: _themeMode == ThemeMode.dark,
        onThemeToggle: toggleTheme,
      ),
    );
  }

  ThemeData _buildTheme(Brightness brightness, Color scaffoldBg) {
    return ThemeData(
      brightness: brightness,
      scaffoldBackgroundColor: scaffoldBg,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff18b8b5),
        primary: const Color(0xff18b8b5),
        secondary: const Color(0xffffcc00),
        brightness: brightness,
      ),
      useMaterial3: true,
      fontFamily: 'Poppins',
    );
  }
}