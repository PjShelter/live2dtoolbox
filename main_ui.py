import sys
import os
import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QListWidget, QDialogButtonBox, QListWidgetItem, QDialog,
    QStackedLayout, QComboBox, QPushButton
)

from pages.batch_tool_page import BatchToolPage
from pages.color_match_page import ColorMatchPage
from pages.import_table_page import ImportTablePage
from pages.jsonl_generator_page import JsonlGeneratorPage
from version_info import check_for_update_gui

CONFIG_PATH = "config.json"


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

        # OK / Cancel 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)
        self.setLayout(layout)

    def get_selected_files(self):
        return [
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        ]


class Float2Encoder(json.JSONEncoder):
    def iterencode(self, o, _one_shot=False):
        for s in super().iterencode(o, _one_shot=_one_shot):
            yield s.replace(".0,", ".00,").replace(".0}", ".00}")
            yield s


def format_transform_code(params: dict) -> str:
    def fmt(v):
        if isinstance(v, float):
            return round(v, 2)
        return v

    fixed = {k: fmt(v) for k, v in params.items()}
    rgb_only = {k: v for k, v in fixed.items() if k.startswith("color")}
    full_line = f'setTransform:{json.dumps(fixed, separators=(",", ":"), ensure_ascii=False)} -target=bg-main -duration=0 -next;'
    rgb_line = f'setTransform:{json.dumps(rgb_only, separators=(",", ":"), ensure_ascii=False)} -target=bg-main -duration=0 -next;'
    note = "\u26a0\ufe0f 完整参数匹配可能存在偏差，仅 RGB 值较为稳定"
    return f"{full_line}\n{rgb_line}\n{note}"


class ToolBox(QWidget):
    def __init__(self):
        super().__init__()
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")

        icon_path = os.path.join(base_path, "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print("⚠️ icon.png 图标未找到！")
        self.setWindowTitle("Live2D 工具箱 - 东山燃灯")
        self.resize(1000, 700)
        self.setMinimumSize(900, 600)

        # 当前主题标志（0: 默认玻璃风, 1: 粉蓝爱祥风）
        self.current_theme_index = 0
        self.theme_files = ["style", "style_pinkblue"]
        self.theme_names = ["玻璃风", "粉蓝风"]


        # 页面初始化
        self.page_color_match = ColorMatchPage()
        self.page_batch_tool = BatchToolPage()
        self.page_jsonl = JsonlGeneratorPage()
        self.page_import = ImportTablePage()

        # 页面栈
        self.stack = QStackedLayout()
        self.stack.addWidget(self.page_color_match)
        self.stack.addWidget(self.page_batch_tool)
        self.stack.addWidget(self.page_jsonl)
        self.stack.addWidget(self.page_import)


        self.theme_button = QPushButton("切换主题：银灰")
        self.theme_button.setFixedWidth(120)
        self.theme_button.clicked.connect(self.toggle_theme)

        # 左侧菜单栏
        self.menu = QListWidget()
        self.menu.setFixedWidth(140)
        self.menu.addItems([
            "🌈 切换主题",
            "⬆️ 检查更新",
            "🎨 色彩匹配",
            "🧰 live2d工具部分",
            "📦 生成 jsonl",
            "📊 IMPORT 参数表"
        ])
        self.menu.currentRowChanged.connect(self.switch_page)
        # 检查更新按钮
        self.update_button = QPushButton("检查更新")
        self.update_button.setFixedWidth(120)
        self.update_button.clicked.connect(lambda: check_for_update_gui(self))


        # 左侧垂直布局
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.menu)
        left_layout.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setFixedWidth(150)

        # 总布局
        main_layout = QHBoxLayout()
        main_layout.addWidget(left_widget)
        main_layout.addLayout(self.stack)
        self.setLayout(main_layout)

        self.apply_theme(self.theme_files[self.current_theme_index])

    def switch_page(self, index):
        if index == 0:
            self.toggle_theme()
            self.menu.setCurrentRow(-1)
        elif index == 1:
            check_for_update_gui(self)
            self.menu.setCurrentRow(-1)
        else:
            self.stack.setCurrentIndex(index - 2)
    def apply_theme(self, theme_name):
        path = os.path.join("resource", f"{theme_name}.qss")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print(f"找不到样式文件: {path}")

    def toggle_theme(self):
        self.current_theme_index = (self.current_theme_index + 1) % len(self.theme_files)
        self.apply_theme(self.theme_files[self.current_theme_index])
        self.theme_button.setText(f"切换主题：{self.theme_names[self.current_theme_index]}")




if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ToolBox()
    window.show()
    sys.exit(app.exec_())
