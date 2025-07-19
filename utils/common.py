# utils/common.py
import os
import json
import sys

CONFIG_PATH = "config.json"

def format_transform_code(transform_dict):
    return f'setTransform:{json.dumps(transform_dict, ensure_ascii=False)}'


def save_config(config: dict):
    if not isinstance(config, dict):
        print("⚠️ 配置不是字典类型，跳过保存")
        return
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("配置文件读取失败：内容非法，已忽略")
        return {}


def get_resource_path(relative_path):
    """兼容 PyInstaller 打包后的路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)
