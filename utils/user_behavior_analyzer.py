import sqlite3
from datetime import datetime, timedelta
from models.database import DatabaseManager
from typing import Dict, List

class UserBehaviorAnalyzer:
    """用户行为分析服务，负责用户行为分析功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self._init_behavior_table()
    
    def _init_behavior_table(self):
        """初始化用户行为记录表"""
        with self.db_manager.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_behaviors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action_type TEXT,
                    action_target TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
    
    def record_user_action(self, user_id: int, action_type: str, action_target: str):
        """记录用户操作行为"""
        with self.db_manager.get_connection() as conn:
            conn.execute('''
                INSERT INTO user_behaviors (user_id, action_type, action_target)
                VALUES (?, ?, ?)
            ''', (user_id, action_type, action_target))
    
    def get_user_visit_frequency(self, days: int = 30) -> Dict:
        """获取用户访问频率统计"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT user_id, COUNT(*) as visit_count
                FROM user_behaviors 
                WHERE timestamp >= date('now', '-{} days')
                GROUP BY user_id
                ORDER BY visit_count DESC
            '''.format(days))
            return cursor.fetchall()
