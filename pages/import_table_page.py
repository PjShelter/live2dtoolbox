import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QFileDialog,
    QLineEdit, QPushButton, QHBoxLayout
)
from PyQt5.QtCore import Qt

class ImportTablePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IMPORT 参数表")
        self.resize(600, 800)

        self.full_data = []  # 存储完整数据以支持搜索

        # 主布局
        self.layout = QVBoxLayout(self)

        # 顶部搜索区域
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 输入关键字搜索 ID / 日文 / 英文 / 中文")
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.perform_search)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        self.layout.addLayout(search_layout)

        # 表格初始化
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "日文名", "英文名", "中文名"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.layout.addWidget(self.table)

        # 自动加载
        self.load_json("name_import.json")

    def load_json_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 name_import.json", "", "JSON 文件 (*.json)")
        if path:
            self.load_json(path)

    def load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.full_data = json.load(f)
        except Exception as e:
            print(f"❌ 加载失败: {e}")
            return

        self.show_data(self.full_data)

    def show_data(self, data):
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            id_item = QTableWidgetItem(str(item.get("import", "")))
            ja_item = QTableWidgetItem(item.get("name_ja", ""))
            en_item = QTableWidgetItem(item.get("name_en", ""))
            zh_item = QTableWidgetItem(item.get("name_zh", ""))

            for col_item in (id_item, ja_item, en_item, zh_item):
                col_item.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row, 0, id_item)
            self.table.setItem(row, 1, ja_item)
            self.table.setItem(row, 2, en_item)
            self.table.setItem(row, 3, zh_item)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def perform_search(self):
        keyword = self.search_input.text().strip().lower()
        if not keyword:
            self.show_data(self.full_data)
            return

        filtered = []
        for item in self.full_data:
            values = [
                str(item.get("import", "")).lower(),
                item.get("name_ja", "").lower(),
                item.get("name_en", "").lower(),
                item.get("name_zh", "").lower(),
            ]
            if any(keyword in v for v in values):
                filtered.append(item)

        self.show_data(filtered)
