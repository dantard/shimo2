import sys

from PyQt5.QtCore import Qt, QTimer, QRectF, QTime
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt5.QtGui import QPixmap, QPainter


class ImageWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set the window title
        self.setWindowTitle("Image Viewer")

        # Create a QGraphicsView widget
        self.view = QGraphicsView(self)
        self.setCentralWidget(self.view)

        # Create a QGraphicsScene
        self.scene = QGraphicsScene(self)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.view.setScene(self.scene)

        self.setMinimumSize(200, 100)

        # Load an image using QPixmap
        self.images = []
        self.images.append(QPixmap("/home/danilo/Desktop/danilo.jpg"))
        self.images.append(QPixmap("/home/danilo/Desktop/2002-3-Festa Domenico-Imagen 080.jpg"))
        self.images.append(QPixmap("/home/danilo/Desktop/Immagine 320.jpg"))

        QApplication.processEvents()
        self.index = 0

        self.pixmap = self.scene.addPixmap(self.images[0])
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.pixmap.setScale(0.1)
        self.zoom()

        self.timer = QTimer()
        self.timer.timeout.connect(self.zoom)
        self.timer.start(50)

        self.clock = QTimer()
        self.clock.timeout.connect(self.update_clock)
        self.clock.start(900)

        self.time = self.scene.addSimpleText("00:00")
        self.title = self.scene.addSimpleText("Image Viewer")
        self.title.setPos(10, 10)

    def update_clock(self):
        self.time.setText(QTime.currentTime().toString("hh:mm"))


    def zoom(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        zoom = self.pixmap.scale()

        if w * zoom > self.width() and h * zoom > self.height():
            self.pixmap.setScale(0.1)
            self.pixmap.setPixmap(self.images[self.index])
            self.index = (self.index + 1) % len(self.images)
            self.center_image()
            return

        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setScale(zoom + 0.01)

    def resizeEvent(self, a0) -> None:
        self.scene.setSceneRect(0, 0, self.width(), self.height())
        self.center_image()
        self.time.setPos(self.scene.sceneRect().width() - self.time.boundingRect().width() - 10, self.scene.sceneRect().height() -self.time.boundingRect().height()-10)

    def center_image(self):
        self.pixmap.setPos(self.scene.sceneRect().width() / 2 - self.pixmap.pixmap().width() / 2,
                           self.scene.sceneRect().height() / 2 - self.pixmap.pixmap().height() / 2)


def main():
    # Create the application
    app = QApplication(sys.argv)

    # Create an instance of the window
    window = ImageWindow()
    window.show()

    # Start the application's event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
