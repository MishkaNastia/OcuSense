"""Original gold coin artwork with raised rims and milled edges."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget
from .. import theme
from .common import label


def draw_coin(p, x, y, radius=24, angle=0):
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    p.scale(radius / 24, radius / 24)
    # The visible front edge has real thickness, with engraved vertical ridges.
    side = QPainterPath(QPointF(-24, 0))
    side.lineTo(-24, 7)
    side.cubicTo(-24, 25, 24, 25, 24, 7)
    side.lineTo(24, 0)
    side.closeSubpath()
    p.setPen(QPen(QColor('#82482F'), 1.4))
    p.setBrush(QColor('#DDA634'))
    p.drawPath(side)
    for i in range(1, 18):
        a = math.pi * i / 18
        px, py = -24 * math.cos(a), 16 * math.sin(a)
        p.setPen(QPen(QColor('#8F5230'), .8))
        p.drawLine(QPointF(px, py + .3), QPointF(px, py + 6.5))
        p.setPen(QPen(QColor('#FFE995'), .65))
        p.drawLine(QPointF(px + .65, py + .7), QPointF(px + .65, py + 6))
    p.setPen(QPen(QColor('#82482F'), 1.4))
    p.setBrush(QColor('#FFE59A'))
    p.drawEllipse(QRectF(-24, -16, 48, 32))
    p.setPen(QPen(QColor('#BA7D39'), .9))
    p.setBrush(QColor('#F2D04E'))
    p.drawEllipse(QRectF(-21.5, -13.7, 43, 27.4))
    p.setPen(QPen(QColor('#FFF3BB'), 1.1))
    p.drawArc(QRectF(-21, -13.2, 42, 26.4), 20 * 16, 145 * 16)
    p.restore()


class CoinPile(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(90, 70)
        self.setAccessibleName('Stacked gold coins')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(79, 51, 28, 25))
        p.drawEllipse(QRectF(7, 51, 78, 15))
        for x, bottom, count, radius in ((45, 39, 5, 15), (23, 49, 4, 17), (66, 50, 3, 17)):
            for level in range(count):
                draw_coin(p, x, bottom - level * 5, radius)
        draw_coin(p, 47, 54, 16, 35)
        draw_coin(p, 65, 60, 16, 20)
        p.end()


class CoinBalance(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(4)
        row.addWidget(CoinPile())
        self.amount = label('', font=theme.number_font(22))
        row.addWidget(self.amount)

    def setText(self, text):
        self.amount.setText(text)
        self.setAccessibleName('Garden balance: ' + text)


class CoinCounter(QWidget):
    """Compact game HUD: a gold medallion and an embossed numeric balance."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = '0'
        self.setFixedSize(195, 46)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def setText(self, text):
        self.text = text.removesuffix(' coins').replace(',', ' ')
        self.setAccessibleName('Garden balance: ' + text)
        width = max(195, self.fontMetrics().horizontalAdvance(self.text) + 95)
        self.setFixedWidth(width)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 8, 0, 38)
        gradient.setColorAt(0, QColor('#D9AC72'))
        gradient.setColorAt(1, QColor('#A9683B'))
        p.setPen(QPen(QColor('#8E532C'), 1.5))
        p.setBrush(gradient)
        p.drawRoundedRect(QRectF(23, 8, self.width()-25, 30), 7, 7)
        p.setPen(QPen(QColor('#EDCA8B'), 1))
        p.drawLine(QPointF(44, 10), QPointF(self.width()-9, 10))
        gold = QLinearGradient(8, 5, 37, 38)
        gold.setColorAt(0, QColor('#FFF095'))
        gold.setColorAt(.5, QColor('#F9CD42'))
        gold.setColorAt(1, QColor('#D5911D'))
        p.setBrush(gold)
        p.setPen(QPen(QColor('#9D6223'), 1.5))
        p.drawEllipse(QRectF(3, 3, 39, 39))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor('#FFF1A0'), 2))
        p.drawEllipse(QRectF(7, 7, 31, 31))
        star = QPainterPath()
        for i in range(10):
            angle = math.radians(-90+i*36)
            r = 11 if i % 2 == 0 else 5.5
            point = QPointF(22.5+math.cos(angle)*r, 22+math.sin(angle)*r)
            if i == 0: star.moveTo(point)
            else: star.lineTo(point)
        star.closeSubpath()
        p.setPen(QPen(QColor('#DB9C27'), 1))
        p.setBrush(QColor('#FFF0A1'))
        p.drawPath(star)
        p.setFont(theme.number_font(19, QFont.Weight.Bold))
        rect = QRectF(49, 8, self.width()-57, 30)
        p.setPen(QColor('#8A5328'))
        p.drawText(rect.translated(1, 1.5), Qt.AlignmentFlag.AlignCenter, self.text)
        p.setPen(QColor('#FFE15A'))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()
