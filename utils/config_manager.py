import json
import os
from typing import Any, Dict

class ConfigManager:
    """配置管理服务，负责系统配置的加载、保存和管理功能"""
    
    def __init__(self, config_file='config/system_config.json'):
        self.config_file = config_file
        self.config_data = {}
        self._ensure_config_directory()
        self.load_config()
    
    def _ensure_config_directory(self):
        """确保配置目录存在"""
        config_dir = os.path.dirname(self.config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)
    
    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                self.config_data = {}
        else:
            # 初始化默认配置
            self.config_data = self._get_default_config()
            self.save_config()
    
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def _get_default_config(self):
        """获取默认配置"""
        return {
            "system": {
                "name": "设备备件管理系统",
                "version": "1.0.0",
                "debug": False
            },
            "database": {
                "backup_enabled": True,
                "backup_interval": 24,
                "max_backups": 10
            },
            "email": {
                "smtp_server": "",
                "smtp_port": 587,
                "use_tls": True
            },
            "inventory": {
                "low_stock_threshold": 10,
                "auto_sync_enabled": True
            }
        }
    
    def get_config(self, key_path: str, default=None):
        """获取配置项值"""
        keys = key_path.split('.')
        value = self.config_data
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set_config(self, key_path: str, value: Any):
        """设置配置项值"""
        keys = key_path.split('.')
        config = self.config_data
        
        # 递归创建嵌套字典结构
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # 设置最终值
        config[keys[-1]] = value
        self.save_config()
