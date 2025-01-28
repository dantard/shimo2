import time

from PyQt5.QtCore import QTimer, pyqtSignal


class Effect(QTimer):
    done = pyqtSignal(object)

    def __init__(self, pixmap, value):
        super().__init__()
        self.pixmap = pixmap
        self.value = value
        self.timeout.connect(self.effect)

    def effect(self):
        pass


class BlurInEffect(Effect):
    def effect(self):
        value = self.value.get_value()
        self.pixmap.setOpacity(self.pixmap.opacity() + (value if value > 0 else 250) / 250)
        if self.pixmap.opacity() >= 1:
            self.stop()
            self.done.emit(self)


class Choose(Effect):
    def __init__(self, func):
        super().__init__(None, func)
        self.setSingleShot(True)

    def effect(self):
        if self.value():
            self.done.emit(self)
        else:
            self.setSingleShot(True)
            self.start(1000)


class ZoomInEffect(Effect):
    def effect(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        zoom = self.pixmap.scale()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setScale(zoom + self.value.get_value() / 1000)
        if w * zoom >= self.pixmap.scene().width() and h * zoom >= self.pixmap.scene().height():
            self.stop()
            self.done.emit(self)


class BlurOutEffect(Effect):
    def effect(self):
        value = self.value.get_value()
        if value > 0:
            self.pixmap.setOpacity(self.pixmap.opacity() - self.value.get_value() / 250)
            if self.pixmap.opacity() <= 0:
                self.stop()
                self.done.emit(self)
        else:
            self.pixmap.setOpacity(1)
            self.stop()
            self.done.emit(self)


class WaitEffect(Effect):
    def __init__(self, a, b):
        super().__init__(a, b)
        self.started_at = None

    def start(self, msec: int, begin=True) -> None:
        super().start(msec)
        if begin:
            self.started_at = time.time()

    def get_started_at(self):
        return self.started_at

    def effect(self):
        self.stop()
        self.started_at = None
        self.done.emit(self)
