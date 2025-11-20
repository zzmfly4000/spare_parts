import unittest
from models.database import DatabaseManager, init_db

class TestDatabase(unittest.TestCase):
    """数据库单元测试"""
    
    def setUp(self):
        """测试前准备"""
        init_db()
        self.db_manager = DatabaseManager()
    
    def test_database_connection(self):
        """测试数据库连接"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
    
    def tearDown(self):
        """测试后清理"""
        pass
