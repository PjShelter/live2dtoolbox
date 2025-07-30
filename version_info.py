import os
import webbrowser
import requests
from PyQt5.QtWidgets import QMessageBox
from dotenv import load_dotenv

load_dotenv()

CURRENT_VERSION = "1.2.5"
GITHUB_REPO = "KonshinHaoshin/gen_model"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def check_for_update_gui(parent_widget=None):
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        response = requests.get(url, headers=headers, timeout=8)

        if response.status_code != 200:
            raise Exception(f"GitHub 返回状态码: {response.status_code}")

        latest = response.json()
        latest_version = latest["tag_name"].lstrip("v")

        if latest_version != CURRENT_VERSION:
            msg = f"发现新版本：v{latest_version}\n当前版本：v{CURRENT_VERSION}\n\n是否前往 GitHub 下载页面？"
            reply = QMessageBox.question(
                parent_widget,
                "发现新版本",
                msg,
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases")
        else:
            QMessageBox.information(parent_widget, "版本检查", f"当前已是最新版本 v{CURRENT_VERSION}")

    except Exception as e:
        QMessageBox.critical(parent_widget, "检查失败", f"无法获取版本信息：\n{str(e)}")
