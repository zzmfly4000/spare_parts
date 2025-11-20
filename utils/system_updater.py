import os
import json
import shutil
from typing import Dict, List
import requests

class SystemUpdater:
    """系统升级服务，负责系统升级和维护功能"""
    
    def __init__(self, version_file='config/version.json'):
        self.version_file = version_file
        self.current_version = self._get_current_version()
    
    def _get_current_version(self) -> str:
        """获取当前系统版本"""
        if os.path.exists(self.version_file):
            with open(self.version_file, 'r') as f:
                version_info = json.load(f)
                return version_info.get('version', '1.0.0')
        else:
            # 创建默认版本文件
            default_version = {'version': '1.0.0'}
            self._save_version_info(default_version)
            return '1.0.0'
    
    def _save_version_info(self, version_info: Dict):
        """保存版本信息"""
        os.makedirs(os.path.dirname(self.version_file), exist_ok=True)
        with open(self.version_file, 'w') as f:
            json.dump(version_info, f, indent=2)
    
    def check_for_updates(self) -> Dict:
        """检查系统更新"""
        try:
            # 这里应该连接到实际的更新服务器
            # 为简化示例，返回模拟结果
            latest_version = "1.2.0"
            has_update = self._compare_versions(latest_version, self.current_version)
            
            return {
                'has_update': has_update,
                'current_version': self.current_version,
                'latest_version': latest_version,
                'update_available': has_update
            }
        except Exception as e:
            return {
                'has_update': False,
                'error': str(e)
            }
    
    def _compare_versions(self, version1: str, version2: str) -> bool:
        """比较版本号"""
        v1_parts = [int(x) for x in version1.split('.')]
        v2_parts = [int(x) for x in version2.split('.')]
        
        for i in range(min(len(v1_parts), len(v2_parts))):
            if v1_parts[i] > v2_parts[i]:
                return True
            elif v1_parts[i] < v2_parts[i]:
                return False
        return len(v1_parts) > len(v2_parts)
    
    def perform_backup(self) -> Dict:
        """执行系统备份"""
        try:
            from utils.backup_manager import BackupManager
            backup_manager = BackupManager()
            result = backup_manager.backup_database()
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
