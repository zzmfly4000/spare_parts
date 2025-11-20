import psutil
import time
from datetime import datetime
from typing import Dict, List
from models.database import DatabaseManager

class PerformanceDashboard:
    """性能监控仪表板服务，负责系统性能监控仪表板功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.metrics_history = {
            'cpu': [],
            'memory': [],
            'disk': [],
            'timestamps': []
        }
    
    def collect_system_metrics(self) -> Dict:
        """收集系统性能指标"""
        # 收集CPU使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # 收集内存使用率
        memory_info = psutil.virtual_memory()
        memory_percent = memory_info.percent
        
        # 收集磁盘使用率
        disk_info = psutil.disk_usage('/')
        disk_percent = (disk_info.used / disk_info.total) * 100
        
        # 获取当前时间
        timestamp = datetime.now().isoformat()
        
        # 保存到历史记录
        self.metrics_history['cpu'].append(cpu_percent)
        self.metrics_history['memory'].append(memory_percent)
        self.metrics_history['disk'].append(disk_percent)
        self.metrics_history['timestamps'].append(timestamp)
        
        # 保持历史记录在合理范围内
        if len(self.metrics_history['timestamps']) > 100:
            self.metrics_history['cpu'].pop(0)
            self.metrics_history['memory'].pop(0)
            self.metrics_history['disk'].pop(0)
            self.metrics_history['timestamps'].pop(0)
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'disk_percent': disk_percent,
            'timestamp': timestamp
        }
    
    def get_database_metrics(self) -> Dict:
        """获取数据库性能指标"""
        try:
            with self.db_manager.get_connection() as conn:
                # 获取表统计信息
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                
                table_stats = []
                total_rows = 0
                
                for table in tables:
                    table_name = table[0]
                    count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                    row_count = count_cursor.fetchone()[0]
                    total_rows += row_count
                    
                    table_stats.append({
                        'table_name': table_name,
                        'row_count': row_count
                    })
                
                return {
                    'total_tables': len(tables),
                    'total_rows': total_rows,
                    'table_stats': table_stats
                }
        except Exception as e:
            return {
                'error': str(e)
            }
