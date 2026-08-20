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

    # Kept as the stable state API used by the desktop tests and by callers
    # that want deterministic animation targets.  The renderer currently uses
    # energy and animation speed, so those are the two interpolated params.
    STATE_PARAMS = {
        IDLE: (0.55, 1.00),
        LISTENING: (0.78, 1.25),
        THINKING: (0.90, 1.45),
        SPEAKING: (1.00, 1.70),
        DISABLED: (0.12, 0.35),
    }

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = self.IDLE
        self._params = list(self.STATE_PARAMS[self.IDLE])
        self._energy = self._params[0]
        self._audio = 0.0
        self._dialogue = 0.0
        self._dialogue_target = 0.0

        # _phase is retained as a compatibility alias/state hook for code that
        # drives the visualizer deterministically.  The two rings still have
        # independent phases for the actual rendering.
        self._phase = 0.0
        self._phase_a = 0.0
        self._phase_b = 2.7

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ------------------------------------------------------------
    # API
    # ------------------------------------------------------------

    def set_state(self, state):
        self._state = state if state in self.STATE_PARAMS else self.IDLE
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
        target_energy, target_speed = self.STATE_PARAMS[self._state]

        # Smoothly converge to the stable state parameters.  _params is kept
        # explicit instead of deriving values ad hoc so animation state remains
        # inspectable and deterministic between frames.
        self._params[0] += (target_energy - self._params[0]) * 0.07
        self._params[1] += (target_speed - self._params[1]) * 0.07

        self._energy = self._params[0] + self._audio * 0.20
        speed = self._params[1]

        self._dialogue += (
            self._dialogue_target
            - self._dialogue
        ) * 0.08

        self._audio *= 0.94

        self._phase += 0.020 * speed
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

    def make_ring(self, cx, cy, radius, width, angle, phase, seed, energy, segments=240):
        outer=[]
        inner=[]
        a=angle
        sa=math.sin(a)
        ca=math.cos(a)
        dz=width*2.2*sa
        for i in range(segments):
            t=math.tau*i/segments
            deform=self.organic(t,phase,seed)
            spikes=sum(self.spike(t,phase,seed,k) for k in range(5))
            profile=(1.0+deform+spikes*energy*3.5)
            ro=radius*profile+width*0.5
            ri=radius-width*0.5
            ox=math.cos(t)*ro
            oy=math.sin(t)*ro
            ix=math.cos(t)*ri
            iy=math.sin(t)*ri
            oz=-dz*0.5
            iz=dz*0.5
            yaw = math.radians(0)
            pitch = math.radians(72)
            cyaw=math.cos(yaw)
            syaw=math.sin(yaw)
            cp=math.cos(pitch)
            sp=math.sin(pitch)
            def project(x,y,z):
                x1=x*cyaw-z*syaw
                z1=x*syaw+z*cyaw
                y1=y*cp-z1*sp
                depth=y*sp+z1*cp
                k=1.0/(1.0+depth/700.0)
                return (cx+x1*k, cy-y1*k)
            px,py=project(ox,oy,oz)
            qx,qy=project(ix,iy,iz)
            outer.append(QPointF(px,py))
            inner.append(QPointF(qx,qy))
        return outer,inner

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw(painter)

    def _draw(self, painter):
        w = self.width()
        h = self.height()
        if w < 100 or h < 100:
            return
        cx = w * 0.5
        cy = h * 0.50
        size = min(w, h)
        energy = max(0.15, min(1.25, self._energy))
        outer, inner = self.make_ring(cx,cy,size * 0.235,size * 0.070,math.radians(48),self._phase_a,17,energy)
        self._draw_ring(painter,outer,inner,self._phase_a,energy,17,1.0)
        outer2, inner2 = self.make_ring(cx,cy,size * 0.225,size * 0.045,math.radians(32),self._phase_b,83,energy * 0.92)
        self._draw_ring(painter,outer2,inner2,self._phase_b,energy * 0.92,83,0.78)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255,45,75,int(18 * energy)),8.0))
        painter.drawEllipse(QPointF(cx, cy), size * 0.20, size * 0.105)

    def _draw_ring(self, painter, outer, inner, phase, energy, seed, opacity):
        if not outer or not inner:
            return
        n = min(len(outer), len(inner))
        if n < 3:
            return
        for glow_width, alpha in ((14.0,5),(8.0,9),(4.0,14)):
            path = QPainterPath()
            path.moveTo(outer[0])
            for p in outer[1:]:
                path.lineTo(p)
            path.closeSubpath()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255,45,75,int(alpha*energy*opacity)),glow_width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
        for i in range(n):
            j=(i+1)%n
            path=QPainterPath()
            path.moveTo(outer[i])
            path.lineTo(outer[j])
            path.lineTo(inner[j])
            path.lineTo(inner[i])
            path.closeSubpath()
            stripe=0.55+0.45*math.sin((i/n)*math.tau*5.0+phase*1.8+seed)
            alpha=int((42+108*stripe)*energy*opacity)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255,45,75,max(0,min(255,alpha))))
            painter.drawPath(path)
