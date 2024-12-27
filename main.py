import os
import sys
import threading
import time
from datetime import datetime

from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QTimer, QRectF, QTime, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QMenu, QPushButton
from PyQt5.QtGui import QPixmap, QPainter, QFont
from easyconfig.EasyConfig import EasyConfig
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

    updating = pyqtSignal(str, int, int, int, int)

    def __init__(self):
        super().__init__()

        # Set the window title
        self.fullscreen_menu = None
        self.counter = 0
        self.screen_on = True
        self.update_running = False
        self.setWindowTitle("Image Viewer")
        self.config = EasyConfig()
        appearance = self.config.root().addSubSection("Appearance")

        self.cfg_show_title = appearance.addCheckbox("show_title", pretty="Show Title", default=True)
        self.cfg_title_size = appearance.addSlider("font_size", pretty="Title Font Size", default=40, min=20, max=120,
                                                   den=1, fmt="{:.0f}")

        self.cfg_show_clock = appearance.addCheckbox("show_clock", pretty="Show Clock", default=True)
        self.cfg_clock_size = appearance.addSlider("clock_size", pretty="Clock Font Size", default=40, min=20, max=120,
                                                   den=1, fmt="{:.0f}")

        self.cfg_show_tr_info = appearance.addCheckbox("show_hr_info", pretty="Show Remaining", default=True)
        self.cfg_tr_info_size = appearance.addSlider("tr_info_size", pretty="Remaining Font Size", default=40, min=20,
                                                     max=120, den=1, fmt="{:.0f}")

        animation = self.config.root().addSubSection("Animation")
        self.cfg_delay = animation.addSlider("delay", pretty="Delay", default=10, min=5, max=60, den=1, fmt="{:.0f}")
        self.cfg_zoom_type = animation.addSlider("zoom_type", pretty="Zoom Type", default=2, min=0, max=2, den=1,
                                                 fmt="{:.0f}")
        self.cfg_zoom_speed = animation.addSlider("zoom_speed", pretty="Zoom Speed", default=0, min=0, max=10, den=1,
                                                  fmt="{:.0f}")
        self.cfg_blur_in = animation.addSlider("blur_in", pretty="Blur in", default=0, min=0, max=10, den=1,
                                               fmt="{:.0f}")
        self.cfg_blur_out = animation.addSlider("blur_out", pretty="Blur out", default=0, min=0, max=10, den=1,
                                                fmt="{:.0f}")

        self.config.load("shimo.yaml")

        # Create a QGraphicsView widget
        self.view = QGraphicsView(self)
        self.view.setCursor(Qt.BlankCursor)
        self.setCentralWidget(self.view)
        #self.button = QPushButton("Click me", self)
        #self.button.clicked.connect(self.auto_update)

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
        self.index = 0
        self.elapsed = 0

        self.pixmap = self.scene.addPixmap(QPixmap())
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.time = self.scene.addSimpleText("00:00")
        self.info = self.scene.addSimpleText("")
        self.hr_info = self.scene.addSimpleText("")

        # Change clock font size and color
        print(self.cfg_clock_size.get_value())

        self.time.setFont(QFont("Arial", int(self.cfg_clock_size.get_value())))
        self.time.setBrush(Qt.white)

        self.info.setFont(QFont("Arial", 20))
        self.info.setBrush(Qt.white)

        self.hr_info.setFont(QFont("Arial", 20))
        self.hr_info.setBrush(Qt.white)

        # Change color, size and position of the title
        self.title = self.scene.addSimpleText("Image Viewer")
        self.title.setPos(20, 15)
        self.title.setFont(QFont("Arial", int(self.cfg_title_size.get_value())))
        self.title.setBrush(Qt.white)

        self.db = Database()
        self.downloader = Downloader(self.db)
        self.downloader.start()

        self.effects_timer = QTimer()
        self.effects_timer.timeout.connect(self.process)

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.auto_update)
        self.update_timer.start(1000*60*60*1)

        QTimer.singleShot(25000, self.auto_update)

        self.updating.connect(self.update_progress)

        self.choose()
        self.showFullScreen()

    def update_progress(self, name, i, n, j, m):
        if i == 0 and n == 0 and j == 0 and m == 0:
            self.info.setText("")
        else:
            self.info.setText(f"Updating {i}/{n} {j}/{m} ({name})")


    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        menu = QMenu(self)
        self.fullscreen_menu = menu.addAction("Fullscreen", self.toggle_fullscreen)
        self.fullscreen_menu.setCheckable(True)
        self.fullscreen_menu.setChecked(self.isFullScreen())

        menu.addAction("Settings", self.edit_config)
        menu.addAction("Edit remotes", self.edit_selection)
        menu.addSeparator()
        menu.addAction("Update", self.auto_update)
        menu.addAction("Shuffle", self.downloader.shuffle)
        menu.addSeparator()
        menu.addAction("Close", QApplication.exit)

        menu.exec_(event.globalPos())

    def edit_config(self):
        self.config.set_dialog_minimum_size(400,400)
        self.config.exec()
        self.config.save("shimo.yaml")

    def update_albums_async(self, result):

        def do(result1):
            self.update_running = True
            i, j = 1, 1
            for remote, vector in result1.items():
                for album, active in vector:
                    if active:
                        self.db.update_album(remote, album)
                        self.updating.emit(album, i, len(result1), j, len(vector))
                        j += 1
                    else:
                        self.db.remove_album(remote, album)

                    self.db.update_album_active(remote, album, active)
                i += 1

            self.downloader.shuffle()
            self.updating.emit("Done", 0, 0, 0, 0)
            self.update_running = False

        threading.Thread(target=do, args=(result,)).start()

    def edit_selection(self):
        dialog = RemoteDialog(self.db, self)
        status = dialog.get_result()
        if dialog.exec():
            result = dialog.get_result()
            results = {}
            for remote1, vector1 in status.items():
                updating = []
                vector2 = result.get(remote1,[])
                for i in range(len(vector1)):
                    album = vector1[i][0]
                    active1 = vector1[i][1]
                    active2 = vector2[i][1]
                    if active1 != active2:
                        updating.append((album, active2))
                results[remote1] = updating

            self.update_albums_async(results)

    def set_screen_on(self, value):
        self.screen_on = value
        if value:
            os.system("/usr/bin/tvservice -p && sudo chvt 6 && sudo chvt 7")
        else:
            os.system("/usr/bin/tvservice -o")

        print("putting screeeeeen OFFF")

    def toggle_fullscreen(self):

        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def retry(self):
        QTimer.singleShot(1000, self.choose)
        return 1000

    def choose(self):

        if self.downloader.photos_queue.empty():
            self.downloader.shuffle(False)

        # get photo index from que downloader queue (non blocking)
        index = self.downloader.get(False)
        if index is None:
            return self.retry()
        info = self.db.get_info_from_id(index)
        if info is None:
            return self.retry()
        remote, folder, file, hashed = info

        albums = self.db.get_album_from_hash(hashed)
        albums = [x[0] for x in albums]

        if file.lower().endswith(".heic"):
            file += ".jpg"

        pixmap = QPixmap("cache/" + folder + "/" + file)

        print("diocaneallora", folder, file)

        if pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
            return self.retry()

        self.set_picture(pixmap)
        self.title.setText("\n".join(albums))  # + " - " + str(self.dw.photos.qsize()) + "_" + str(index) + " - " + str(self.dw.queue.qsize()))
        self.hr_info.setText(str(self.downloader.photos_queue.qsize()))

        # delete image from disk
        os.remove("cache/" + folder + "/" + file)

        # self.db.insert_recent(index)

    def update_clock(self):

        font = self.time.font()
        font.setPointSize(int(self.cfg_clock_size.get_value()))
        self.time.setFont(font)
        self.time.setText(QTime.currentTime().toString("hh:mm"))
        self.time.setVisible(self.cfg_show_clock.get_value())

        font = self.title.font()
        font.setPointSize(int(self.cfg_title_size.get_value()))
        self.title.setFont(font)
        self.title.setVisible(self.cfg_show_title.get_value())

        font = self.hr_info.font()
        font.setPointSize(int(self.cfg_tr_info_size.get_value()))
        self.hr_info.setFont(font)
        self.hr_info.setVisible(self.cfg_show_tr_info.get_value())

        self.set_time_pos()

        if datetime.now().hour == 23 and datetime.now().minute == 0 and self.screen_on:
            self.set_screen_on(False)

        if datetime.now().hour == 7 and datetime.now().minute == 0 and not self.screen_on:
            self.set_screen_on(True)

    def auto_update(self):
        print("Starting auto update")
        remotes = self.db.get_remotes()

        data = {}
        for remote in remotes:
            print("Update remote", remote, "albums")
            self.db.update_remote(remote)

            data[remote] = []
            albums = self.db.get_albums(remote)
            for _, title, active in albums:
                if active:
                    print("Adding album", title, "to update list")
                    data[remote].append((title, active))

        self.update_albums_async(data)

    def effect_blur_in(self):
        self.pixmap.setOpacity(self.pixmap.opacity() + self.cfg_blur_in.get_value() / 250)
        return self.pixmap.opacity() >= 1

    def effect_zoom_in(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        zoom = self.pixmap.scale()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setScale(zoom + self.cfg_zoom_speed.get_value() / 1000)
        return w * zoom > self.width() and h * zoom > self.height()

    def effect_blur_out(self):
        self.pixmap.setOpacity(self.pixmap.opacity() - self.cfg_blur_out.get_value() / 250)
        return self.pixmap.opacity() <= 0

    def set_picture(self, picture):

        self.pixmap.setPixmap(picture)
        self.center_image()

        w_ratio = self.scene.sceneRect().width() / self.pixmap.pixmap().width()
        h_ratio = self.scene.sceneRect().height() / self.pixmap.pixmap().height()

        self.state = ImageWindow.BEGIN

        if self.cfg_zoom_type.get_value() in [0, 2]:
            self.pixmap.setScale(min(w_ratio, h_ratio))
        elif self.cfg_zoom_type.get_value() == 1:
            self.pixmap.setScale(max(w_ratio, h_ratio))

        if self.cfg_blur_in.get_value() > 0:
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
        # set hr_info on the top right corner
        self.hr_info.setPos(self.scene.sceneRect().width() - self.hr_info.boundingRect().width() - 20, 20)

    def center_image(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setPos(self.scene.sceneRect().width() / 2 - self.pixmap.pixmap().width() / 2,
                           self.scene.sceneRect().height() / 2 - self.pixmap.pixmap().height() / 2)

    def process(self):
        if self.state == ImageWindow.BEGIN:
            self.state = ImageWindow.BLUR_IN

        elif self.state == ImageWindow.BLUR_IN:
            if self.cfg_blur_in.get_value() > 0:
                if self.effect_blur_in():
                    self.state = ImageWindow.ZOOM_IN
            else:
                self.state = ImageWindow.ZOOM_IN

        elif self.state == ImageWindow.ZOOM_IN:
            if self.cfg_zoom_type.get_value() == 2:
                if self.effect_zoom_in():
                    self.state = ImageWindow.WAITING
                    self.elapsed = time.time()
            else:
                self.elapsed = time.time()
                self.state = ImageWindow.WAITING

        elif self.state == ImageWindow.WAITING:
            if time.time() - self.elapsed > self.cfg_delay.get_value() and not self.downloader.queue.empty():
                self.state = ImageWindow.BLUR_OUT

        elif self.state == ImageWindow.BLUR_OUT:
            if self.cfg_blur_out.get_value() > 0:
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
