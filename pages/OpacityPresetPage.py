import os
import json
import shutil
import pygame
import live2d.v2 as live2d
import errno

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QListWidget, QListWidgetItem, QHBoxLayout, QTableWidget,
    QHeaderView, QTableWidgetItem, QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt

from sections.gen_jsonl import is_valid_live2d_json

PARTS_JSON_PATH = os.path.join("resource", "parts.json")


# ========= 通用工具 =========
def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def _ensure_parent_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def _same_volume(src: str, dst: str) -> bool:
    """Windows: 比较盘符；POSIX: 比较 st_dev。"""
    try:
        src_drive = os.path.splitdrive(os.path.abspath(src))[0].lower()
        dst_drive = os.path.splitdrive(os.path.abspath(dst))[0].lower()
        if src_drive or dst_drive:
            return src_drive == dst_drive
    except Exception:
        pass
    try:
        return os.stat(os.path.abspath(src)).st_dev == os.stat(os.path.abspath(os.path.dirname(dst))).st_dev
    except Exception:
        return False

def _fsync_file(path: str):
    try:
        with open(path, 'rb') as f:
            os.fsync(f.fileno())
    except Exception:
        pass

def _fsync_dir(dir_path: str):
    try:
        if os.name == "nt":
            return
        fd = os.open(dir_path, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass

def _dedup_target_path(dst_path: str) -> str:
    """若目标重名，自动追加 _1/_2/..."""
    base = os.path.basename(dst_path)
    name, ext = os.path.splitext(base)
    folder = os.path.dirname(dst_path)
    final_dst = dst_path
    i = 1
    while os.path.exists(final_dst):
        final_dst = os.path.join(folder, f"{name}_{i}{ext}")
        i += 1
    return final_dst

def safe_move(src: str, dst: str) -> str:
    """
    可靠移动：
      - 先尝试 shutil.move
      - 跨盘或失败则 copy2 + fsync + unlink
      - 返回最终目标（含重名去重）
    """
    _ensure_parent_dir(dst)
    final_dst = _dedup_target_path(dst)

    try:
        shutil.move(src, final_dst)
        return final_dst
    except Exception as e:
        is_exdev = getattr(e, 'errno', None) == errno.EXDEV
        if is_exdev or not _same_volume(src, final_dst):
            try:
                shutil.copy2(src, final_dst)
                _fsync_file(final_dst)
                _fsync_dir(os.path.dirname(final_dst))
                os.unlink(src)
                _fsync_dir(os.path.dirname(src))
                return final_dst
            except Exception as e2:
                raise RuntimeError(f"跨盘复制删除失败：{src} -> {final_dst}, 错误: {e2}") from e2
        else:
            try:
                shutil.copy2(src, final_dst)
                _fsync_file(final_dst)
                _fsync_dir(os.path.dirname(final_dst))
                os.unlink(src)
                _fsync_dir(os.path.dirname(src))
                return final_dst
            except Exception as e3:
                raise RuntimeError(f"复制删除兜底失败：{src} -> {final_dst}, 错误: {e3}") from e3


# ========= 主页面 =========
class OpacityPresetPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.label = QLabel("选择文件夹后，自动列出所有合法的 model.json，选择分类后点击套用")
        layout.addWidget(self.label)

        top_btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("📁 选择文件夹")
        self.select_btn.clicked.connect(self.select_folder)
        top_btn_layout.addWidget(self.select_btn)

        # 来源子目录（仅遍历这一层）
        self.source_subdir_input = QLineEdit()
        self.source_subdir_input.setPlaceholderText("来源子目录（默认：1.后发）")
        self.source_subdir_input.setText("1.后发")
        top_btn_layout.addWidget(self.source_subdir_input)

        # 复制/移动选择
        self.copy_mode_checkbox = QCheckBox("仅复制 .mtn/.exp.json（不删除源文件）")
        self.copy_mode_checkbox.setChecked(True)  # 默认更安全
        top_btn_layout.addWidget(self.copy_mode_checkbox)

        self.apply_btn = QPushButton("✅ 应用预设")
        self.apply_btn.clicked.connect(self.apply_preset)
        top_btn_layout.addWidget(self.apply_btn)

        layout.addLayout(top_btn_layout)

        self.category_list = QListWidget()
        self.category_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(QLabel("🧩 选择保留透明度为 1 的分类"))
        layout.addWidget(self.category_list)

        self.json_table = QTableWidget()
        self.json_table.setColumnCount(3)
        self.json_table.setHorizontalHeaderLabels(["✔", "model.json 路径", "当前预设"])
        self.json_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.json_table.setColumnWidth(0, 40)
        self.json_table.setColumnWidth(2, 120)
        layout.addWidget(self.json_table)

        self.parts_data = {}
        self.root_dir = ""
        self.load_parts_json()

    def load_parts_json(self):
        if not os.path.exists(PARTS_JSON_PATH):
            QMessageBox.warning(self, "警告", f"未找到 parts.json：{PARTS_JSON_PATH}")
            return
        with open(PARTS_JSON_PATH, encoding="utf-8") as f:
            self.parts_data = json.load(f)
            for category in self.parts_data:
                item = QListWidgetItem(category)
                item.setCheckState(Qt.Unchecked)
                self.category_list.addItem(item)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择模型文件夹")
        if not folder:
            return

        self.root_dir = folder
        self.label.setText(f"✅ 已选择：{folder}")
        self.json_table.setRowCount(0)

        json_files = []

        def _collect_jsons(path, depth=0):
            if depth > 2:
                return
            try:
                for name in sorted(os.listdir(path)):
                    full = os.path.join(path, name)
                    if os.path.isdir(full):
                        _collect_jsons(full, depth + 1)
                    elif name.endswith(".json") and is_valid_live2d_json(full):
                        json_files.append(full)
            except Exception as e:
                print(f"❌ 错误: {e}")

        _collect_jsons(folder)

        for i, path in enumerate(json_files):
            self.json_table.insertRow(i)
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            self.json_table.setCellWidget(i, 0, checkbox)

            path_item = QTableWidgetItem(path)
            path_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.json_table.setItem(i, 1, path_item)

            preset_item = QTableWidgetItem(self.detect_preset(path) or "无")
            preset_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.json_table.setItem(i, 2, preset_item)

    def detect_preset(self, json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                model = json.load(f)
            if "init_opacities" not in model:
                return "无"
            used_parts = [entry["id"] for entry in model["init_opacities"] if entry["value"] == 1.0]
            for category, parts in self.parts_data.items():
                if set(used_parts) == set(parts):
                    return category
            return "自定义"
        except Exception:
            return "未知"

    def apply_preset(self):
        selected_categories = [
            self.category_list.item(i).text()
            for i in range(self.category_list.count())
            if self.category_list.item(i).checkState() == Qt.Checked
        ]
        if not selected_categories:
            QMessageBox.warning(self, "警告", "请至少勾选一个分类")
            return

        selected_jsons = []
        for row in range(self.json_table.rowCount()):
            checkbox = self.json_table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                item = self.json_table.item(row, 1)
                if item:
                    selected_jsons.append(item.text())
        if not selected_jsons:
            QMessageBox.warning(self, "警告", "请至少勾选一个 model.json")
            return

        # 需要拷贝/移动的来源一级子目录名
        subdir_name = (self.source_subdir_input.text() or "1.后发").strip()

        target_parts = set()
        for cat in selected_categories:
            target_parts.update(self.parts_data.get(cat, []))

        use_copy_only = self.copy_mode_checkbox.isChecked()

        updated = 0
        exported = 0
        skipped = 0

        for json_path in selected_jsons:
            try:
                # 1) 写 init_opacities + 清空 motions/expressions
                all_parts = self.get_all_parts(json_path)
                init_opacities = [
                    {"id": pid, "value": 1.0 if pid in target_parts else 0.0}
                    for pid in all_parts
                ]

                with open(json_path, "r", encoding="utf-8") as f:
                    model_data = json.load(f)
                model_data.pop("motions", None)
                model_data.pop("expressions", None)
                model_data["init_opacities"] = init_opacities

                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(model_data, f, ensure_ascii=False, indent=2)
                updated += 1

                # 2) 仅遍历 <模型目录>
                source_base = os.path.join(self.root_dir, subdir_name)
                if not os.path.isdir(source_base):
                    print(f"⚠️ 来源子目录不存在：{os.path.normpath(source_base)}")
                else:
                    export_dir = os.path.join(self.root_dir, "expnmtn", subdir_name)
                    _ensure_dir(export_dir)

                    for dirpath, dirnames, filenames in os.walk(source_base):
                        for file in filenames:
                            low = file.lower()
                            if not (low.endswith(".mtn") or low.endswith(".exp.json")):
                                continue

                            src = os.path.join(dirpath, file)
                            dst_path = os.path.join(export_dir, file)  # 只保留原文件名（扁平化）

                            try:
                                if use_copy_only:
                                    final_dst = _dedup_target_path(dst_path)
                                    shutil.copy2(src, final_dst)
                                    _fsync_file(final_dst)
                                    _fsync_dir(export_dir)
                                else:
                                    final_dst = safe_move(src, dst_path)
                                exported += 1
                            except Exception as e:
                                print(f"❌ 集中失败：{src} -> {dst_path}，错误: {e}")
                                skipped += 1
            except Exception as e:
                print(f"❌ 处理失败: {json_path} 错误: {e}")

        QMessageBox.information(
            self,
            "完成",
            f"成功处理了 {updated} 个 model.json\n"
            f"{'复制' if use_copy_only else '移动'}了 {exported} 个动作/表情文件到 expnmtn\\{subdir_name}\n"
            f"跳过/失败：{skipped}"
        )

    def get_all_parts(self, model_path):
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.OPENGL | pygame.HIDDEN)
        live2d.init()
        live2d.glewInit()
        model = live2d.LAppModel()
        model.LoadModelJson(model_path)
        part_ids = model.GetPartIds()
        live2d.dispose()
        pygame.quit()
        return part_ids
