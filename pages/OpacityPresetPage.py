import os
import json
import shutil
import pygame
import live2d.v2 as live2d
import errno
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QListWidget, QListWidgetItem, QHBoxLayout, QTableWidget,
    QHeaderView, QTableWidgetItem, QCheckBox, QLineEdit, QComboBox,
    QGroupBox, QFormLayout, QRadioButton, QDialog
)
from PyQt5.QtCore import Qt

from sections.gen_jsonl import is_valid_live2d_json
from sections.py_live2d_editor import get_all_parts
from pages.single_model_preview_window import SingleModelPreviewWindow
from pages.opacity_detail_editor_dialog import OpacityDetailEditorDialog
from utils.common import get_resource_path

PARTS_JSON_PATH = get_resource_path(os.path.join("resource", "parts.json"))


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

def _display_relpath(abs_path: str, base: str) -> str:
    """用于 UI 显示的相对路径；跨盘失败则退化为文件名"""
    try:
        rel = os.path.relpath(abs_path, base)
        return rel.replace("\\", "/")
    except ValueError:
        return os.path.basename(abs_path)

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

        self.label = QLabel("选择文件夹后，自动列出所有合法的 model.json；逐行选择并套用预设")
        layout.addWidget(self.label)

        top_btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("📁 选择文件夹")
        self.select_btn.clicked.connect(self.select_folder)
        top_btn_layout.addWidget(self.select_btn)

        # 来源子目录相关
        self.source_subdir_combo = QComboBox()
        self.source_subdir_combo.setEnabled(False)
        self.source_subdir_combo.setPlaceholderText("先选择根目录…")
        top_btn_layout.addWidget(self.source_subdir_combo)

        self.all_subdirs_checkbox = QCheckBox("遍历全部子目录")
        self.all_subdirs_checkbox.setChecked(False)
        self.all_subdirs_checkbox.toggled.connect(
            lambda checked: self.source_subdir_combo.setEnabled(not checked)
        )
        top_btn_layout.addWidget(self.all_subdirs_checkbox)

        # 复制/移动选择
        self.copy_mode_checkbox = QCheckBox("仅复制 .mtn/.exp.json（不删除源文件）")
        self.copy_mode_checkbox.setChecked(True)
        top_btn_layout.addWidget(self.copy_mode_checkbox)

        # 批量设为（作用于“勾选的行”）
        self.bulk_preset_combo = QComboBox()
        self.bulk_apply_btn = QPushButton("批量设为")
        self.bulk_apply_btn.clicked.connect(self.apply_bulk_preset_to_checked_rows)
        top_btn_layout.addWidget(self.bulk_preset_combo)
        top_btn_layout.addWidget(self.bulk_apply_btn)

        # 应用按钮
        self.apply_btn = QPushButton("应用所选预设")
        self.apply_btn.clicked.connect(self.apply_preset)
        top_btn_layout.addWidget(self.apply_btn)

        layout.addLayout(top_btn_layout)

        # 预设说明
        layout.addWidget(QLabel("提示：在下表中逐行选择预设；“保持不变”将跳过该行，“清空(全0)”会把所有部件设为0。"))

        # ✅ 表格：按行选择预设
        self.json_table = QTableWidget()
        self.json_table.setColumnCount(5)
        self.json_table.setHorizontalHeaderLabels(["✔", "model.json 路径", "检测到的预设", "选择预设", "操作"])
        self.json_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.json_table.setColumnWidth(0, 44)
        self.json_table.setColumnWidth(2, 120)
        self.json_table.setColumnWidth(3, 160)
        self.json_table.setColumnWidth(4, 130)  # 增加操作列宽度，确保两个按钮能显示
        layout.addWidget(self.json_table)

        # === 新增：从单一源 JSON 复制 motions/expressions 到勾选目标 ===
        copy_group = QGroupBox("🧩 从单一源 JSON 复制 motions / expressions 到勾选目标")
        copy_form = QFormLayout(copy_group)

        self.src_json_edit = QLineEdit()
        self.src_json_btn = QPushButton("选择源 JSON…")
        self.src_json_btn.clicked.connect(self._browse_src_json)
        row_src = QHBoxLayout()
        row_src.addWidget(self.src_json_edit)
        row_src.addWidget(self.src_json_btn)
        copy_form.addRow("源 JSON：", row_src)

        opts_row = QHBoxLayout()
        self.rb_merge = QRadioButton("合并（去重）")
        self.rb_overwrite = QRadioButton("覆盖")
        self.rb_merge.setChecked(True)

        self.cb_motions = QCheckBox("motions")
        self.cb_expressions = QCheckBox("expressions")
        self.cb_motions.setChecked(True)
        self.cb_expressions.setChecked(True)

        opts_row.addWidget(self.rb_merge)
        opts_row.addWidget(self.rb_overwrite)
        opts_row.addSpacing(16)
        opts_row.addWidget(self.cb_motions)
        opts_row.addWidget(self.cb_expressions)
        copy_form.addRow("选项：", opts_row)

        self.copy_btn = QPushButton("复制到勾选的目标")
        self.copy_btn.clicked.connect(self.copy_src_fields_to_checked_rows)
        copy_form.addRow(self.copy_btn)

        layout.addWidget(copy_group)

        self.parts_data = {}
        self.root_dir = ""
        self.preset_names = []  # parts.json 的 key 列表（加载后填充）
        # 预览窗口相关
        self.preview_thread = None  # 预览窗口线程引用
        self.preview_window = None  # 预览窗口实例引用（用于关闭）
        self.main_window = None  # 主窗口引用
        self.load_parts_json()

    def load_parts_json(self):
        if not os.path.exists(PARTS_JSON_PATH):
            QMessageBox.warning(self, "警告", f"未找到 parts.json：{PARTS_JSON_PATH}")
            return
        with open(PARTS_JSON_PATH, encoding="utf-8") as f:
            self.parts_data = json.load(f)

        # 预设下拉的可选项（顺序可按需调整）
        self.preset_names = list(self.parts_data.keys())
        specials = ["保持不变", "清空(全0)"]
        # 批量下拉
        self.bulk_preset_combo.clear()
        self.bulk_preset_combo.addItems(specials + self.preset_names)

    def _list_first_level_subdirs(self, base):
        try:
            return sorted(
                [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
            )
        except Exception:
            return []

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择模型文件夹")
        if not folder:
            return

        self.root_dir = folder
        self.label.setText(f"✅ 已选择：{folder}")
        self.json_table.setRowCount(0)

        # 填充来源子目录
        subdirs = self._list_first_level_subdirs(folder)
        self.source_subdir_combo.clear()
        self.source_subdir_combo.setEnabled(False)
        if subdirs:
            self.source_subdir_combo.addItems(subdirs)
            self.source_subdir_combo.setEnabled(not self.all_subdirs_checkbox.isChecked())

        # 枚举 model.json
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

        # 填充表格（逐行可选预设）
        for i, abs_path in enumerate(json_files):
            self.json_table.insertRow(i)

            # ✔ 是否处理
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            self.json_table.setCellWidget(i, 0, checkbox)

            # 路径列：显示相对路径，但把绝对路径放到 UserRole
            disp = _display_relpath(abs_path, self.root_dir)
            path_item = QTableWidgetItem(disp)
            path_item.setData(Qt.UserRole, abs_path)  # ← 存绝对路径，后面读这个
            path_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.json_table.setItem(i, 1, path_item)

            # 检测到的预设（用绝对路径进行检测）
            detected = self.detect_preset(abs_path) or "无"
            detected_item = QTableWidgetItem(detected)
            detected_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.json_table.setItem(i, 2, detected_item)

            # 选择预设
            preset_combo = QComboBox()
            options = ["保持不变", "清空(全0)"] + self.preset_names
            preset_combo.addItems(options)
            preset_combo.setCurrentText(detected if detected in self.preset_names else "保持不变")
            self.json_table.setCellWidget(i, 3, preset_combo)

            # 预览和详细编辑按钮
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)
            
            preview_btn = QPushButton("查看")
            preview_btn.setMinimumSize(50, 24)
            preview_btn.setMaximumSize(60, 28)
            preview_btn.clicked.connect(lambda _, row=i: self.preview_row_preset(row))
            btn_layout.addWidget(preview_btn)
            
            detail_btn = QPushButton("详细")
            detail_btn.setMinimumSize(50, 24)
            detail_btn.setMaximumSize(60, 28)
            detail_btn.clicked.connect(lambda _, row=i: self.open_detail_editor(row))
            btn_layout.addWidget(detail_btn)
            
            btn_widget = QWidget()
            btn_widget.setLayout(btn_layout)
            self.json_table.setCellWidget(i, 4, btn_widget)

    def preview_row_preset(self, row: int):
        """预览该行模型（根据选中的预设创建虚拟 JSON 并打开预览窗口）"""
        # 如果已有预览窗口在运行，先关闭它
        if self.preview_thread and self.preview_thread.is_alive():
            self._close_preview_window()
        
        # 获取模型路径
        path_item = self.json_table.item(row, 1)
        if not path_item:
            QMessageBox.warning(self, "错误", "无法获取模型路径")
            return
        
        model_json_path = path_item.data(Qt.UserRole)  # 绝对路径
        if not model_json_path or not os.path.isfile(model_json_path):
            QMessageBox.warning(self, "错误", f"模型文件不存在：{model_json_path}")
            return
        
        # 获取选中的预设
        combo = self.json_table.cellWidget(row, 3)
        if not combo:
            QMessageBox.warning(self, "错误", "无法获取预设选择")
            return
        
        preset_name = combo.currentText()
        print(f"🔍 预览预设: {preset_name}, 模型路径: {model_json_path}")
        
        # 根据预设创建 init_opacities
        init_opacities = None
        if preset_name == "保持不变":
            # 使用原始 JSON 中的 init_opacities（在预览窗口中会读取）
            init_opacities = None
            print("📌 使用原始 init_opacities")
        elif preset_name == "清空(全0)":
            # 获取所有部件，全部设为 0
            try:
                all_parts = get_all_parts(model_json_path)
                init_opacities = [{"id": pid, "value": 0.0} for pid in all_parts]
                print(f"📌 清空预设: 共 {len(init_opacities)} 个部件，全部设为 0")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"获取部件列表失败：{e}")
                return
        else:
            # 使用预设的部件列表
            target_parts = set(self.parts_data.get(preset_name, []))
            print(f"📌 预设 '{preset_name}' 包含的部件: {target_parts}")
            if not target_parts:
                QMessageBox.warning(self, "警告", f"预设 '{preset_name}' 未找到或为空，请检查 parts.json")
                return
            try:
                all_parts = get_all_parts(model_json_path)
                print(f"📌 模型共有 {len(all_parts)} 个部件")
                init_opacities = [
                    {"id": pid, "value": 1.0 if pid in target_parts else 0.0}
                    for pid in all_parts
                ]
                # 统计实际设置为 1.0 的部件数量
                visible_count = sum(1 for item in init_opacities if item["value"] == 1.0)
                print(f"📌 创建的 init_opacities: 共 {len(init_opacities)} 个，其中 {visible_count} 个可见（value=1.0）")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"获取部件列表失败：{e}")
                return
        
        # 禁用主窗口
        if self.main_window:
            self.main_window.disable_main_window()
        
        # 创建预览窗口并在线程中运行
        try:
            self.preview_window = SingleModelPreviewWindow(model_json_path, init_opacities)
            
            def run_preview():
                try:
                    self.preview_window.run()
                except Exception as e:
                    print(f"预览窗口运行错误: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # 预览窗口关闭后，启用主窗口
                    if self.main_window:
                        self.main_window.enable_main_window()
            
            self.preview_thread = threading.Thread(target=run_preview, daemon=True)
            self.preview_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动预览失败：{e}")
            import traceback
            traceback.print_exc()
            # 如果启动失败，也要启用主窗口
            if self.main_window:
                self.main_window.enable_main_window()
    
    def open_detail_editor(self, row: int):
        """打开详细编辑对话框"""
        # 获取模型路径
        path_item = self.json_table.item(row, 1)
        if not path_item:
            QMessageBox.warning(self, "错误", "无法获取模型路径")
            return
        
        model_json_path = path_item.data(Qt.UserRole)  # 绝对路径
        if not model_json_path or not os.path.isfile(model_json_path):
            QMessageBox.warning(self, "错误", f"模型文件不存在：{model_json_path}")
            return
        
        # 获取当前的预设和 init_opacities
        combo = self.json_table.cellWidget(row, 3)
        if not combo:
            QMessageBox.warning(self, "错误", "无法获取预设选择")
            return
        
        preset_name = combo.currentText()
        
        # 根据预设创建当前的 init_opacities
        current_init_opacities = None
        if preset_name == "保持不变":
            # 读取原始 JSON 中的 init_opacities
            try:
                with open(model_json_path, "r", encoding="utf-8") as f:
                    model_data = json.load(f)
                current_init_opacities = model_data.get("init_opacities", [])
            except Exception as e:
                QMessageBox.warning(self, "警告", f"读取原始 init_opacities 失败：{e}")
                current_init_opacities = []
        elif preset_name == "清空(全0)":
            # 获取所有部件，全部设为 0
            try:
                all_parts = get_all_parts(model_json_path)
                current_init_opacities = [{"id": pid, "value": 0.0} for pid in all_parts]
            except Exception as e:
                QMessageBox.critical(self, "错误", f"获取部件列表失败：{e}")
                return
        else:
            # 使用预设的部件列表
            target_parts = set(self.parts_data.get(preset_name, []))
            try:
                all_parts = get_all_parts(model_json_path)
                current_init_opacities = [
                    {"id": pid, "value": 1.0 if pid in target_parts else 0.0}
                    for pid in all_parts
                ]
            except Exception as e:
                QMessageBox.critical(self, "错误", f"获取部件列表失败：{e}")
                return
        
        # 打开编辑对话框
        dialog = OpacityDetailEditorDialog(model_json_path, current_init_opacities, self)
        if dialog.exec_() == QDialog.Accepted:
            # 获取编辑后的 init_opacities
            new_init_opacities = dialog.get_init_opacities()
            
            # 如果预览窗口正在运行，更新它
            if self.preview_window and self.preview_thread and self.preview_thread.is_alive():
                # 更新预览窗口的 init_opacities
                self.preview_window.init_opacities = new_init_opacities
                
                # 重新应用透明度设置
                try:
                    if self.preview_window.model:
                        part_ids = self.preview_window.model.GetPartIds()
                        part_id_to_index = {part_id: idx for idx, part_id in enumerate(part_ids)}
                        
                        for item in new_init_opacities:
                            part_id = item.get("id")
                            opacity = float(item.get("value", 0.0))
                            
                            if part_id in part_id_to_index:
                                part_index = part_id_to_index[part_id]
                                if hasattr(self.preview_window.model, "SetPartOpacity"):
                                    self.preview_window.model.SetPartOpacity(part_index, opacity)
                                elif hasattr(self.preview_window.model, "SetPart"):
                                    self.preview_window.model.SetPart(part_index, opacity)
                        
                        print(f"✅ 已更新预览窗口的透明度设置")
                except Exception as e:
                    print(f"⚠️ 更新预览窗口透明度时出错: {e}")
            
            QMessageBox.information(self, "完成", "已更新透明度设置！\n"
                                                   "如果预览窗口正在运行，已自动应用更改。")
    
    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window
    
    def _close_preview_window(self):
        """关闭预览窗口"""
        if self.preview_window:
            try:
                self.preview_window.running = False
            except:
                pass
        if self.preview_thread and self.preview_thread.is_alive():
            # 等待线程结束（最多等待 1 秒）
            self.preview_thread.join(timeout=1.0)
        self.preview_window = None
        self.preview_thread = None
        
        # 启用主窗口
        if self.main_window:
            self.main_window.enable_main_window()

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

    # 批量把 bulk_preset_combo 选中的预设，应用到“勾选的行”的“选择预设”下拉框
    def apply_bulk_preset_to_checked_rows(self):
        preset_name = self.bulk_preset_combo.currentText().strip()
        for row in range(self.json_table.rowCount()):
            cb = self.json_table.cellWidget(row, 0)
            if cb and cb.isChecked():
                combo = self.json_table.cellWidget(row, 3)
                if combo:
                    combo.setCurrentText(preset_name)
        QMessageBox.information(self, "完成", f"已将 {preset_name} 应用于勾选行的“选择预设”下拉。")

    def apply_preset(self):
        # 逐行处理
        traverse_all = self.all_subdirs_checkbox.isChecked()
        chosen_subdir = None
        if not traverse_all:
            if self.source_subdir_combo.count() > 0:
                chosen_subdir_text = self.source_subdir_combo.currentText().strip()
                # 只有当明确选择了子目录时才设置 chosen_subdir
                if chosen_subdir_text:
                    chosen_subdir = chosen_subdir_text
        
        # 判断是否需要集中处理 motions/expressions
        # 只有在明确选择了"遍历所有子目录"或"来源子目录"时才处理文件
        should_organize_files = traverse_all or (chosen_subdir is not None)

        use_copy_only = self.copy_mode_checkbox.isChecked()

        updated = 0
        exported = 0
        skipped = 0

        # —— 写入各自预设
        for row in range(self.json_table.rowCount()):
            cb = self.json_table.cellWidget(row, 0)
            if not (cb and cb.isChecked()):
                continue

            path_item = self.json_table.item(row, 1)
            combo = self.json_table.cellWidget(row, 3)
            if not path_item or not combo:
                continue

            json_path = path_item.data(Qt.UserRole)  # 绝对路径
            choice = combo.currentText().strip()

            if choice == "保持不变":
                continue

            try:
                all_parts = get_all_parts(json_path)
                if choice == "清空(全0)":
                    target_parts = set()
                else:
                    target_parts = set(self.parts_data.get(choice, []))

                init_opacities = [
                    {"id": pid, "value": 1.0 if pid in target_parts else 0.0}
                    for pid in all_parts
                ]

                with open(json_path, "r", encoding="utf-8") as f:
                    model_data = json.load(f)
                
                # 只有在需要集中处理文件时才删除 motions 和 expressions
                if should_organize_files:
                    model_data.pop("motions", None)
                    model_data.pop("expressions", None)
                
                model_data["init_opacities"] = init_opacities
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(model_data, f, ensure_ascii=False, indent=2)
                updated += 1
            except Exception as e:
                print(f"❌ 处理失败: {json_path} 错误: {e}")

        # —— 集中动作/表情（只有在选择了遍历或来源子目录时才执行）
        if should_organize_files:
            try:
                if traverse_all:
                    for dirpath, _, filenames in os.walk(self.root_dir):
                        for file in filenames:
                            low = file.lower()
                            if not (low.endswith(".mtn") or low.endswith(".exp.json")):
                                continue
                            src = os.path.join(dirpath, file)
                            rel = os.path.relpath(dirpath, self.root_dir)
                            top = rel.split(os.sep)[0] if rel != "." else "_root"
                            export_dir = os.path.join(self.root_dir, "expnmtn", top)
                            _ensure_dir(export_dir)
                            try:
                                if use_copy_only:
                                    final_dst = _dedup_target_path(os.path.join(export_dir, file))
                                    shutil.copy2(src, final_dst)
                                    _fsync_file(final_dst); _fsync_dir(export_dir)
                                else:
                                    _ = safe_move(src, os.path.join(export_dir, file))
                                exported += 1
                            except Exception as e:
                                print(f"❌ 集中失败：{src} -> {export_dir}，错误: {e}")
                                skipped += 1
                else:
                    source_base = os.path.join(self.root_dir, chosen_subdir)
                    if not os.path.isdir(source_base):
                        print(f"⚠️ 来源子目录不存在：{os.path.normpath(source_base)}")
                    else:
                        export_dir = os.path.join(self.root_dir, "expnmtn", chosen_subdir)
                        _ensure_dir(export_dir)
                        for dirpath, _, filenames in os.walk(source_base):
                            for file in filenames:
                                low = file.lower()
                                if not (low.endswith(".mtn") or low.endswith(".exp.json")):
                                    continue
                                src = os.path.join(dirpath, file)
                                try:
                                    if use_copy_only:
                                        final_dst = _dedup_target_path(os.path.join(export_dir, file))
                                        shutil.copy2(src, final_dst)
                                        _fsync_file(final_dst); _fsync_dir(export_dir)
                                    else:
                                        _ = safe_move(src, os.path.join(export_dir, file))
                                    exported += 1
                                except Exception as e:
                                    print(f"❌ 集中失败：{src} -> {export_dir}，错误: {e}")
                                    skipped += 1
            except Exception as e:
                print(f"❌ 遍历错误：{e}")

        # 构建完成消息
        message = f"已更新 init_opacities：{updated} 个"
        if should_organize_files:
            message += f"\n{'复制' if use_copy_only else '移动'}了 {exported} 个动作/表情到 expnmtn\\(按首层目录分组)"
            if skipped > 0:
                message += f"\n跳过/失败：{skipped}"
        else:
            message += "\n（未处理 motions/expressions 文件和字段）"
        
        QMessageBox.information(self, "完成", message)

    # ========= 新增：从单一源 JSON 复制到勾选目标 =========
    def _browse_src_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择源 model.json", filter="JSON (*.json)")
        if path:
            self.src_json_edit.setText(path)

    def copy_src_fields_to_checked_rows(self):
        src_path = self.src_json_edit.text().strip()
        if not (src_path and os.path.isfile(src_path)):
            QMessageBox.warning(self, "⚠️", "请先选择正确的源 model.json")
            return
        if not (self.cb_motions.isChecked() or self.cb_expressions.isChecked()):
            QMessageBox.warning(self, "⚠️", "请至少勾选 motions 或 expressions 之一")
            return

        # 读取源
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                src_obj = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "❌ 出错", f"读取源 JSON 失败：\n{e}")
            return

        mode = "merge" if self.rb_merge.isChecked() else "overwrite"
        success, fail = 0, 0

        # 对勾选行执行复制
        for row in range(self.json_table.rowCount()):
            cb = self.json_table.cellWidget(row, 0)
            if not (cb and cb.isChecked()):
                continue
            path_item = self.json_table.item(row, 1)
            if not path_item:
                continue
            dst_path = path_item.data(Qt.UserRole)
            if not (dst_path and os.path.isfile(dst_path)):
                continue

            try:
                with open(dst_path, "r", encoding="utf-8") as f:
                    dst_obj = json.load(f)

                if self.cb_motions.isChecked():
                    dst_obj = self._apply_copy_for_field("motions", src_obj, dst_obj, mode)
                if self.cb_expressions.isChecked():
                    dst_obj = self._apply_copy_for_field("expressions", src_obj, dst_obj, mode)

                self._safe_backup(dst_path)
                with open(dst_path, "w", encoding="utf-8") as f:
                    json.dump(dst_obj, f, ensure_ascii=False, indent=2)
                success += 1
            except Exception as e:
                print(f"[复制失败] {dst_path}: {e}")
                fail += 1

        QMessageBox.information(self, "完成", f"复制完成：成功 {success} 个，失败 {fail} 个。")

    def _apply_copy_for_field(self, field: str, src_obj: dict, target: dict, mode: str):
        s_val = src_obj.get(field)
        t_val = target.get(field)

        if mode == "overwrite":
            merged = self._merge_field_values(s_val, None, None)
            if merged is not None:
                target[field] = merged
            else:
                target.pop(field, None)
        else:
            merged = self._merge_field_values(s_val, None, t_val)
            if merged is not None:
                target[field] = merged
            else:
                target.pop(field, None)
        return target

    def _merge_field_values(self, a_val, b_val, t_val):
        """
        合并两大类结构并去重：
        1) dict: { "name": [ {"file": "..."} ] }
        2) list: [ {"name":"...", "file":"..."} ]
        a_val: 源；b_val: 兼容占位，这里固定 None；t_val: 目标原值
        """
        if a_val is None and t_val is None:
            return None

        has_dict = any(isinstance(v, dict) for v in (a_val, t_val) if v is not None)

        if has_dict:
            # 目标结构：dict[str, list[{"file": "..."}]]
            base = {}
            for src in (t_val, a_val):  # 先保留 target，再叠加源
                if not isinstance(src, dict):
                    continue
                for k, arr in src.items():
                    if not isinstance(arr, list):
                        continue
                    bucket = base.setdefault(k, [])
                    seen = {json.dumps(x, sort_keys=True) for x in bucket if isinstance(x, dict)}
                    for x in arr:
                        if not isinstance(x, dict):
                            continue
                        key = json.dumps(x, sort_keys=True)
                        if key not in seen:
                            bucket.append(x)
                            seen.add(key)
            return base if base else None
        else:
            # 目标结构：list[{"name": "...", "file": "..."}]
            merged_list = []
            seen_pairs = set()

            def add_from(src):
                if not isinstance(src, list):
                    return
                for x in src:
                    if not isinstance(x, dict):
                        continue
                    name = x.get("name")
                    file_ = x.get("file")
                    key = (name, file_)
                    if key not in seen_pairs:
                        merged_list.append(x)
                        seen_pairs.add(key)

            for src in (t_val, a_val):
                add_from(src)

            return merged_list if merged_list else None

    def _safe_backup(self, path: str):
        try:
            bak = path + ".bak"
            if not os.path.exists(bak):
                import shutil
                shutil.copy2(path, bak)
        except Exception:
            pass
