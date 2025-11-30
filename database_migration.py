# database_migration.py
import sqlite3
import os
from datetime import datetime


def migrate_database():
    """执行数据库结构迁移"""
    db_path = 'spare_parts.db'

    if not os.path.exists(db_path):
        print("数据库文件不存在，请检查路径")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 开始事务
        conn.execute('BEGIN TRANSACTION')

        print("开始数据库迁移...")

        # 1. 创建临时表保存现有数据
        print("步骤1: 创建临时表...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations_backup (
                location_code TEXT PRIMARY KEY,
                rack TEXT,
                level TEXT,
                position TEXT,
                side TEXT,
                status TEXT DEFAULT 'free',
                capacity INTEGER DEFAULT 0,
                size_type TEXT,
                description TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. 备份现有数据到临时表
        print("步骤2: 备份现有数据...")
        cursor.execute('''
            INSERT OR REPLACE INTO locations_backup 
            SELECT location_code, rack, level, position, side, status, capacity, size_type, description, last_updated
            FROM locations
        ''')

        # 3. 删除原表
        print("步骤3: 删除原表...")
        cursor.execute('DROP TABLE IF EXISTS locations')

        # 4. 创建新表结构
        print("步骤4: 创建新表结构...")
        cursor.execute('''
            CREATE TABLE locations (
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

        # 5. 从备份表恢复数据
        print("步骤5: 恢复数据到新表...")
        cursor.execute('''
            INSERT INTO locations 
            (location_code, rack, level, position, side, status, capacity, size_type, description, last_updated)
            SELECT location_code, rack, level, position, side, status, capacity, size_type, description, last_updated
            FROM locations_backup
        ''')

        # 6. 删除备份表
        print("步骤6: 清理备份表...")
        cursor.execute('DROP TABLE IF EXISTS locations_backup')

        # 7. 重新创建索引
        print("步骤7: 重新创建索引...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_locations_status ON locations(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_locations_rack ON locations(rack)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_locations_level ON locations(level)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_locations_status_category ON locations(status_category)')

        # 提交事务
        conn.commit()
        print("数据库迁移成功完成!")

        # 8. 初始化新的统计字段
        print("步骤8: 初始化统计字段...")
        initialize_location_metrics(conn)

        conn.close()
        return True

    except Exception as e:
        print(f"数据库迁移失败: {str(e)}")
        conn.rollback()
        conn.close()
        return False


def initialize_location_metrics(conn):
    """初始化库位统计指标"""
    cursor = conn.cursor()

    # 获取所有库位
    cursor.execute('SELECT location_code FROM locations')
    locations = cursor.fetchall()

    updated_count = 0
    for location in locations:
        location_code = location[0]
        metrics = calculate_location_metrics_for_migration(conn, location_code)

        if metrics:
            cursor.execute('''
                UPDATE locations SET 
                    variety_count = ?,
                    total_quantity = ?,
                    utilization_rate = ?,
                    low_stock_varieties = ?,
                    out_of_stock_varieties = ?,
                    total_value = ?,
                    status_category = ?
                WHERE location_code = ?
            ''', (
                metrics['variety_count'],
                metrics['total_quantity'],
                metrics['utilization_rate'],
                metrics['low_stock_varieties'],
                metrics['out_of_stock_varieties'],
                metrics['total_value'],
                metrics['status_category'],
                location_code
            ))
            updated_count += 1

    conn.commit()
    print(f"成功初始化 {updated_count} 个库位的统计指标")


def calculate_location_metrics_for_migration(conn, location_code):
    """迁移时计算库位指标"""
    cursor = conn.execute('''
        SELECT 
            l.location_code,
            l.capacity,
            COUNT(DISTINCT p.id) as variety_count,
            COALESCE(SUM(p.current_stock), 0) as total_quantity,
            COALESCE(SUM(p.current_stock * p.unit_price), 0.0) as total_value,
            COUNT(CASE WHEN p.current_stock <= p.min_stock AND p.current_stock > 0 THEN 1 END) as low_stock_count,
            COUNT(CASE WHEN p.current_stock = 0 THEN 1 END) as out_of_stock_count
        FROM locations l
        LEFT JOIN spare_parts p ON l.location_code = p.location
        WHERE l.location_code = ?
        GROUP BY l.location_code, l.capacity
    ''', (location_code,))

    result = cursor.fetchone()
    if result:
        capacity = result[2] or 1  # 避免除零
        utilization_rate = (result[3] / capacity * 100) if capacity > 0 else 0

        # 计算专业状态分类
        status_category = calculate_professional_status(
            result[1],  # variety_count
            result[5],  # out_of_stock_count
            result[4],  # low_stock_count
            utilization_rate
        )

        return {
            'variety_count': result[1],
            'total_quantity': result[2],
            'utilization_rate': round(utilization_rate, 2),
            'low_stock_varieties': result[4],
            'out_of_stock_varieties': result[5],
            'total_value': result[3],
            'status_category': status_category
        }
    return None


def calculate_professional_status(variety_count, out_of_stock_count, low_stock_count, utilization_rate):
    """计算专业库位状态分类"""
    if variety_count == 0:
        return 'empty'  # 空置
    elif out_of_stock_count == variety_count:
        return 'all_out_of_stock'  # 全部缺货
    elif out_of_stock_count > 0:
        return 'partial_out_of_stock'  # 部分缺货
    elif low_stock_count == variety_count:
        return 'all_low_stock'  # 全部低库存
    elif low_stock_count > 0:
        return 'partial_low_stock'  # 部分低库存
    elif utilization_rate >= 90:
        return 'full'  # 满载
    elif utilization_rate >= 70:
        return 'high_utilization'  # 高利用率
    else:
        return 'normal'  # 正常


if __name__ == "__main__":
    print("开始执行数据库迁移...")
    print("警告: 请在执行前备份数据库!")

    confirm = input("确定要继续吗? (y/N): ")
    if confirm.lower() == 'y':
        success = migrate_database()
        if success:
            print("迁移完成!")
        else:
            print("迁移失败!")
    else:
        print("已取消迁移")