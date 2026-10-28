"""Two perspective energy rings, painted locally without model/voice calls."""
import time

from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtGui import QPainter, QImage
from PySide6.QtWidgets import QWidget


class CoreWidget(QWidget):
    """Composite offline-rendered frames; no live ring geometry."""
    def __init__(self, parent=None):
        super().__init__(parent)
        from pathlib import Path
        import sys
        from PySide6.QtGui import QPixmap
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        sheet = QPixmap(str(root / 'assets' / 'core_atlas.png'))
        self.frames = [sheet.copy((i % 8)*360, (i // 8)*210, 360, 210) for i in range(128)]
        self.setMinimumHeight(170)
        self.setMaximumHeight(250)
        self.setAccessibleName('Ядро Акиры: две волны плазмы')
        self.working = False
        self.bands = []
        self.audio_at = 0.0
        self.started = time.monotonic()
        self.energy = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._advance)

    def set_working(self, working):
        self.working = bool(working)

    def set_spectrum(self, bands):
        self.bands = [max(0.0, min(1.0, float(value))) for value in bands]
        self.audio_at = time.monotonic()

    def _advance(self):
        live = bool(self.bands) and time.monotonic() - self.audio_at < 0.5
        target = max(max(self.bands) if live else 0.0, 0.65 if self.working else 0.025)
        self.energy += (target - self.energy) * (0.25 if target > self.energy else 0.1)
        self.update()

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Crossfade adjacent temporal frames and intensity banks on a fixed plane.
        phase = ((time.monotonic() - self.started) * 12) % 32
        bank = max(0.0, min(3.0, self.energy * 3))
        first, blend = int(phase), phase % 1
        low, amount = int(bank), bank % 1
        size = min(self.width(), self.height() * 360 / 210)
        rect = QRectF((self.width()-size)/2, (self.height()-size*210/360)/2, size, size*210/360)
        canvas = QImage(360, 210, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        mixer = QPainter(canvas)
        mixer.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for level, weight in ((low, 1-amount), (min(3,low+1), amount)):
            for index, opacity in ((first, 1-blend), ((first+1)%32, blend)):
                if weight * opacity > 0:
                    mixer.setOpacity(weight * opacity)
                    mixer.drawPixmap(0, 0, self.frames[level*32+index])
        mixer.end()
        painter.drawImage(rect, canvas)


class SystemAudioSpectrum(QThread):
    """Use an existing loopback device only; never open the default microphone."""
    spectrum = Signal(object)
    available = Signal(bool)

    def run(self):
        try:
            import numpy as np
            import sounddevice as sd
            devices = sd.query_devices()
            device = next((index for index, info in enumerate(devices)
                           if info['max_input_channels'] > 0 and any(
                               name in info['name'].casefold()
                               for name in ('blackhole', 'loopback', 'stereo mix', 'стерео микшер', 'soundflower'))), None)
            if device is None:
                self.available.emit(False)
                return
            rate = int(devices[device]['default_samplerate'])
            channels = min(2, devices[device]['max_input_channels'])
            def callback(data, frames, timing, status):
                signal = data.mean(axis=1)
                spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) / max(1, len(signal))
                edges = np.geomspace(1, max(2, len(spectrum) - 1), 33).astype(int)
                bands = [min(1.0, float(np.max(spectrum[a:max(a + 1, b)])) * 35) for a, b in zip(edges, edges[1:])]
                self.spectrum.emit(bands)
            with sd.InputStream(device=device, channels=channels, samplerate=rate, blocksize=2048, callback=callback):
                self.available.emit(True)
                while not self.isInterruptionRequested():
                    self.msleep(100)
        except Exception:
            self.available.emit(False)
