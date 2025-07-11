# log.py
import sys
import logging

LOG_FILE = "log.txt"
ERROR_FILE = "error.log"

# 设置日志记录器
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# INFO 日志 -> log.txt
log_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
log_handler.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)

# ERROR 日志 -> error.log
error_handler = logging.FileHandler(ERROR_FILE, mode='a', encoding='utf-8')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(log_formatter)
logger.addHandler(error_handler)

# 包装 stdout 使 print 输出也写入日志
class LoggerWrapper:
    def __init__(self, stream):
        self.stream = stream

    def write(self, message):
        if message.strip():
            logging.info(message.strip())
        if self.stream:  # ✅ 避免 None 报错
            self.stream.write(message)

    def flush(self):
        if self.stream:
            self.stream.flush()

# 重定向 stdout
sys.stdout = LoggerWrapper(sys.__stdout__)
