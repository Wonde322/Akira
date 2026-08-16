"""Живая бионическая сфера из точек.

Сфера воспринимается как поверхность энергетического объекта: по ней
непрерывно проходят несколько волн, поверхность «дышит», граница мягко
деформируется, центр светится ярче периферии. Никаких случайных скачков:
вся анимация — детерминированная суперпозиция синусоид.

Состояния: IDLE, LISTENING, THINKING, SPEAKING, DISABLED.
Переходы между состояниями плавные: параметры интерполируются к целевым
(easing), поэтому сфера никогда не мигает и не «переключается» рывком.

Для производительности геометрия и тригонометрические константы каждой
точки вычисляются один раз при resize; во время отрисовки пересчитываются
только временные компоненты волн.
"""

import math

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class HalftoneWidget(QWidget):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    DISABLED = "disabled"

    clicked = Signal()

    # (base, amp, speed, deform, rim)
    STATE_PARAMS = {
        IDLE: (0.58, 0.50, 0.55, 0.060, 0.58),
        LISTENING: (0.78, 0.60, 0.95, 0.110, 0.48),
        THINKING: (0.84, 0.68, 0.85, 0.130, 0.44),
        SPEAKING: (1.00, 0.78, 1.25, 0.170, 0.40),
        DISABLED: (0.13, 0.04, 0.12, 0.010, 0.68),
    }

    _TICK_MS = 16
    # Насколько быстро параметры догоняют целевые (0..1 за тик).
    _EASE = 0.09
    # Скорость продвижения фазы (доля цикла за тик).
    _PHASE_STEP = 0.022

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self._state = self.IDLE
        self._phase = 0.0
        self._dots = []
        self._params = list(self.STATE_PARAMS[self.IDLE])
        self._audio_level = 0.0
        self._dialogue_glow = 0.0
        self._dialogue_target = 0.0
        self._glow_cache = None
        self._glow_size = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._TICK_MS)

    # ---------------------------------------------------------------- state
    def set_state(self, state):
        if state not in self.STATE_PARAMS:
            state = self.IDLE
        if state != self._state:
            self._state = state
            self.update()

    def state(self):
        return self._state

    def set_dialogue(self, enabled):
        """Включает/выключает внешнее кольцо dialogue mode (плавно)."""
        self._dialogue_target = 1.0 if enabled else 0.0

    def set_audio_level(self, level):
        """Опциональный уровень речи для SPEAKING (0..1), сглаживается."""
        self._audio_level = max(0.0, min(1.0, level))

    # ------------------------------------------------------------- animation
    def _target_params(self):
        return self.STATE_PARAMS[self._state]

    def _tick(self):
        # Фаза никогда не сбрасывается: все волны — периодические функции
        # фазы, и если оборвать цикл на произвольной длине, края кадра не
        # совпадут. Позволяя фазе расти непрерывно, суперпозиция синусоид
        # становится бесконечной и бесшовной — шва между циклами нет.
        self._phase += self._PHASE_STEP

        target = self._target_params()
        for i in range(len(self._params)):
            self._params[i] += (target[i] - self._params[i]) * self._EASE

        self._dialogue_glow += (self._dialogue_target - self._dialogue_glow) * 0.08
        self._audio_level *= 0.94
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        self._build_dots()
        super().resizeEvent(event)

    def _build_dots(self):
        w, h = self.width(), self.height()
        if w < 2 or h < 2:
            self._dots = []
            self._glow_cache = None
            return

        center_x, center_y = w / 2.0, h / 2.0
        radius = min(w, h) * 0.42
        step = 12.0
        dots = []

        # Органичная (не-сеточная) раскладка точек: равномерное угловое
        # распределение по спирали с детерминированным дрожанием радиуса.
        index = 0
        max_dots = 1400
        # Площадь диска покрывается спиралью; шаг подбирается под размер.
        spiral_step = max(3.5, min(w, h) / 55.0)
        angle = 0.0
        for ring in range(1, int(radius / spiral_step) + 1):
            circumference = 2.0 * math.pi * ring * spiral_step
            count = max(6, int(circumference / (spiral_step * 1.35)))
            for k in range(count):
                if index >= max_dots:
                    break
                theta = (k * 2.0 * math.pi / count) + (ring * 1.7) + (index * 0.03)
                r = (ring + _hash_noise(index, 3) * 0.55) * spiral_step
                if r > radius:
                    continue
                jx = (_hash_noise(index, 1) - 0.5) * spiral_step * 0.7
                jy = (_hash_noise(index, 2) - 0.5) * spiral_step * 0.7
                px = jx + r * math.cos(theta)
                py = jy + r * math.sin(theta)
                if math.hypot(px, py) > radius:
                    continue
                density = max(0.0, 1.0 - r / radius)
                rn = r / radius if radius else 0.0
                ang = math.atan2(py, px)
                dots.append(
                    (
                        center_x + px,
                        center_y + py,
                        density,
                        rn,
                        math.cos(ang),
                        math.sin(ang),
                        math.sin(2.0 * ang),
                        math.cos(2.0 * ang),
                        math.sin(3.0 * ang),
                        math.cos(3.0 * ang),
                        _hash_noise(index, 0),
                    )
                )
                index += 1
            if index >= max_dots:
                break

        self._dots = dots
        self._build_glow_cache(radius)

    def _build_glow_cache(self, radius):
        """Пре-рендерит мягкое свечение в QImage один раз на resize.

        Кадры рисуют кэш целиком (быстрый blit) вместо дорогого
        QRadialGradient на каждой отрисовке.
        """
        size = int(radius * 2) + 4
        if size < 8:
            self._glow_cache = None
            self._glow_size = 0
            return

        glow = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        glow.fill(QColor(0, 0, 0, 0))
        painter = QPainter(glow)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = size / 2.0
        grad = QRadialGradient(cx, cy, size / 2.0)
        grad.setColorAt(0.0, QColor(255, 50, 66, 255))
        grad.setColorAt(0.35, QColor(230, 28, 44, 200))
        grad.setColorAt(0.6, QColor(170, 16, 30, 80))
        grad.setColorAt(0.8, QColor(90, 8, 16, 22))
        grad.setColorAt(1.0, QColor(40, 2, 8, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(cx, cy), size / 2.0, size / 2.0)
        painter.end()

        self._glow_cache = glow
        self._glow_size = size

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw(painter)

    def _draw(self, painter):
        """Рисует сферу на переданном painter (выносим для тестирования)."""
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return

        base, amp, speed, deform, rim = self._params
        t = self._phase * math.tau

        center_x, center_y = w / 2.0, h / 2.0
        radius = min(w, h) * 0.42

        speech_boost = amp * self._audio_level * 0.6

        # Мягкое внешнее свечение (bloom) вокруг всей сферы.
        breath = 0.5 + 0.5 * math.sin(t * 0.5)
        glow_alpha = max(0.0, base * 1.2 - 0.30)
        if self._glow_cache is not None:
            painter.setOpacity(min(1.0, glow_alpha))
            painter.drawImage(
                QPointF(center_x - self._glow_size / 2.0, center_y - self._glow_size / 2.0),
                self._glow_cache,
            )
            painter.setOpacity(1.0)

        # Кольцо dialogue mode + мягкий внешний halo.
        if self._dialogue_glow > 0.015:
            pulse = 0.7 + 0.3 * math.sin(t * 1.1)
            ring_alpha = int(160 * self._dialogue_glow * pulse)
            ring_radius = radius * 1.32 * (1.0 + 0.022 * math.sin(t * 0.8))
            painter.setPen(QPen(QColor(255, 70, 88, ring_alpha), 2.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(center_x, center_y), ring_radius, ring_radius)

            # Мягкое красное свечение сразу за границей сферы.
            halo_alpha = int(42 * self._dialogue_glow * pulse)
            halo = QRadialGradient(center_x, center_y, radius * 1.45)
            halo.setColorAt(0.78, QColor(0, 0, 0, 0))
            halo.setColorAt(1.0, QColor(255, 55, 72, halo_alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(center_x, center_y), radius * 1.45, radius * 1.45)

            painter.setPen(Qt.PenStyle.NoPen)

        # Фазы нескольких независимых волн.
        wave_dir = t * 0.35
        cwd = math.cos(wave_dir)
        swd = math.sin(wave_dir)
        t05c = math.cos(t * 0.5)
        t05s = math.sin(t * 0.5)
        t065c = math.cos(t * 0.65)
        t065s = math.sin(t * 0.65)
        t12c = math.cos(t * 1.2)
        t12s = math.sin(t * 1.2)
        deform_amp = deform * radius * 0.09

        # Точки крошечные — AA им не нужен; glow и кольцо рисуются выше.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Скорость волн: temporal-компонента домножается для заметного движения.
        speed_t = speed * 3.2

        for x, y, density, rn, cos_a, sin_a, sin_2a, cos_2a, sin_3a, cos_3a, jitter in self._dots:
            if density <= 0.02:
                continue

            # Волна a: вращающийся фронт (cos(ang - wave_dir) разложен).
            cosa = cwd * cos_a + swd * sin_a
            wave_a = math.sin(rn * 6.0 - t * speed_t + 1.7 * cosa)

            # Волна b: поперечная (sin(2ang + t*0.5) разложен).
            sin2 = t05c * sin_2a + t05s * cos_2a
            wave_b = math.sin(rn * 9.0 - t * speed_t * 0.78 + 3.0 * sin2)

            # Волна c: угловая, затухает к центру.
            sin3 = t065c * sin_3a + t065s * cos_3a
            wave_c = sin3 * (1.0 - rn)

            # Волна d: быстрая мелкая «рябь» — движение по всей поверхности.
            sin12 = t12c * cos_a + t12s * sin_a
            wave_d = math.sin(rn * 13.0 - t * speed_t * 1.6 + 2.4 * sin12) * 0.5

            flow = (wave_a + wave_b + wave_c + wave_d) / 4.0

            # Яркий «световой поток»: бегущее пятно по поверхности — главное
            # видимое движение, создающее ощущение живого энергетического тела.
            sweep_dir = t * 0.9
            swc = math.cos(sweep_dir) * cos_a + math.sin(sweep_dir) * sin_a
            sweep = 0.5 + 0.5 * math.sin(rn * 2.5 - t * speed_t * 0.9 + 2.0 * swc)

            # Детерминированная «зернистость» поверхности.
            grain = math.sin(t * 0.5 + jitter * math.tau)

            intensity = (
                base
                + amp * (0.38 * flow + 0.40 * sweep + 0.22 * grain)
                + speech_boost
            )

            # Дыхание границы: мягкая деформация радиуса.
            deform_wave = math.sin(t * 0.5 + rn * 4.0)
            edge = 1.0 - max(0.0, rn - (1.0 - 0.45 * deform_wave))
            edge = min(1.0, edge * 2.4)

            brightness = max(0.0, min(1.0, intensity))
            # Кривая яркости: быстрее вспыхивают пики.
            core = brightness * brightness
            fade = edge * edge * (1.0 - rim * rn)

            if fade < 0.04:
                continue

            # «Переливание»: на пиках волн цвет теплеет (оранжево-красный),
            # в провалах остаётся глубоким багровым.
            warm = max(0.0, flow) * (0.5 + 0.5 * sweep)
            red = int(58 + 190 * core + 30 * warm)
            green = int(9 + 46 * core + 50 * warm)
            blue = int(13 + 42 * core + 26 * warm)
            red = min(255, red)
            green = min(255, green)
            blue = min(255, blue)
            alpha = int(255 * fade * (0.22 + 0.78 * brightness))

            dot_radius = max(0.7, 2.4 * fade * (0.55 + 1.15 * brightness))

            # Слегка деформируем положение по вертикали — «дышит» весь объём.
            py = y - deform_wave * deform_amp

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(red, green, blue, alpha))
            painter.drawEllipse(QPointF(x, py), dot_radius, dot_radius)


def _hash_noise(index, salt):
    value = math.sin(index * 12.9898 + salt * 78.233) * 43758.5453
    return value - math.floor(value)