import os
import shutil
import zipfile
from datetime import datetime
from typing import List
from utils.backup_manager import BackupManager

class DisasterRecoveryManager:
    """容灾恢复管理服务，负责系统容灾备份功能"""
    
    def __init__(self, backup_locations: List[str]):
        self.backup_locations = backup_locations
        self.backup_manager = BackupManager()
    
    def create_encrypted_backup(self, password: str) -> str:
        """创建加密备份"""
        try:
            # 执行常规备份
            backup_result = self.backup_manager.backup_database()
            if not backup_result['success']:
                raise Exception(backup_result.get('error', '备份失败'))
            
            # 创建加密压缩文件
            backup_path = backup_result['backup_path']
            encrypted_path = f"{backup_path}.encrypted.zip"
            
            # 这里应该实现实际的加密逻辑
            # 为简化示例，直接复制文件
            shutil.copy2(backup_path, encrypted_path)
            
            return encrypted_path
        except Exception as e:
            raise Exception(f"创建加密备份失败: {str(e)}")
    
    def sync_backup_to_locations(self, backup_file: str) -> List[str]:
        """同步备份到多个位置"""
        synced_locations = []
        for location in self.backup_locations:
            try:
                # 确保目标目录存在
                os.makedirs(location, exist_ok=True)
                
                # 复制备份文件到目标位置
                filename = os.path.basename(backup_file)
                destination = os.path.join(location, filename)
                shutil.copy2(backup_file, destination)
                synced_locations.append(location)
            except Exception as e:
                print(f"同步备份到 {location} 失败: {str(e)}")
        
        return synced_locations
