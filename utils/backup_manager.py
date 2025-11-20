import shutil
import os
import zipfile
from datetime import datetime
from models.database import DatabaseManager

class BackupManager:
    """备份管理服务，负责系统备份和恢复功能"""
    
    def __init__(self, backup_dir='backups'):
        self.backup_dir = backup_dir
        self.db_manager = DatabaseManager()
        self._ensure_backup_directory()
    
    def _ensure_backup_directory(self):
        """确保备份目录存在"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def backup_database(self):
        """备份数据库"""
        try:
            # 生成备份文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"spare_parts_backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # 复制数据库文件
            shutil.copy2(self.db_manager.db_path, backup_path)
            
            return {
                'success': True,
                'backup_path': backup_path,
                'timestamp': timestamp
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_backups(self):
        """列出所有备份文件"""
        try:
            backups = []
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.db'):
                    file_path = os.path.join(self.backup_dir, filename)
                    file_stat = os.stat(file_path)
                    backups.append({
                        'filename': filename,
                        'size': file_stat.st_size,
                        'modified_time': datetime.fromtimestamp(file_stat.st_mtime)
                    })
            return sorted(backups, key=lambda x: x['modified_time'], reverse=True)
        except Exception as e:
            return []
