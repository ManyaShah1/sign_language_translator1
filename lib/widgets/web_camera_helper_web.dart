import 'dart:async';
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;
import 'dart:js' as js;

void registerWebCameraView() {
  ui_web.platformViewRegistry.registerViewFactory(
    'web-camera-view',
    (int viewId) {
      final container = html.DivElement()
        ..id = 'web-camera-container'
        ..style.width = '100%'
        ..style.height = '100%'
        ..style.position = 'relative'
        ..style.backgroundColor = '#000000';

      final video = html.VideoElement()
        ..id = 'web-camera-video'
        ..autoplay = true
        ..style.display = 'none'; // We keep video hidden and draw to canvas

      final canvas = html.CanvasElement()
        ..id = 'web-camera-canvas'
        ..style.width = '100%'
        ..style.height = '100%'
        ..style.objectFit = 'cover';

      container.append(video);
      container.append(canvas);
      return container;
    },
  );
}

void startWebHandTracking(Function(String jsonLandmarks) callback) {
  final videoElement = html.document.getElementById('web-camera-video');
  final canvasElement = html.document.getElementById('web-camera-canvas');
  if (videoElement != null && canvasElement != null) {
    if (js.context.hasProperty('aslWebTracker')) {
      js.context['aslWebTracker'].callMethod('start', [
        videoElement,
        canvasElement,
        callback,
      ]);
    } else {
      html.window.console.error('aslWebTracker not found on window object.');
    }
  } else {
    // If elements not in DOM yet, try again on next event loop tick
    Timer(const Duration(milliseconds: 100), () {
      startWebHandTracking(callback);
    });
  }
}

void stopWebHandTracking() {
  if (js.context.hasProperty('aslWebTracker')) {
    js.context['aslWebTracker'].callMethod('stop');
  }
}
