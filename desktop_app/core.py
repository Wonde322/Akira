"""Two perspective energy rings, painted locally without model/voice calls."""
import math
import time

from PySide6.QtCore import Qt, QTimer, QPointF, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class CoreWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setMaximumHeight(250)
        self.setAccessibleName('Ядро Акиры: два энергетических кольца')
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

    def ring_points(self, radius, phase, count=96):
        t = time.monotonic() - self.started
        live = bool(self.bands) and time.monotonic() - self.audio_at < 0.5
        points = []
        for index in range(count):
            angle = math.tau * index / count
            wave = abs(math.sin(index * 1.71 + t * 2.3 + phase)) ** 5
            wave *= 0.55 + 0.45 * math.sin(angle * 5 - t * 1.7) ** 2
            if live:
                wave = self.bands[index * len(self.bands) // count]
            height = 2 + 2 * math.sin(angle * 4 + t * 0.65 + phase) ** 2
            height += self.energy * (12 + 85 * wave)
            x = math.cos(angle) * radius
            y = math.sin(angle) * radius * 0.34
            points.append((QPointF(x, y), QPointF(x + math.cos(angle) * height * 0.23, y - height)))
        return points

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() * 0.68)
        scale = min(1.0, self.width() / 500, self.height() / 230)
        painter.scale(scale, scale)
        for radius, phase, color in ((150, 0, '#ed5649'), (112, 1.8, '#f5c574')):
            pairs = self.ring_points(radius, phase)
            floor = QPainterPath()
            floor.addEllipse(QPointF(0, 0), radius, radius * 0.34)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for width, alpha in ((9, 12), (4, 26), (1, 150)):
                shade = QColor(color); shade.setAlpha(alpha)
                painter.setPen(QPen(shade, width))
                painter.drawPath(floor)
            # Sort facets from back to front to keep the ring's perspective legible.
            for index in sorted(range(len(pairs)), key=lambda i: pairs[i][0].y()):
                base, tip = pairs[index]
                next_base, _ = pairs[(index + 1) % len(pairs)]
                shape = QPainterPath(base)
                shape.lineTo(tip); shape.lineTo(next_base); shape.closeSubpath()
                shade = QColor(color); shade.setAlpha(35 + int(40 * self.energy))
                painter.setBrush(shade)
                edge = QColor(color); edge.setAlpha(130)
                painter.setPen(QPen(edge, 0.7))
                painter.drawPath(shape)


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
