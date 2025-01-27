import os
import sys

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QLabel, \
    QCheckBox, QInputDialog, QFileDialog, QHBoxLayout, QProgressDialog, QComboBox, QDialogButtonBox, QLineEdit, \
    QHeaderView
from rclone_python import rclone

from rclone_python.remote_types import RemoteTypes

from progressing import Progressing


class SelectRemote(QDialog):
    def __init__(self, options, parent=None):
        super().__init__(parent)

        options.append("New")
        self.setWindowTitle("Select Remote")
        self.setGeometry(200, 200, 300, 150)

        layout = QVBoxLayout()
        # align top
        layout.setAlignment(Qt.AlignTop)

        self.comboBox = QComboBox()

        layout.addWidget(QLabel("Select Remote"))
        layout.addWidget(self.comboBox)

        self.path_comboBox = QComboBox()
        self.path_comboBox.addItems(
            ["album", "shared-album", "media/by-year"])

        layout.addWidget(QLabel("Select Path"))
        layout.addWidget(self.path_comboBox)

        self.line_edit = QLineEdit()
        self.label = QLabel("New remote name")

        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)
        self.line_edit.textChanged.connect(self.on_text_changed)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        self.comboBox.currentTextChanged.connect(self.on_combo_box_changed)
        self.comboBox.addItems(options)
        self.setLayout(layout)

    def on_text_changed(self, text):
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(text != "")

    def on_combo_box_changed(self, text):
        if text == "New":
            self.line_edit.setVisible(True)
            self.label.setVisible(True)
            self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(self.line_edit.text() != "")
        else:
            self.line_edit.setVisible(False)
            self.label.setVisible(False)
            self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(True)

        QApplication.processEvents()
        QTimer.singleShot(0, self.adjustSize)

    def get_remote_name(self):
        return self.line_edit.text()

    def get_selected(self):
        return self.comboBox.currentText()

    def get_path(self):
        return self.path_comboBox.currentText()

class RemoteDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Tree Widget Dialog")
        self.db = db

        # Create a QVBoxLayout
        layout = QVBoxLayout()

        # Create a QTreeWidget
        self.treeWidget = QTreeWidget()
        self.treeWidget.setHeaderLabels(["Name", "Enable", "Count"])
        self.treeWidget.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        self.treeWidget.itemSelectionChanged.connect(self.selection_changed)

        header = self.treeWidget.header()
        #header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # Add the QTreeWidget to the layout
        layout.addWidget(self.treeWidget)

        # Create buttons
        buttonBox1 = QPushButton("Ok")
        buttonBox1.clicked.connect(self.accept)
        buttonBox2 = QPushButton("Add Remote")
        buttonBox2.clicked.connect(self.add_remote)
        buttonBox3 = QPushButton("Add Folder")
        buttonBox3.clicked.connect(self.add_folder)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_remote)
        self.remove_button.setEnabled(False)

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.update_remote)
        self.update_button.setEnabled(False)

        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)

        # Add buttons to layout

        layout2 = QHBoxLayout()
        layout2.addWidget(buttonBox3)
        layout2.addWidget(buttonBox2)
        layout2.addWidget(self.remove_button)
        layout2.addWidget(self.update_button)
        layout.addLayout(layout2)
        layout.addWidget(buttonBox1)
        # layout.addWidget(cancelButton)
        # self.treeWidget.itemClicked.connect(self.item_clicked)

        self.setMinimumHeight(800)
        # Set the layout for the dialog
        self.setLayout(layout)
        self.populate()

    def selection_changed(self):
        selected = self.treeWidget.selectedItems()
        self.remove_button.setEnabled(len(selected) == 1 and selected[0].parent() is None)
        self.update_button.setEnabled(len(selected) == 1 and selected[0].parent() is None)

    def remove_remote(self):
        selected = self.treeWidget.selectedItems()
        if len(selected) == 1:
            if selected[0].parent() is None:
                remote = selected[0].text(0)
                self.db.remove_remote(remote)
                self.populate()

    def add_remote(self):
        dialog = SelectRemote(rclone.get_remotes(), self)
        if dialog.exec_():
            remote = dialog.get_selected()
            if remote == "New":
                remote_name = dialog.get_remote_name().replace(":", "")
                rclone.create_remote(remote_name, RemoteTypes.google_photos)
                remote = remote_name + ":"
            path = dialog.get_path()
            print("rerer", remote, path)
            self.db.add_remote(remote + path)
            self.pd = Progressing(self, title="Syncing")

            def update():
                self.db.update_remote(remote + path)
                self.populate()

            self.pd.start(update)

    def update_remote(self):
        selected = self.treeWidget.selectedItems()
        if len(selected) == 1:
            if selected[0].parent() is None:
                remote = selected[0].text(0)
                self.pd = Progressing(self, title="Syncing")

                def update():
                    self.db.update_remote(remote)
                    self.populate()

                self.pd.start(update)

    def populate(self):
        self.treeWidget.clear()
        for remote in self.db.get_remotes():
            item = QTreeWidgetItem([remote, "",""])
            self.treeWidget.addTopLevelItem(item)

            cb = QCheckBox()
            cb.setContentsMargins(15, 0, 0, 0)
            self.treeWidget.setItemWidget(item, 1, cb)
            cb.stateChanged.connect(lambda state, item=item: self.check_all(item))
            all_active = True
            for remote, title, active in self.db.get_albums(remote):
                count = self.db.count(remote, title)
                album_item = QTreeWidgetItem([title, "", str(count)])
                item.addChild(album_item)
                album_item.setCheckState(1, Qt.Checked if active else Qt.Unchecked)
                all_active = all_active and active

            cb.setCheckState(Qt.Checked if all_active else Qt.Unchecked)
        self.treeWidget.expandAll()

    def check_all(self, item):
        for i in range(item.childCount()):
            item.child(i).setCheckState(1, Qt.Checked if self.sender().isChecked() else Qt.Unchecked)

    def get_result(self):
        result = {}
        for i in range(self.treeWidget.topLevelItemCount()):
            remote = self.treeWidget.topLevelItem(i).text(0)
            result[remote] = []
            for j in range(self.treeWidget.topLevelItem(i).childCount()):
                album = self.treeWidget.topLevelItem(i).child(j).text(0)
                active = self.treeWidget.topLevelItem(i).child(j).checkState(1) == Qt.Checked
                result[remote].append((album, active))
        return result

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.db.add_folder(folder)
            self.db.update_folder(folder)
            self.populate()


'''
if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = MyDialog()
    dialog.exec_()
'''
