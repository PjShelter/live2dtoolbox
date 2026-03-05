import sys
import os
import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QCloseEvent
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QListWidget, QDialogButtonBox, QListWidgetItem, QDialog,
    QStackedLayout, QComboBox, QPushButton
)

from utils.common import save_config, load_config, get_resource_path

from pages.WmdlConverterPage import WmdlConverterPage
from pages.OpacityPresetPage import OpacityPresetPage
from pages.batch_tool_page import BatchToolPage
from pages.import_table_page import ImportTablePage
from pages.jsonl_editor_page import JsonlEditorPage
from pages.jsonl_generator_page import JsonlGeneratorPage
from pages.part_editor_page import PartEditorPage
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
        self.page_batch_tool = BatchToolPage()
        self.page_jsonl = JsonlGeneratorPage()
        self.page_jsonl_editor=JsonlEditorPage()
        self.page_import = ImportTablePage()
        self.page_part_editor = PartEditorPage()
        self.page_wmdl = WmdlConverterPage()
        self.page_opacity_preset = OpacityPresetPage()
        
        # 将主窗口引用传递给需要预览功能的页面
        self.page_jsonl_editor.set_main_window(self)
        self.page_opacity_preset.set_main_window(self)
        self.page_part_editor.set_main_window(self)

        # 页面栈
        self.stack = QStackedLayout()
        self.stack.addWidget(self.page_batch_tool)
        self.stack.addWidget(self.page_part_editor)
        self.stack.addWidget(self.page_jsonl)
        self.stack.addWidget(self.page_jsonl_editor)
        self.stack.addWidget(self.page_import)
        self.stack.addWidget(self.page_wmdl)
        self.stack.addWidget(self.page_opacity_preset)

        self.theme_button = QPushButton("切换主题：银灰")
        self.theme_button.setFixedWidth(120)
        self.theme_button.clicked.connect(self.toggle_theme)

        # 左侧菜单栏
        self.menu = QListWidget()
        self.menu.addItems([
            "🌈 切换主题",
            "⬆️ 检查更新",
            "🧰 live2d工具部分",
            "🧩 略爱区编辑器",
            "📦 生成 jsonl",
            "✏️ 编辑 JSONL",
            "📊 IMPORT 参数表",
            "🔄 WMDL 转换",
            "🪞 一键生成拼好模"
        ])
        self.menu.itemClicked.connect(self.on_menu_item_clicked)
        
        # 加载上次选择的页面（必须在 menu 和 stack 创建之后）
        self.load_last_selected_page()
        # 检查更新按钮
        self.update_button = QPushButton("检查更新")
        self.update_button.setFixedWidth(120)
        self.update_button.clicked.connect(lambda: check_for_update_gui(self))


        # 左侧垂直布局

        # 左侧垂直布局
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)  # ✔ 取消内边距
        left_layout.setSpacing(0)  # ✔ 取消间距
        # 让 menu 以 stretch=1 撑满
        left_layout.addWidget(self.menu, 1)
        # left_layout.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setFixedWidth(200)  # 只固定外层宽度

        stack_container = QWidget()
        stack_container.setLayout(self.stack)

        # 总布局
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(left_widget)  # 左：定宽
        main_layout.addWidget(stack_container)  # 右：自适应
        main_layout.setStretch(0, 0)  # 左栏不拉伸（定宽）
        main_layout.setStretch(1, 1)  # 右侧内容拉伸
        self.setLayout(main_layout)

        self.apply_theme(self.theme_files[self.current_theme_index])

    def on_menu_item_clicked(self, item):
        idx = self.menu.row(item)
        if idx == 0:  # 🌈 切换主题
            self.toggle_theme()
            # 清空选择，防止焦点返回时又选中第 0 行
            self.menu.blockSignals(True)
            self.menu.setCurrentRow(3)
            self.menu.clearSelection()
            self.menu.blockSignals(False)
            return

        if idx == 1:  # ⬆️ 检查更新
            check_for_update_gui(self)
            self.menu.blockSignals(True)
            self.menu.clearSelection()
            self.menu.blockSignals(False)
            return

        # 其它项是页面：按 (idx - 2) 对应 stack
        page_index = idx - 2
        self.stack.setCurrentIndex(page_index)
        # 保存当前选择的页面
        self.save_selected_page(page_index)

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
        path = get_resource_path(os.path.join("resource", f"{theme_name}.qss"))
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print(f"找不到样式文件: {path}")

    def toggle_theme(self):
        self.current_theme_index = (self.current_theme_index + 1) % len(self.theme_files)
        self.apply_theme(self.theme_files[self.current_theme_index])
        self.theme_button.setText(f"切换主题：{self.theme_names[self.current_theme_index]}")

    def disable_main_window(self):
        """禁用主窗口的所有操作"""
        self.setEnabled(False)
        # 禁用菜单栏
        self.menu.setEnabled(False)
        # 禁用所有页面
        for i in range(self.stack.count()):
            widget = self.stack.widget(i)
            if widget:
                widget.setEnabled(False)
    
    def enable_main_window(self):
        """启用主窗口的所有操作"""
        self.setEnabled(True)
        # 启用菜单栏
        self.menu.setEnabled(True)
        # 启用所有页面
        for i in range(self.stack.count()):
            widget = self.stack.widget(i)
            if widget:
                widget.setEnabled(True)
    
    def save_selected_page(self, page_index: int):
        """保存当前选择的页面索引到 config.json"""
        save_config({"last_selected_page": page_index})
    
    def load_last_selected_page(self):
        """从 config.json 加载上次选择的页面"""
        config = load_config()
        last_page = config.get("last_selected_page", 0)
        
        # 确保索引有效
        if 0 <= last_page < self.stack.count():
            self.stack.setCurrentIndex(last_page)
            # 更新菜单选中状态（菜单索引 = 页面索引 + 2）
            menu_index = last_page + 2
            if menu_index < self.menu.count():
                self.menu.setCurrentRow(menu_index)
    
    def closeEvent(self, event: QCloseEvent):
        """主窗口关闭事件，确保关闭所有预览窗口"""
        # 关闭 JSONL 编辑页面的预览窗口
        if hasattr(self.page_jsonl_editor, '_close_preview_window'):
            self.page_jsonl_editor._close_preview_window()
        
        # 关闭透明度预设页面的预览窗口
        if hasattr(self.page_opacity_preset, '_close_preview_window'):
            self.page_opacity_preset._close_preview_window()
        
        # 关闭略爱区编辑器的预览窗口
        if hasattr(self.page_part_editor, '_close_preview_window'):
            self.page_part_editor._close_preview_window()
        
        # 保存当前选择的页面
        current_index = self.stack.currentIndex()
        self.save_selected_page(current_index)
        
        # 接受关闭事件
        event.accept()




if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ToolBox()
    window.show()
    sys.exit(app.exec_())
