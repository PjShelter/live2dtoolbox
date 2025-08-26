import json
import os
import numpy as np

from PIL import Image
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QGroupBox, QMessageBox, QFileDialog, QSlider, QCheckBox, QSpacerItem, QSizePolicy, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from sections.LUT_3D import parse_cube_lut, apply_lut_rgb_uint8, numpy_to_pil_rgb, pil_to_qpixmap

# 如果你有配置文件路径就用已有的；否则给一个默认位置
try:
    from utils.common import CONFIG_PATH
except Exception:
    CONFIG_PATH = os.path.join(os.getcwd(), "colormatch_lut_config.json")



class ColorMatchPage(QWidget):
    """
    只保留 LUT(.cube) 调色功能：
    - 选择源图
    - 选择 LUT 目录 & LUT 文件
    - 预览（最近邻/三线性、缩放、与原图混合对比）
    - 保存结果
    - 记忆最近一次选择（source、lut_dir、lut_name）
    """
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 🎨 LUT 区域
        group_lut = QGroupBox("🎨 LUT 调色（.cube）")
        lut_layout = QVBoxLayout()

        # ---- 选择源图
        row_src = QHBoxLayout()
        self.btn_pick_src = QPushButton("选择源图像")
        self.src_path_edit = QLineEdit()
        self.src_path_edit.setPlaceholderText("未选择")
        self.src_path_edit.setReadOnly(True)
        row_src.addWidget(QLabel("源图"))
        row_src.addWidget(self.src_path_edit, 1)
        row_src.addWidget(self.btn_pick_src)
        lut_layout.addLayout(row_src)

        # ---- 选择 LUT 目录 + 文件
        row_lut_dir = QHBoxLayout()
        self.btn_pick_lut_dir = QPushButton("选择 LUT 目录")
        self.lut_dir_edit = QLineEdit()
        self.lut_dir_edit.setPlaceholderText("包含 .cube 文件的目录（例如 output）")
        self.lut_dir_edit.setReadOnly(True)
        row_lut_dir.addWidget(QLabel("LUT 目录"))
        row_lut_dir.addWidget(self.lut_dir_edit, 1)
        row_lut_dir.addWidget(self.btn_pick_lut_dir)

        row_lut_file = QHBoxLayout()
        self.cmb_lut = QComboBox()
        row_lut_file.addWidget(QLabel("LUT 文件"))
        row_lut_file.addWidget(self.cmb_lut, 1)

        row_opts = QHBoxLayout()
        self.chk_trilinear = QCheckBox("三线性插值")
        self.chk_trilinear.setChecked(True)

        self.mix_slider = QSlider(Qt.Horizontal)
        self.mix_slider.setRange(0, 100)  # 0 = 仅原图, 100 = 仅LUT
        self.mix_slider.setValue(100)

        row_opts.addWidget(self.chk_trilinear)
        row_opts.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        row_opts.addWidget(QLabel("对比"))
        row_opts.addWidget(self.mix_slider, 1)

        # ---- 预览
        row_prev = QHBoxLayout()
        self.lbl_src = QLabel("原图")
        self.lbl_src.setFixedSize(220, 160)
        self.lbl_src.setAlignment(Qt.AlignCenter)
        self.lbl_src.setStyleSheet("QLabel { background:#111; color:#bbb; border:1px solid #333; }")

        self.lbl_result = QLabel("LUT 结果")
        self.lbl_result.setFixedSize(220, 160)
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setStyleSheet("QLabel { background:#111; color:#bbb; border:1px solid #333; }")

        row_prev.addWidget(self.lbl_src)
        row_prev.addWidget(self.lbl_result)

        # ---- 操作按钮
        row_actions = QHBoxLayout()
        self.btn_apply = QPushButton("应用并保存")
        self.btn_apply.setMinimumWidth(200)
        row_actions.addWidget(self.btn_apply)
        row_actions.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # 装配
        lut_layout.addLayout(row_src)
        lut_layout.addLayout(row_lut_dir)
        lut_layout.addLayout(row_lut_file)
        lut_layout.addLayout(row_opts)
        lut_layout.addLayout(row_prev)
        lut_layout.addLayout(row_actions)

        group_lut.setLayout(lut_layout)
        layout.addWidget(group_lut)

        # 状态
        self._orig_img_pil: Image.Image | None = None
        self._orig_img_rgb: np.ndarray | None = None
        self._lut_cache: dict[str, np.ndarray] = {}
        self._current_lut: np.ndarray | None = None

        # 信号
        self.btn_pick_src.clicked.connect(self._pick_source)
        self.btn_pick_lut_dir.clicked.connect(self._pick_lut_dir)
        self.cmb_lut.currentIndexChanged.connect(self._on_lut_changed)
        self.chk_trilinear.stateChanged.connect(self._schedule_preview)
        self.mix_slider.valueChanged.connect(self._schedule_preview)
        self.btn_apply.clicked.connect(self._apply_and_save)

        # 轻微防抖，避免频繁重算
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._render_preview)

        # 恢复配置
        self._load_config()
        # 初始化列表
        self._refresh_lut_combo()

    # ========== IO/配置 ==========
    def _load_config(self):
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            src = cfg.get("lut_source_path", "")
            lut_dir = cfg.get("lut_dir", "")
            lut_name = cfg.get("lut_name", "")

            if src and os.path.isfile(src):
                self.src_path_edit.setText(src)
                self._load_source_image(src)

            if lut_dir and os.path.isdir(lut_dir):
                self.lut_dir_edit.setText(lut_dir)
                self._refresh_lut_combo()
                if lut_name and lut_name in [self.cmb_lut.itemText(i) for i in range(self.cmb_lut.count())]:
                    self.cmb_lut.setCurrentText(lut_name)
        except Exception as e:
            print("读取配置失败：", e)

    def _save_config(self):
        cfg = {
            "lut_source_path": self.src_path_edit.text().strip(),
            "lut_dir": self.lut_dir_edit.text().strip(),
            "lut_name": self.cmb_lut.currentText().strip(),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("保存配置失败：", e)

    # ========== 选择/载入 ==========
    def _pick_source(self):
        initial = os.path.dirname(self.src_path_edit.text().strip()) if self.src_path_edit.text().strip() else ""
        path, _ = QFileDialog.getOpenFileName(self, "选择源图像", initial, "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        self.src_path_edit.setText(path)
        self._load_source_image(path)
        self._save_config()

    def _load_source_image(self, path: str):
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"无法读取图像：\n{e}")
            return
        self._orig_img_pil = img
        self._orig_img_rgb = np.array(img, dtype=np.uint8)
        # 原图预览
        self._preview_label_set_pixmap(self.lbl_src, img)
        self._schedule_preview()

    def _pick_lut_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择 LUT 目录")
        if not path:
            return
        self.lut_dir_edit.setText(path)
        self._refresh_lut_combo()
        self._save_config()

    def _refresh_lut_combo(self):
        self.cmb_lut.blockSignals(True)
        self.cmb_lut.clear()
        lut_dir = self.lut_dir_edit.text().strip()
        if os.path.isdir(lut_dir):
            names = [n for n in os.listdir(lut_dir) if n.lower().endswith(".cube")]
            names.sort()
            self.cmb_lut.addItems(names)
        self.cmb_lut.blockSignals(False)
        if self.cmb_lut.count() > 0:
            self.cmb_lut.setCurrentIndex(0)
            self._on_lut_changed()

    def _on_lut_changed(self):
        name = self.cmb_lut.currentText().strip()
        lut_dir = self.lut_dir_edit.text().strip()
        if not name or not lut_dir:
            self._current_lut = None
            self._schedule_preview()
            return
        full = os.path.join(lut_dir, name)
        if name not in self._lut_cache:
            try:
                self._lut_cache[name] = parse_cube_lut(full)
            except Exception as e:
                QMessageBox.critical(self, "解析失败", f"LUT 解析失败：\n{e}")
                return
        self._current_lut = self._lut_cache[name]
        self._save_config()
        self._schedule_preview()

    # ========== 预览/渲染 ==========
    def _schedule_preview(self):
        self._timer.start()  # 50ms 后触发 _render_preview

    def _render_preview(self):
        if self._orig_img_rgb is None:
            self.lbl_result.setText("请先选择源图")
            return
        if self._current_lut is None:
            self._preview_label_set_pixmap(self.lbl_result, self._orig_img_pil)
            return

        try:
            mapped = apply_lut_rgb_uint8(
                self._orig_img_rgb,
                self._current_lut,
                trilinear=self.chk_trilinear.isChecked()
            )
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"LUT 应用失败：\n{e}")
            return

        mix = self.mix_slider.value() / 100.0
        base = self._orig_img_pil
        lut_img = numpy_to_pil_rgb(mapped)
        blended = Image.blend(base, lut_img, alpha=mix)

        self._preview_label_set_pixmap(self.lbl_result, blended)

    def _preview_label_set_pixmap(self, label: QLabel, img: Image.Image):
        # 将 PIL 图缩放到 label 尺寸内（等比）
        tw, th = label.width(), label.height()
        if tw > 0 and th > 0:
            img = img.copy()
            img.thumbnail((tw, th), Image.LANCZOS)
        label.setPixmap(pil_to_qpixmap(img))

    # ========== 保存 ==========
    def _apply_and_save(self):
        src_path = self.src_path_edit.text().strip()
        if not src_path or self._orig_img_rgb is None:
            QMessageBox.warning(self, "缺少图像", "请先选择源图像。")
            return
        if self._current_lut is None:
            QMessageBox.warning(self, "缺少 LUT", "请先选择 LUT。")
            return

        try:
            mapped = apply_lut_rgb_uint8(
                self._orig_img_rgb,
                self._current_lut,
                trilinear=self.chk_trilinear.isChecked()
            )
            lut_img = numpy_to_pil_rgb(mapped)
        except Exception as e:
            QMessageBox.critical(self, "处理失败", f"应用 LUT 失败：\n{e}")
            return

        # 根据“对比”滑块混合保存
        mix = self.mix_slider.value() / 100.0
        out_img = Image.blend(self._orig_img_pil, lut_img, alpha=mix)

        base_dir = os.path.dirname(src_path)
        base_name = os.path.splitext(os.path.basename(src_path))[0]
        lut_name = self.cmb_lut.currentText().strip()
        lut_stem = os.path.splitext(lut_name)[0] if lut_name else "lut"
        pct = int(round(mix * 100))
        out_path = os.path.join(base_dir, f"{base_name}__{lut_stem}__mix{pct}.png")

        try:
            out_img.save(out_path)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存：\n{e}")
            return

        QMessageBox.information(self, "完成", f"已保存：\n{out_path}")

