import os
import json
import pygame
import live2d.v2 as live2d
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import Qt

from sections.py_live2d_editor import list_model_info
from pages.single_model_preview_window import SingleModelPreviewWindow


def list_model_parts(model_json_path):
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.OPENGL | pygame.HIDDEN)
    live2d.init()
    live2d.glewInit()

    model = live2d.LAppModel()
    model.LoadModelJson(model_json_path)

    part_ids = model.GetPartIds()

    live2d.dispose()
    pygame.quit()

    return part_ids


class PartEditorPage(QWidget):
    def __init__(self):
        super().__init__()

        self.model_path = ""
        self.part_ids = []
        self.part_opacities = {}

        self.layout = QVBoxLayout(self)
        self.label = QLabel("未选择 model.json")
        self.layout.addWidget(self.label)

        self.load_btn = QPushButton("📂 选择 model.json 并编辑透明度")
        self.load_btn.clicked.connect(self.load_model_json)
        self.layout.addWidget(self.load_btn)

        # 预览按钮
        preview_btn_layout = QHBoxLayout()
        self.preview_btn = QPushButton("👁️ 预览模型")
        self.preview_btn.clicked.connect(self.preview_model)
        self.preview_btn.setEnabled(False)  # 初始状态禁用
        preview_btn_layout.addWidget(self.preview_btn)
        preview_btn_layout.addStretch()
        self.layout.addLayout(preview_btn_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["部件名 Part ID", "透明度 (0 ~ 1)"])
        self.table.itemChanged.connect(self.on_opacity_changed)  # 监听透明度变化
        self.layout.addWidget(self.table)

        # 参数区初始化
        self.param_ids = []
        self.param_values = {}

        self.param_label = QLabel("参数列表（init_params）")
        self.layout.addWidget(self.param_label)

        self.param_table = QTableWidget()
        self.param_table.setColumnCount(5)
        self.param_table.setHorizontalHeaderLabels(["参数名 Param ID", "初始值", "默认值", "最小值", "最大值"])
        self.layout.addWidget(self.param_table)

        self.save_btn = QPushButton("💾 保存更改到 model.json")
        self.save_btn.clicked.connect(self.save_model_json)
        self.layout.addWidget(self.save_btn)
        
        # 预览窗口相关
        self.preview_thread = None
        self.preview_window = None
        self.main_window = None
        self.user_changing = False  # 防止循环更新

    def load_model_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 model.json 文件", "", "Model JSON (*.json)")
        if not file_path:
            return

        self.model_path = file_path
        self.label.setText(f"已加载: {file_path}")
        
        # 启用预览按钮
        self.preview_btn.setEnabled(True)

        try:
            self.part_ids, param_objs = list_model_info(file_path)

            # 保存参数范围信息
            self.param_data_map = {}
            for p in param_objs:
                self.param_data_map[str(p.id)] = {
                    "default": p.default,
                    "min": p.min,
                    "max": p.max
                }
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"模型加载失败：{str(e)}")
            return

        # 加载已有 init_opacities（如有）
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
                init_opacities = model_data.get("init_opacities", [])
                self.part_opacities = {entry["id"]: entry["value"] for entry in init_opacities}
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法读取已有透明度信息：{str(e)}")
            self.part_opacities = {}

        self.refresh_table()

        # 导入 init_param 初始值（只用于显示默认值）
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
                init_params = model_data.get("init_params", [])
                self.param_values = {entry["id"]: entry["value"] for entry in init_params}
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法读取参数信息：{str(e)}")
            self.param_values = {}

        # ✅ 使用模型实际的 paramId 列表，而不是只用 json 中的 init_params
        self.param_ids = []
        self.param_data_map = {}
        for p in param_objs:
            pid = str(p.id)  # ⚠️ 确保是字符串
            self.param_ids.append(pid)
            self.param_data_map[pid] = {
                "default": p.default,
                "min": p.min,
                "max": p.max
            }
        self.refresh_param_table()

    def refresh_param_table(self):
        self.param_table.setRowCount(len(self.param_ids))
        for row, param_id in enumerate(self.param_ids):
            id_item = QTableWidgetItem(param_id)
            id_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.param_table.setItem(row, 0, id_item)

            # 初始值（可编辑）
            # 优先使用 json 里的初始值，其次使用模型内建默认值
            if param_id in self.param_values:
                init_val = self.param_values[param_id]
            else:
                init_val = self.param_data_map.get(param_id, {}).get("default", 0.0)
            init_item = QTableWidgetItem(str(round(init_val, 3)))
            self.param_table.setItem(row, 1, init_item)

            # 默认值、最小值、最大值（只读）
            data = self.param_data_map.get(param_id, {})
            default = QTableWidgetItem(str(round(data.get("default", 0.0), 3)))
            default.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.param_table.setItem(row, 2, default)

            min_val = QTableWidgetItem(str(round(data.get("min", 0.0), 3)))
            min_val.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.param_table.setItem(row, 3, min_val)

            max_val = QTableWidgetItem(str(round(data.get("max", 1.0), 3)))
            max_val.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.param_table.setItem(row, 4, max_val)

    def refresh_table(self):
        # 暂时断开信号，避免加载时触发实时更新
        try:
            self.table.itemChanged.disconnect(self.on_opacity_changed)
        except TypeError:
            # 如果信号未连接，忽略错误
            pass
        
        self.table.setRowCount(len(self.part_ids))
        for row, part_id in enumerate(self.part_ids):
            id_item = QTableWidgetItem(part_id)
            id_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row, 0, id_item)

            opacity_val = self.part_opacities.get(part_id, 1.0)
            opacity_item = QTableWidgetItem(str(round(opacity_val, 2)))
            self.table.setItem(row, 1, opacity_item)
        
        # 重新连接信号
        self.table.itemChanged.connect(self.on_opacity_changed)
    
    def on_opacity_changed(self, item):
        """当透明度值改变时，实时更新预览"""
        if self.user_changing:
            return
        
        # 如果预览窗口正在运行，更新透明度
        if self.preview_window and self.preview_thread and self.preview_thread.is_alive():
            try:
                if self.preview_window.model:
                    # 获取当前行的部件ID
                    row = item.row()
                    part_id_item = self.table.item(row, 0)
                    if part_id_item:
                        part_id = part_id_item.text()
                        try:
                            opacity = float(item.text())
                            opacity = max(0.0, min(1.0, opacity))
                            
                            # 更新预览窗口中的透明度
                            part_ids = self.preview_window.model.GetPartIds()
                            part_id_to_index = {pid: idx for idx, pid in enumerate(part_ids)}
                            
                            if part_id in part_id_to_index:
                                part_index = part_id_to_index[part_id]
                                if hasattr(self.preview_window.model, "SetPartOpacity"):
                                    self.preview_window.model.SetPartOpacity(part_index, opacity)
                                elif hasattr(self.preview_window.model, "SetPart"):
                                    self.preview_window.model.SetPart(part_index, opacity)
                        except ValueError:
                            pass
            except Exception as e:
                print(f"实时更新预览失败: {e}")
    
    def preview_model(self):
        """预览模型"""
        if not self.model_path or not os.path.isfile(self.model_path):
            QMessageBox.warning(self, "未加载文件", "请先选择 model.json 文件")
            return
        
        # 如果已有预览窗口在运行，先关闭它
        if self.preview_thread and self.preview_thread.is_alive():
            self._close_preview_window()
        
        # 获取当前的 init_opacities
        current_init_opacities = []
        for row in range(self.table.rowCount()):
            part_id = self.table.item(row, 0).text()
            value_str = self.table.item(row, 1).text()
            try:
                value = max(0.0, min(1.0, float(value_str)))
            except ValueError:
                value = 1.0
            current_init_opacities.append({"id": part_id, "value": value})
        
        # 禁用主窗口
        if self.main_window:
            self.main_window.disable_main_window()
        
        # 创建预览窗口并在线程中运行
        try:
            self.preview_window = SingleModelPreviewWindow(self.model_path, current_init_opacities)
            
            def run_preview():
                try:
                    self.preview_window.run()
                except Exception as e:
                    print(f"预览窗口运行错误: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # 预览窗口关闭后，启用主窗口
                    if self.main_window:
                        self.main_window.enable_main_window()
            
            self.preview_thread = threading.Thread(target=run_preview, daemon=True)
            self.preview_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动预览失败：{e}")
            import traceback
            traceback.print_exc()
            # 如果启动失败，也要启用主窗口
            if self.main_window:
                self.main_window.enable_main_window()
    
    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window
    
    def _close_preview_window(self):
        """关闭预览窗口"""
        if self.preview_window:
            try:
                self.preview_window.running = False
            except:
                pass
        if self.preview_thread and self.preview_thread.is_alive():
            # 等待线程结束（最多等待 1 秒）
            self.preview_thread.join(timeout=1.0)
        self.preview_window = None
        self.preview_thread = None
        
        # 启用主窗口
        if self.main_window:
            self.main_window.enable_main_window()

    def save_model_json(self):
        if not self.model_path:
            return

        # 读取原始 model.json
        try:
            with open(self.model_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法读取 model.json：{str(e)}")
            return

        # 提取透明度
        new_opacities = []
        for row in range(self.table.rowCount()):
            part_id = self.table.item(row, 0).text()
            value_str = self.table.item(row, 1).text()
            try:
                value = max(0.0, min(1.0, float(value_str)))
            except ValueError:
                value = 1.0
            new_opacities.append({"id": part_id, "value": value})
        model_data["init_opacities"] = new_opacities

        # ✅ 提取参数初始值
        new_params = []
        for row in range(self.param_table.rowCount()):
            param_id = self.param_table.item(row, 0).text()
            value_str = self.param_table.item(row, 1).text()
            try:
                value = float(value_str)
            except ValueError:
                value = 0.0
            new_params.append({"id": param_id, "value": value})
        model_data["init_params"] = new_params

        # 写回 model.json
        try:
            with open(self.model_path, 'w', encoding='utf-8') as f:
                json.dump(model_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "保存成功", "已成功写入 init_opacities 与 init_params 到 model.json！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法写入文件：{str(e)}")
