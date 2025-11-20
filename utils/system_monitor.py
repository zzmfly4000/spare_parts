from models.database import DatabaseManager
import sqlite3
import psutil
import platform
from datetime import datetime

class SystemMonitor:
    """系统监控服务，负责系统监控和健康检查功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def check_database_status(self):
        """检查数据库状态"""
        try:
            with self.db_manager.get_connection() as conn:
                # 执行简单查询测试数据库连接
                cursor = conn.execute("SELECT 1")
                cursor.fetchone()
                return {
                    'status': 'healthy',
                    'message': '数据库连接正常'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'message': f'数据库连接异常: {str(e)}'
            }
    
    def get_system_info(self):
        """获取系统信息"""
        return {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'hostname': platform.node(),
            'processor': platform.processor(),
            'python_version': platform.python_version()
        }
    
    def get_resource_usage(self):
        """获取系统资源使用情况"""
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent
        }
    
    def get_health_status(self):
        """获取系统健康状态"""
        database_status = self.check_database_status()
        resource_usage = self.get_resource_usage()
        
        # 简单的健康状态判断逻辑
        is_healthy = (
            database_status['status'] == 'healthy' and
            resource_usage['cpu_percent'] < 90 and
            resource_usage['memory_percent'] < 90 and
            resource_usage['disk_usage'] < 90
        )
        
        return {
            'overall_status': 'healthy' if is_healthy else 'unhealthy',
            'database': database_status,
            'resources': resource_usage,
            'timestamp': datetime.now().isoformat()
        }
