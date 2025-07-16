import log

import sys
import os
import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QFileDialog,
    QVBoxLayout, QHBoxLayout, QMessageBox, QComboBox, QTextEdit,
    QGroupBox, QLineEdit, QFormLayout, QListWidget, QAbstractItemView, QDialogButtonBox, QListWidgetItem, QDialog,
    QCheckBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PIL import Image
from live2d_tool import remove_duplicates_and_check_files, scan_live2d_directory, update_model_json_bulk, \
    batch_update_mtn_param_text
from color_transfer import match_color, extract_webgal_full_transform, visualize, plot_parameter_comparison
from version_info import check_for_update_gui
from gen_jsonl import collect_jsons_to_jsonl
CONFIG_PATH = "config.json"


def get_resource_path(relative_path):
    """兼容 PyInstaller 打包后的路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

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


class Float2Encoder(json.JSONEncoder):
    def iterencode(self, o, _one_shot=False):
        for s in super().iterencode(o, _one_shot=_one_shot):
            yield s.replace(".0,", ".00,").replace(".0}", ".00}")  # 保底小数位
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
    note = "⚠️ 完整参数匹配可能存在偏差，仅 RGB 值较为稳定"
    return f"{full_line}\n{rgb_line}\n{note}"



class ToolBox(QWidget):

    def __init__(self):
        super().__init__()
        # ✅ 设置图标（兼容打包后路径）
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
        self.resize(900, 1200)  # 初始窗口大小
        self.setMinimumSize(700, 600)  # 可选：防止太小导致排版错乱

        self.source_path = ""
        self.target_path = ""
        self.result_path = ""

        layout = QVBoxLayout()
        layout.setSpacing(12)

        top_button_layout = QHBoxLayout()

        btn_check_update = QPushButton("🔄 检查更新")
        btn_check_update.clicked.connect(lambda: check_for_update_gui(self))

        btn_show_import_table = QPushButton("📋 查看 import 参数表")
        btn_show_import_table.clicked.connect(self.show_import_table)

        top_button_layout.addWidget(btn_check_update)
        top_button_layout.addWidget(btn_show_import_table)

        layout.addLayout(top_button_layout)

        # 🎨 色彩匹配工具区域
        group_color = QGroupBox("🎨 色彩匹配工具")
        color_layout = QVBoxLayout()

        image_select_layout = QHBoxLayout()
        self.source_btn = QPushButton("选择源图像")
        self.source_btn.setMinimumWidth(160)
        self.source_btn.clicked.connect(self.choose_source)

        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(160)
        self.refresh_target_list()
        self.target_combo.currentIndexChanged.connect(self.select_target_image)

        image_select_layout.addWidget(self.source_btn)
        image_select_layout.addWidget(self.target_combo)

        preview_layout = QHBoxLayout()
        self.source_label = QLabel("源图像")
        self.source_label.setFixedSize(220, 160)
        self.target_label = QLabel("参考图像")
        self.target_label.setFixedSize(220, 160)
        self.result_label = QLabel("匹配结果")
        self.result_label.setFixedSize(220, 160)

        self.compare_btn = QPushButton("显示对比图表")
        self.compare_btn.setMinimumWidth(300)
        self.compare_btn.clicked.connect(self.show_comparison)
        color_layout.addWidget(self.compare_btn)

        preview_layout.addWidget(self.source_label)
        preview_layout.addWidget(self.target_label)
        preview_layout.addWidget(self.result_label)

        self.match_btn = QPushButton("执行色彩匹配")
        self.match_btn.setMinimumWidth(300)
        self.match_btn.clicked.connect(self.run_match)

        self.webgal_output = QTextEdit()
        self.webgal_output.setPlaceholderText("此处将显示 WebGAL 指令...")
        self.webgal_output.setMinimumHeight(60)

        color_layout.addLayout(image_select_layout)
        color_layout.addLayout(preview_layout)
        color_layout.addWidget(self.match_btn)
        color_layout.addWidget(self.webgal_output)

        group_color.setLayout(color_layout)
        layout.addWidget(group_color)

        # 🧰 Live2D 工具区域
        group_l2d = QGroupBox("🧰 Live2D 工具部分")
        l2d_layout = QVBoxLayout()

        self.scan_btn = QPushButton("扫描目录并生成 model.json")
        self.scan_btn.setMinimumWidth(300)
        self.scan_btn.clicked.connect(self.generate_model_json)
        l2d_layout.addWidget(self.scan_btn)

        self.cleanup_btn = QPushButton("去重并清理 model.json")
        self.cleanup_btn.setMinimumWidth(300)
        self.cleanup_btn.clicked.connect(self.cleanup_model_json)
        l2d_layout.addWidget(self.cleanup_btn)

        # 📦 批量添加动作/表情
        group_l2d = QGroupBox("🧰 Live2D 工具部分")
        l2d_main_layout = QHBoxLayout()

        # 左列：两个按钮
        left_layout = QVBoxLayout()
        self.scan_btn = QPushButton("扫描目录并生成 model.json")
        self.scan_btn.setMinimumWidth(240)
        self.scan_btn.clicked.connect(self.generate_model_json)

        self.cleanup_btn = QPushButton("去重并清理 model.json")
        self.cleanup_btn.setMinimumWidth(240)
        self.cleanup_btn.clicked.connect(self.cleanup_model_json)

        left_layout.addWidget(self.scan_btn)
        left_layout.addWidget(self.cleanup_btn)
        left_layout.addStretch()

        # 中列：📦 批量添加动作/表情
        group_batch_add = QGroupBox("📦 批量添加动作/表情")
        batch_layout = QFormLayout()

        self.batch_model_label = QLabel("未选择")
        btn_model = QPushButton("选择 model.json")
        btn_model.clicked.connect(self.select_batch_model_json)

        self.batch_file_label = QLabel("未选择")
        btn_file = QPushButton("选择动作/表情文件夹")
        btn_file.clicked.connect(self.select_batch_file_or_dir)

        self.prefix_input = QLineEdit()
        btn_add = QPushButton("执行添加")
        btn_add.clicked.connect(self.run_batch_add)

        batch_layout.addRow(btn_model, self.batch_model_label)
        batch_layout.addRow(btn_file, self.batch_file_label)
        batch_layout.addRow("前缀：", self.prefix_input)
        batch_layout.addRow("", btn_add)

        group_batch_add.setLayout(batch_layout)

        # 右列：🔧 批量修改 MTN 参数
        group_mtn_edit = QGroupBox("🔧 批量修改 MTN 文件参数")
        mtn_layout = QFormLayout()

        self.mtn_dir_label = QLabel("未选择")
        btn_select_mtn_dir = QPushButton("选择含 mtn 的文件夹")
        btn_select_mtn_dir.clicked.connect(self.select_mtn_directory)

        self.mtn_param_name_input = QLineEdit("PARAM_IMPORT")
        self.mtn_param_value_input = QLineEdit("30")

        btn_apply_mtn = QPushButton("批量更新")
        btn_apply_mtn.clicked.connect(self.run_mtn_batch_update)

        mtn_layout.addRow(btn_select_mtn_dir, self.mtn_dir_label)
        mtn_layout.addRow("参数名：", self.mtn_param_name_input)
        mtn_layout.addRow("新值：", self.mtn_param_value_input)
        mtn_layout.addRow("", btn_apply_mtn)

        group_mtn_edit.setLayout(mtn_layout)

        # 添加到主布局
        l2d_main_layout.addLayout(left_layout)
        l2d_main_layout.addWidget(group_batch_add)
        l2d_main_layout.addWidget(group_mtn_edit)

        group_l2d.setLayout(l2d_main_layout)
        layout.addWidget(group_l2d)

        # 📄 JSONL 生成区域（横向排布）
        group_jsonl = QGroupBox("📄 生成 JSONL 文件")
        jsonl_main_layout = QHBoxLayout()

        # 左列：目录选择 + 前缀 + 生成按钮
        left_layout = QVBoxLayout()
        self.jsonl_root_label = QLabel("未选择")
        btn_select_root = QPushButton("选择根目录")
        btn_select_root.clicked.connect(self.select_jsonl_root)

        self.append_import_checkbox = QCheckBox("统一import")
        self.append_import_checkbox.setChecked(False)
        left_layout.addWidget(self.append_import_checkbox)

        self.import_value_input = QLineEdit("50")  # 默认值为50,祥子的
        self.import_value_input.setPlaceholderText("Import 数值")
        left_layout.addWidget(self.import_value_input)

        self.jsonl_prefix_input = QLineEdit("myid")
        btn_gen_jsonl = QPushButton("生成 JSONL")
        btn_gen_jsonl.clicked.connect(self.run_generate_jsonl)

        left_layout.addWidget(btn_select_root)
        left_layout.addWidget(self.jsonl_root_label)
        left_layout.addWidget(QLabel("ID 前缀："))
        left_layout.addWidget(self.jsonl_prefix_input)
        left_layout.addWidget(btn_gen_jsonl)
        left_layout.addStretch()

        # 中列：子目录列表 + 刷新按钮
        mid_layout = QVBoxLayout()
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.folder_list.setMinimumHeight(180)
        self.folder_list.setMaximumWidth(250)

        self.btn_refresh_folders = QPushButton("📂 列出子目录")
        self.btn_refresh_folders.clicked.connect(self.populate_folder_list)

        mid_layout.addWidget(QLabel("子目录列表："))
        mid_layout.addWidget(self.folder_list)
        mid_layout.addWidget(self.btn_refresh_folders)
        mid_layout.addStretch()

        # 右列：上移下移按钮
        right_layout = QVBoxLayout()
        self.btn_up = QPushButton("↑ 上移")
        self.btn_up.clicked.connect(self.move_folder_up)

        self.btn_down = QPushButton("↓ 下移")
        self.btn_down.clicked.connect(self.move_folder_down)

        right_layout.addWidget(QLabel("顺序调整："))
        right_layout.addWidget(self.btn_up)
        right_layout.addWidget(self.btn_down)
        right_layout.addStretch()

        # 整合三列
        jsonl_main_layout.addLayout(left_layout)
        jsonl_main_layout.addLayout(mid_layout)
        jsonl_main_layout.addLayout(right_layout)

        group_jsonl.setLayout(jsonl_main_layout)
        layout.addWidget(group_jsonl)

        self.setLayout(layout)

        self.load_last_config()

    def show_comparison(self):
        try:
            if not hasattr(self, "_source_img") or not hasattr(self, "_target_img"):
                QMessageBox.warning(self, "未找到图像", "请先执行色彩匹配")
                return
            plot_parameter_comparison(self._source_img, self._target_img)
        except Exception as e:
            QMessageBox.critical(self, "出错", f"无法显示对比图：\n{str(e)}")

    def load_last_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # 色彩匹配路径
                self.source_path = config.get("color_match_source_path", "")
                if os.path.isfile(self.source_path):
                    self.source_label.setPixmap(QPixmap(self.source_path).scaled(200, 160))

                # Live2D 批量路径
                model_json_path = config.get("l2d_model_json_path", "")
                if os.path.isfile(model_json_path):
                    self.batch_model_json_path = model_json_path
                    self.batch_model_label.setText(model_json_path)

                file_or_dir = config.get("l2d_file_or_dir", "")
                if os.path.isdir(file_or_dir):
                    self.batch_file_or_dir = file_or_dir
                    self.batch_file_label.setText(file_or_dir)

                self.target_path = config.get("color_match_target_path", "")
                if os.path.isfile(self.target_path):
                    self.target_label.setPixmap(QPixmap(self.target_path).scaled(200, 160))

                jsonl_root_path = config.get("jsonl_root_path", "")
                if os.path.isdir(jsonl_root_path):
                    self.jsonl_root = jsonl_root_path
                    self.jsonl_root_label.setText(jsonl_root_path)

            except Exception as e:
                print("配置文件读取失败：", e)

    def save_config(self):
        config = {
            "color_match_source_path": self.source_path,
            "color_match_target_path": self.target_path,
            "l2d_model_json_path": getattr(self, "batch_model_json_path", ""),
            "l2d_file_or_dir": getattr(self, "batch_file_or_dir", ""),
            "jsonl_root_path": getattr(self, "jsonl_root", "")  # ✅ 新增
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def refresh_target_list(self):
        png_dir = "png"
        self.target_combo.clear()
        if os.path.isdir(png_dir):
            files = [f for f in os.listdir(png_dir) if f.lower().endswith(".png")]
            self.target_combo.addItems(files or ["⚠ 无 PNG 文件"])
        else:
            self.target_combo.addItem("⚠ 缺少 png 文件夹")

    def select_target_image(self, index):
        if index < 0:
            return
        file_name = self.target_combo.itemText(index)
        path = os.path.join("png", file_name)
        if os.path.isfile(path):
            self.target_path = path
            self.target_label.setPixmap(QPixmap(path).scaled(200, 160))

    def choose_source(self):
        initial_dir = os.path.dirname(self.source_path) if self.source_path else ""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择源图像", initial_dir, "Images (*.png *.jpg *.jpeg)")
        if file_path:
            self.source_path = file_path
            self.source_label.setPixmap(QPixmap(file_path).scaled(200, 160))
            self.save_config()

    def run_match(self):
        if not self.source_path or not self.target_path:
            QMessageBox.warning(self, "错误", "请先选择源图和参考图。")
            return

        source = Image.open(self.source_path).convert("RGB")
        target = Image.open(self.target_path).convert("RGB").resize(source.size)

        matched = match_color(source, target)
        source_dir = os.path.dirname(self.source_path)
        src = os.path.splitext(os.path.basename(self.source_path))[0]
        tgt = os.path.splitext(os.path.basename(self.target_path))[0]
        out_path = os.path.join(source_dir, f"matched_{src}_{tgt}.png")
        matched.save(out_path)

        self.result_path = out_path
        self.result_label.setPixmap(QPixmap(out_path).scaled(200, 160))

        webgal = extract_webgal_full_transform(source, target)
        self.webgal_output.setText(format_transform_code(webgal))
        QMessageBox.information(self, "完成", f"已保存匹配图像到：{out_path}")

        # 对比图
        self._source_img = source
        self._target_img = target
        self._matched_img = matched

    def generate_model_json(self):
        initial_dir = os.path.dirname(self.batch_model_json_path) if hasattr(self, "batch_model_json_path") else ""
        folder = QFileDialog.getExistingDirectory(self, "选择 Live2D 资源目录", initial_dir)
        if folder:
            data = scan_live2d_directory(folder)
            path = os.path.join(folder, "model.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "完成", f"已生成 model.json 到：{path}")

    # 添加对jsonl的适配
    def cleanup_model_json(self):
        initial_dir = os.path.dirname(self.batch_model_json_path) if hasattr(self, "batch_model_json_path") else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 model.json 或 JSONL 文件", initial_dir,
            "JSON / JSONL 文件 (*.json *.jsonl);;JSON 文件 (*.json);;JSONL 文件 (*.jsonl);;所有文件 (*)"
        )
        if not path or not os.path.isfile(path):
            return

        try:
            if path.endswith(".json"):
                remove_duplicates_and_check_files(path)
                QMessageBox.information(self, "完成", f"已完成清理：{path}")
            elif path.endswith(".jsonl"):
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                jsonl_dir = os.path.dirname(path)
                temp_parent = jsonl_dir
                while os.path.basename(temp_parent) != "game" and os.path.dirname(temp_parent) != temp_parent:
                    temp_parent = os.path.dirname(temp_parent)

                success = 0
                for idx, line in enumerate(lines):
                    try:
                        obj = json.loads(line)
                        model_path = obj.get("path")
                        if not model_path:
                            print(f"⚠️ 第 {idx + 1} 行无 path 字段")
                            continue

                        if os.path.basename(temp_parent) == "game" and model_path.startswith("game/"):
                            model_path = model_path[len("game/"):]

                        abs_path = os.path.normpath(os.path.join(temp_parent, model_path))
                        if not os.path.isfile(abs_path):
                            print(f"❌ model.json 文件不存在: {abs_path}")
                            continue

                        remove_duplicates_and_check_files(abs_path)
                        success += 1
                    except Exception as e:
                        print(f"❌ 第 {idx + 1} 行处理失败: {e}")

                QMessageBox.information(self, "完成", f"已清理 {success} 个 model.json")
        except Exception as e:
            QMessageBox.critical(self, "❌ 出错", f"处理失败：\n{str(e)}")

    def select_batch_model_json(self):
        initial_dir = os.path.dirname(self.batch_model_json_path) if hasattr(self, "batch_model_json_path") else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 model.json 或 JSONL 文件",
            initial_dir,
            "JSON Files (*.json *.jsonl);;All Files (*)"
        )
        if path:
            self.batch_model_json_path = path
            self.batch_model_label.setText(path)
            self.save_config()

    def select_batch_file_or_dir(self):
        initial_dir = self.batch_file_or_dir if hasattr(self, "batch_file_or_dir") else ""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", initial_dir)
        if folder:
            self.batch_file_or_dir = folder
            self.batch_file_label.setText(folder)
            self.save_config()

    def run_batch_add(self):
        if not hasattr(self, "batch_model_json_path") or not hasattr(self, "batch_file_or_dir"):
            QMessageBox.warning(self, "⚠", "请先选择 model.json（或 JSONL）和资源目录")
            return

        prefix = self.prefix_input.text().strip()

        # 弹出文件选择对话框
        dialog = FileSelectionDialog(self.batch_file_or_dir, self)
        if dialog.exec_() == QDialog.Rejected:
            return  # 用户取消

        selected_files = dialog.get_selected_files()
        if not selected_files:
            QMessageBox.warning(self, "⚠️", "未选择任何文件")
            return

        import tempfile, shutil

        temp_dir = tempfile.mkdtemp()
        try:
            selected_full_paths = [os.path.join(self.batch_file_or_dir, f) for f in selected_files]

            if self.batch_model_json_path.endswith(".jsonl"):
                try:
                    with open(self.batch_model_json_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    success = 0

                    jsonl_dir = os.path.dirname(self.batch_model_json_path)

                    for idx, line in enumerate(lines):
                        try:
                            obj = json.loads(line)
                            model_path = obj.get("path")
                            if not model_path:
                                continue

                            abs_model_path = os.path.normpath(os.path.join(jsonl_dir, model_path))
                            if not os.path.isfile(abs_model_path):
                                print(f"⚠️ 第 {idx + 1} 行 path 无效：{abs_model_path}")
                                continue

                            update_model_json_bulk(abs_model_path, selected_full_paths, prefix=prefix)
                            print(f"✅ 已处理: {model_path}")
                            success += 1

                        except Exception as e:
                            print(f"❌ 第 {idx + 1} 行处理失败: {e}")

                    QMessageBox.information(self, "完成", f"已批量更新 {success} 个 model.json！")

                    if success > 0:
                        new_motions = set()
                        new_expressions = set()
                        for f in selected_files:
                            name = os.path.splitext(os.path.basename(f))[0]
                            if f.endswith(".mtn"):
                                new_motions.add(prefix + name)
                            elif f.endswith(".exp.json"):
                                exp_name = os.path.splitext(name)[0]
                                new_expressions.add(prefix + exp_name)

                        # 原逻辑（存在就读取 motions / expressions）
                        if lines and '"motions"' in lines[-1] and '"expressions"' in lines[-1]:
                            try:
                                old_summary = json.loads(lines[-1])
                                old_motions = set(old_summary.get("motions", []))
                                old_expressions = set(old_summary.get("expressions", []))
                                old_import = old_summary.get("import")  # ✅ 加上这一行
                            except Exception:
                                old_motions = set()
                                old_expressions = set()
                                old_import = None  # ✅
                            lines = lines[:-1]
                        else:
                            old_motions = set()
                            old_expressions = set()
                            old_import = None  # ✅

                        merged_summary = {
                            "motions": sorted(old_motions.union(new_motions)),
                            "expressions": sorted(old_expressions.union(new_expressions))
                        }
                        if old_import is not None:  # ✅ 如果原来有 import 字段，保留
                            merged_summary["import"] = old_import

                        lines.append(json.dumps(merged_summary, ensure_ascii=False) + '\n')

                        with open(self.batch_model_json_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)

                        print("✅ 已更新 JSONL 末尾 summary 行")

                except Exception as e:
                    QMessageBox.critical(self, "❌ 出错", f"读取 JSONL 失败：\n{str(e)}")

            else:
                # 普通单个 model.json 模式
                update_model_json_bulk(self.batch_model_json_path, selected_full_paths, prefix)
                QMessageBox.information(self, "完成", "批量添加完成！")

        finally:
            shutil.rmtree(temp_dir)

    def select_mtn_directory(self):
        initial_dir = self.mtn_dir if hasattr(self, "mtn_dir") else ""
        folder = QFileDialog.getExistingDirectory(self, "选择 MTN 文件夹", initial_dir)
        if folder:
            self.mtn_dir = folder
            self.mtn_dir_label.setText(folder)

    def run_mtn_batch_update(self):
        if not hasattr(self, "mtn_dir") or not os.path.isdir(self.mtn_dir):
            QMessageBox.warning(self, "⚠️", "请先选择 MTN 文件所在目录")
            return

        param_name = self.mtn_param_name_input.text().strip()
        try:
            new_value = int(self.mtn_param_value_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "⚠️", "请输入有效的整数值作为参数新值")
            return

        batch_update_mtn_param_text(self.mtn_dir, param_name, new_value)
        QMessageBox.information(self, "完成", f"已更新 {param_name} 为 {new_value}")


    # 生成拼好模所需的jsonl文件
    def run_generate_jsonl(self):
        if not hasattr(self, "jsonl_root"):
            QMessageBox.warning(self, "⚠️", "请先选择目录")
            return

        prefix = self.jsonl_prefix_input.text().strip()
        if not prefix:
            QMessageBox.warning(self, "⚠️", "请输入有效的 ID 前缀")
            return

        selected_items = self.folder_list.selectedItems()
        selected_folders = [item.text() for item in selected_items]

        if not selected_folders:
            QMessageBox.warning(self, "⚠️", "请至少选择一个子目录")
            return

        base_folder_name = os.path.basename(self.jsonl_root.rstrip(os.sep))
        output_path = os.path.join(self.jsonl_root, f"{base_folder_name}.jsonl")

        try:
            collect_jsons_to_jsonl(self.jsonl_root, output_path, prefix, base_folder_name, selected_folders)

            # ✅ 如勾选了“添加 import 字段”，就在最后一行加 import
            if self.append_import_checkbox.isChecked():
                try:
                    with open(output_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    if lines:
                        last_line = lines[-1].strip()
                        try:
                            last_obj = json.loads(last_line)
                            if isinstance(last_obj, dict):
                                try:
                                    import_val = int(self.import_value_input.text().strip())
                                    last_obj["import"] = import_val
                                except ValueError:
                                    print("⚠️ import 不是有效整数，跳过添加")
                                lines[-1] = json.dumps(last_obj, ensure_ascii=False) + "\n"
                                with open(output_path, "w", encoding="utf-8") as f:
                                    f.writelines(lines)
                                print("✅ 已在 summary 行添加 import 字段")
                        except json.JSONDecodeError:
                            print("⚠️ 最后一行不是有效 JSON，未修改")
                except Exception as e:
                    QMessageBox.warning(self, "⚠️ 修改失败", f"无法添加 import 字段：\n{str(e)}")

            QMessageBox.information(self, "完成", f"JSONL 文件已生成：{output_path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ 出错", f"生成失败：{str(e)}")

    def select_jsonl_root(self):
        folder = QFileDialog.getExistingDirectory(self, "选择用于生成 JSONL 的目录")
        if folder:
            self.jsonl_root = folder
            self.jsonl_root_label.setText(folder)
            self.save_config()  # ✅ 记住路径

    # 选择jsonl
    def populate_folder_list(self):
        self.folder_list.clear()
        if not hasattr(self, "jsonl_root"):
            QMessageBox.warning(self, "⚠️", "请先选择根目录")
            return

        for name in sorted(os.listdir(self.jsonl_root)):
            full_path = os.path.join(self.jsonl_root, name)
            if os.path.isdir(full_path) and not name.startswith("_"):
                self.folder_list.addItem(name)

    def move_folder_up(self):
        row = self.folder_list.currentRow()
        if row > 0:
            item = self.folder_list.takeItem(row)
            self.folder_list.insertItem(row - 1, item)
            self.folder_list.setCurrentRow(row - 1)

    def move_folder_down(self):
        row = self.folder_list.currentRow()
        if row < self.folder_list.count() - 1:
            item = self.folder_list.takeItem(row)
            self.folder_list.insertItem(row + 1, item)
            self.folder_list.setCurrentRow(row + 1)

    def show_import_table(self):
        json_path = get_resource_path("name_import.json")
        if not os.path.isfile(json_path):
            QMessageBox.warning(self, "未找到文件", "无法找到 name_import.json 文件")
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                import_data = json.load(f)

            lines = []
            for item in sorted(import_data, key=lambda x: x.get("import", 0)):
                import_id = item.get("import", "")
                ja = item.get("name_ja", "")
                en = item.get("name_en", "")
                zh = item.get("name_zh", "")
                lines.append(f'{import_id:>2} | {ja:<10} | {en:<20} | {zh}')

            text = "\n".join(lines)

            dialog = QDialog(self)
            dialog.setWindowTitle("Import 参数列表")
            dialog.resize(600, 600)
            layout = QVBoxLayout()

            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setText(text)
            layout.addWidget(text_edit)

            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.setLayout(layout)
            dialog.exec_()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取 name_import.json 出错：\n{str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    if os.path.exists("style.qss"):
        with open("style.qss", "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    window = ToolBox()
    window.show()
    sys.exit(app.exec_())