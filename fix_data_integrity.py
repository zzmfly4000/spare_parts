# [file name]: fix_data_integrity.py
# [file content begin]
from models.database import DatabaseManager


def fix_data_integrity():
    """修复数据完整性问题"""
    db_manager = DatabaseManager()

    with db_manager.get_connection() as conn:
        # 修复 spare_parts 表中的 NULL 值
        conn.execute('''
            UPDATE spare_parts 
            SET current_stock = 0 
            WHERE current_stock IS NULL
        ''')

        conn.execute('''
            UPDATE spare_parts 
            SET min_stock = 0 
            WHERE min_stock IS NULL
        ''')

        conn.execute('''
            UPDATE spare_parts 
            SET max_stock = 0 
            WHERE max_stock IS NULL
        ''')

        # 修复 locations 表中的 NULL 值
        conn.execute('''
            UPDATE locations 
            SET capacity = 0 
            WHERE capacity IS NULL
        ''')

        conn.execute('''
            UPDATE locations 
            SET part_count = 0 
            WHERE part_count IS NULL
        ''')

        print("数据完整性修复完成")


if __name__ == '__main__':
    fix_data_integrity()
# [file content end]