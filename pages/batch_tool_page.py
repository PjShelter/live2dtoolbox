import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QGroupBox, QMessageBox, QDialog
)
from PyQt5.QtCore import Qt

from filedialog.FileSelectionDialog import FileSelectionDialog
from sections.live2d_tool import (
    scan_live2d_directory,
    update_model_json_bulk,
    remove_duplicates_and_check_files,
    batch_update_mtn_param_text
)
from utils.common import save_config


class BatchToolPage(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setSpacing(12)

        # 1️⃣ 扫描生成 model.json
        btn_scan = QPushButton("📂 扫描目录并生成 model.json")
        btn_scan.clicked.connect(self.generate_model_json)
        layout.addWidget(btn_scan)

        # 2️⃣ 去重清理
        btn_dedup = QPushButton("🧹 去重并清理 model.json")
        btn_dedup.clicked.connect(self.clean_model_json)
        layout.addWidget(btn_dedup)

        # 3️⃣ 批量添加动作/表情
        group_add = QGroupBox("📦 批量添加动作/表情")
        add_layout = QVBoxLayout()

        self.model_path_input = QLineEdit()
        self.model_path_input.setPlaceholderText("立绘json路径或聚合模型jsonl路径")
        self.model_path_btn = QPushButton("🎯")
        self.model_path_btn.setFixedWidth(30)
        self.model_path_btn.clicked.connect(self.select_batch_model_json)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("📘 model.json"))
        row1.addWidget(self.model_path_input)
        row1.addWidget(self.model_path_btn)

        self.motion_dir_input = QLineEdit()
        self.motion_dir_input.setPlaceholderText("动作或表情所在目录")
        self.motion_dir_btn = QPushButton("📁")
        self.motion_dir_btn.setFixedWidth(30)
        self.motion_dir_btn.clicked.connect(self.choose_motion_dir)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("📂 动作/表情"))
        row2.addWidget(self.motion_dir_input)
        row2.addWidget(self.motion_dir_btn)

        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("前缀（可选）")

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("🔤 前缀"))
        row3.addWidget(self.prefix_input)

        self.add_btn = QPushButton("执行添加")
        self.add_btn.clicked.connect(self.run_batch_add)

        add_layout.addLayout(row1)
        add_layout.addLayout(row2)
        add_layout.addLayout(row3)
        add_layout.addWidget(self.add_btn)

        group_add.setLayout(add_layout)
        layout.addWidget(group_add)

        # 4️⃣ 批量修改 MTN 文件参数
        group_param = QGroupBox("🛠️ 批量修改 MTN 文件参数")
        param_layout = QVBoxLayout()

        self.mtn_dir_input = QLineEdit()
        self.mtn_dir_input.setPlaceholderText("包含 mtn 的目录")
        self.mtn_dir_btn = QPushButton("📁")
        self.mtn_dir_btn.setFixedWidth(30)
        self.mtn_dir_btn.clicked.connect(self.choose_mtn_dir)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("📁 mtn 目录"))
        row4.addWidget(self.mtn_dir_input)
        row4.addWidget(self.mtn_dir_btn)

        self.param_name_input = QLineEdit()
        self.param_name_input.setPlaceholderText("参数名（如 PARAM_IMPORT）")
        self.param_name_input.setText("PARAM_IMPORT")

        self.param_value_input = QLineEdit()
        self.param_value_input.setPlaceholderText("新值（可参考import参数表）")

        row5 = QHBoxLayout()
        row5.addWidget(QLabel("参数名"))
        row5.addWidget(self.param_name_input)
        row5.addWidget(QLabel("新值"))
        row5.addWidget(self.param_value_input)

        self.update_btn = QPushButton("批量更新")
        self.update_btn.clicked.connect(self.update_param)

        param_layout.addLayout(row4)
        param_layout.addLayout(row5)
        param_layout.addWidget(self.update_btn)

        group_param.setLayout(param_layout)
        layout.addWidget(group_param)

        self.setLayout(layout)

        self.load_config()

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
            self.model_path_input.setText(path)
            self.save_config()

    def choose_motion_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择动作或表情目录")
        if path:
            self.motion_dir_input.setText(path)
            self.batch_file_or_dir = path
    def choose_mtn_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择包含 .mtn 的目录")
        if path:
            self.mtn_dir_input.setText(path)

    def generate_model_json(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择 Live2D 资源目录")
        if not dir_path:
            return
        model = scan_live2d_directory(dir_path)
        save_path = os.path.join(dir_path, "model.json")
        with open(save_path, "w", encoding="utf-8") as f:
            import json
            json.dump(model, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "完成", f"model.json 已生成：\n{save_path}")

    def clean_model_json(self):
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

    def save_config(self):
        from utils.common import save_config as global_save_config

        config = {
            "l2d_model_json_path": getattr(self, "batch_model_json_path", ""),
            "l2d_file_or_dir": getattr(self, "batch_file_or_dir", "")
        }
        global_save_config(config)

    def load_config(self):
        from utils.common import load_config
        config = load_config()

        self.batch_model_json_path = config.get("l2d_model_json_path", "")
        self.batch_file_or_dir = config.get("l2d_file_or_dir", "")

        self.model_path_input.setText(self.batch_model_json_path)
        self.motion_dir_input.setText(self.batch_file_or_dir)

    def update_param(self):
        dir_path = self.mtn_dir_input.text().strip()
        param = self.param_name_input.text().strip()
        value = self.param_value_input.text().strip()

        if not dir_path or not param or not value:
            QMessageBox.warning(self, "缺少信息", "请填写完整的目录、参数名和新值")
            return

        try:
            batch_update_mtn_param_text(dir_path, param, value)
            QMessageBox.information(self, "完成", f"{param} 已更新为 {value}")
        except Exception as e:
            QMessageBox.critical(self, "出错", f"更新失败：\n{str(e)}")

