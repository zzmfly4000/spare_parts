# fix_location_data.py
import sqlite3
import os


def fix_location_data():
    """修复库位数据"""
    db_path = 'spare_parts.db'

    if not os.path.exists(db_path):
        print(f"数据库文件 {db_path} 不存在")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 检查 locations 表结构
        cursor.execute("PRAGMA table_info(locations)")
        columns = [col[1] for col in cursor.fetchall()]
        print("locations 表结构:", columns)

        # 检查是否有数据
        cursor.execute("SELECT COUNT(*) FROM locations")
        count = cursor.fetchone()[0]
        print(f"locations 表记录数: {count}")

        # 如果有数据，显示前几条
        if count > 0:
            cursor.execute("SELECT * FROM locations LIMIT 5")
            rows = cursor.fetchall()
            print("前5条记录:")
            for row in rows:
                print(row)

        # 如果没有数据，插入一些示例数据
        if count == 0:
            print("插入示例数据...")
            sample_locations = [
                ('A-01-01', 'A', '01', '01', '左', 'free', 100, '标准', '示例库位1', 0, 0, 0.0, 0, 0, 0.0, 'empty'),
                ('A-01-02', 'A', '01', '02', '左', 'free', 100, '标准', '示例库位2', 0, 0, 0.0, 0, 0, 0.0, 'empty'),
                ('B-01-01', 'B', '01', '01', '右', 'free', 150, '大型', '示例库位3', 0, 0, 0.0, 0, 0, 0.0, 'empty'),
            ]

            cursor.executemany('''
                INSERT INTO locations 
                (location_code, rack, level, position, side, status, capacity, 
                 size_type, description, variety_count, total_quantity, 
                 utilization_rate, low_stock_varieties, out_of_stock_varieties, 
                 total_value, status_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', sample_locations)

            conn.commit()
            print("✅ 示例数据插入成功")

        # 检查 rack_layouts 表
        cursor.execute("SELECT COUNT(*) FROM rack_layouts")
        rack_count = cursor.fetchone()[0]
        print(f"rack_layouts 表记录数: {rack_count}")

        # 如果没有货架布局数据，插入一些
        if rack_count == 0:
            print("插入货架布局数据...")
            sample_layouts = [
                ('A', 100, 100, 300, 200, 0),
                ('B', 200, 150, 300, 200, 0),
            ]

            cursor.executemany('''
                INSERT OR REPLACE INTO rack_layouts (rack, x, y, width, height, rotation)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', sample_layouts)

            conn.commit()
            print("✅ 货架布局数据插入成功")

    except Exception as e:
        print(f"❌ 修复数据时出错: {str(e)}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    fix_location_data()