# Live2DToolbox 项目分析 (2026-03)

## 概述

- 定位：Live2D 相关桌面工具集（模型编辑、颜色校正、参数操作等）
- 语言：Python 3
- 打包：PyInstaller → 单文件 Windows exe
- GUI：待确认（PyQt / tkinter / pygame?）

## 核心文件

- main_ui.py → 主界面逻辑
- main.py → 可能入口或调试模式
- Live2DToolbox.spec → 打包配置
- config.json / deformer_import.json / mtn.json → 数据驱动部分
- lut/ → 3D LUT 预设（颜色风格迁移）

## 功能推测

1. Live2D 模型 deformer 编辑 / 导入
2. 颜色风格迁移（color transfer）
3. 表情/动作参数调整（mtn.json）
4. 自定义文件选择对话框

## 改进建议

- 清理构建产物进 .gitignore
- 拆分模块（gui / core / utils）
- 添加 requirements.txt 或 pyproject.toml
- 考虑迁移到 PySide6 + modern packaging (briefcase / pyoxidizer)

待补充：详细模块依赖 & 功能流程图