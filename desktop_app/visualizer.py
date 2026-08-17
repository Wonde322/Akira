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

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = self.IDLE
        self._energy = 0.55
        self._audio = 0.0
        self._dialogue = 0.0
        self._dialogue_target = 0.0

        self._phase_a = 0.0
        self._phase_b = 2.7

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ------------------------------------------------------------
    # API
    # ------------------------------------------------------------

    def set_state(self, state):
        self._state = state
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
        targets = {
            self.IDLE: (0.55, 1.0),
            self.LISTENING: (0.78, 1.25),
            self.THINKING: (0.90, 1.45),
            self.SPEAKING: (1.00, 1.70),
            self.DISABLED: (0.12, 0.35),
        }

        target, speed = targets.get(
            self._state,
            targets[self.IDLE],
        )

        target += self._audio * 0.20

        self._energy += (
            target - self._energy
        ) * 0.07

        self._dialogue += (
            self._dialogue_target
            - self._dialogue
        ) * 0.08

        self._audio *= 0.94

        self._phase_a += 0.020 * speed
        self._phase_b += 0.014 * speed

        self.update()

    # ------------------------------------------------------------
    # deterministic organic noise
    # ------------------------------------------------------------

    @staticmethod
    def noise(x):
        v = math.sin(
            x * 127.1 + 311.7
        ) * 43758.5453123
        return v - math.floor(v)

    @classmethod
    def organic(cls, theta, phase, seed):
        """
        Медленная органическая деформация.
        Не набор одинаковых зубцов.
        """

        n1 = cls.noise(
            theta * 3.7
            + phase * 0.55
            + seed
        )

        n2 = cls.noise(
            theta * 8.3
            - phase * 0.31
            + seed * 3.7
        )

        n3 = cls.noise(
            theta * 15.1
            + phase * 0.82
            + seed * 7.1
        )

        return (
            (n1 - 0.5) * 0.075
            + (n2 - 0.5) * 0.035
            + (n3 - 0.5) * 0.015
            + math.sin(
                theta * 2.0
                + phase * 0.9
            ) * 0.035
            + math.sin(
                theta * 5.0
                - phase * 0.7
            ) * 0.022
        )

    @classmethod
    def spike(cls, theta, phase, seed, index):
        """
        Редкие длинные языки.
        Они являются частью края ленты.
        """

        center = (
            cls.noise(
                seed * 19
                + index * 31
            ) * math.tau
            + phase * (
                0.09
                + index * 0.013
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
            + cls.noise(
                seed * 41
                + index * 17
            ) * 0.040
        )

        if d >= width:
            return 0.0

        q = 1.0 - d / width

        return (
            q ** 2.0
            * (
                0.10
                + cls.noise(
                    seed * 53
                    + index * 23
                ) * 0.16
            )
        )

    # ------------------------------------------------------------
    # 2D projection of the two planes
    # ------------------------------------------------------------

    def make_ring(
        self,
        cx,
        cy,
        radius,
        width,
        angle,
        phase,
        seed,
        energy,
        segments=240,
    ):
        """
        Кольцевая КОНИЧЕСКАЯ поверхность.

        Внешний радиус и внутренний радиус находятся
        на РАЗНЫХ высотах.

        Это принципиально не эллипс:
        поверхность между краями имеет настоящий наклон.
        """

        outer=[]
        inner=[]

        # угол поверхности относительно горизонтали
        a=angle
        sa=math.sin(a)
        ca=math.cos(a)

        # Высота перепада специально большая,
        # чтобы пространственную геометрию было видно.
        dz=width*2.2*sa

        for i in range(segments):
            t=math.tau*i/segments

            deform=self.organic(
                t,phase,seed
            )

            spikes=sum(
                self.spike(
                    t,phase,seed,k
                )
                for k in range(5)
            )

            # Верхняя грань получает большие энергетические пики.
            # Базовая органическая деформация остаётся прежней.
            profile=(
                1.0+
                deform+
                spikes*energy*3.5
            )

            ro=radius*profile+width*0.5
            # Нижняя грань полностью ровная — без deform и spikes.
            ri=radius-width*0.5

            # Внешний край.
            ox=math.cos(t)*ro
            oy=math.sin(t)*ro

            # Внутренний край.
            ix=math.cos(t)*ri
            iy=math.sin(t)*ri

            # --------------------------------------------------
            # НАСТОЯЩАЯ НАКЛОННАЯ ПОВЕРХНОСТЬ.
            #
            # Внешний край выше.
            # Внутренний ниже.
            # --------------------------------------------------

            # Поверхность раскрывается ВВЕРХ.
            oz=-dz*0.5
            iz=dz*0.5

            # --------------------------------------------------
            # Камера: СБОКУ + НЕМНОГО СВЕРХУ.
            # --------------------------------------------------

            # Строго сбоку, но немного выше поверхности.
            yaw = math.radians(0)
            pitch = math.radians(72)

            cyaw=math.cos(yaw)
            syaw=math.sin(yaw)

            cp=math.cos(pitch)
            sp=math.sin(pitch)

            def project(x,y,z):
                # camera yaw
                x1=x*cyaw-z*syaw
                z1=x*syaw+z*cyaw

                # camera pitch
                y1=y*cp-z1*sp
                depth=y*sp+z1*cp

                # умеренная перспектива
                k=1.0/(1.0+depth/700.0)

                return (
                    cx+x1*k,
                    cy-y1*k
                )

            px,py=project(ox,oy,oz)
            qx,qy=project(ix,iy,iz)

            outer.append(QPointF(px,py))
            inner.append(QPointF(qx,qy))

        return outer,inner

    # ------------------------------------------------------------
    # paint
    # ------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        self._draw(painter)

    def _draw(self, painter):
        w = self.width()
        h = self.height()

        if w < 100 or h < 100:
            return

        cx = w * 0.5
        cy = h * 0.50

        size = min(w, h)

        energy = max(
            0.15,
            min(1.25, self._energy),
        )

        # ========================================================
        # ВНЕШНЕЕ КОЛЬЦО
        #
        # Больше.
        # Более горизонтальное.
        # Большие пики.
        # ========================================================

        outer, inner = self.make_ring(
            cx=cx,
            cy=cy,
            radius=size * 0.235,
            width=size * 0.070,
            angle=math.radians(48),
            phase=self._phase_a,
            seed=17,
            energy=energy,
        )

        self._draw_ring(
            painter,
            outer,
            inner,
            self._phase_a,
            energy,
            17,
            1.0,
        )

        # ========================================================
        # ВНУТРЕННЕЕ КОЛЬЦО
        #
        # Меньше.
        # Более вертикальное.
        # Пики меньше.
        #
        # Именно поэтому оно визуально проходит через внешнее.
        # ========================================================

        outer2, inner2 = self.make_ring(
            cx=cx,
            cy=cy,
            radius=size * 0.225,
            width=size * 0.045,
            angle=math.radians(32),
            phase=self._phase_b,
            seed=83,
            energy=energy * 0.92,
        )

        self._draw_ring(
            painter,
            outer2,
            inner2,
            self._phase_b,
            energy * 0.92,
            83,
            0.78,
        )

        # --------------------------------------------------------
        # Very subtle central glow.
        # --------------------------------------------------------

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                QColor(
                    255,
                    45,
                    75,
                    int(
                        18 * energy
                    ),
                ),
                8.0,
            )
        )

        painter.drawEllipse(
            QPointF(cx, cy),
            size * 0.20,
            size * 0.105,
        )

    # ------------------------------------------------------------
    # ring rendering
    # ------------------------------------------------------------

    def _draw_ring(
        self,
        painter,
        outer,
        inner,
        phase,
        energy,
        seed,
        opacity,
    ):
        # make_ring() может вернуть пустые списки во время
        # промежуточного состояния/невалидной геометрии.
        # paintEvent никогда не должен падать из-за этого.
        if not outer or not inner:
            return

        n = min(len(outer), len(inner))

        if n < 3:
            return

        # --------------------------------------------------------
        # Glow behind the actual surface.
        # --------------------------------------------------------

        for glow_width, alpha in (
            (14.0, 5),
            (8.0, 9),
            (4.0, 14),
        ):
            path = QPainterPath()
            path.moveTo(outer[0])

            for p in outer[1:]:
                path.lineTo(p)

            path.closeSubpath()

            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )

            painter.setPen(
                QPen(
                    QColor(
                        255,
                        45,
                        75,
                        int(
                            alpha
                            * energy
                            * opacity
                        ),
                    ),
                    glow_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )

            painter.drawPath(path)

        # --------------------------------------------------------
        # Actual wide energy sheet.
        # --------------------------------------------------------

        for i in range(n):
            j = (i + 1) % n

            path = QPainterPath()
            path.moveTo(outer[i])
            path.lineTo(outer[j])
            path.lineTo(inner[j])
            path.lineTo(inner[i])
            path.closeSubpath()

            # Несколько бегущих цветовых зон.
            t = (
                i / n
                + phase * 0.035
            )

            r = (
                0.5
                + 0.5
                * math.sin(
                    t * math.tau * 3.0
                    - phase * 1.4
                )
            )

            g = (
                0.5
                + 0.5
                * math.sin(
                    t * math.tau * 4.0
                    + phase * 1.9
                    + 1.7
                )
            )

            b = (
                0.5
                + 0.5
                * math.sin(
                    t * math.tau * 5.0
                    - phase * 1.1
                    + 3.1
                )
            )

            # Палитра референса:
            # белый / розовый / красный /
            # жёлтый-зелёный / голубой.
            rr = int(
                225
                + 30 * r
            )

            gg = int(
                45
                + 150 * g
            )

            bb = int(
                65
                + 165 * b
            )

            alpha = int(
                105
                * energy
                * opacity
            )

            painter.setPen(
                Qt.PenStyle.NoPen
            )

            painter.setBrush(
                QColor(
                    rr,
                    gg,
                    bb,
                    alpha,
                )
            )

            painter.drawPath(path)

        # --------------------------------------------------------
        # Светлая внутренняя структура.
        # --------------------------------------------------------

        for layer in range(5):
            path = QPainterPath()

            for i in range(n):
                j = (i + 1) % n

                q = (
                    0.16
                    + layer * 0.17
                )

                ax = (
                    outer[i].x()
                    * (1.0 - q)
                    + inner[i].x() * q
                )

                ay = (
                    outer[i].y()
                    * (1.0 - q)
                    + inner[i].y() * q
                )

                bx = (
                    outer[j].x()
                    * (1.0 - q)
                    + inner[j].x() * q
                )

                by = (
                    outer[j].y()
                    * (1.0 - q)
                    + inner[j].y() * q
                )

                if i == 0:
                    path.moveTo(
                        QPointF(ax, ay)
                    )

                path.lineTo(
                    QPointF(bx, by)
                )

            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )

            painter.setPen(
                QPen(
                    QColor(
                        255,
                        210,
                        225,
                        int(
                            22
                            * energy
                            * opacity
                        ),
                    ),
                    1.0,
                )
            )

            painter.drawPath(path)

        # --------------------------------------------------------
        # Outer edge.
        # --------------------------------------------------------

        path = QPainterPath()
        path.moveTo(outer[0])

        for p in outer[1:]:
            path.lineTo(p)

        path.closeSubpath()

        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )

        painter.setPen(
            QPen(
                QColor(
                    255,
                    70,
                    105,
                    int(
                        175
                        * energy
                        * opacity
                    ),
                ),
                1.5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )

        painter.drawPath(path)

        # --------------------------------------------------------
        # Inner edge.
        # --------------------------------------------------------

        path = QPainterPath()
        path.moveTo(inner[0])

        for p in inner[1:]:
            path.lineTo(p)

        path.closeSubpath()

        painter.setPen(
            QPen(
                QColor(
                    255,
                    150,
                    180,
                    int(
                        90
                        * energy
                        * opacity
                    ),
                ),
                1.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )

        painter.drawPath(path)

        # --------------------------------------------------------
        # Hot fragments — не регулярные зубцы.
        # --------------------------------------------------------

        for k in range(18):
            idx = (
                int(
                    k * 37
                    + phase * 18
                )
                % n
            )

            p = outer[idx]

            pulse = (
                0.5
                + 0.5
                * math.sin(
                    phase * 3.7
                    + k * 1.91
                )
            )

            painter.setPen(
                QPen(
                    QColor(
                        255,
                        235,
                        245,
                        int(
                            (
                                60
                                + 100 * pulse
                            )
                            * energy
                            * opacity
                        ),
                    ),
                    1.4
                    + pulse * 1.5,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )

            painter.drawPoint(p)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])

    w = HalftoneWidget()
    w.resize(700, 700)
    w.show()

    app.exec()
