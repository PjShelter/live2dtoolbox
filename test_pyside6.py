#!/usr/bin/env python3
import sys
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)
label = QLabel('PySide6迁移测试成功! 🎉')
label.show()
app.exec()
print('✅ PySide6运行正常')