"""Original vector garden artwork: biomorphic crops and ink constellations."""
import math
import time
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QLinearGradient, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QPushButton, QWidget, QSizePolicy
from ocusense.core.garden import PLANTS
from .. import theme
from .artwork import draw_star
from .garden_coins import draw_coin


def ink(p, fill=None, width=2):
    p.setPen(QPen(theme.color(theme.INK), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(theme.color(fill) if fill else Qt.BrushStyle.NoBrush)


def leaf(p, x, y, flip=1):
    path = QPainterPath(QPointF(x, y))
    path.cubicTo(x + 33 * flip, y - 38, x + 42 * flip, y + 8, x, y)
    ink(p, theme.GREEN, 1.6)
    p.drawPath(path)


def crop(p, key, stage, x=130, y=114, scale=1):
    p.save()
    p.translate(x, y)
    p.scale(scale, scale)
    if key in ('carrot', 'lettuce', 'pumpkin') and stage >= 2:
        # Ground crops grow out of the soil, rather than hanging on stems.
        if key == 'carrot':
            for dx in (-18, 14):
                ink(p, '#EE922D', 1.7)
                root = QPainterPath(QPointF(dx-13, -13))
                root.cubicTo(dx-17, -36, dx+19, -35, dx+13, -13)
                root.lineTo(dx, 12); root.closeSubpath()
                p.drawPath(root)
                leaf(p, dx, -26, -1); leaf(p, dx, -26, 1)
                p.setPen(QPen(QColor('#A96027'), 1.3))
                p.drawLine(QPointF(dx-9,-14),QPointF(dx+2,-14))
                p.drawLine(QPointF(dx-4,-4),QPointF(dx+4,-4))
        elif key == 'lettuce':
            for dx, dy, r, color in ((-19,-17,23,'#468C46'),(19,-18,25,'#62A94D'),(0,-36,24,'#79B951'),(0,-10,29,'#8FC65B')):
                ink(p,color,1.5); p.drawEllipse(QPointF(dx,dy),r,r)
            ink(p,'#AEDC70',1.5)
            path=QPainterPath(QPointF(0,9))
            path.cubicTo(-34,-5,-15,-47,0,-23)
            path.cubicTo(20,-48,35,-4,0,9)
            p.drawPath(path)
            ink(p,None,1.3); p.drawLine(QPointF(0,5),QPointF(0,-17))
        else:
            leaf(p,-17,-5,-1); leaf(p,19,-8,1)
            radius=24 if stage==2 else 34
            ink(p,'#E88627',2); p.drawEllipse(QPointF(0,-22),radius,radius*.91)
            ink(p,'#F8A037',1.4); p.drawEllipse(QPointF(0,-22),radius*.64,radius*.91)
            ink(p,'#FFB13D',1.1); p.drawEllipse(QPointF(0,-22),radius*.3,radius*.91)
            ink(p,'#397C47',2)
            p.drawRoundedRect(QRectF(-4,-radius-29,9,16),3,3)
        p.restore()
        return
    ink(p, None, 2.4)
    stem = QPainterPath(QPointF(0, 14))
    stem.cubicTo(-8, -5, 8, -35, -4, -57)
    p.drawPath(stem)
    leaf(p, 0, -7, -1)
    leaf(p, 1, -22)
    if stage >= 1:
        leaf(p, -4, -43, -1)
        leaf(p, 1, -4)
    if stage >= 2:
        for dx, dy in ((-29, -29), (24, -43), (2, -60)):
            if stage == 2:
                ink(p, theme.PAPER, 1)
                for a in range(0, 360, 72):
                    p.drawEllipse(QPointF(dx + math.cos(math.radians(a)) * 7, dy + math.sin(math.radians(a)) * 7), 5, 5)
                ink(p, theme.GOLDEN, 1)
                p.drawEllipse(QPointF(dx, dy), 4, 4)
                continue
            ink(p, PLANTS[key].color)
            if key in ('strawberry', 'carrot'):
                path = QPainterPath(QPointF(dx - 14, dy - 10))
                path.cubicTo(dx - 24, dy + 2, dx - 5, dy + 24, dx, dy + 28)
                path.cubicTo(dx + 8, dy + 19, dx + 25, dy - 11, dx - 14, dy - 10)
                p.drawPath(path)
                if key == 'strawberry':
                    p.setPen(QPen(theme.color(theme.GOLDEN), 2.4))
                    for sx, sy in ((-5, 0), (5, 4), (0, 13)):
                        p.drawPoint(QPointF(dx + sx, dy + sy))
            elif key == 'lettuce':
                for ox, oy in ((-8, 0), (8, -4), (0, 7)):
                    ink(p, '#78A25B', 1.5)
                    p.drawEllipse(QPointF(dx + ox, dy + oy), 15, 16)
                ink(p, None, 1)
                p.drawArc(QRectF(dx - 9, dy - 5, 20, 22), 30 * 16, 260 * 16)
            else:
                p.drawEllipse(QPointF(dx, dy), 18 if key == 'pumpkin' else 14, 17)
                if key == 'pumpkin':
                    ink(p, None, 1)
                    p.drawEllipse(QPointF(dx, dy), 8, 17)
                if key == 'blueberry':
                    draw_star(p, dx, dy - 5, 4, theme.INK, 1.2)
            ink(p, theme.GREEN, 1)
            p.drawPolygon(QPolygonF([QPointF(dx - 9, dy - 12), QPointF(dx, dy - 19), QPointF(dx + 9, dy - 11), QPointF(dx, dy - 9)]))
    p.restore()


def draw_label(p, rect, text, size, weight, color):
    """Keep text in widget pixels even when the illustrated bed stretches."""
    bounds = p.transform().mapRect(rect)
    p.save()
    p.resetTransform()
    font = theme.ui_font(size, weight)
    p.setFont(font)
    # Smaller windows still need to fit the full status in the wooden label.
    while p.fontMetrics().horizontalAdvance(text) > bounds.width() - 8 and font.pixelSize() > 10:
        font.setPixelSize(font.pixelSize() - 1)
        p.setFont(font)
    p.setPen(theme.color(color))
    p.drawText(bounds, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


def duration(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    return f'{minutes // 60}h {minutes % 60:02d}m' if minutes >= 60 else f'{minutes}m'


def flower(p, x, y, size=5):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.color('#FFF4CF'))
    for angle in range(0, 360, 72):
        a = math.radians(angle)
        p.drawEllipse(QPointF(x + math.cos(a) * size, y + math.sin(a) * size), size * .65, size * .65)
    p.setBrush(theme.color(theme.GOLDEN))
    p.drawEllipse(QPointF(x, y), size * .5, size * .5)


def bush(p, x, y, radius=25):
    p.setPen(Qt.PenStyle.NoPen)
    for dx, dy, r, color in ((0, 3, radius, '#267A54'), (-radius*.6, 0, radius*.72, '#318B55'),
                              (radius*.45, -radius*.45, radius*.8, '#489B50'), (0, -radius*.7, radius*.64, '#62AD55')):
        p.setBrush(theme.color(color))
        p.drawEllipse(QPointF(x+dx, y+dy), r, r)


class GardenSky(QWidget):
    """One continuous landscape behind the interactive raised beds."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.decorations = []
        self.setMinimumHeight(400)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 25, 25)
        p.setClipPath(clip)
        sky = QLinearGradient(0, 0, 0, 185)
        sky.setColorAt(0, QColor('#54BCEB'))
        sky.setColorAt(1, QColor('#C4EDDC'))
        p.fillRect(self.rect(), sky)
        # Clouds, distant rolling hills and a little blue river.
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, scale in ((w*.28, 49, 1), (w*.57, 27, .7), (w*.88, 64, .7)):
            p.setBrush(theme.color('#EDF9F4'))
            for dx, dy, rx, ry in ((-24, 6, 27, 12), (0, -6, 24, 23), (28, 5, 30, 13)):
                p.drawEllipse(QPointF(x+dx*scale,y+dy*scale),rx*scale,ry*scale)
        for y, color in ((120, '#7CBD80'), (144, '#A0CC6B')):
            path = QPainterPath(QPointF(-20, y))
            path.cubicTo(w*.2,y-95,w*.28,y+30,w*.48,y-10)
            path.cubicTo(w*.72,y-100,w*.81,y+10,w+20,y-65)
            path.lineTo(w+20,220); path.lineTo(-20,220); path.closeSubpath()
            p.setBrush(theme.color(color)); p.drawPath(path)
        p.setBrush(theme.color('#77CEDB'))
        river = QPainterPath(QPointF(w*.57,100))
        river.cubicTo(w*.52,129,w*.81,109,w*.69,161)
        river.lineTo(w*.85,165)
        river.cubicTo(w*.93,117,w*.6,132,w*.62,100)
        p.drawPath(river)
        grass = QLinearGradient(0, 143, 0, h)
        grass.setColorAt(0, QColor('#B5D96E')); grass.setColorAt(1, QColor('#79B94F'))
        p.fillRect(QRectF(0,160,w,h-160),grass)
        # A curved path links the beds instead of enclosing each in a UI card.
        path = QPainterPath(QPointF(20,155))
        path.cubicTo(78,230,8,h*.6,42,h-32)
        path.cubicTo(w*.25,h-18,w*.7,h-40,w+25,h-24)
        pen = QPen(QColor('#E9C987'), 35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        if self.layout():
            rows = self.layout().rowCount()
            for row in range(1, rows):
                item = self.layout().itemAtPosition(row, 0)
                if item:
                    y = item.geometry().top()-4
                    p.setPen(QPen(QColor('#DFBF79'), 18, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(QPointF(36,y),QPointF(w-25,y+3))
        # Friendly timber fence at the back of the grass patch.
        ink(p, '#C8904B', 1.5)
        p.drawRoundedRect(QRectF(0,137,w,11),4,4)
        p.drawRoundedRect(QRectF(0,155,w,9),3,3)
        for x in range(13,int(w),47):
            ink(p, '#E3AF65', 1.5)
            p.drawRoundedRect(QRectF(x,125,12,47),5,5)
            p.setPen(QPen(QColor('#F5CE8E'),2)); p.drawLine(QPointF(x+4,132),QPointF(x+4,165))
        # A cottage tucked behind the fence.
        ink(p, '#F7DC9A', 2)
        p.drawRoundedRect(QRectF(13,61,82,90),7,7)
        ink(p, '#D96B43', 2)
        p.drawPolygon(QPolygonF([QPointF(4,65),QPointF(50,19),QPointF(107,66)]))
        ink(p, '#A96735', 1.8)
        p.drawRoundedRect(QRectF(41,106,28,45),13,13)
        ink(p, '#9CDAE3', 2)
        p.drawRoundedRect(QRectF(28,74,22,22),4,4)
        p.drawLine(QPointF(39,74),QPointF(39,96)); p.drawLine(QPointF(28,85),QPointF(50,85))
        # Rounded trees, a smiling sun, and just one Miró-like star accent.
        bush(p, 4, 10, 48); bush(p,w-2,110,38)
        ink(p, '#FFD456', 1.6)
        p.drawEllipse(QPointF(w*.77,48),27,27)
        p.setPen(QPen(QColor('#FFDB61'),4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        for angle in range(0,360,45):
            a=math.radians(angle)
            p.drawLine(QPointF(w*.77+math.cos(a)*34,48+math.sin(a)*34),QPointF(w*.77+math.cos(a)*40,48+math.sin(a)*40))
        ink(p, '#65472C', 1)
        for dx in (-8,8): p.drawEllipse(QPointF(w*.77+dx,45),2,3)
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawArc(QRectF(w*.77-8,48,16,10),180*16,180*16)
        draw_star(p,w*.66,35,6,theme.COBALT,1.5)
        # Grass tufts and daisies keep the ground visibly continuous.
        for i in range(50):
            x = (i*137+17) % max(1,int(w))
            y = 184 + (i*83) % max(1,int(h-200))
            p.setPen(QPen(QColor('#66A841'),1.8))
            p.drawLine(QPointF(x-3,y-3),QPointF(x,y+2)); p.drawLine(QPointF(x,y+2),QPointF(x+4,y-4))
        for x,y in ((16,225),(w-15,290),(21,h-97),(w-25,h-58)):
            flower(p,x,y,5)
        for x in (4,w-3):
            bush(p,x,h-9,36); bush(p,x,h*.56,19)
        for i in range(5):
            x=w*.15+i*w*.17
            ink(p,'#C3B08B',.7)
            p.drawEllipse(QPointF(x,h-28+(i%2)*7),12,6)
        if 'flowers' in self.decorations:
            for i in range(9): flower(p,65+i*(w-130)/8,h-10,5)
        if 'mobile' in self.decorations:
            ink(p,None,1.3); p.drawLine(QPointF(w*.49,0),QPointF(w*.49,53))
            draw_star(p,w*.49,55,8,theme.VERMILION,1.5)
        p.end()


class GardenPlot(QPushButton):
    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.plot = None
        self.animations = True
        self.effect = None
        self.effect_started = 0
        self.decorations = []
        self.setStyleSheet("QPushButton { min-height: 235px; max-height: 235px; min-width: 170px; padding: 0; border: none; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def celebrate(self, effect):
        self.effect, self.effect_started = effect, time.monotonic()
        self.update()

    def paintEvent(self, event):
        if self.plot is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 270, self.height() / 235)
        now = time.time()
        state = self.plot.state(now)
        ready = state == 'READY_TO_HARVEST'
        # Transparent hit target: beds sit directly on the shared lawn.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(52, 97, 36, 60))
        p.drawEllipse(QRectF(15, 136, 245, 65))
        if self.underMouse() or ready or self.hasFocus():
            p.setBrush(QColor(255, 224, 87, 105))
            p.drawRoundedRect(QRectF(10, 47, 251, 151), 24, 24)
        if self.hasFocus():
            p.setPen(QPen(theme.color(theme.COBALT), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(8, 39, 255, 185), 20, 20)
        ink(p, '#C48A49', 2.4)
        p.drawPolygon(QPolygonF([QPointF(38, 78), QPointF(233, 78), QPointF(257, 166), QPointF(16, 166)]))
        ink(p, '#725037', 2)
        p.drawPolygon(QPolygonF([QPointF(47, 87), QPointF(224, 87), QPointF(243, 153), QPointF(30, 153)]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#8F6644'))
        for i in range(16):
            p.drawEllipse(QPointF(46+(i*43)%182,100+(i*17)%43),4,2)
        ink(p, '#DDA65E', 2.4)
        p.drawPolygon(QPolygonF([QPointF(16,166),QPointF(257,166),QPointF(252,195),QPointF(21,195)]))
        p.setPen(QPen(QColor('#AD773E'),1.5))
        p.drawLine(QPointF(25,177),QPointF(246,177))
        p.drawLine(QPointF(26,187),QPointF(93,187))
        if self.plot.plant:
            growth = self.plot.growth(now)
            stage = min(3, int(growth * 4)) if state in ('GROWING', 'READY_TO_HARVEST') else 1
            elapsed = time.monotonic() - self.effect_started
            bounce = -math.sin(elapsed * 9) * 4 * max(0, 1 - elapsed / 2) if self.effect and self.animations else 0
            # Several plants per bed: full, rounded vegetable patches like the reference.
            for x, y, size in ((86,112,.78),(172,111,.82),(128,145,.95)):
                crop(p, self.plot.plant, stage, x, y + bounce, size)
        # Small wooden plant labels, rather than separate dashboard cards.
        ink(p, '#FFF0C5', 2)
        p.drawRoundedRect(QRectF(42,171,189,59),10,10)
        if state == 'NEEDS_WATER':
            ink(p, theme.COBALT, 1.4)
            drop = QPainterPath(QPointF(226, 31))
            drop.cubicTo(207, 55, 244, 58, 226, 31)
            p.drawPath(drop)
        if ready:
            draw_star(p, 52, 56, 10, theme.GOLDEN, 2.5)
            draw_star(p, 216, 83, 7, theme.VERMILION, 2)
        if 'flowers' in self.decorations:
            draw_star(p, 40, 140, 7, theme.VERMILION, 2.6)
            draw_star(p, 224, 130, 6, theme.GOLDEN, 2.6)
        title = PLANTS[self.plot.plant].name if self.plot.plant else 'An empty patch'
        draw_label(p, QRectF(43, 174, 188, 23), title, 17, QFont.Weight.Bold, theme.INK)
        text = {'EMPTY': 'Choose a seed  +', 'NEEDS_WATER': 'Ready to water', 'EXERCISING': 'Taking a little pause…',
                'READY_TO_HARVEST': f'Collect!  +{PLANTS[self.plot.plant].reward if self.plot.plant else 0} coins',
                'GROWING': f'Growing · {duration((self.plot.ready_at or now) - now)} left'}[state]
        draw_label(p, QRectF(43, 199, 188, 22), text, 13, QFont.Weight.Medium,
                   theme.COBALT if state in ('NEEDS_WATER', 'EMPTY') else theme.INK)
        if state == 'GROWING':
            p.fillRect(QRectF(65, 223, 140, 3), theme.color(theme.PAPER_DEEP))
            p.fillRect(QRectF(65, 223, 140 * self.plot.growth(now), 3), theme.color(theme.GREEN))
        age = time.monotonic() - self.effect_started
        if self.effect and age < 2.5:
            self.paint_effect(p, age if self.animations else 1)
        p.end()

    def paint_effect(self, p, age):
        if self.effect == 'water':
            ink(p, theme.COBALT if 'can' in self.decorations else theme.GOLDEN, 2)
            p.drawRoundedRect(QRectF(180, 20, 30, 24), 5, 5)
            p.drawLine(QPointF(181, 36), QPointF(166, 30))
            p.drawArc(QRectF(198, 13, 25, 25), -70 * 16, 240 * 16)
            for i in range(5):
                ink(p, theme.COBALT, 1)
                p.drawEllipse(QPointF(160 - i * 12, 45 + ((age * 60 + i * 14) % 58)), 3, 6)
        else:
            ink(p, '#C79C69', 2)
            p.drawRoundedRect(QRectF(174, 108, 48, 28), 7, 7)
            p.drawArc(QRectF(180, 91, 36, 29), 0, 180 * 16)
            # Produce travels toward the basket before the bed is replanted.
            crop(p, self.effect, 3, 130 + min(age, 1) * 68, 75 + min(age, 1) * 44, .35)
            for i in range(3):
                draw_coin(p, 70 + i * 50, 94 - ((age * 35 + i * 12) % 70), 11, -15 + i * 15)
