from models.database import DatabaseManager
import sqlite3
from datetime import datetime, timedelta

class DataAnalyticsService:
    """数据统计分析服务，负责数据统计和分析功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def get_part_usage_statistics(self, days=30):
        """获取备件使用频率统计"""
        with self.db_manager.get_connection() as conn:
            # 统计指定天数内各备件的使用次数
            cursor = conn.execute('''
                SELECT part_no, description, COUNT(*) as usage_count
                FROM operation_records 
                WHERE operation_date >= date('now', '-{} days')
                AND operation_type = 'Stock out'
                GROUP BY part_no, description
                ORDER BY usage_count DESC
                LIMIT 10
            '''.format(days))
            return cursor.fetchall()
    
    def get_inventory_trend(self, part_no, days=30):
        """获取备件库存变化趋势"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT date(operation_date) as date, 
                       SUM(CASE WHEN operation_type LIKE 'Stock in%' THEN quantity ELSE -quantity END) as net_change
                FROM operation_records 
                WHERE part_no = ? 
                AND operation_date >= date('now', '-{} days')
                GROUP BY date(operation_date)
                ORDER BY date
            '''.format(days), (part_no,))
            return cursor.fetchall()
    
    def get_location_usage_statistics(self):
        """获取库位使用率统计"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT location_code, part_count, capacity,
                       CASE 
                           WHEN capacity > 0 THEN CAST(part_count AS FLOAT) / capacity * 100
                           ELSE 0 
                       END as usage_percentage
                FROM locations
                WHERE capacity > 0
                ORDER BY usage_percentage DESC
            ''')
            return cursor.fetchall()
