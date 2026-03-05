import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox


class WmdlConverterPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("JSONL ⇄ WMDL 格式转换"))

        # JSONL 转 WMDL
        self.jsonl_to_wmdl_btn = QPushButton("📄 JSONL 转 WMDL")
        self.jsonl_to_wmdl_btn.clicked.connect(self.convert_jsonl_to_wmdl)
        layout.addWidget(self.jsonl_to_wmdl_btn)

        # WMDL 转 JSONL
        self.wmdl_to_jsonl_btn = QPushButton("📦 WMDL 转 JSONL")
        self.wmdl_to_jsonl_btn.clicked.connect(self.convert_wmdl_to_jsonl)
        layout.addWidget(self.wmdl_to_jsonl_btn)

        layout.addStretch()
        self.setLayout(layout)

    def convert_jsonl_to_wmdl(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 JSONL 文件", "", "JSONL (*.jsonl)")
        if not path:
            return

        try:
            from sections.gen_jsonl import jsonl_to_wmdl
            output = jsonl_to_wmdl(path)
            QMessageBox.information(self, "转换成功", f"已生成：\n{output}")
        except Exception as e:
            QMessageBox.critical(self, "转换失败", str(e))

    def convert_wmdl_to_jsonl(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 WMDL 文件", "", "WMDL (*.wmdl)")
        if not path:
            return

        # 自动使用 wmdl 文件所在目录作为 figure 根目录
        figure_dir = os.path.dirname(path)

        try:
            from sections.gen_jsonl import wmdl_to_jsonl
            output = wmdl_to_jsonl(path, figure_dir)
            QMessageBox.information(self, "转换成功", f"已生成：\n{output}")
        except Exception as e:
            QMessageBox.critical(self, "转换失败", str(e))
