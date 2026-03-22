import json
import os
import sys
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QHBoxLayout, QMessageBox, QLabel, QHeaderView, QLineEdit, QGroupBox
)
from PySide6.QtCore import Qt
from utils.composite_jsonl import parse_composite_jsonl, stringify_composite_jsonl
from utils.common import save_config, load_config

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


class JsonlEditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.jsonl_path = ""
        self.data = []
        self.summary_line = None  # 保存 summary 行（包含 motions/expressions/import）
        # 预览窗口相关
        self.preview_thread = None  # 预览窗口线程引用
        self.preview_window = None  # 预览窗口实例引用（用于关闭）
        self.main_window = None  # 主窗口引用

        self.layout = QVBoxLayout(self)

        # 顶部按钮
        btn_layout = QHBoxLayout()
        self.load_btn = QPushButton("📂 导入 JSONL")
        self.load_btn.clicked.connect(self.load_jsonl)
        self.save_btn = QPushButton("💾 保存 JSONL")
        self.save_btn.clicked.connect(self.save_jsonl)
        self.save_as_btn = QPushButton("📝 另存为 JSONL")
        self.save_as_btn.clicked.connect(self.save_as_jsonl)
        self.preview_btn = QPushButton("👁️ 预览模型")
        self.preview_btn.clicked.connect(self.preview_models)
        btn_layout.addWidget(self.load_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.save_as_btn)
        btn_layout.addWidget(self.preview_btn)


        self.layout.addLayout(btn_layout)

        # 文件路径显示
        self.path_label = QLabel("未加载")
        self.layout.addWidget(self.path_label)

        # Import 参数编辑区域
        import_group = QGroupBox("Import 参数（最后一行）")
        import_layout = QHBoxLayout()
        import_layout.addWidget(QLabel("version:"))
        self.version_input = QLineEdit()
        self.version_input.setPlaceholderText("2")
        self.version_input.setMaximumWidth(120)
        import_layout.addWidget(self.version_input)
        import_layout.addWidget(QLabel("import:"))
        self.import_input = QLineEdit()
        self.import_input.setPlaceholderText("输入数字（例如：100）")
        self.import_input.setMaximumWidth(200)
        import_layout.addWidget(self.import_input)
        import_layout.addStretch()
        import_group.setLayout(import_layout)
        self.layout.addWidget(import_group)

        # 表格展示
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.table)

    def load_jsonl(self):
        config = load_config()
        last_open_dir = config.get("jsonl_last_open_dir", "")
        if not last_open_dir or not os.path.isdir(last_open_dir):
            last_open_dir = ""

        path, _ = QFileDialog.getOpenFileName(
            self, "选择 JSONL 文件", last_open_dir, "JSONL 文件 (*.jsonl)"
        )
        if not path:
            return

        self._load_file(path)

    def _parse_and_display(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                manifest = parse_composite_jsonl(f.read(), source=path)

            self.jsonl_path = path
            self.path_label.setText(f"当前文件：{path}")
            self.data = [dict(item) for item in manifest.get("parts", [])]
            for item in self.data:
                item.pop("lineNumber", None)
            self.summary_line = dict(manifest.get("summary", {}))
            self.summary_line.pop("lineNumber", None)
            version_val = self.summary_line.get("version")
            if version_val is not None:
                self.version_input.setText(str(version_val))
            else:
                self.version_input.clear()
            import_val = self.summary_line.get("import")
            if import_val is not None:
                self.import_input.setText(str(import_val))
            else:
                self.import_input.clear()
            self.table.setRowCount(0)

            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "读取失败", str(e))

    def refresh_table(self):
        self.table.setRowCount(len(self.data))
        for row, obj in enumerate(self.data):
            for col, key in enumerate(TABLE_COLUMNS):
                value = obj.get(key, "")
                item = QTableWidgetItem(str(value))
                if key in ["index", "x", "y", "xscale", "yscale", "loop", "muted", "autoplay", "playsinline"]:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    def save_jsonl(self):
        if not self.jsonl_path or not os.path.isfile(self.jsonl_path):
            QMessageBox.warning(self, "未加载文件", "请先导入 JSONL 文件")
            return

        try:
            # 从表格更新 self.data
            for row, obj in enumerate(self.data):
                for col, key in enumerate(TABLE_COLUMNS):
                    item = self.table.item(row, col)
                    text = item.text().strip() if item else ""
                    if key == "index":
                        if text:
                            try:
                                obj[key] = int(float(text))
                            except ValueError:
                                pass
                        elif key in obj:
                            del obj[key]
                    elif key in ["x", "y", "xscale", "yscale"]:
                        try:
                            value = float(text) if text else None
                            if value is not None:
                                obj[key] = value
                            elif key in obj:
                                del obj[key]
                        except ValueError:
                            continue
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
                    else:
                        if text:
                            obj[key] = text
                        elif key in obj:
                            del obj[key]

            summary = dict(self.summary_line or {})
            version_text = self.version_input.text().strip()
            if version_text:
                try:
                    summary["version"] = int(float(version_text))
                except ValueError:
                    QMessageBox.warning(self, "警告", f"version 必须是整数，当前值：{version_text}")
                    return
            else:
                summary.pop("version", None)
            import_text = self.import_input.text().strip()
            if import_text:
                try:
                    summary["import"] = int(import_text)
                except ValueError:
                    QMessageBox.warning(self, "警告", f"import 参数必须是整数，当前值：{import_text}")
                    return
            else:
                summary.pop("import", None)

            new_text = stringify_composite_jsonl(self.data, summary)

            with open(self.jsonl_path, "w", encoding="utf-8") as f:
                f.write(new_text + "\n")

            QMessageBox.information(self, "保存成功", f"已保存：{self.jsonl_path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def save_as_jsonl(self):
        if not self.jsonl_path or not os.path.isfile(self.jsonl_path):
            QMessageBox.warning(self, "⚠️", "请先导入 JSONL 文件")
            return

        # 更新 self.data 以包含用户在表格中的修改
        try:
            for row, obj in enumerate(self.data):
                for col, key in enumerate(TABLE_COLUMNS):
                    item = self.table.item(row, col)
                    if item:
                        text = item.text().strip()
                        if key == "index":
                            if text:
                                try:
                                    obj[key] = int(float(text))
                                except ValueError:
                                    obj[key] = 0
                            elif key in obj:
                                del obj[key]
                        elif key in ["x", "y", "xscale", "yscale"]:
                            try:
                                obj[key] = float(text)
                            except Exception:
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
                        else:
                            if text:
                                obj[key] = text
                            elif key in obj:
                                del obj[key]
        except Exception as e:
            QMessageBox.critical(self, "⚠️", f"更新表格数据失败：{e}")
            return

        # 选择保存路径
        # 优先使用上次保存的目录，其次使用当前文件所在目录
        config = load_config()
        last_save_dir = config.get("jsonl_last_save_dir", "")
        if last_save_dir and os.path.isdir(last_save_dir):
            default_path = os.path.join(last_save_dir, "new_file.jsonl")
        else:
            dir_path = os.path.dirname(self.jsonl_path)
            default_path = os.path.join(dir_path, "new_file.jsonl")
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, "另存为 JSONL 文件", default_path, "JSONL 文件 (*.jsonl)"
        )
        if not save_path:
            return
        
        # 保存本次保存的目录到配置
        save_dir = os.path.dirname(save_path)
        if save_dir and os.path.isdir(save_dir):
            save_config({"jsonl_last_save_dir": save_dir})

        try:
            summary = dict(self.summary_line or {})
            version_text = self.version_input.text().strip()
            if version_text:
                try:
                    summary["version"] = int(float(version_text))
                except ValueError:
                    QMessageBox.warning(self, "警告", f"version 必须是整数，当前值：{version_text}")
                    return
            else:
                summary.pop("version", None)
            import_text = self.import_input.text().strip()
            if import_text:
                try:
                    summary["import"] = int(import_text)
                except ValueError:
                    QMessageBox.warning(self, "警告", f"import 参数必须是整数，当前值：{import_text}")
                    return
            else:
                summary.pop("import", None)

            text = stringify_composite_jsonl(self.data, summary)

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(text + "\n")

            QMessageBox.information(self, "保存成功", f"文件已保存为：{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def preview_models(self):
        """预览 JSONL 文件中的模型"""
        if not self.jsonl_path or not os.path.isfile(self.jsonl_path):
            QMessageBox.warning(self, "未加载文件", "请先导入 JSONL 文件")
            return

        if not self.data:
            QMessageBox.warning(self, "无数据", "JSONL 文件中没有有效的模型数据")
            return

        # 检查是否已有预览窗口在运行，如果有则直接关闭
        if self.preview_thread is not None and self.preview_thread.is_alive():
            # 直接关闭旧的预览窗口
            self._close_preview_window()

        # 禁用主窗口
        if self.main_window:
            self.main_window.disable_main_window()
        
        # 在单独线程中运行预览窗口（避免阻塞 UI）
        self.preview_thread = threading.Thread(target=self._run_preview_window, daemon=True)
        self.preview_thread.start()

    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().endswith(".jsonl") for u in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith(".jsonl") and os.path.isfile(path):
                self._load_file(path)
                break

    def _load_file(self, path: str):
        """统一的文件加载入口，供按钮和拖拽共用"""
        open_dir = os.path.dirname(path)
        if open_dir and os.path.isdir(open_dir):
            save_config({"jsonl_last_open_dir": open_dir})
        self._parse_and_display(path)
    
    def _close_preview_window(self):
        """关闭预览窗口并等待线程退出"""
        if self.preview_window is not None:
            try:
                self.preview_window.running = False
            except Exception as e:
                print(f"关闭预览窗口时出错: {e}")
            finally:
                self.preview_window = None

        if self.preview_thread is not None and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=3.0)
            if self.preview_thread.is_alive():
                print("警告: 预览窗口线程未能及时关闭")
        self.preview_thread = None

        if self.main_window:
            self.main_window.enable_main_window()

    def _run_preview_window(self):
        """在独立线程中运行预览窗口"""
        try:
            from pages.jsonl_preview_window import JsonlPreviewWindow
            self.preview_window = JsonlPreviewWindow(self.jsonl_path, self.data)
            self.preview_window.run()
        except Exception as e:
            # 使用 QMessageBox 需要在主线程，这里用 print
            print(f"预览窗口启动失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.main_window:
                self.main_window.enable_main_window()
            self.preview_window = None
            self.preview_thread = None


