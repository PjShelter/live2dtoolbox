# pages/jsonl_generator_page.py
import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QCheckBox, QTextEdit, QDialog, QAbstractItemView
)

from sections.gen_jsonl import collect_jsons_to_jsonl, find_live2d_json_file, is_valid_live2d_json
from utils.common import save_config, get_resource_path


class JsonlGeneratorPage(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.append_import_checkbox = QCheckBox("统一 import")
        self.import_value_input = QLineEdit()
        self.import_value_input.setPlaceholderText("50")

        row1 = QHBoxLayout()
        row1.addWidget(self.append_import_checkbox)
        row1.addWidget(self.import_value_input)
        self.layout.addLayout(row1)

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

        # 子目录列表
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

        self.generate_btn = QPushButton("生成 JSONL")
        self.generate_btn.clicked.connect(self.run_generate_jsonl)
        self.layout.addWidget(self.generate_btn)

        # self.import_table_btn = QPushButton("📄 查看 import 参数表")
        # self.import_table_btn.clicked.connect(self.show_import_table)
        # self.layout.addWidget(self.import_table_btn)

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
                    # ✅ 只检查文件，不尝试对它 listdir
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

    def run_generate_jsonl(self):
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

        # ✅ 已经是合法的 model.json 相对路径了，直接使用
        valid_relative_paths = selected_relative_paths

        base_folder_name = os.path.basename(self.jsonl_root.rstrip(os.sep))
        output_path = os.path.join(self.jsonl_root, f"{base_folder_name}.jsonl")

        try:
            collect_jsons_to_jsonl(self.jsonl_root, output_path, prefix, base_folder_name, selected_relative_paths)

            if self.append_import_checkbox.isChecked():
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

            QMessageBox.information(self, "完成", f"JSONL 文件已生成：{output_path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ 出错", f"生成失败：{str(e)}")

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

    def save_config(self):
        from utils.common import save_config
        config = {
            "jsonl_root_path": getattr(self, "jsonl_root", "")
        }
        save_config(config)
