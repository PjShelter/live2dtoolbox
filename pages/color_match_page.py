import json
import os

from PIL import Image
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QTextEdit, QGroupBox, \
    QMessageBox, QFileDialog
from PyQt5.QtCore import Qt

from utils.common import CONFIG_PATH, format_transform_code
from sections.color_transfer import extract_webgal_full_transform, match_color, plot_parameter_comparison
from sections.color_transfer import extract_webgal_rgb_only

class ColorMatchPage(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setSpacing(12)

        # 🎨 匹配工具区域
        group_color = QGroupBox("🎨 色彩匹配工具")
        color_layout = QVBoxLayout()

        # 按钮区域
        image_select_layout = QHBoxLayout()
        self.source_btn = QPushButton("选择源图像")
        self.source_btn.setMinimumWidth(160)
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(160)

        image_select_layout.addWidget(self.source_btn)
        image_select_layout.addWidget(self.target_combo)

        # 预览区域
        preview_layout = QHBoxLayout()
        self.source_label = QLabel("源图像")
        self.source_label.setFixedSize(220, 160)
        self.source_label.setAlignment(Qt.AlignCenter)
        self.target_label = QLabel("参考图像")
        self.target_label.setFixedSize(220, 160)
        self.target_label.setAlignment(Qt.AlignCenter)
        self.result_label = QLabel("匹配结果")
        self.result_label.setFixedSize(220, 160)
        self.result_label.setAlignment(Qt.AlignCenter)

        preview_layout.addWidget(self.source_label)
        preview_layout.addWidget(self.target_label)
        preview_layout.addWidget(self.result_label)

        # 按钮
        self.match_btn = QPushButton("执行色彩匹配")
        self.match_btn.setMinimumWidth(300)
        self.compare_btn = QPushButton("显示对比图表")
        self.compare_btn.setMinimumWidth(300)

        # 输出
        self.webgal_output = QTextEdit()
        self.webgal_output.setPlaceholderText("此处将显示 WebGAL 指令...")
        self.webgal_output.setMinimumHeight(60)

        # RGB-only 输出
        self.rgb_output = QTextEdit()
        self.rgb_output.setPlaceholderText("仅 RGB 参数代码输出（可用于滤镜）...")
        self.rgb_output.setMinimumHeight(60)

        # 拼装布局
        color_layout.addLayout(image_select_layout)
        color_layout.addLayout(preview_layout)
        color_layout.addWidget(self.match_btn)
        color_layout.addWidget(self.compare_btn)
        color_layout.addWidget(self.webgal_output)

        group_color.setLayout(color_layout)
        layout.addWidget(group_color)
        self.setLayout(layout)

        # ✅ 初始化行为
        self.refresh_target_list()
        self.load_last_config()

        # ✅ 正确位置：在 __init__ 中绑定按钮事件
        self.source_btn.clicked.connect(self.choose_source)
        self.target_combo.currentIndexChanged.connect(self.select_target_image)
        self.match_btn.clicked.connect(self.run_match)
        self.compare_btn.clicked.connect(self.show_comparison)

    def show_comparison(self):
        try:
            if not hasattr(self, "_source_img") or not hasattr(self, "_target_img"):
                QMessageBox.warning(self, "未找到图像", "请先执行色彩匹配")
                return
            plot_parameter_comparison(self._source_img, self._target_img)
        except Exception as e:
            QMessageBox.critical(self, "出错", f"无法显示对比图：\n{str(e)}")

    def load_last_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)

                self.source_path = config.get("color_match_source_path", "")
                if os.path.isfile(self.source_path):
                    self.source_label.setPixmap(QPixmap(self.source_path).scaled(200, 160))

                self.target_path = config.get("color_match_target_path", "")
                if os.path.isfile(self.target_path):
                    self.target_label.setPixmap(QPixmap(self.target_path).scaled(200, 160))

            except Exception as e:
                print("配置文件读取失败：", e)

    def save_config(self):
        config = {
            "color_match_source_path": self.source_path,
            "color_match_target_path": self.target_path,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def refresh_target_list(self):
        png_dir = "png"
        self.target_combo.clear()
        if os.path.isdir(png_dir):
            files = [f for f in os.listdir(png_dir) if f.lower().endswith(".png")]
            self.target_combo.addItems(files or ["⚠ 无 PNG 文件"])
        else:
            self.target_combo.addItem("⚠ 缺少 png 文件夹")

    def select_target_image(self, index):
        if index < 0:
            return
        file_name = self.target_combo.itemText(index)
        path = os.path.join("png", file_name)
        if os.path.isfile(path):
            self.target_path = path
            self.target_label.setPixmap(QPixmap(path).scaled(200, 160))
            self.save_config()

    def choose_source(self):
        initial_dir = os.path.dirname(getattr(self, "source_path", "")) if hasattr(self, "source_path") else ""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择源图像", initial_dir, "Images (*.png *.jpg *.jpeg)")
        if file_path:
            self.source_path = file_path
            self.source_label.setPixmap(QPixmap(file_path).scaled(200, 160))
            self.save_config()

    def run_match(self):
        if not hasattr(self, "source_path") or not hasattr(self, "target_path"):
            QMessageBox.warning(self, "错误", "请先选择源图和参考图。")
            return

        source = Image.open(self.source_path).convert("RGB")
        target = Image.open(self.target_path).convert("RGB").resize(source.size)

        matched = match_color(source, target)
        source_dir = os.path.dirname(self.source_path)
        src = os.path.splitext(os.path.basename(self.source_path))[0]
        tgt = os.path.splitext(os.path.basename(self.target_path))[0]
        out_path = os.path.join(source_dir, f"matched_{src}_{tgt}.png")
        matched.save(out_path)


        self.result_path = out_path
        self.result_label.setPixmap(QPixmap(out_path).scaled(200, 160))

        webgal = extract_webgal_full_transform(source, target)
        full_code = format_transform_code(webgal)
        rgb_only = extract_webgal_rgb_only(source, target)
        rgb_code = f'setTransform:{{"colorRed":{rgb_only["colorRed"]},"colorGreen":{rgb_only["colorGreen"]},"colorBlue":{rgb_only["colorBlue"]}}} -target=bg-main -duration=0 -next;'
        combined_code = full_code + "\n" + rgb_code
        self.webgal_output.setText(combined_code)


        QMessageBox.information(self, "完成", f"已保存匹配图像到：{out_path}")

        # 对比图
        self._source_img = source
        self._target_img = target
        self._matched_img = matched
