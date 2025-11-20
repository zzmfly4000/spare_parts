import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

class LogManager:
    """日志管理服务，负责系统日志记录和管理功能"""
    
    def __init__(self, log_dir='logs', max_bytes=10*1024*1024, backup_count=5):
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._ensure_log_directory()
        self._setup_logging()
    
    def _ensure_log_directory(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def _setup_logging(self):
        """设置日志配置"""
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # 创建文件处理器（带轮转）
        log_file = os.path.join(self.log_dir, 'system.log')
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=self.max_bytes, 
            backupCount=self.backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    def log_operation(self, user, operation, details=None):
        """记录操作日志"""
        logger = logging.getLogger('operation')
        message = f"User: {user}, Operation: {operation}"
        if details:
            message += f", Details: {details}"
        logger.info(message)
    
    def log_system_event(self, event, level='INFO', details=None):
        """记录系统事件日志"""
        logger = logging.getLogger('system')
        message = f"Event: {event}"
        if details:
            message += f", Details: {details}"
        
        if level == 'ERROR':
            logger.error(message)
        elif level == 'WARNING':
            logger.warning(message)
        elif level == 'DEBUG':
            logger.debug(message)
        else:
            logger.info(message)
    
    def get_log_entries(self, level='INFO', limit=100):
        """获取日志条目"""
        # 这里应该实现实际的日志查询逻辑
        # 为简化示例，返回空列表
        return []
