import time
import sqlite3
from models.database import DatabaseManager

class PerformanceOptimizer:
    """性能优化服务，负责系统性能监控和优化功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def analyze_query_performance(self, query, params=None):
        """分析查询性能"""
        start_time = time.time()
        
        with self.db_manager.get_connection() as conn:
            if params:
                cursor = conn.execute(query, params)
            else:
                cursor = conn.execute(query)
            results = cursor.fetchall()
        
        execution_time = time.time() - start_time
        
        return {
            'query': query,
            'execution_time': execution_time,
            'result_count': len(results)
        }
    
    def get_database_stats(self):
        """获取数据库统计信息"""
        with self.db_manager.get_connection() as conn:
            # 获取表信息
            tables_cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = tables_cursor.fetchall()
            
            table_stats = []
            for table in tables:
                table_name = table[0]
                # 获取表行数
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = count_cursor.fetchone()[0]
                
                table_stats.append({
                    'table_name': table_name,
                    'row_count': row_count
                })
            
            return table_stats
    
    def suggest_indexes(self):
        """建议数据库索引优化"""
        suggestions = []
        
        # 检查常用查询字段是否已建立索引
        common_queries = [
            {'table': 'spare_parts', 'columns': ['part_no', 'name']},
            {'table': 'operation_records', 'columns': ['operation_date', 'part_no']},
            {'table': 'locations', 'columns': ['status']}
        ]
        
        with self.db_manager.get_connection() as conn:
            for query in common_queries:
                table = query['table']
                columns = query['columns']
                
                # 检查是否已存在相关索引
                index_cursor = conn.execute(f"PRAGMA index_list({table})")
                existing_indexes = index_cursor.fetchall()
                
                # 简化的索引建议逻辑
                suggestions.append({
                    'table': table,
                    'columns': columns,
                    'recommendation': f'考虑为 {table} 表的 {", ".join(columns)} 字段创建复合索引'
                })
        
        return suggestions
