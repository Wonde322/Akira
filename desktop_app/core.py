"""Two perspective energy rings, painted locally without model/voice calls."""
import time

from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget


class CoreWidget(QWidget):
    """Play the supplied reference artwork, without synthesizing its shapes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        from pathlib import Path
        import sys
        from PySide6.QtGui import QMovie, QPixmap
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets'
        self.idle = QPixmap(str(root / 'core_reference_idle.jpg'))
        self.movies = [QMovie(str(root / name)) for name in ('core_reference.gif', 'core_reference_active.gif')]
        for movie in self.movies:
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.frameChanged.connect(self.update)
            movie.jumpToFrame(0)
        self.mode = 0
        self.setMinimumHeight(170)
        self.setMaximumHeight(280)
        self.setAccessibleName('Ядро Акиры: исходная анимация колец')
        self.working = False
        self.bands = []
        self.audio_at = 0.0
        self.energy = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(50)
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
        # Hysteresis avoids flashing between different source clips on each beat.
        mode = 2 if self.energy > 0.78 else (1 if self.energy > 0.15 else 0)
        if self.mode == 2 and self.energy > 0.6: mode = 2
        if self.mode == 1 and 0.08 < self.energy < 0.85: mode = 1
        if mode != self.mode:
            for movie in self.movies: movie.stop()
            self.mode = mode
            if mode and self.isVisible(): self.movies[mode-1].start()
        self.update()

    def showEvent(self, event):
        self.timer.start()
        if self.mode: self.movies[self.mode-1].start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        for movie in self.movies: movie.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pixmap = self.movies[self.mode-1].currentPixmap() if self.mode else self.idle
        if pixmap.isNull(): return
        width = min(self.width(), self.height() * pixmap.width() / pixmap.height())
        height = width * pixmap.height() / pixmap.width()
        painter.drawPixmap(QRectF((self.width()-width)/2, (self.height()-height)/2, width, height),
                           pixmap, QRectF(pixmap.rect()))


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
