from models.database import DatabaseManager

class HealthCheck:
    """健康检查工具"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def check_database_connection(self):
        """检查数据库连接"""
        try:
            with self.db_manager.get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    def system_health_report(self):
        """生成系统健康报告"""
        return {
            'database': self.check_database_connection(),
            'status': 'healthy' if self.check_database_connection() else 'unhealthy'
        }
