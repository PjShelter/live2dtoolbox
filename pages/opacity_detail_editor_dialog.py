"""
部件透明度详细编辑对话框
"""
import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QMessageBox, QHeaderView, QDialogButtonBox
)
from PyQt5.QtCore import Qt

from sections.py_live2d_editor import get_all_parts


class OpacityDetailEditorDialog(QDialog):
    """部件透明度详细编辑对话框"""
    
    def __init__(self, model_json_path: str, init_opacities: list = None, parent=None):
        """
        Args:
            model_json_path: model.json 文件路径
            init_opacities: 当前的 init_opacities 列表，格式为 [{"id": "PARTS_XXX", "value": 1.0}, ...]
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("详细编辑部件透明度")
        self.resize(600, 700)
        self.setMinimumSize(500, 500)
        
        self.model_json_path = model_json_path
        self.init_opacities = init_opacities or []
        self.part_ids = []
        self.part_opacities = {}  # {part_id: opacity_value}
        
        # 从 init_opacities 构建字典
        for item in self.init_opacities:
            part_id = item.get("id")
            value = float(item.get("value", 1.0))
            self.part_opacities[part_id] = value
        
        # 获取所有部件列表
        try:
            self.part_ids = get_all_parts(model_json_path)
            # 对于不在 init_opacities 中的部件，默认设为 1.0
            for part_id in self.part_ids:
                if part_id not in self.part_opacities:
                    self.part_opacities[part_id] = 1.0
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取部件列表失败：{e}")
            self.part_ids = []
        
        self.setup_ui()
        self.refresh_table()
    
    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        
        # 说明标签
        info_label = QLabel(f"模型: {os.path.basename(self.model_json_path)}\n"
                           f"共 {len(self.part_ids)} 个部件\n"
                           f"提示: 透明度范围为 0.0 ~ 1.0")
        layout.addWidget(info_label)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["部件名 Part ID", "透明度 (0 ~ 1)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        # 设置行高（使每行更高）
        self.table.verticalHeader().setDefaultSectionSize(36)  # 默认行高为 36 像素
        layout.addWidget(self.table)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        
        # 全设为 1.0
        btn_all_1 = QPushButton("全部设为 1.0")
        btn_all_1.clicked.connect(lambda: self.set_all_opacity(1.0))
        btn_layout.addWidget(btn_all_1)
        
        # 全设为 0.0
        btn_all_0 = QPushButton("全部设为 0.0")
        btn_all_0.clicked.connect(lambda: self.set_all_opacity(0.0))
        btn_layout.addWidget(btn_all_0)
        
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        # 对话框按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def refresh_table(self):
        """刷新表格"""
        self.table.setRowCount(len(self.part_ids))
        for row, part_id in enumerate(self.part_ids):
            # 部件名（只读）
            id_item = QTableWidgetItem(part_id)
            id_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row, 0, id_item)
            
            # 透明度（可编辑）
            opacity_val = self.part_opacities.get(part_id, 1.0)
            opacity_item = QTableWidgetItem(str(round(opacity_val, 2)))
            self.table.setItem(row, 1, opacity_item)
    
    def set_all_opacity(self, value: float):
        """设置所有部件的透明度"""
        for row in range(self.table.rowCount()):
            part_id = self.table.item(row, 0).text()
            self.part_opacities[part_id] = value
            opacity_item = self.table.item(row, 1)
            if opacity_item:
                opacity_item.setText(str(round(value, 2)))
    
    def get_init_opacities(self) -> list:
        """获取编辑后的 init_opacities 列表"""
        new_opacities = []
        for row in range(self.table.rowCount()):
            part_id = self.table.item(row, 0).text()
            value_str = self.table.item(row, 1).text()
            try:
                value = max(0.0, min(1.0, float(value_str)))
            except ValueError:
                value = 1.0
            new_opacities.append({"id": part_id, "value": value})
        return new_opacities

