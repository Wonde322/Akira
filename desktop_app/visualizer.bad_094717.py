import math

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class HalftoneWidget(QWidget):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    DISABLED = "disabled"

    clicked = Signal()

    STATE = {
        IDLE: (0.55, 0.55),
        LISTENING: (0.78, 0.85),
        THINKING: (0.90, 1.05),
        SPEAKING: (1.00, 1.25),
        DISABLED: (0.10, 0.18),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self.IDLE
        self._energy = 0.55
        self._audio = 0.0
        self._dialogue = 0.0
        self._dialogue_target = 0.0

        # Два экземпляра одной геометрии.
        self._phase_a = 0.0
        self._phase_b = 2.71
        self._rotation_a = 0.0
        self._rotation_b = 1.83

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ------------------------------------------------------------
    # API, который уже использует MainWindow
    # ------------------------------------------------------------

    def set_state(self, state):
        self._state = state if state in self.STATE else self.IDLE
        self.update()

    def state(self):
        return self._state

    def set_dialogue(self, enabled):
        self._dialogue_target = 1.0 if enabled else 0.0

    def set_audio_level(self, level):
        self._audio = max(0.0, min(1.0, float(level)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    # ------------------------------------------------------------
    # animation
    # ------------------------------------------------------------

    def _tick(self):
        target_energy, speed = self.STATE[self._state]
        target_energy += self._audio * 0.25

        self._energy += (target_energy - self._energy) * 0.075
        self._dialogue += (
            self._dialogue_target - self._dialogue
        ) * 0.08

        self._audio *= 0.94

        self._phase_a += 0.018 * speed
        self._phase_b += 0.013 * speed

        self._rotation_a += 0.0045 * speed
        self._rotation_b -= 0.0031 * speed

        self.update()

    # ------------------------------------------------------------
    # deterministic procedural noise
    # ------------------------------------------------------------

    @staticmethod
    def noise(n):
        x = math.sin(n * 12.9898 + 78.233) * 43758.5453123
        return x - math.floor(x)

    @classmethod
    def smooth_noise(cls, x, seed):
        i = math.floor(x)
        f = x - i
        a = cls.noise(i + seed * 17)
        b = cls.noise(i + 1 + seed * 17)
        f = f * f * (3.0 - 2.0 * f)
        return a + (b - a) * f

    @classmethod
    def profile(cls, angle, phase, energy, seed):
        """
        Профиль одной энергетической поверхности.

        Важное отличие от предыдущих вариантов:
        пики не накладываются сверху на кольцо.
        Они являются частью радиального профиля самой поверхности.
        """

        u = angle / math.tau

        # Большие медленно бегущие деформации.
        n1 = cls.smooth_noise(
            u * 7.0 + phase * 0.55,
            seed,
        )

        n2 = cls.smooth_noise(
            u * 13.0 - phase * 0.85,
            seed + 11,
        )

        wave = (
            math.sin(angle * 2.0 + phase * 1.1)
            * 0.035
            + math.sin(angle * 3.0 - phase * 0.73)
            * 0.028
            + math.sin(angle * 5.0 + phase * 1.61)
            * 0.018
        )

        organic = (
            (n1 - 0.5) * 0.055
            + (n2 - 0.5) * 0.030
        )

        # Нерегулярные энергетические языки.
        spikes = 0.0

        for k in range(6):
            center = (
                cls.noise(seed * 31 + k * 17) * math.tau
                + phase * (
                    0.10
                    + k * 0.021
                )
            )

            width = (
                0.025
                + cls.noise(seed * 43 + k * 7)
                * 0.065
            )

            d = abs(
                math.atan2(
                    math.sin(angle - center),
                    math.cos(angle - center),
                )
            )

            if d < width:
                q = 1.0 - d / width
                strength = (
                    0.07
                    + cls.noise(seed * 61 + k * 5)
                    * 0.14
                )
                spikes += (
                    q ** 2.5
                    * strength
                    * energy
                )

        return 1.0 + wave + organic + spikes

    # ------------------------------------------------------------
    # 3D projection
    # ------------------------------------------------------------

    @staticmethod
    def rotate_y(v, angle):
        x, y, z = v
        c = math.cos(angle)
        s = math.sin(angle)
        return (
            x * c + z * s,
            y,
            -x * s + z * c,
        )

    @staticmethod
    def rotate_x(v, angle):
        x, y, z = v
        c = math.cos(angle)
        s = math.sin(angle)
        return (
            x,
            y * c - z * s,
            y * s + z * c,
        )

    @staticmethod
    def project(v, cx, cy, scale):
        x, y, z = v

        return QPointF(
            cx + x * scale,
            cy - y * scale,
        )

    def ring_surface(
        self,
        phase,
        rotation,
        tilt_x,
        tilt_y,
        radius,
        band,
        energy,
        seed,
        segments=180,
    ):
        """
        ПЛОСКАЯ энергетическая лента.

        Это намеренно НЕ тор и НЕ трубка.
        Кольцо состоит из широкой поверхности между двумя
        независимыми рваными краями.

        Затем вся поверхность наклоняется в 3D.
        """

        verts = []

        for i in range(segments):
            theta = math.tau * i / segments

            # Общая форма кольца.
            base = self.profile(
                theta,
                phase,
                energy,
                seed,
            )

            # Внешний край.
            outer_noise = (
                self.smooth_noise(
                    i * 0.055
                    + phase * 0.32,
                    seed + 100,
                )
                - 0.5
            )

            outer = (
                radius * base
                + band * 0.50
                + outer_noise * band * 0.55
            )

            # Внутренний край.
            inner_noise = (
                self.smooth_noise(
                    i * 0.071
                    - phase * 0.27,
                    seed + 200,
                )
                - 0.5
            )

            inner = (
                radius * base
                - band * 0.50
                + inner_noise * band * 0.35
            )

            # Редкие большие языки В САМOЙ ПЛОСКОСТИ.
            # Они вытягивают край радиально, а не создают
            # вертикальные зубцы поверх тора.
            for k in range(4):
                center = (
                    self.noise(seed * 91 + k * 37)
                    * math.tau
                    + phase * (
                        0.08
                        + k * 0.017
                    )
                )

                d = abs(
                    math.atan2(
                        math.sin(theta - center),
                        math.cos(theta - center),
                    )
                )

                width = (
                    0.025
                    + self.noise(
                        seed * 113 + k * 19
                    ) * 0.045
                )

                if d < width:
                    q = 1.0 - d / width

                    # Острый, но органичный пик.
                    spike = (
                        q ** 2.2
                        * band
                        * (
                            0.8
                            + self.noise(
                                seed * 137 + k * 23
                            ) * 1.8
                        )
                        * energy
                    )

                    outer += spike

            # Край кольца лежит в локальной XY-плоскости.
            # Никакой толщины по Z.
            outer_v = (
                math.cos(theta) * outer,
                math.sin(theta) * outer,
                0.0,
            )

            inner_v = (
                math.cos(theta) * inner,
                math.sin(theta) * inner,
                0.0,
            )

            # Наклон всей ПЛОСКОСТИ.
            outer_v = self.rotate_x(
                outer_v,
                tilt_x,
            )
            outer_v = self.rotate_y(
                outer_v,
                tilt_y,
            )
            outer_v = self.rotate_y(
                outer_v,
                rotation,
            )

            inner_v = self.rotate_x(
                inner_v,
                tilt_x,
            )
            inner_v = self.rotate_y(
                inner_v,
                tilt_y,
            )
            inner_v = self.rotate_y(
                inner_v,
                rotation,
            )

            verts.append(
                self.project(
                    outer_v,
                    0,
                    0,
                    1.0,
                )
            )

            verts.append(
                self.project(
                    inner_v,
                    0,
                    0,
                    1.0,
                )
            )

        return verts, segments, 2

    # ------------------------------------------------------------
    # colour
    # ------------------------------------------------------------

    @staticmethod
    def colour(t, alpha):
        """
        Палитра берётся из GIF:
        white -> pink -> red -> cyan/green -> pink.
        """

        t %= 1.0

        stops = [
            (0.00, (255, 245, 248)),
            (0.18, (255, 155, 190)),
            (0.38, (255, 45, 80)),
            (0.54, (255, 205, 110)),
            (0.67, (125, 235, 185)),
            (0.79, (120, 205, 255)),
            (0.91, (255, 90, 155)),
            (1.00, (255, 245, 248)),
        ]

        for i in range(len(stops) - 1):
            p1, c1 = stops[i]
            p2, c2 = stops[i + 1]

            if p1 <= t <= p2:
                q = (t - p1) / (p2 - p1)

                return QColor(
                    int(c1[0] + (c2[0] - c1[0]) * q),
                    int(c1[1] + (c2[1] - c1[1]) * q),
                    int(c1[2] + (c2[2] - c1[2]) * q),
                    int(alpha),
                )

        return QColor(255, 100, 150, int(alpha))

    # ------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        self.draw_scene(painter)

    def draw_scene(self, painter):
        w = self.width()
        h = self.height()

        if w < 50 or h < 50:
            return

        cx = w * 0.5
        cy = h * 0.50

        # ========================================================
        # ДВА ОДИНАКОВЫХ КОЛЬЦА
        #
        # Внешнее:
        #   крупнее
        #   примерно 50° к горизонтали
        #
        # Внутреннее:
        #   меньше
        #   примерно 70°
        # ========================================================

        rings = [
            {
                "radius": min(w, h) * 0.235,
                "band": min(w, h) * 0.050,
                "tilt_x": math.radians(48),
                "tilt_y": math.radians(-7),
                "phase": self._phase_a,
                "rotation": self._rotation_a,
                "energy": self._energy,
                "seed": 17,
                "alpha": 0.88,
            },
            {
                "radius": min(w, h) * 0.160,
                "band": min(w, h) * 0.042,
                "tilt_x": math.radians(70),
                "tilt_y": math.radians(9),
                "phase": self._phase_b,
                "rotation": self._rotation_b,
                "energy": self._energy * 0.92,
                "seed": 53,
                "alpha": 0.78,
            },
        ]

        surfaces = []

        for ring in rings:
            verts, segments, width = self.ring_surface(
                ring["phase"],
                ring["rotation"],
                ring["tilt_x"],
                ring["tilt_y"],
                ring["radius"],
                ring["band"],
                ring["energy"],
                ring["seed"],
            )

            # Добавляем центр экрана.
            verts = [
                QPointF(
                    p.x() + cx,
                    p.y() + cy,
                )
                for p in verts
            ]

            surfaces.append(
                (
                    ring,
                    verts,
                    segments,
                    width,
                )
            )

        # Сортируем не идеально физически, но достаточно,
        # чтобы задний слой чаще рисовался первым.
        surfaces.reverse()

        # ========================================================
        # Рисуем поверхности полосами.
        # ========================================================

        for ring, verts, segments, width in surfaces:
            self.draw_surface(
                painter,
                ring,
                verts,
                segments,
                width,
            )

        # ========================================================
        # Очень лёгкое свечение вокруг всей конструкции.
        # ========================================================

        if self._energy > 0.15:
            painter.setBrush(Qt.BrushStyle.NoBrush)

            for mul, alpha in (
                (1.0, 16),
                (1.08, 10),
                (1.17, 5),
            ):
                painter.setPen(
                    QPen(
                        QColor(
                            255,
                            45,
                            90,
                            int(
                                alpha
                                * self._energy
                            ),
                        ),
                        2.0,
                    )
                )

                painter.drawEllipse(
                    QPointF(cx, cy),
                    min(w, h) * 0.26 * mul,
                    min(w, h) * 0.14 * mul,
                )

    def draw_surface(
        self,
        painter,
        ring,
        verts,
        segments,
        width,
    ):
        """
        Рисуем широкую плоскую аннулярную поверхность.
        Каждый сегмент — четырёхугольник между внешним
        и внутренним краем.
        """

        energy = ring["energy"]
        alpha_base = ring["alpha"]

        for i in range(segments):
            ni = (i + 1) % segments

            outer_a = verts[i * 2]
            inner_a = verts[i * 2 + 1]

            outer_b = verts[ni * 2]
            inner_b = verts[ni * 2 + 1]

            path = QPainterPath()
            path.moveTo(outer_a)
            path.lineTo(outer_b)
            path.lineTo(inner_b)
            path.lineTo(inner_a)
            path.closeSubpath()

            # Живая цветовая текстура.
            t = (
                i / segments
                + ring["phase"] * 0.045
            )

            pulse = (
                0.72
                + 0.28
                * math.sin(
                    ring["phase"] * 3.0
                    + i * 0.17
                )
            )

            color = self.colour(
                t,
                175
                * alpha_base
                * energy
                * pulse,
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)

            # Полупрозрачные внутренние потоки.
            for layer in range(3):
                q = (
                    0.22
                    + layer * 0.28
                )

                ax = (
                    outer_a.x()
                    * (1.0 - q)
                    + inner_a.x() * q
                )
                ay = (
                    outer_a.y()
                    * (1.0 - q)
                    + inner_a.y() * q
                )

                bx = (
                    outer_b.x()
                    * (1.0 - q)
                    + inner_b.x() * q
                )
                by = (
                    outer_b.y()
                    * (1.0 - q)
                    + inner_b.y() * q
                )

                flow = (
                    0.5
                    + 0.5
                    * math.sin(
                        i * 0.23
                        + ring["phase"] * 2.7
                        + layer
                    )
                )

                painter.setPen(
                    QPen(
                        QColor(
                            255,
                            225,
                            240,
                            int(
                                24
                                + 38
                                * flow
                                * energy
                            ),
                        ),
                        1.0,
                    )
                )

                painter.drawLine(
                    QPointF(ax, ay),
                    QPointF(bx, by),
                )

        # Горячий рваный внешний край.
        outer = [
            verts[i * 2]
            for i in range(segments)
        ]

        path = QPainterPath()
        path.moveTo(outer[0])

        for p in outer[1:]:
            path.lineTo(p)

        path.closeSubpath()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                QColor(
                    255,
                    75,
                    105,
                    int(
                        175
                        * energy
                        * alpha_base
                    ),
                ),
                1.4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )

        painter.drawPath(path)

        # Внутренний край слабее.
        inner = [
            verts[i * 2 + 1]
            for i in range(segments)
        ]

        path = QPainterPath()
        path.moveTo(inner[0])

        for p in inner[1:]:
            path.lineTo(p)

        path.closeSubpath()

        painter.setPen(
            QPen(
                QColor(
                    255,
                    130,
                    160,
                    int(
                        105
                        * energy
                        * alpha_base
                    ),
                ),
                1.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )

        painter.drawPath(path)

        # Яркие живые участки.
        for i in range(0, segments, 11):
            idx = (
                i
                + int(
                    ring["phase"] * 10
                )
            ) % segments

            p = verts[idx * 2]

            pulse = (
                0.5
                + 0.5
                * math.sin(
                    ring["phase"] * 4.0
                    + i * 1.7
                )
            )

            painter.setPen(
                QPen(
                    QColor(
                        255,
                        235,
                        245,
                        int(
                            100
                            + 100
                            * pulse
                            * energy
                        ),
                    ),
                    2.0 + pulse,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )

            painter.drawPoint(p)

        if self._dialogue > 0.01:
            painter.setPen(
                QPen(
                    QColor(
                        255,
                        80,
                        100,
                        int(
                            45
                            * self._dialogue
                        ),
                    ),
                    2.0,
                )
            )
            painter.drawPath(path)

