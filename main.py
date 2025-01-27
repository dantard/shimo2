import os
import sys
import threading
import time
from datetime import datetime
from datetime import time as time2
import exifread
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QTimer, QRectF, QTime, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QMenu, QPushButton, QShortcut
from PyQt5.QtGui import QPixmap, QPainter, QFont, QPen
from easyconfig.EasyConfig import EasyConfig
from rclone_python import rclone
from rclone_python.remote_types import RemoteTypes

from database import Database
from dialogs import RemoteDialog, SelectRemote
from downloader import Downloader
from progressing import Progressing


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


class Effect(QTimer):
    done = pyqtSignal(object)

    def __init__(self, pixmap, value):
        super().__init__()
        self.pixmap = pixmap
        self.value = value
        self.timeout.connect(self.effect)


class BlurInEffect(Effect):
    def effect(self):
        self.pixmap.setOpacity(self.pixmap.opacity() + self.value.get_value() / 250)
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
        self.pixmap.setOpacity(self.pixmap.opacity() - self.value.get_value() / 250)
        if self.pixmap.opacity() <= 0:
            self.stop()
            self.done.emit(self)


class WaitEffect(Effect):
    def effect(self):
        self.stop()
        self.done.emit(self)


class ImageWindow(QMainWindow):
    updating = pyqtSignal(str, int, int, int, int)

    def is_within_time_span(self, start_time, end_time, check_time=None):
        """
        Determines if a given time is within a time span.

        Args:
            start_time (time): The start of the time span.
            end_time (time): The end of the time span.
            check_time (time, optional): The time to check. Defaults to the current time.

        Returns:
            bool: True if the check_time is within the time span, False otherwise.
        """
        if check_time is None:
            check_time = datetime.now().time()

        # If the time span does not cross midnight
        if start_time <= end_time:
            return start_time <= check_time < end_time
        # If the time span crosses midnight
        else:
            return check_time >= start_time or check_time < end_time

    def __init__(self):
        super().__init__()

        # Set the window title
        self.image_info = (None, None, None, None)
        self.fullscreen_menu = None

        self.screen_on = True
        self.update_running = False
        self.setWindowTitle("Image Viewer")
        self.config = EasyConfig()

        appearance = self.config.root().addSubSection("Appearance")

        self.cfg_show_title = appearance.addCheckbox("show_title", pretty="Show Title", default=True)
        self.cfg_title_size = appearance.addSlider("font_size", pretty="Title Font Size", default=40, min=20, max=120,
                                                   den=1, fmt="{:.0f}", label_width=40)

        self.cfg_show_clock = appearance.addCheckbox("show_clock", pretty="Show Clock", default=True)
        self.cfg_show_date = appearance.addCheckbox("show_date", pretty="Show Date", default=False)
        self.cfg_clock_size = appearance.addSlider("clock_size", pretty="Clock Font Size", default=40, min=20, max=120,
                                                   den=1, fmt="{:.0f}", label_width=40)

        self.cfg_show_tr_info = appearance.addCheckbox("show_hr_info", pretty="Show Remaining", default=True)
        self.cfg_tr_info_size = appearance.addSlider("tr_info_size", pretty="Remaining Font Size", default=40, min=20,
                                                     max=120, den=1, fmt="{:.0f}", label_width=40)

        animation = self.config.root().addSubSection("Animation")
        self.cfg_delay = animation.addSlider("delay", pretty="Delay", default=10, min=5, max=60, den=1, fmt="{:.0f}",
                                             label_width=40)
        self.cfg_zoom_type = animation.addSlider("zoom_type", pretty="Zoom Type", default=2, min=0, max=2, den=1,
                                                 fmt="{:.0f}")
        self.cfg_zoom_speed = animation.addSlider("zoom_speed", pretty="Zoom Speed", default=0, min=0, max=10, den=1,
                                                  fmt="{:.0f}", label_width=40)
        self.cfg_blur_in = animation.addSlider("blur_in", pretty="Blur in", default=0, min=0, max=10, den=1,
                                               fmt="{:.0f}", label_width=40)
        self.cfg_blur_out = animation.addSlider("blur_out", pretty="Blur out", default=0, min=0, max=10, den=1,
                                                fmt="{:.0f}", label_width=40)
        self.loop_mode = animation.addCombobox("loop_mode", pretty="Loop Mode",
                                               items=["Random", "One per Album", "Complete albums"])

        self.config.load("shimo.yaml")

        # Create a QGraphicsView widget
        self.view = MyQGraphicsView(self)
        self.view.setCursor(Qt.BlankCursor)
        self.setCentralWidget(self.view)
        self.view.save.connect(lambda: self.saved_clicked(0))
        self.view.delete.connect(lambda: self.saved_clicked(1))
        self.view.moved.connect(self.mouse_moved)

        # Create a QGraphicsScene
        self.scene = QGraphicsScene(self)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.view.setScene(self.scene)
        # set view background color
        self.view.setBackgroundBrush(Qt.black)
        self.view.setFrameShape(QGraphicsView.NoFrame)

        self.setMinimumSize(800, 600)

        self.index = 0

        self.pixmap = self.scene.addPixmap(QPixmap())
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.time = self.scene.addSimpleText("00:00")
        self.time.setPen(QPen(Qt.black, 1))
        self.info = self.scene.addSimpleText("")
        self.info.setPen(QPen(Qt.black, 1))
        self.hr_info = self.scene.addSimpleText("")
        self.hr_info.setPen(QPen(Qt.black, 1))

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
        self.title.setPen(QPen(Qt.black, 1))

        self.db = Database()
        self.downloader = Downloader(self.db)
        self.downloader.set_loop_mode(self.loop_mode.get_value())
        self.downloader.start()

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        self.update_timer = QTimer()
        #self.update_timer.timeout.connect(self.auto_update)
        self.update_timer.start(1000 * 60 * 60 * 24)

        self.blur_in = BlurInEffect(self.pixmap, self.cfg_blur_in)
        self.zoom = ZoomInEffect(self.pixmap, self.cfg_zoom_speed)
        self.wait = WaitEffect(self.pixmap, self.cfg_delay)
        self.blur_out = BlurOutEffect(self.pixmap, self.cfg_blur_out)
        self.chooser = Choose(self.choose)

        effects = [self.blur_in, self.zoom, self.blur_out, self.wait, self.chooser]
        for effect in effects:
            effect.done.connect(self.effect_done)

        self.updating.connect(self.update_progress)

        # Esc to remove fullscreen
        shortcut = QShortcut(QtGui.QKeySequence("Esc"), self)
        shortcut.activated.connect(self.toggle_fullscreen)

        #QTimer.singleShot(0, self.choose)
        self.chooser.start(0)

        self.showFullScreen()

    def effect_done(self, effect):
        if effect is self.chooser:
            self.blur_in.start(10)
        elif effect == self.blur_in:
            self.zoom.start(25)
        elif effect == self.zoom:
            print("Start wait", self.cfg_delay.get_value() * 1000)
            self.wait.start(int(self.cfg_delay.get_value() * 1000))
        elif effect == self.wait:
            if self.downloader.is_empty():
                self.time.setPen(QPen(Qt.red, 2))
                self.wait.start(1000)
            else:
                self.blur_out.start(10)
                self.time.setPen(QPen(Qt.black, 1))
        elif effect == self.blur_out:
            self.chooser.start(0)

    def saved_clicked(self, i):
        remote, folder, file, hashed = self.image_info

        if i == 1:
            self.title.setPen(QPen(Qt.red, 2))
            self.downloader.play(remote, folder)
        else:
            self.db.set_saved(file, folder, i)
            self.title.setPen(QPen(Qt.green, 2))
        QTimer.singleShot(1000, lambda: self.title.setPen(QPen(Qt.black, 1)))

    #        self.db.set_saved()

    def mouse_moved(self):
        pass

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
        m1 = menu.addMenu("Play")
        remotes = self.db.get_remotes()
        for remote in remotes:
            m2 = m1.addMenu(remote)
            albums = self.db.get_albums(remote)
            count = 0
            for _, title, active in albums:
                ids = self.db.get_ids_by_album(remote, title)
                if len(ids) > 0:
                    if count % 20 == 0:
                        m3 = m2.addMenu(title)
                    action = m3.addAction(title)
                    action.triggered.connect(
                        lambda checked, remote=remote, title=title: self.downloader.play(remote, title))
                    count = count + 1

        menu.addSeparator()
        menu.addAction("Close", QApplication.exit)

        menu.exec_(event.globalPos())

    def edit_config(self):
        self.config.set_dialog_minimum_size(600, 400)
        self.config.exec()
        self.downloader.set_loop_mode(self.loop_mode.get_value())
        self.config.save("shimo.yaml")

    def extract_date_from_exif(self, image_path):
        with open(image_path, 'rb') as image_file:
            tags = exifread.process_file(image_file)
            return tags.get("EXIF DateTimeOriginal")

    def update_albums_async(self, result):

        def do(result1):
            self.update_running = True
            i, j = 1, 1
            for remote, vector in result1.items():
                for album, active in vector:
                    if active:
                        self.db.update_album(remote, album)
                        self.updating.emit(album, i, len(result1), j, len(vector))
                        QApplication.processEvents()
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
                vector2 = result.get(remote1, [])
                for i in range(len(vector1)):
                    album = vector1[i][0]
                    active1 = vector1[i][1]

                    if len(vector2) > i:
                        active2 = vector2[i][1]
                    else:
                        active2 = False

                    if active1 != active2:
                        updating.append((album, active2))
                results[remote1] = updating

            self.update_albums_async(results)

    def set_screen_power(self, value):
        self.screen_on = value
        if value:
            #os.system("xset dpms force on")  # For Linux
            os.system("/usr/bin/xrandr --output HDMI-1 --auto")#vservice -p && sudo chvt 6 && sudo chvt 7")
        else:
            #os.system("xset dpms force off")  # For Linux
            #os.system("/usr/bin/tvservice -o")
            os.system("/usr/bin/xrandr --output HDMI-1 --off")

    def toggle_fullscreen(self):

        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def choose(self):
        if self.is_within_time_span(time2(7, 0), time2(0, 6)):
            if not self.screen_on:
                self.set_screen_power(True)
        else:
            if self.screen_on:
                self.set_screen_power(False)
                self.auto_update()
            return False

        if self.downloader.photos_queue.empty():
            self.downloader.shuffle(False)
            return False

        # get photo index from que downloader queue (non blocking)
        index = self.downloader.get(False)
        if index is None:
            return False

        info = self.db.get_info_from_id(index)

        if info is None:
            return False

        remote, folder, file, hashed = info

        self.db.increment_seen(index)
        self.image_info = info

        albums = self.db.get_album_from_hash(hashed)
        albums = [x[0] for x in albums]

        if file.lower().endswith(".heic"):
            file += ".jpg"

        if not os.path.exists("cache/" + folder + "/" + file):
            return False

        image_album = "\n".join(albums)

        if self.cfg_show_date.get_value():
            exif_data = self.extract_date_from_exif("cache/" + folder + "/" + file)
            if exif_data is not None:
                exif_data = str(exif_data).split(" ")[0]
                exif_data = exif_data.replace(":", "-")
                image_album += "\n" + str(exif_data)

        pixmap = QPixmap("cache/" + folder + "/" + file)

        os.remove("cache/" + folder + "/" + file)

        if pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
            return False

        self.set_picture(pixmap, image_album)

        return True

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
            self.set_screen_power(False)

        if datetime.now().hour == 7 and datetime.now().minute == 0 and not self.screen_on:
            self.set_screen_power(True)

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

    def set_picture(self, pixmap, image_album):


        self.title.setText(image_album)
        self.hr_info.setText(str(self.downloader.photos_queue.qsize()))

        self.pixmap.setPixmap(pixmap)
        self.center_image()

        w_ratio = self.scene.sceneRect().width() / self.pixmap.pixmap().width()
        h_ratio = self.scene.sceneRect().height() / self.pixmap.pixmap().height()

        if self.cfg_zoom_type.get_value() in [0, 2]:
            self.pixmap.setScale(min(w_ratio, h_ratio))
        elif self.cfg_zoom_type.get_value() == 1:
            self.pixmap.setScale(max(w_ratio, h_ratio))
        if self.cfg_blur_in.get_value() > 0:
            self.pixmap.setOpacity(0)

    def resizeEvent(self, a0) -> None:
        self.scene.setSceneRect(0, 0, self.width(), self.height())
        self.center_image()
        self.set_time_pos()

    def set_time_pos(self):
        self.time.setPos(self.scene.sceneRect().width() - self.time.boundingRect().width() - 20,
                         self.scene.sceneRect().height() - self.time.boundingRect().height() - 15)
        self.info.setPos(20, self.scene.sceneRect().height() - self.info.boundingRect().height() - 30)
        # set hr_info in the top right corner
        self.hr_info.setPos(self.scene.sceneRect().width() - self.hr_info.boundingRect().width() - 20, 20)

    def center_image(self):
        w, h = self.pixmap.pixmap().width(), self.pixmap.pixmap().height()
        self.pixmap.setTransformOriginPoint(w / 2, h / 2)
        self.pixmap.setPos(self.scene.sceneRect().width() / 2 - self.pixmap.pixmap().width() / 2,
                           self.scene.sceneRect().height() / 2 - self.pixmap.pixmap().height() / 2)


def main():
    # Create the application
    app = QApplication(sys.argv)
    font = QFont()
    font.setPointSize(20)  # Adjust size
    app.setFont(font)

    # Create an instance of the window
    window = ImageWindow()
    window.show()

    # Start the application's event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
