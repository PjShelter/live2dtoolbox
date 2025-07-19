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
        self.resize(700, 800)

        self.full_data = []       # name_import 内容
        self.deformer_data = {}   # deformer_import 内容

        # 主布局
        self.layout = QVBoxLayout(self)

        # 搜索区
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 输入关键字搜索 ID / 日文 / 英文 / 中文")
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.perform_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        self.layout.addLayout(search_layout)

        self.sorted_by_height = False

        self.sort_button = QPushButton("按身高排序")
        self.sort_button.clicked.connect(self.toggle_sort)
        search_layout.addWidget(self.sort_button)

        # 表格区
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "日文名", "英文名", "中文名", "体型等级", "身高排名"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)

        self.layout.addWidget(self.table)

        # 默认加载
        self.load_json("name_import.json")

    def load_json_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 name_import.json", "", "JSON 文件 (*.json)")
        if path:
            self.load_json(path)

    def load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.full_data = json.load(f)

            with open("deformer_import.json", "r", encoding="utf-8") as f:
                self.deformer_data = json.load(f)

            self.show_data(self.full_data)
        except Exception as e:
            print(f"❌ 加载失败: {e}")

    def show_data(self, data):
        self.table.setRowCount(len(data))
        for row, item in enumerate(data):
            import_id = item.get("import")
            id_str = str(import_id)

            ja = item.get("name_ja", "")
            en = item.get("name_en", "")
            zh = item.get("name_zh", "")

            # 默认空
            height_level = ""
            height_rank = ""

            # ❗使用 import 作为 key 查找 deformer 中的身高数据
            deform = self.deformer_data.get(id_str)
            if deform:
                height_level = str(deform.get("heightLevel", ""))
                height_rank = str(deform.get("heightRank", ""))

            # 创建表格项
            cells = [
                QTableWidgetItem(id_str),
                QTableWidgetItem(ja),
                QTableWidgetItem(en),
                QTableWidgetItem(zh),
                QTableWidgetItem(height_level),
                QTableWidgetItem(height_rank),
            ]

            # 支持复制内容 & 居中显示
            for col, cell in enumerate(cells):
                cell.setTextAlignment(Qt.AlignCenter)
                cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, col, cell)

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

    def toggle_sort(self):
        if not self.sorted_by_height:
            # 排序状态：heightRank 升序
            def height_rank_key(item):
                deform = self.deformer_data.get(str(item.get("import")))
                return deform.get("heightRank", float("inf")) if deform else float("inf")

            sorted_data = sorted(self.full_data, key=height_rank_key)
            self.show_data(sorted_data)
            self.sorted_by_height = True
            self.sort_button.setText("恢复默认排序")
        else:
            # 恢复默认排序：import 升序
            sorted_data = sorted(self.full_data, key=lambda item: item.get("import", float("inf")))
            self.show_data(sorted_data)
            self.sorted_by_height = False
            self.sort_button.setText("按身高排序")


