# pages/jsonl_generator_page.py
import os
import json
import tempfile
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel,
    QListWidget, QFileDialog, QMessageBox, QCheckBox, QTextEdit, QDialog,
    QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox
)
from PySide6.QtCore import Qt

from sections.gen_jsonl import collect_jsons_to_jsonl, is_valid_live2d_json
from sections.py_live2d_editor import get_all_param_info_list
from utils.composite_jsonl import parse_composite_jsonl, stringify_composite_jsonl
from utils.common import save_config, load_config, get_resource_path, _norm_id, _pget, _to_key

# ===== Live2D 依赖（用于一键计算）=====
import pygame

try:
    import live2d.v2 as live2d

    _LIVE2D_OK = True
except Exception:
    _LIVE2D_OK = False

TABLE_COLUMNS = [
    "index",
    "type",
    "id",
    "path",
    "folder",
    "x",
    "y",
    "xscale",
    "yscale",
    "loop",
    "muted",
    "autoplay",
    "playsinline",
]


def _parse_bool_text(value: str):
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    return None


class JsonlGeneratorPage(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # ===== 统一 import 选项 =====
        self.append_import_checkbox = QCheckBox("统一 import")
        self.import_value_input = QLineEdit()
        self.import_value_input.setPlaceholderText("50")

        row1 = QHBoxLayout()
        row1.addWidget(self.append_import_checkbox)
        row1.addWidget(self.import_value_input)
        self.layout.addLayout(row1)

        # ===== 根目录 & 前缀 =====
        self.select_root_btn = QPushButton("选择根目录")
        self.select_root_btn.clicked.connect(self.select_jsonl_root)
        self.layout.addWidget(self.select_root_btn)

        self.jsonl_root_label = QLabel("未选择")
        self.layout.addWidget(self.jsonl_root_label)

        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("ID 前缀")
        self.jsonl_prefix_input = self.prefix_input
        self.layout.addWidget(QLabel("ID 前缀："))
        self.layout.addWidget(self.prefix_input)

        # ===== 子目录列表 =====
        sub_list_layout = QHBoxLayout()
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        sub_list_layout.addWidget(self.folder_list)

        btn_layout = QVBoxLayout()
        self.up_btn = QPushButton("↑ 上移")
        self.up_btn.clicked.connect(self.move_folder_up)
        self.down_btn = QPushButton("↓ 下移")
        self.down_btn.clicked.connect(self.move_folder_down)
        btn_layout.addWidget(QLabel("顺序调整："))
        btn_layout.addWidget(self.up_btn)
        btn_layout.addWidget(self.down_btn)
        sub_list_layout.addLayout(btn_layout)
        self.layout.addLayout(sub_list_layout)

        self.list_btn = QPushButton("📂 列出子目录")
        self.list_btn.clicked.connect(self.populate_folder_list)
        self.layout.addWidget(self.list_btn)

        # ===== 生成 JSONL（改为：先弹窗编辑 / 计算；不在磁盘留初稿）=====
        self.generate_btn = QPushButton("生成 JSONL（先预览并填写/计算 x/y/scale）")
        self.generate_btn.clicked.connect(self.run_generate_jsonl_with_preview)
        self.layout.addWidget(self.generate_btn)

    def select_jsonl_root(self):
        folder = QFileDialog.getExistingDirectory(self, "选择用于生成 JSONL 的目录")
        if folder:
            self.jsonl_root = folder
            self.jsonl_root_label.setText(folder)
            self.save_config()

    def populate_folder_list(self):
        self.folder_list.clear()
        if not hasattr(self, "jsonl_root"):
            QMessageBox.warning(self, "⚠️", "请先选择根目录")
            return

        found_count = 0
        for root, _, files in os.walk(self.jsonl_root):
            for file in files:
                if file.endswith(".json"):
                    abs_path = os.path.join(root, file)
                    if os.path.isfile(abs_path) and is_valid_live2d_json(abs_path):
                        rel_path = os.path.relpath(abs_path, self.jsonl_root).replace("\\", "/")
                        self.folder_list.addItem(rel_path)
                        found_count += 1

        if found_count == 0:
            QMessageBox.information(self, "提示", "未找到任何合法的 model.json 文件")

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

    # ======= 生成 + 预览对话框（不落地初稿）=======
    def run_generate_jsonl_with_preview(self):
        if not hasattr(self, "jsonl_root"):
            QMessageBox.warning(self, "⚠️", "请先选择目录")
            return

        prefix = self.jsonl_prefix_input.text().strip()
        if not prefix:
            QMessageBox.warning(self, "⚠️", "请输入有效的 ID 前缀")
            return

        selected_items = self.folder_list.selectedItems()
        selected_relative_paths = [item.text() for item in selected_items]
        if not selected_relative_paths:
            QMessageBox.warning(self, "⚠️", "请至少选择一个子目录")
            return

        base_folder_name = os.path.basename(self.jsonl_root.rstrip(os.sep))

        # 1) 写到临时文件（放到系统临时目录；不会污染你的工程）
        fd, temp_path = tempfile.mkstemp(prefix=f"{base_folder_name}_", suffix=".tmp.jsonl")
        os.close(fd)
        try:
            collect_jsons_to_jsonl(self.jsonl_root, temp_path, prefix, base_folder_name, selected_relative_paths)

            # 2) 如果需要统一 import，先把 import 写到 summary（只是写在临时文件里）
            summary_import = None
            if self.append_import_checkbox.isChecked():
                try:
                    summary_import = int(self.import_value_input.text().strip())
                except ValueError:
                    summary_import = None
                if summary_import is not None:
                    self._inject_import_to_summary(temp_path, summary_import)

            # 3) 弹窗编辑；保存时选择“正式文件路径”
            dlg = JsonlPreviewDialog(
                temp_jsonl_path=temp_path,
                base_dir=self.jsonl_root,
                default_save_dir=self.jsonl_root,
                summary_import=summary_import,
                parent=self,
            )
            dlg.exec_()
        finally:
            # 4) 无论如何删除临时文件——不保留初稿
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    def _inject_import_to_summary(self, output_path: str, import_val: int):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                manifest = parse_composite_jsonl(f.read(), source=output_path)
            summary = dict(manifest.get("summary", {}))
            summary["import"] = import_val
            text = stringify_composite_jsonl(manifest.get("parts", []), summary)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception as e:
            print(f"⚠️ 注入 import 失败：{e}")

    def save_config(self):
        config = {"jsonl_root_path": getattr(self, "jsonl_root", "")}
        save_config(config)


# ========= 生成后“预览并填写/一键计算”对话框 =========
class JsonlPreviewDialog(QDialog):
    """
    从临时 JSONL 读取数据到表格；支持编辑 x/y/xscale/yscale；
    “一键计算 x/y”：读取 deformer_import.json 的 OriginX/OriginY，与 Live2D 的 PARAM_IMPORT 参数值结合计算。
    点击“保存并完成”时，询问最终保存路径并写出正式 JSONL 文件。
    """

    def __init__(self, temp_jsonl_path: str, base_dir: str, default_save_dir: str,
                 summary_import: int = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成前预览与参数填写")
        self.resize(1000, 680)

        self.jsonl_path = temp_jsonl_path  # 只读：临时文件
        self.base_dir = base_dir
        self.default_save_dir = default_save_dir
        self.summary_import = summary_import

        self.data = []  # 普通行
        self.summary_lines = []  # motions/expressions 行

        layout = QVBoxLayout(self)

        # ===== 默认值区域 =====
        defaults_row = QHBoxLayout()
        self.x_default = QLineEdit();
        self.x_default.setPlaceholderText("x 默认 (可空)")
        self.y_default = QLineEdit();
        self.y_default.setPlaceholderText("y 默认 (可空)")
        self.xs_default = QLineEdit();
        self.xs_default.setPlaceholderText("xscale 默认 (可空)")
        self.ys_default = QLineEdit();
        self.ys_default.setPlaceholderText("yscale 默认 (可空)")
        self.apply_all_btn = QPushButton("应用到全部")
        self.apply_all_btn.clicked.connect(self.apply_defaults_to_all)
        for w in (self.x_default, self.y_default, self.xs_default, self.ys_default, self.apply_all_btn):
            defaults_row.addWidget(w)
        layout.addLayout(defaults_row)

        # ===== 一键计算区域（独立 GroupBox，避免被挤掉）=====
        calc_group = QGroupBox("一键计算 x / y")
        calc_layout = QHBoxLayout(calc_group)
        self.import_id_edit = QLineEdit();
        self.import_id_edit.setPlaceholderText("Import ID（目标 import，例如 50）")
        self.calc_btn = QPushButton("计算全部行")
        self.calc_btn.clicked.connect(self.compute_xy_for_all)
        calc_layout.addWidget(self.import_id_edit)
        calc_layout.addWidget(self.calc_btn)
        layout.addWidget(calc_group)

        # ===== 表格 =====
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # ===== 底部按钮 =====
        btns = QHBoxLayout()
        self.save_btn = QPushButton("保存并完成")
        self.cancel_btn = QPushButton("取消")
        self.save_btn.clicked.connect(self.save_as_jsonl)  # 这里是“另存为”，不会覆盖临时文件
        self.cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.save_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        # 载入数据
        self.load_jsonl()

    # ---------- 数据加载/表格 ----------
    def load_jsonl(self):
        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                manifest = parse_composite_jsonl(f.read(), source=self.jsonl_path)

            self.data = [dict(item) for item in manifest.get("parts", [])]
            for item in self.data:
                item.pop("lineNumber", None)
            self.summary_lines = []
            summary = dict(manifest.get("summary", {}))
            summary.pop("lineNumber", None)
            if summary:
                self.summary_lines.append(summary)

            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "读取失败", str(e))
            self.reject()

    def refresh_table(self):
        self.table.setRowCount(len(self.data))
        for row, obj in enumerate(self.data):
            for col, key in enumerate(TABLE_COLUMNS):
                value = obj.get(key, "")
                item = QTableWidgetItem("" if value is None else str(value))
                if key in ["index", "id", "path", "folder"]:
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if key == "index":
                        item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    # ---------- 默认值批量填充 ----------
    def apply_defaults_to_all(self):
        defaults = {
            "x": self.x_default.text().strip(),
            "y": self.y_default.text().strip(),
            "xscale": self.xs_default.text().strip(),
            "yscale": self.ys_default.text().strip(),
        }
        for row in range(self.table.rowCount()):
            for key in ["x", "y", "xscale", "yscale"]:
                col = TABLE_COLUMNS.index(key)
                item = self.table.item(row, col)
                if not item:
                    item = QTableWidgetItem("")
                    self.table.setItem(row, col, item)
                item.setText(defaults[key])

    def compute_xy_for_all(self):
        import os, json
        from PySide6.QtWidgets import QMessageBox, QTableWidgetItem

        LIVE2D_Y_MAX = 2000.0  # 大多数立绘画幅 2000x2000
        WEBGAL_CANVAS_H = 1440  # WebGAL 高度
        SCALE_Y = WEBGAL_CANVAS_H / LIVE2D_Y_MAX  # 0.72

        # ---- 读取 deformer_import.json ----
        deform = None
        for p in [
            os.path.join(os.path.dirname(self.jsonl_path), "deformer_import.json"),
            os.path.join(os.getcwd(), "deformer_import.json"),
            get_resource_path("deformer_import.json"),  # 从打包资源读取
        ]:
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        deform = json.load(f)
                    break
                except Exception:
                    pass
        if deform is None:
            QMessageBox.warning(self, "提示", "未找到 deformer_import.json，无法读取 OriginX/OriginY。")
            return

        # ---- 目标 import（必须填）：把它作为“目标绝对坐标”的键 ----
        ui_import_raw = (self.import_id_edit.text() or "").strip()
        if not ui_import_raw:
            QMessageBox.warning(self, "提示", "请在“Import ID”输入框填写目标 Import ID（例如 50）。")
            return

        # 工具：与 utils.common 同名函数保持一致
        def _to_key(s):
            s = str(s).strip()
            if s == "":
                return None
            try:
                return str(int(round(float(s))))  # e.g. "50.0" -> "50"
            except Exception:
                return s

        def _pget(p, key, default=None):
            if isinstance(p, dict):
                return p.get(key, default)
            return getattr(p, key, default)

        def _norm_id(x):
            try:
                if isinstance(x, str):
                    return x
                if isinstance(x, (bytes, bytearray)):
                    return x.decode("utf-8", errors="ignore")
                return str(x)
            except Exception:
                return ""

        # 目标 import 的键与数值
        target_key = _to_key(ui_import_raw)
        target_entry = deform.get(target_key)
        if not isinstance(target_entry, dict):
            QMessageBox.warning(self, "提示", f"deformer_import.json 中不存在键：{target_key}")
            return
        target_x = float(target_entry.get("OriginX", 0.0))
        target_y = float(target_entry.get("OriginY", 0.0))

        # 目标 import 的“数值”（用于范围判定）
        try:
            target_import_val = float(ui_import_raw)
        except Exception:
            # 如果输入不是数值（比如特殊键名），就不做范围检测，只做坐标计算
            target_import_val = None

        success, fail = 0, 0

        # === 新增：收集“范围不覆盖目标 import”的模型信息 ===
        not_covered = []  # [(row_index, model_basename, min, max)]

        for row in range(self.table.rowCount()):
            path_item = self.table.item(row, TABLE_COLUMNS.index("path"))
            if not path_item:
                fail += 1
                continue
            model_path = path_item.text().strip()
            if not os.path.isabs(model_path):
                model_path = os.path.normpath(os.path.join(self.base_dir, model_path))
            if not os.path.isfile(model_path):
                print(f"[计算失败] 模型不存在: {model_path}")
                fail += 1
                continue

            try:
                param_info_list = get_all_param_info_list(model_path)
                if not param_info_list:
                    raise RuntimeError("未获取到模型参数")

                # 找到一个 PARAM_IMPORT*，用其 default 作为“本行”的键；同时收集它们的 min/max 以做范围检验
                default_key = None
                import_ranges = []  # [(min, max)]
                for p in param_info_list:
                    pid = _norm_id(_pget(p, "id", ""))
                    if pid.startswith("PARAM_IMPORT"):
                        # 记录范围
                        try:
                            pmin = float(_pget(p, "min", float("-inf")) or 0.0)
                        except Exception:
                            pmin = float("-inf")
                        try:
                            pmax = float(_pget(p, "max", float("inf")) or 0.0)
                        except Exception:
                            pmax = float("inf")
                        import_ranges.append((pmin, pmax))

                        # 取 default -> 键
                        d = _pget(p, "default", None)
                        if d is not None and default_key is None:
                            try:
                                default_key = _to_key(d)
                            except Exception:
                                pass

                if not import_ranges:
                    raise RuntimeError("未找到任何 PARAM_IMPORT 参数")

                # === 范围检测：目标 import 必须在任一 IMPORT 的 [min, max] 里才算覆盖 ===
                if target_import_val is not None:
                    covered_here = any((rng[0] <= target_import_val <= rng[1]) for rng in import_ranges)
                    if not covered_here:
                        # 取一个代表性的范围显示（第 1 个）
                        rmin, rmax = import_ranges[0]
                        not_covered.append((row, os.path.basename(model_path), rmin, rmax))

                if not default_key:
                    raise RuntimeError("未找到 PARAM_IMPORT 的 default 值")

                row_entry = deform.get(default_key)
                if not isinstance(row_entry, dict):
                    raise RuntimeError(f"deformer_import.json 中不存在键（由 default 推导）：{default_key}")

                row_x = float(row_entry.get("OriginX", 0.0))
                row_y = float(row_entry.get("OriginY", 0.0))

                # 差值（Live2D 坐标系）
                delta_x = target_x - row_x
                delta_y = (target_y - row_y) * SCALE_Y  # 仅对 Y 做比例缩放

                # 回写表格（x/y 填相对量）
                for k, v in (("x", delta_x), ("y", delta_y)):
                    col = TABLE_COLUMNS.index(k)
                    item = self.table.item(row, col)
                    if not item:
                        item = QTableWidgetItem("")
                        self.table.setItem(row, col, item)
                    item.setText(f"{v:.6f}")

                success += 1

            except Exception as e:
                print(f"[计算失败] {model_path}: {e}")
                fail += 1

        # === 结束提示：附带“统一 import”建议 ===
        if target_import_val is not None and len(not_covered) == 0:
            # 所有模型都覆盖目标 import
            QMessageBox.information(
                self,
                "完成",
                f"已计算 {success} 行；失败 {fail} 行。\n\n"
                f"✅ 所有模型的 PARAM_IMPORT 取值范围都覆盖目标 import={target_import_val}。\n"
                f"可以在主界面勾选“统一 import”，并填写 {int(round(target_import_val))} 以统一导出。"
            )
        else:
            extra = ""
            if target_import_val is not None and not_covered:
                lines = []
                for r, name, rmin, rmax in not_covered:
                    lines.append(f" - 行 {r + 1}（{name}）范围 [{rmin}, {rmax}] 不覆盖 {target_import_val}")
                extra = "\n\n⚠️ 部分模型范围不覆盖目标 import：\n" + "\n".join(lines)
            QMessageBox.information(self, "完成", f"已计算 {success} 行；失败 {fail} 行。{extra}")

    # ---------- 另存为（最终写出 JSONL） ----------
    def save_as_jsonl(self):
        # 先把表格回写到 self.data
        try:
            for row, obj in enumerate(self.data):
                for col, key in enumerate(TABLE_COLUMNS):
                    item = self.table.item(row, col)
                    text = item.text().strip() if item else ""
                    if key in ["index", "id", "path", "folder"]:
                        continue
                    if key in ["x", "y", "xscale", "yscale"]:
                        if text == "":
                            if key in obj:
                                del obj[key]
                            continue
                        try:
                            obj[key] = float(text)
                        except ValueError:
                            if key in obj:
                                del obj[key]
                    elif key in ["loop", "muted", "autoplay", "playsinline"]:
                        parsed = _parse_bool_text(text)
                        if parsed is not None:
                            obj[key] = parsed
                        elif key in obj:
                            del obj[key]
                    elif key == "type":
                        normalized = text.lower() if text else ""
                        if normalized in {"live2d", "image", "gif", "video"}:
                            obj[key] = normalized
                        elif key in obj:
                            del obj[key]
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"读取表格出错：{e}")
            return

        # 询问保存路径
        from PySide6.QtWidgets import QFileDialog
        # 读取上次保存的目录
        config = load_config()
        last_save_dir = config.get("jsonl_last_save_dir", "")
        if last_save_dir and os.path.isdir(last_save_dir):
            default_path = os.path.join(last_save_dir, "model.jsonl")
        else:
            default_path = os.path.join(self.default_save_dir, "model.jsonl")
        
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 JSONL",
            default_path,  # ✅ 使用上次保存的目录或默认目录
            "JSONL 文件 (*.jsonl)"
        )
        if not save_path:
            return
        
        # 保存本次保存的目录到配置
        save_dir = os.path.dirname(save_path)
        if save_dir and os.path.isdir(save_dir):
            save_config({"jsonl_last_save_dir": save_dir})

        # 组装最终行：普通行 + summary 行（必要时覆盖 summary.import）
        try:
            lines = []
            for obj in self.data:
                lines.append(json.dumps(obj, ensure_ascii=False) + "\n")

            if self.summary_lines:
                summary = self.summary_lines[-1]
                if isinstance(summary, dict) and self.summary_import is not None:
                    summary["import"] = self.summary_import
                lines.append(json.dumps(summary, ensure_ascii=False) + "\n")

            with open(save_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            QMessageBox.information(self, "保存成功", f"已保存：{save_path}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
