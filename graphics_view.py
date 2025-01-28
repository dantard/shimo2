from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QGraphicsView


class MyQGraphicsView(QGraphicsView):
    save = pyqtSignal()
    delete = pyqtSignal()
    moved = pyqtSignal()

    def __init__(self, a):
        super().__init__(a)
        self.setMouseTracking(True)
        self.timer = QTimer()
        self.timer.timeout.connect(self.mouse_timer)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        is_left_side = event.x() < self.width() / 2
        if is_left_side:
            self.save.emit()
        else:
            self.delete.emit()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        super().mouseMoveEvent(a0)
        self.timer.stop()
        self.timer.start(2500)
        self.setCursor(Qt.ArrowCursor)
        self.moved.emit()

    def mouse_timer(self):
        self.timer.stop()
        self.setCursor(Qt.BlankCursor)