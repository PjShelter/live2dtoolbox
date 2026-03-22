import os
import json
import pygame
import live2d.v2 as live2d
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QUndoStack, QUndoCommand, QKeySequence, QShortcut

from sections.py_live2d_editor import list_model_info
from pages.single_model_preview_window import SingleModelPreviewWindow
from utils.common import save_config, load_config


class _ModelLoader(QThread):
    """后台加载模型信息，避免阻塞 UI 主线程"""
    finished = Signal(list, list)   # part_ids, param_objs
    error = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            part_ids, param_objs = list_model_info(self.file_path)
            self.finished.emit(part_ids, param_objs)
        except Exception as e:
            self.error.emit(str(e))


class _OpacityChangeCommand(QUndoCommand):
    """记录单次透明度修改，支持撤销/重做"""
    def __init__(self, page, row: int, old_val: str, new_val: str):
        super().__init__(f"修改透明度 行{row+1}: {old_val} → {new_val}")
        self.page = page
        self.row = row
        self.old_val = old_val
        self.new_val = new_val

    def _set(self, val: str):
        self.page.user_changing = True
        item = self.page.table.item(self.row, 1)
        if item:
            item.setText(val)
        self.page.user_changing = False

    def undo(self):
        self._set(self.old_val)

    def redo(self):
        self._set(self.new_val)


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
        self.setAcceptDrops(True)

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
        self._loader = None  # 后台模型加载线程

        # 撤销/重做
        self._undo_stack = QUndoStack(self)
        self._pending_old_val = {}  # row -> 编辑前的值，用于构造 Command
        self.table.itemDoubleClicked.connect(self._capture_old_val)

        QShortcut(QKeySequence.StandardKey.Undo, self, self._undo_stack.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self._undo_stack.redo)

    def load_model_json(self):
        config = load_config()
        last_dir = config.get("part_last_open_dir", "")
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = ""

        file_path, _ = QFileDialog.getOpenFileName(self, "选择 model.json 文件", last_dir, "Model JSON (*.json)")
        if not file_path:
            return

        self._load_file(file_path)

    def _on_model_load_error(self, msg: str):
        self.load_btn.setEnabled(True)
        self.label.setText("加载失败")
        QMessageBox.critical(self, "加载失败", f"模型加载失败：{msg}")

    def _on_model_loaded(self, part_ids: list, param_objs: list):
        self.load_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.label.setText(f"已加载: {self.model_path}")

        self.part_ids = part_ids

        # 加载已有 init_opacities
        try:
            with open(self.model_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
            self.part_opacities = {e["id"]: e["value"] for e in model_data.get("init_opacities", [])}
            self.param_values = {e["id"]: e["value"] for e in model_data.get("init_params", [])}
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法读取已有配置信息：{str(e)}")
            self.part_opacities = {}
            self.param_values = {}

        self.param_ids = []
        self.param_data_map = {}
        for p in param_objs:
            pid = str(p.id)
            self.param_ids.append(pid)
            self.param_data_map[pid] = {"default": p.default, "min": p.min, "max": p.max}

        self.refresh_table()
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
            pass

        self._undo_stack.clear()
        self._pending_old_val.clear()
        
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
    
    def _capture_old_val(self, item):
        """双击时记录编辑前的值，用于构造撤销命令"""
        if item.column() == 1:
            self._pending_old_val[item.row()] = item.text()

    def on_opacity_changed(self, item):
        """当透明度值改变时，推送撤销命令并实时更新预览"""
        if self.user_changing or item.column() != 1:
            return

        row = item.row()
        new_val = item.text()
        old_val = self._pending_old_val.pop(row, new_val)

        # 只有值真正变化时才推入撤销栈
        if old_val != new_val:
            cmd = _OpacityChangeCommand(self, row, old_val, new_val)
            # 推入时不再触发 redo（值已经是新的），直接 push 即可
            self._undo_stack.push(cmd)

        # 实时更新预览窗口
        if self.preview_window and self.preview_thread and self.preview_thread.is_alive():
            try:
                if self.preview_window.model:
                    part_id_item = self.table.item(row, 0)
                    if part_id_item:
                        part_id = part_id_item.text()
                        try:
                            opacity = max(0.0, min(1.0, float(new_val)))
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
        """关闭预览窗口并等待线程退出"""
        if self.preview_window:
            try:
                self.preview_window.running = False
            except:
                pass
            self.preview_window = None
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=3.0)
            if self.preview_thread.is_alive():
                print("警告: 预览窗口线程未能及时关闭")
        self.preview_thread = None

        # 启用主窗口
        if self.main_window:
            self.main_window.enable_main_window()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().endswith(".json") for u in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith(".json") and os.path.isfile(path):
                self._load_file(path)
                break

    def _load_file(self, file_path: str):
        """统一的文件加载入口，供按钮和拖拽共用"""
        save_config({"part_last_open_dir": os.path.dirname(file_path)})
        self.model_path = file_path
        self.label.setText(f"正在加载: {file_path} ...")
        self.load_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)

        self._loader = _ModelLoader(file_path)
        self._loader.finished.connect(self._on_model_loaded)
        self._loader.error.connect(self._on_model_load_error)
        self._loader.start()

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
