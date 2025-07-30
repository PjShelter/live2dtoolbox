# pages/l2dw_conf_page.py
import os
import json
import sys

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox
)


class L2dwConfPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        self.figure_path = ""
        self.jsonl_path = ""
        self.output_dir = ""

        self.info_label = QLabel("请选择 WebGAL Terre 的 figure 文件夹和 JSONL 文件喵～")
        self.layout().addWidget(self.info_label)

        self.select_figure_btn = QPushButton("📁 选择 figure 文件夹")
        self.select_figure_btn.clicked.connect(self.select_figure_folder)
        self.layout().addWidget(self.select_figure_btn)

        self.select_jsonl_btn = QPushButton("📄 选择 .jsonl 文件")
        self.select_jsonl_btn.clicked.connect(self.select_jsonl_file)
        self.layout().addWidget(self.select_jsonl_btn)

        self.generate_btn = QPushButton("🛠️ 生成 conf 文件")
        self.generate_btn.clicked.connect(self.generate_conf)
        self.layout().addWidget(self.generate_btn)

        self.select_output_btn = QPushButton("📁 选择输出目录（可选）")
        self.select_output_btn.clicked.connect(self.select_output_folder)
        self.layout().addWidget(self.select_output_btn)

        self.conf_path = ""

        self.select_conf_btn = QPushButton("📄 选择 conf 文件")
        self.select_conf_btn.clicked.connect(self.select_conf_file)
        self.layout().addWidget(self.select_conf_btn)

        self.convert_conf_btn = QPushButton("🔁 conf 转 JSONL")
        self.convert_conf_btn.clicked.connect(self.convert_conf_to_jsonl)
        self.layout().addWidget(self.convert_conf_btn)


    def select_figure_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 figure 文件夹")
        if folder:
            self.figure_path = folder
            self.update_info()

    def select_jsonl_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 .jsonl 文件", "", "JSONL 文件 (*.jsonl)")
        if path:
            self.jsonl_path = path
            self.update_info()

    def update_info(self):
        self.info_label.setText(
            f"🎀 figure 文件夹: {self.figure_path or '未选择'}\n"
            f"🎀 JSONL 文件: {self.jsonl_path or '未选择'}\n"
            f"📤 输出目录: {self.output_dir or '未设置（默认 jsonl/output_conf）'}"
        )

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.output_dir = folder
            self.update_info()

    def generate_conf(self):
        if not self.figure_path or not self.jsonl_path:
            QMessageBox.warning(self, "未完成选择", "请先选择 figure 文件夹和 JSONL 文件喵～")
            return

        try:
            # 1. 读取 jsonl 中的 path 字段
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                jsonl_lines = [
                    json.loads(line)
                    for line in f
                    if line.strip().startswith("{") and '"path"' in line and '"id"' in line
                ]

            relative_model_paths = [entry["path"] for entry in jsonl_lines if "path" in entry]
            if not relative_model_paths:
                QMessageBox.warning(self, "格式错误", "JSONL 文件中未找到有效的 path 字段喵～")
                return

            # 2. 计算相对路径（jsonl 所在目录相对于 figure 根目录）
            jsonl_dir = os.path.dirname(self.jsonl_path)
            figure_rel_path = os.path.relpath(jsonl_dir, self.figure_path).replace("\\", "/")

            # 3. 拼接完整模型路径
            full_paths = [f"{figure_rel_path}/{path}".replace("\\", "/") for path in relative_model_paths]

            # 4. 构建 conf 内容
            conf_base_name = os.path.splitext(os.path.basename(self.jsonl_path))[0]
            change_lines = [
                f"changeFigure:{path} -id={entry.get('id', 'model')} %me%;"
                for path, entry in zip(full_paths, jsonl_lines)
            ]
            change_line = "\\n".join(change_lines)

            settransform_lines = [
                f"setTransform:%me% -target={entry.get('id', 'model')} -duration=750;"
                for entry in jsonl_lines
            ]
            settransform_line = "\\n".join(settransform_lines)

            # ✅ 默认 transform 行
            transform_line = "0.000|0.000|1.000|0.000"

            # ✅ 构建动态 offset 行：从第 2 个模型开始
            offsets = []

            # 获取主模型的位置
            main_model = jsonl_lines[0]
            main_x = float(main_model.get("x", 0))
            main_y = float(main_model.get("y", 0))

            for entry in jsonl_lines[1:]:
                x = float(entry.get("x", 0))
                y = float(entry.get("y", 0))
                offset_x = abs(round(x - main_x))
                offset_y = abs(round(y - main_y))
                offsets.append(str(offset_x))
                offsets.append(str(offset_y))

            offset_line = ",".join(offsets)

            conf_lines = [
                conf_base_name,
                change_line,
                full_paths[0],
                settransform_line,
                transform_line,  # 固定主模型位移
                "\\n".join(full_paths[1:]),
                offset_line,  # 所有部件的 x, y 差值（动态）
                "0"
            ]

            # 5. 保存路径：output_conf 在软件目录下
            if self.output_dir:
                output_path = self.output_dir
            else:
                # 软件根目录
                base_dir = getattr(sys, '_MEIPASS', os.path.abspath("."))
                output_path = os.path.join(base_dir, "output_conf")
                os.makedirs(output_path, exist_ok=True)

            conf_path = os.path.join(output_path, f"{conf_base_name}.conf")
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(conf_lines))

            QMessageBox.information(self, "生成成功喵", f"conf 文件已生成：\n{conf_path}")
        except Exception as e:
            QMessageBox.critical(self, "出错了喵", f"生成 conf 失败：\n{str(e)}")

    def select_conf_file(self):
        default_dir = os.path.join(os.path.abspath("."), "output_conf")
        path, _ = QFileDialog.getOpenFileName(self, "选择 .conf 文件", default_dir, "CONF 文件 (*.conf)")
        if path:
            self.conf_path = path
            self.update_info()

    def convert_conf_to_jsonl(self):
        if not self.conf_path or not self.figure_path:
            QMessageBox.warning(self, "未完成选择", "请先选择 conf 文件 和 figure 文件夹喵～")
            return
        try:
            from sections.gen_jsonl import conf_to_jsonl_with_summary
            output_path = conf_to_jsonl_with_summary(self.conf_path, self.figure_path)
            QMessageBox.information(self, "转换完成喵～", f"已生成 JSONL 文件：\n{output_path}")
        except Exception as e:
            QMessageBox.critical(self, "出错了喵", f"转换失败：\n{str(e)}")

