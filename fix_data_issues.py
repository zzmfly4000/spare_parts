# [file name]: fix_data_issues.py
# [file content begin]
from models.database import DatabaseManager


def fix_data_issues():
    """修复数据完整性问题 - 彻底清理 NULL 值"""
    db_manager = DatabaseManager()

    with db_manager.get_connection() as conn:
        print("开始修复数据完整性问题...")

        # 修复 spare_parts 表中的 NULL 值
        conn.execute('''
            UPDATE spare_parts 
            SET current_stock = 0 
            WHERE current_stock IS NULL
        ''')
        print("修复 current_stock NULL 值完成")

        conn.execute('''
            UPDATE spare_parts 
            SET min_stock = 0 
            WHERE min_stock IS NULL
        ''')
        print("修复 min_stock NULL 值完成")

        conn.execute('''
            UPDATE spare_parts 
            SET max_stock = 0 
            WHERE max_stock IS NULL
        ''')
        print("修复 max_stock NULL 值完成")

        conn.execute('''
            UPDATE spare_parts 
            SET lt_weeks = 0 
            WHERE lt_weeks IS NULL
        ''')
        print("修复 lt_weeks NULL 值完成")

        conn.execute('''
            UPDATE spare_parts 
            SET unit_price = 0.0 
            WHERE unit_price IS NULL
        ''')
        print("修复 unit_price NULL 值完成")

        conn.execute('''
            UPDATE spare_parts 
            SET key_part = FALSE 
            WHERE key_part IS NULL
        ''')
        print("修复 key_part NULL 值完成")

        # 修复 locations 表中的 NULL 值
        conn.execute('''
            UPDATE locations 
            SET capacity = 0 
            WHERE capacity IS NULL
        ''')
        print("修复 locations capacity NULL 值完成")

        conn.execute('''
            UPDATE locations 
            SET part_count = 0 
            WHERE part_count IS NULL
        ''')
        print("修复 locations part_count NULL 值完成")

        conn.execute('''
            UPDATE locations 
            SET status = 'free' 
            WHERE status IS NULL
        ''')
        print("修复 locations status NULL 值完成")

        print("所有数据完整性问题修复完成！")


if __name__ == '__main__':
    fix_data_issues()
# [file content end]