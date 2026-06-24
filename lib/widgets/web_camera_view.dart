import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'web_camera_helper_stub.dart' if (dart.library.html) 'web_camera_helper_web.dart';

class WebCameraView extends StatefulWidget {
  final Function(String jsonLandmarks) onLandmarks;

  const WebCameraView({
    super.key,
    required this.onLandmarks,
  });

  @override
  State<WebCameraView> createState() => _WebCameraViewState();
}

class _WebCameraViewState extends State<WebCameraView> {
  @override
  void initState() {
    super.initState();
    if (kIsWeb) {
      registerWebCameraView();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        startWebHandTracking(widget.onLandmarks);
      });
    }
  }

  @override
  void dispose() {
    if (kIsWeb) {
      stopWebHandTracking();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) {
      return const Center(child: Text("WebCameraView is only supported on Web."));
    }
    return const HtmlElementView(viewType: 'web-camera-view');
  }
}
