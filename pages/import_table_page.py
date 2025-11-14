import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QFileDialog,
    QLineEdit, QPushButton, QHBoxLayout, QLabel
)
from PyQt5.QtCore import Qt
from utils.common import get_resource_path


class ImportTablePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IMPORT 参数表")
        self.resize(760, 840)

        self.full_data = []       # name_import 内容
        self.deformer_data = {}   # deformer_import 内容（以 import 的字符串为 key）

        # 主布局
        self.layout = QVBoxLayout(self)

        # 顶部文件区（可选）
        file_layout = QHBoxLayout()
        self.path_label = QLabel("未加载 name_import.json / deformer_import.json")
        self.load_file_btn = QPushButton("📂 选择 name_import.json")
        self.load_file_btn.clicked.connect(self.load_json_file)
        file_layout.addWidget(self.path_label)
        file_layout.addWidget(self.load_file_btn)
        self.layout.addLayout(file_layout)

        # 搜索+排序区
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 输入关键字搜索 ID / 日文 / 英文 / 中文")
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.perform_search)
        self.sort_button = QPushButton("按身高排序")
        self.sort_button.clicked.connect(self.toggle_sort)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.sort_button)
        self.layout.addLayout(search_layout)

        self.sorted_by_height = False

        # 表格区（新增 OriginX / OriginY 两列 -> 共 8 列）
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "日文名", "英文名", "中文名",
            "体型等级", "身高排名", "OriginX", "OriginY"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.layout.addWidget(self.table)

        # 默认加载打包资源或当前工作目录下的文件
        default_path = get_resource_path("name_import.json")
        if not os.path.exists(default_path):
            default_path = "name_import.json"
        self.load_json(default_path)

    def load_json_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 name_import.json", "", "JSON 文件 (*.json)")
        if path:
            self.load_json(path)

    def load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.full_data = json.load(f)

            # deformer_import.json 与 name_import.json 同目录下，或从打包资源加载
            deform_path = os.path.join(os.path.dirname(path), "deformer_import.json")
            if not os.path.exists(deform_path):
                # 尝试从打包资源加载
                deform_path = get_resource_path("deformer_import.json")
            with open(deform_path, "r", encoding="utf-8") as f:
                self.deformer_data = json.load(f)

            self.path_label.setText(f"已加载：{path}  |  {deform_path}")
            self.show_data(self.full_data)
        except Exception as e:
            self.path_label.setText("❌ 加载失败")
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
            origin_x = ""
            origin_y = ""

            # 使用 import 作为 key 查找 deformer 中的数据
            deform = self.deformer_data.get(id_str)
            if deform:
                # 显示时尽量转成字符串，避免 None 导致显示 "None"
                height_level = "" if deform.get("heightLevel") is None else str(deform.get("heightLevel"))
                height_rank  = "" if deform.get("heightRank")  is None else str(deform.get("heightRank"))
                origin_x     = "" if deform.get("OriginX")     is None else str(deform.get("OriginX"))
                origin_y     = "" if deform.get("OriginY")     is None else str(deform.get("OriginY"))

            cells = [
                QTableWidgetItem(id_str),
                QTableWidgetItem(ja),
                QTableWidgetItem(en),
                QTableWidgetItem(zh),
                QTableWidgetItem(height_level),
                QTableWidgetItem(height_rank),
                QTableWidgetItem(origin_x),
                QTableWidgetItem(origin_y),
            ]

            for col, cell in enumerate(cells):
                # 统一居中，便于快速查看
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
            # heightRank 升序；缺失的排到最后
            def height_rank_key(item):
                deform = self.deformer_data.get(str(item.get("import")))
                if not deform or deform.get("heightRank") is None:
                    return float("inf")
                try:
                    return float(deform.get("heightRank"))
                except Exception:
                    return float("inf")

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
