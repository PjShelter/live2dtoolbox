import json
import os
import sys
import threading
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QHBoxLayout, QMessageBox, QLabel, QHeaderView, QLineEdit, QGroupBox
)
from PyQt5.QtCore import Qt


class JsonlEditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.jsonl_path = ""
        self.data = []
        self.summary_line = None  # 保存 summary 行（包含 motions/expressions/import）
        # 预览窗口相关
        self.preview_thread = None  # 预览窗口线程引用
        self.preview_window = None  # 预览窗口实例引用（用于关闭）

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
        import_layout.addWidget(QLabel("import:"))
        self.import_input = QLineEdit()
        self.import_input.setPlaceholderText("输入数字（例如：100）")
        self.import_input.setMaximumWidth(200)
        import_layout.addWidget(self.import_input)
        import_layout.addStretch()
        import_group.setLayout(import_layout)
        self.layout.addWidget(import_group)

        # 表格展示
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["index", "id", "path", "folder", "x", "y", "xscale", "yscale"])
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.table)

    def load_jsonl(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 JSONL 文件", "", "JSONL 文件 (*.jsonl)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            self.jsonl_path = path
            self.path_label.setText(f"当前文件：{path}")
            self.data = []
            self.summary_line = None

            self.table.setRowCount(0)

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "motions" in obj or "expressions" in obj:
                    # 保存 summary 行
                    self.summary_line = obj
                    # 读取 import 参数并显示
                    import_val = obj.get("import")
                    if import_val is not None:
                        self.import_input.setText(str(import_val))
                    else:
                        self.import_input.clear()
                    continue
                self.data.append(obj)

            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "读取失败", str(e))

    def refresh_table(self):
        self.table.setRowCount(len(self.data))
        for row, obj in enumerate(self.data):
            for col, key in enumerate(["index", "id", "path", "folder", "x", "y", "xscale", "yscale"]):
                value = obj.get(key, "")
                item = QTableWidgetItem(str(value))
                if key in ["index", "x", "y", "xscale", "yscale"]:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    def save_jsonl(self):
        if not self.jsonl_path or not os.path.isfile(self.jsonl_path):
            QMessageBox.warning(self, "未加载文件", "请先导入 JSONL 文件")
            return

        try:
            # 从表格更新 self.data
            for row, obj in enumerate(self.data):
                for key in ["x", "y", "xscale", "yscale"]:
                    item = self.table.item(row, ["index", "id", "path", "folder", "x", "y", "xscale", "yscale"].index(key))
                    try:
                        value = float(item.text()) if item and item.text().strip() else None
                        if value is not None:
                            obj[key] = value
                        elif key in obj:
                            del obj[key]  # 删除空值字段
                    except ValueError:
                        continue  # 跳过非法数字

            # 读取原始 JSONL 并写回（保留 summary 行）
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            idx = 0
            for line in lines:
                obj = json.loads(line)
                if "motions" in obj or "expressions" in obj:
                    # 更新 summary 行的 import 参数
                    import_text = self.import_input.text().strip()
                    if import_text:
                        try:
                            obj["import"] = int(import_text)
                        except ValueError:
                            QMessageBox.warning(self, "警告", f"import 参数必须是整数，当前值：{import_text}")
                            return
                    elif "import" in obj:
                        # 如果输入框为空，删除 import 字段
                        del obj["import"]
                    new_lines.append(json.dumps(obj, ensure_ascii=False) + '\n')
                else:
                    new_lines.append(json.dumps(self.data[idx], ensure_ascii=False) + '\n')
                    idx += 1

            with open(self.jsonl_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

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
                for col, key in enumerate(["index", "id", "path", "folder", "x", "y", "xscale", "yscale"]):
                    item = self.table.item(row, col)
                    if item:
                        text = item.text().strip()
                        if key in ["index"]:
                            obj[key] = int(text) if text.isdigit() else 0
                        elif key in ["x", "y", "xscale", "yscale"]:
                            try:
                                obj[key] = float(text)
                            except:
                                if key in obj:
                                    del obj[key]  # 无效数字就删掉
                        else:
                            obj[key] = text
        except Exception as e:
            QMessageBox.critical(self, "⚠️", f"更新表格数据失败：{e}")
            return

        # 选择保存路径
        dir_path = os.path.dirname(self.jsonl_path)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "另存为 JSONL 文件", os.path.join(dir_path, "new_file.jsonl"), "JSONL 文件 (*.jsonl)"
        )
        if not save_path:
            return

        try:
            # 构建新的 JSONL 内容
            lines = []
            for obj in self.data:
                lines.append(json.dumps(obj, ensure_ascii=False) + "\n")

            # 添加原始 JSONL 的 summary 行（更新 import 参数）
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                        if "motions" in obj or "expressions" in obj:
                            # 更新 import 参数
                            import_text = self.import_input.text().strip()
                            if import_text:
                                try:
                                    obj["import"] = int(import_text)
                                except ValueError:
                                    QMessageBox.warning(self, "警告", f"import 参数必须是整数，当前值：{import_text}")
                                    return
                            elif "import" in obj:
                                # 如果输入框为空，删除 import 字段
                                del obj["import"]
                            lines.append(json.dumps(obj, ensure_ascii=False) + "\n")
                    except:
                        continue

            with open(save_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

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

        # 在单独线程中运行预览窗口（避免阻塞 UI）
        self.preview_thread = threading.Thread(target=self._run_preview_window, daemon=True)
        self.preview_thread.start()

    def _close_preview_window(self):
        """关闭预览窗口"""
        if self.preview_window is not None:
            try:
                # 如果预览窗口有关闭方法，调用它
                if hasattr(self.preview_window, 'close'):
                    self.preview_window.close()
                elif hasattr(self.preview_window, 'running'):
                    self.preview_window.running = False
            except Exception as e:
                print(f"关闭预览窗口时出错: {e}")
            finally:
                self.preview_window = None
        
        # 等待线程结束（最多等待 1 秒）
        if self.preview_thread is not None and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=1.0)
            if self.preview_thread.is_alive():
                print("警告: 预览窗口线程未能及时关闭")

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
            # 清理引用
            self.preview_window = None
            # 注意：不要在这里设置 self.preview_thread = None，因为线程可能还在运行


