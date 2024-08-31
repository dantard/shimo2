import sys
import threading
import time

from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QTimer, QRectF, QTime, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QMenu
from PyQt5.QtGui import QPixmap, QPainter, QFont
from rclone_python import rclone
from rclone_python.remote_types import RemoteTypes

from database import Database
from dialogs import RemoteDialog, SelectRemote
from downloader import Downloader
from progressing import Progressing


class ImageWindow(QMainWindow):
    BEGIN = 0
    BLUR_IN = 1
    ZOOM_IN = 2
    WAITING = 3
    BLUR_OUT = 4
    DONE = 255

    updating = pyqtSignal(str, int,int,int,int)

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
        self.view.setFrameShape(QGraphicsView.NoFrame)

        self.setMinimumSize(800, 600)

        self.state = ImageWindow.BEGIN
        self.blur_in = False
        self.blur_out = False
        self.zoom_type = 0
        self.index = 0
        self.elapsed = 0

        self.pixmap = self.scene.addPixmap(QPixmap())
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.time = self.scene.addSimpleText("00:00")
        self.info = self.scene.addSimpleText("")
        # Change clock font size and color
        self.time.setFont(QFont("Arial", 40))
        self.time.setBrush(Qt.white)

        self.info.setFont(QFont("Arial", 20))
        self.info.setBrush(Qt.white)

        # Change color, size and position of the title
        self.title = self.scene.addSimpleText("Image Viewer")
        self.title.setPos(20, 15)
        self.title.setFont(QFont("Arial", 40))
        self.title.setBrush(Qt.white)

        self.db = Database()
        self.dw = Downloader(self.db)
        self.dw.start()

        self.effects_timer = QTimer()
        self.effects_timer.timeout.connect(self.process)

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.updating.connect(self.update_progress)

        self.choose()

    def update_progress(self, name, i, n, j, m):
        if i == 0 and n == 0 and j == 0 and m == 0:
            self.info.setText("")
        else:
            self.info.setText(f"Updating {i}/{n} {j}/{m} ({name})")

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        menu = QMenu(self)
        menu.addAction("Fullscreen", self.toggle_fullscreen)
        # menu.addAction("Settings", self.edit_config)
        menu.addAction("Edit remotes", self.edit_selection)
        menu.addSeparator()

        menu.exec_(event.globalPos())

    def edit_selection(self):
        dialog = RemoteDialog(self.db, self)
        if dialog.exec():
            result = dialog.get_result()

            def update_async(result1):
                i, j = 1, 1
                for remote, vector in result1.items():
                    for album, active in vector:

                        print("updating album", album, "active", active)
                        if active:
                            self.updating.emit(album, i, len(result1), j, len(vector))
                            self.db.update_album(remote, album)
                            j += 1
                        else:
                            self.db.remove_album(remote, album)

                        self.db.update_album_active(remote, album, active)

                    i += 1

                self.dw.shuffle()
                self.updating.emit("Done", 0,0,0,0)

            threading.Thread(target=update_async, args=(result,)).start()

    # def add_remotes(self):
    #     dialog = SelectRemote(rclone.get_remotes(), self)
    #     if dialog.exec_():
    #         remote = dialog.get_selected()
    #         if remote == "New":
    #             remote_name = dialog.get_remote_name().replace(":", "")
    #             rclone.create_remote(remote_name, RemoteTypes.google_photos)
    #             remote = remote_name + ":"
    #         self.pd = Progressing(self, title="Syncing")
    #         self.pd.start(lambda : self.db.update_remote(remote, 0))
    #
    #         #dialog = RemoteDialog(self.db, self)
    #         #dialog.exec_()

    def toggle_fullscreen(self):

        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def retry(self):
        QTimer.singleShot(0, self.choose)

    def choose(self):
        print("choose")

        if self.dw.photos.empty():
            self.dw.shuffle(False)

        index = self.dw.get(False)
        if index is None:
            return self.retry()

        info = self.db.get_name_from_id(index)

        if info is None:
            return self.retry()

        remote, folder, file, hash = info
        albums = self.db.get_album_from_hash(hash)

        if file.lower().endswith(".heic"):
            file += ".jpg"

        pixmap = QPixmap("cache/" + folder + "/" + file)

        if pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
            return self.retry()

        print("set kimage", folder, file, index)
        self.set_picture(pixmap)
        self.title.setText("\n".join(albums) + " - " + str(self.dw.photos.qsize()) + "_" + str(index) + " - " + str(self.dw.queue.qsize()))
        self.db.insert_recent(index)


    def update_clock(self):
        self.time.setText(QTime.currentTime().toString("hh:mm"))

    def effect_blur_in(self):
        self.pixmap.setOpacity(self.pixmap.opacity() + 0.01)
        return self.pixmap.opacity() >= 1

    def effect_zoom_in(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        zoom = self.pixmap.scale()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setScale(zoom + 0.001)
        return w * zoom > self.width() and h * zoom > self.height()

    def effect_blur_out(self):
        self.pixmap.setOpacity(self.pixmap.opacity() - 0.01)
        return self.pixmap.opacity() <= 0

    def set_picture(self, picture):

        self.pixmap.setPixmap(picture)
        self.center_image()

        w_ratio = self.scene.sceneRect().width() / self.pixmap.pixmap().width()
        h_ratio = self.scene.sceneRect().height() / self.pixmap.pixmap().height()

        self.state = ImageWindow.BEGIN

        if self.zoom_type in [0, 2]:
            self.pixmap.setScale(min(w_ratio, h_ratio))
        elif self.zoom_type == 1:
            self.pixmap.setScale(max(w_ratio, h_ratio))

        if self.blur_in:
            self.pixmap.setOpacity(0)
        self.elapsed = 0
        self.effects_timer.start(20)

    def resizeEvent(self, a0) -> None:
        self.scene.setSceneRect(0, 0, self.width(), self.height())
        self.center_image()
        self.set_time_pos()

    def set_time_pos(self):
        self.time.setPos(self.scene.sceneRect().width() - self.time.boundingRect().width() - 20,
                         self.scene.sceneRect().height() - self.time.boundingRect().height() - 15)
        self.info.setPos(20, self.scene.sceneRect().height() - self.info.boundingRect().height() - 30)


    def center_image(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setPos(self.scene.sceneRect().width() / 2 - self.pixmap.pixmap().width() / 2,
                           self.scene.sceneRect().height() / 2 - self.pixmap.pixmap().height() / 2)

    def process(self):
        if self.state == ImageWindow.BEGIN:
            self.state = ImageWindow.BLUR_IN

        elif self.state == ImageWindow.BLUR_IN:
            if self.blur_in:
                if self.effect_blur_in():
                    self.state = ImageWindow.ZOOM_IN
            else:
                self.state = ImageWindow.ZOOM_IN

        elif self.state == ImageWindow.ZOOM_IN:
            if self.zoom_type == 2:
                if self.effect_zoom_in():
                    self.state = ImageWindow.WAITING
                    self.elapsed = time.time()
            else:
                self.elapsed = time.time()
                self.state = ImageWindow.WAITING

        elif self.state == ImageWindow.WAITING:
            print(time.time() - self.elapsed, self.state)
            if time.time() - self.elapsed > 2 and not self.dw.queue.empty():
                print("preeeeeeeeee")
                self.state = ImageWindow.BLUR_OUT

        elif self.state == ImageWindow.BLUR_OUT:
            if self.blur_out:
                if self.effect_blur_out():
                    self.state = ImageWindow.DONE
            else:
                self.state = ImageWindow.DONE

        elif self.state == ImageWindow.DONE:
            self.effects_timer.stop()
            self.choose()


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
