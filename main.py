import sys

from PyQt5.QtCore import Qt, QTimer, QRectF, QTime
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PyQt5.QtGui import QPixmap, QPainter, QFont

from database import Database
from downloader import Downloader


class ImageWindow(QMainWindow):
    BLUR_IN = 0
    ZOOM_IN = 1
    BLUR_OUT = 3
    WAITING = 2
    DONE = 4

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
        # set view background color
        self.view.setBackgroundBrush(Qt.black)

        self.setMinimumSize(200, 100)

        # Load an image using QPixmap
        self.images = []
        self.images.append(QPixmap("/home/danilo/Desktop/danilo.jpg"))
        self.images.append(QPixmap("/home/danilo/Desktop/2002-3-Festa Domenico-Imagen 080.jpg"))
        self.images.append(QPixmap("/home/danilo/Desktop/Immagine 320.jpg"))

        self.state = ImageWindow.BLUR_IN
        self.blur_in = True
        self.blur_out = True
        self.zoom_type = 2
        self.index = 0
        self.elapsed = 0

        self.pixmap = self.scene.addPixmap(self.images[0])
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.pixmap.setScale(0.1)
        self.zoom()

        self.time = self.scene.addSimpleText("00:00")
        # Change clock font size and color
        self.time.setFont(QFont("Arial", 20))
        self.time.setBrush(Qt.white)

        # Change color, size and position of the title
        self.title = self.scene.addSimpleText("Image Viewer")
        self.title.setPos(10, 10)
        self.title.setFont(QFont("Arial", 20))
        self.title.setBrush(Qt.white)

        self.zoom_timer = QTimer()
        self.zoom_timer.timeout.connect(self.zoom)

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(900)

        self.db = Database()
        self.dw = Downloader(self.db)
        self.dw.start()

        QTimer.singleShot(2000, self.choose)

    def choose(self):
        index = self.dw.get(False)
        if index:
            folder, file = self.db.get_name_from_id(index)
            print("riiririr", "cache/" + folder + "/" + file)
            if file!="":
                self.set_picture(QPixmap("cache/" + folder + "/" + file))
            else:
                QTimer.singleShot(1000, self.choose)
        else:
            QTimer.singleShot(1000, self.choose)

    def update_clock(self):
        self.time.setText(QTime.currentTime().toString("hh:mm"))

    def set_picture(self, picture):

        self.pixmap.setPixmap(picture)
        self.center_image()

        w_ratio = self.scene.sceneRect().width() / self.pixmap.pixmap().width()
        h_ratio = self.scene.sceneRect().height() / self.pixmap.pixmap().height()

        if self.zoom_type in [0, 2]:
            self.pixmap.setScale(min(w_ratio, h_ratio))
        elif self.zoom_type == 1:
            self.pixmap.setScale(max(w_ratio, h_ratio))

        if self.blur_in:
            self.pixmap.setOpacity(0)
        self.elapsed = 0
        self.zoom_timer.start(20)

    def zoom(self):
        if self.state == ImageWindow.BLUR_IN:
            if self.blur_in:
                self.pixmap.setOpacity(self.pixmap.opacity() + 0.01)
                if self.pixmap.opacity() >= 1:
                    self.state = ImageWindow.ZOOM_IN
            else:
                self.state = ImageWindow.ZOOM_IN

        elif self.state == ImageWindow.ZOOM_IN:
            if self.zoom_type == 2:
                w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
                zoom = self.pixmap.scale()
                self.pixmap.setTransformOriginPoint(w / 2, h / 2)
                self.pixmap.setScale(zoom + 0.01)

                if w * zoom > self.width() and h * zoom > self.height():
                    self.state = ImageWindow.WAITING
            else:
                self.state = ImageWindow.WAITING

        elif self.state == ImageWindow.WAITING:
            self.elapsed += 1
            if self.elapsed >= 200:
                self.state = ImageWindow.BLUR_OUT

        elif self.state == ImageWindow.BLUR_OUT:
            if self.blur_out:
                self.pixmap.setOpacity(self.pixmap.opacity() - 0.01)
                if self.pixmap.opacity() <= 0:
                    self.state = ImageWindow.DONE
            else:
                self.state = ImageWindow.DONE

        elif self.state == ImageWindow.DONE:
            self.zoom_timer.stop()
            self.state = ImageWindow.BLUR_IN
            QTimer.singleShot(2000, self.choose)

    def resizeEvent(self, a0) -> None:
        self.scene.setSceneRect(0, 0, self.width(), self.height())
        self.center_image()
        self.set_time_pos()

    def set_time_pos(self):
        self.time.setPos(self.scene.sceneRect().width() - self.time.boundingRect().width() - 10,
                         self.scene.sceneRect().height() - self.time.boundingRect().height() - 10)

    def center_image(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
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
