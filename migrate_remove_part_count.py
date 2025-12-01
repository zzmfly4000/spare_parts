# migrate_remove_part_count.py
import sqlite3
import os


def migrate_database():
    """迁移数据库，移除 part_count 列"""
    db_path = 'spare_parts.db'

    if not os.path.exists(db_path):
        print(f"数据库文件 {db_path} 不存在")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 创建临时表（不包含 part_count）
        cursor.execute('''
            CREATE TABLE locations_new (
                location_code TEXT PRIMARY KEY,
                rack TEXT,
                level TEXT,
                position TEXT,
                side TEXT,
                status TEXT DEFAULT 'free',
                capacity INTEGER DEFAULT 0,
                size_type TEXT,
                description TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                variety_count INTEGER DEFAULT 0,
                total_quantity INTEGER DEFAULT 0,
                utilization_rate REAL DEFAULT 0.0,
                low_stock_varieties INTEGER DEFAULT 0,
                out_of_stock_varieties INTEGER DEFAULT 0,
                total_value REAL DEFAULT 0.0,
                status_category TEXT DEFAULT 'empty'
            )
        ''')

        # 复制数据（排除 part_count）
        cursor.execute('''
            INSERT INTO locations_new 
            (location_code, rack, level, position, side, status, capacity, 
             size_type, description, last_updated, variety_count, total_quantity,
             utilization_rate, low_stock_varieties, out_of_stock_varieties, 
             total_value, status_category)
            SELECT 
                location_code, rack, level, position, side, status, capacity,
                size_type, description, last_updated, variety_count, total_quantity,
                utilization_rate, low_stock_varieties, out_of_stock_varieties,
                total_value, status_category
            FROM locations
        ''')

        # 删除旧表
        cursor.execute('DROP TABLE locations')

        # 重命名新表
        cursor.execute('ALTER TABLE locations_new RENAME TO locations')

        print("✅ 成功移除 part_count 列")

    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}")
        conn.rollback()
    finally:
        conn.commit()
        conn.close()


if __name__ == '__main__':
    migrate_database()