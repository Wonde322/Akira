"""Two perspective energy rings, painted locally without model/voice calls."""
import time

from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget


class CoreWidget(QWidget):
    """Continuously play prepared plasma frames, including while idle."""
    def __init__(self, parent=None):
        super().__init__(parent)
        from pathlib import Path
        import sys
        from PySide6.QtGui import QPixmap
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets'
        sheet = QPixmap(str(root / 'core_motion.png'))
        self.frames = [sheet.copy((i%8)*320, (i//8)*210, 320, 210) for i in range(256)]
        self.setMinimumHeight(170)
        self.setMaximumHeight(270)
        self.setAccessibleName('Ядро Акиры: анимированная плазма')
        self.working = False
        self.bands = []
        self.audio_at = 0.0
        self.energy = 0.0
        self.phase = 0.0
        self.bank = 0
        self.last_tick = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._advance)

    def set_working(self, working):
        self.working = bool(working)

    def set_spectrum(self, bands):
        self.bands = [max(0.0, min(1.0, float(value))) for value in bands]
        self.audio_at = time.monotonic()

    def _advance(self):
        now = time.monotonic()
        live = bool(self.bands) and now-self.audio_at < .5
        target = max(max(self.bands) if live else 0, .65 if self.working else .025)
        self.energy += (target-self.energy) * (.2 if target>self.energy else .08)
        self.phase = (self.phase + min(.1, now-self.last_tick)*(10+18*self.energy)) % 64
        self.last_tick = now
        # Hysteresis avoids rapidly switching amplitude banks on quiet transients.
        bounds = (.15,.45,.8)
        while self.bank<3 and self.energy>bounds[self.bank]+.03: self.bank+=1
        while self.bank>0 and self.energy<bounds[self.bank-1]-.03: self.bank-=1
        self.update()

    def showEvent(self, event):
        self.last_tick=time.monotonic()
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        level = min(3.0, max(0.0, (self.energy - .025) / .975 * 3))
        lower = int(level)
        blend = level - lower
        image=self.frames[lower*64+int(self.phase)]
        width=min(self.width(),self.height()*320/210)
        height=width*210/320
        destination = QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)
        painter.drawPixmap(destination, image, QRectF(0,0,320,210))
        if blend > .001 and lower < 3:
            painter.setOpacity(blend)
            painter.drawPixmap(destination, self.frames[(lower+1)*64+int(self.phase)], QRectF(0,0,320,210))


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
