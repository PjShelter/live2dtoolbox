import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QListWidgetItem, QHBoxLayout, QPushButton, QVBoxLayout, QListWidget, QDialog, \
    QDialogButtonBox


class FileSelectionDialog(QDialog):
    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要添加的动作/表情文件")
        self.setMinimumSize(400, 400)
        self.selected_files = []

        layout = QVBoxLayout()
        self.list_widget = QListWidget()

        files = []
        for root, _, filenames in os.walk(folder_path):
            for f in filenames:
                if f.lower().endswith((".mtn", ".exp.json", ".motion3.json", ".exp3.json")):
                    full_path = os.path.join(root, f)
                    try:
                        rel_path = os.path.relpath(full_path, folder_path)
                    except ValueError:
                        rel_path = os.path.basename(full_path)
                    files.append(rel_path)

        files.sort()
        for f in files:
            item = QListWidgetItem(f)
            item.setCheckState(Qt.Checked)
            self.list_widget.addItem(item)

        layout.addWidget(QLabel(f"文件夹: {folder_path}"))
        layout.addWidget(self.list_widget)

        # ✅ 添加全选 / 全不选按钮
        select_buttons = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_deselect_all = QPushButton("全不选")
        select_buttons.addWidget(btn_select_all)
        select_buttons.addWidget(btn_deselect_all)
        layout.addLayout(select_buttons)

        btn_select_all.clicked.connect(self.select_all)
        btn_deselect_all.clicked.connect(self.deselect_all)

        # ✅ OK / Cancel 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)
        self.setLayout(layout)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)

    def get_selected_files(self):
        return [
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        ]
