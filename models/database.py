import sqlite3
import os
import logging
from contextlib import contextmanager
from datetime import datetime


class DatabaseManager:
    """数据库管理器，负责数据库连接和操作 - 性能优化版本"""

    def __init__(self, db_path='spare_parts.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库连接池和性能优化"""
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)

        # 配置SQLite性能优化参数
        with sqlite3.connect(self.db_path) as conn:
            # 性能优化设置
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")  # 写前日志，提高并发
            conn.execute("PRAGMA synchronous = NORMAL")  # 平衡性能和数据安全
            conn.execute("PRAGMA cache_size = 100000")  # 增加缓存大小
            conn.execute("PRAGMA temp_store = MEMORY")  # 临时表存储在内存中
            conn.execute("PRAGMA mmap_size = 268435456")  # 256MB内存映射
            conn.execute("PRAGMA page_size = 4096")  # 合适的页面大小

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器 - 性能优化版本"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使用Row工厂提高性能

        # 设置连接级别的优化
        conn.execute("PRAGMA optimize")  # 优化查询计划
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
        else:
            conn.commit()
        finally:
            # 清理连接
            conn.execute("PRAGMA optimize")
            conn.close()


def calculate_stock_from_operations(part_no):
    """根据操作记录计算备件库存"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 计算入库总量
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND operation_type = 'Stock in'
        ''', (part_no,))
        total_in = cursor.fetchone()[0]

        # 计算出库总量
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND operation_type = 'Stock out'
        ''', (part_no,))
        total_out = cursor.fetchone()[0]

        return total_in - total_out


def update_stock_for_part(part_id, new_stock):
    """更新单个备件的库存数量"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            UPDATE spare_parts 
            SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (new_stock, part_id))
        return cursor.rowcount


def recalculate_all_stock():
    """重新计算所有备件的库存"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 获取所有备件
        cursor = conn.execute('SELECT part_no FROM spare_parts')
        parts = cursor.fetchall()

        updated_count = 0
        for part in parts:
            part_no = part[0]
            calculated_stock = calculate_stock_from_operations(part_no)

            # 更新备件库存
            cursor = conn.execute('''
                UPDATE spare_parts 
                SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                WHERE part_no = ?
            ''', (calculated_stock, part_no))

            if cursor.rowcount > 0:
                updated_count += 1

        return updated_count


def is_low_stock(part_id):
    """判断备件是否处于低库存状态"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT current_stock, min_stock 
            FROM spare_parts 
            WHERE id = ?
        ''', (part_id,))
        result = cursor.fetchone()

        if result:
            current_stock, min_stock = result
            return current_stock <= min_stock
        return False


# 确保 get_low_stock_parts 函数存在
def get_low_stock_parts():
    """获取所有低库存备件列表"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT * FROM spare_parts 
            WHERE current_stock <= min_stock 
            ORDER BY current_stock ASC
        ''')
        return cursor.fetchall()


def init_db():
    """初始化数据库表结构和索引"""
    db_manager = DatabaseManager()

    with db_manager.get_connection() as conn:
        # 创建备件表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS spare_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_no TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT,
                current_stock INTEGER DEFAULT 0,
                min_stock INTEGER DEFAULT 0,
                max_stock INTEGER DEFAULT 0,
                key_part BOOLEAN DEFAULT FALSE,
                lt_weeks INTEGER DEFAULT 0,
                unit_price REAL DEFAULT 0.0,
                unit TEXT,
                location TEXT,
                supplier TEXT,
                description TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(part_no, name)
            )
        ''')

        # 创建操作记录表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS operation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                operation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                supplier_recipient TEXT,
                location TEXT,
                part_no TEXT,
                description TEXT,
                part_type TEXT,
                quantity INTEGER,
                work_center TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建库位表 - 更新结构
        conn.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                location_code TEXT PRIMARY KEY,  -- 实际库位（关键字段）
                rack TEXT,                       -- 机架
                level TEXT,                      -- 层
                position TEXT,                   -- 层上的位置
                side TEXT,                       -- 库位所在边
                status TEXT DEFAULT 'free',      -- 库存状态
                capacity INTEGER DEFAULT 0,      -- 库位容量
                size_type TEXT,                  -- 库位空间大小
                description TEXT,                -- 库位描述
                part_count INTEGER DEFAULT 0,    -- 当前零件数量
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引以提高查询性能
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_location ON spare_parts(location)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_type ON spare_parts(type)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_stock ON spare_parts(current_stock, min_stock)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_part_no ON spare_parts(part_no)')

        # 为操作记录表创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_date ON operation_records(operation_date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_part_no ON operation_records(part_no)')

        # 为库位表创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_locations_status ON locations(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_locations_rack ON locations(rack)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_locations_level ON locations(level)')

def get_spare_part_by_id(part_id):
    """根据ID获取备件信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM spare_parts WHERE id = ?', (part_id,))
        return cursor.fetchone()


def get_spare_part_by_part_no(part_no):
    """根据备件编号获取备件信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM spare_parts WHERE part_no = ?', (part_no,))
        return cursor.fetchone()


def create_spare_part(part_data):
    """创建新备件 - 增强错误处理版本"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            # 验证必要字段
            if not part_data.get('part_no') or not part_data.get('name'):
                raise ValueError("备件编号和名称不能为空")

            # 验证数据类型
            current_stock = safe_int(part_data.get('current_stock', 0))
            min_stock = safe_int(part_data.get('min_stock', 0))
            max_stock = safe_int(part_data.get('max_stock', 0))

            if current_stock < 0 or min_stock < 0 or max_stock < 0:
                raise ValueError("库存数量不能为负数")

            if min_stock > max_stock and max_stock > 0:
                raise ValueError("最低库存不能大于最高库存")

            cursor = conn.execute('''
                INSERT INTO spare_parts 
                (part_no, name, type, current_stock, min_stock, max_stock, key_part, 
                 lt_weeks, unit_price, unit, location, supplier, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                part_data['part_no'], part_data['name'], part_data.get('type', ''),
                current_stock, min_stock, max_stock, part_data.get('key_part', False),
                safe_int(part_data.get('lt_weeks', 0)), safe_float(part_data.get('unit_price', 0.0)),
                part_data.get('unit', ''), part_data.get('location', ''),
                part_data.get('supplier', ''), part_data.get('description', '')
            ))
            return cursor.lastrowid

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError(f"备件编号 '{part_data.get('part_no')}' 已存在")
        else:
            raise ValueError(f"数据库完整性错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"创建备件失败: {str(e)}")


def update_spare_part(part_id, part_data):
    """更新备件信息 - 增强错误处理版本"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            # 构建动态更新语句
            fields = []
            values = []
            for key, value in part_data.items():
                if key != 'id':  # 排除ID字段
                    fields.append(f"{key} = ?")

                    # 验证关键字段的数据类型
                    if key in ['current_stock', 'min_stock', 'max_stock', 'lt_weeks']:
                        validated_value = safe_int(value)
                        if validated_value < 0:
                            raise ValueError(f"{key} 不能为负数")
                        values.append(validated_value)
                    elif key == 'unit_price':
                        validated_value = safe_float(value)
                        if validated_value < 0:
                            raise ValueError("单价不能为负数")
                        values.append(validated_value)
                    else:
                        values.append(value)

            if not fields:
                raise ValueError("没有需要更新的字段")

            values.append(part_id)  # 添加WHERE条件值

            query = f"UPDATE spare_parts SET {', '.join(fields)} WHERE id = ?"
            cursor = conn.execute(query, values)

            if cursor.rowcount == 0:
                raise ValueError("备件不存在或没有数据被更新")

            return cursor.rowcount

    except sqlite3.IntegrityError as e:
        raise ValueError(f"数据完整性错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"更新备件失败: {str(e)}")


def delete_spare_part(part_id):
    """删除备件"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('DELETE FROM spare_parts WHERE id = ?', (part_id,))
        return cursor.rowcount


def get_all_spare_parts():
    """获取所有备件列表"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM spare_parts ORDER BY part_no')
        return cursor.fetchall()


def create_operation_record(operation_data):
    """创建操作记录 - 增强错误处理版本"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            # 验证必要字段
            if not operation_data.get('operation_type'):
                raise ValueError("操作类型不能为空")
            if not operation_data.get('part_no'):
                raise ValueError("备件编号不能为空")

            quantity = safe_int(operation_data.get('quantity', 0))
            if quantity == 0:
                raise ValueError("操作数量不能为0")

            # 验证操作类型和数量的关系
            operation_type = operation_data['operation_type'].lower()
            if 'in' in operation_type and quantity < 0:
                raise ValueError("入库操作数量不能为负数")
            elif 'out' in operation_type and quantity > 0:
                raise ValueError("出库操作数量不能为正数")

            cursor = conn.execute('''
                INSERT INTO operation_records 
                (operation_type, supplier_recipient, location, part_no, description, 
                 part_type, quantity, work_center)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                operation_data['operation_type'], operation_data.get('supplier_recipient', ''),
                operation_data.get('location', ''), operation_data['part_no'],
                operation_data['description'], operation_data.get('part_type', ''),
                quantity, operation_data.get('work_center', '')
            ))
            return cursor.lastrowid

    except sqlite3.IntegrityError as e:
        raise ValueError(f"数据库完整性错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"创建操作记录失败: {str(e)}")


def create_location(location_data):
    """创建新库位 - 支持新字段结构"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            # 验证关键字段
            if not location_data.get('location_code'):
                raise ValueError("实际库位不能为空")

            # 验证容量
            capacity = safe_int(location_data.get('capacity', 0))
            if capacity < 0:
                raise ValueError("库位容量不能为负数")

            # 验证状态 - 放宽验证
            valid_statuses = ['free', 'in_use', 'low_stock']
            status = location_data.get('status', 'free')
            if status not in valid_statuses:
                # 不在标准列表中，使用默认值但不报错
                status = 'free'
                logging.warning(f"库位状态值 '{location_data.get('status')}' 不在标准列表中，已设置为默认值 'free'")

            cursor = conn.execute('''
                INSERT INTO locations 
                (location_code, rack, level, position, side, status, capacity, size_type, description, part_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                location_data['location_code'],
                location_data.get('rack', ''),
                location_data.get('level', ''),
                location_data.get('position', ''),
                location_data.get('side', ''),
                status,
                capacity,
                location_data.get('size_type', ''),
                location_data.get('description', ''),
                location_data.get('part_count', 0)
            ))
            return cursor.lastrowid

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError(f"实际库位代码 '{location_data.get('location_code')}' 已存在")
        else:
            raise ValueError(f"数据库完整性错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"创建库位失败: {str(e)}")


def get_location_by_code(location_code):
    """根据库位代码获取库位信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM locations WHERE location_code = ?', (location_code,))
        return cursor.fetchone()


def update_location(location_code, location_data):
    """更新库位信息 - 支持新字段结构"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            # 构建动态更新语句
            fields = []
            values = []
            for key, value in location_data.items():
                if key != 'location_code':  # 排除主键字段
                    fields.append(f"{key} = ?")

                    # 验证关键字段
                    if key == 'capacity':
                        validated_value = safe_int(value)
                        if validated_value < 0:
                            raise ValueError("容量不能为负数")
                        values.append(validated_value)
                    elif key == 'status':
                        # 状态标准化
                        valid_statuses = ['free', 'in_use', 'low_stock']
                        if value not in valid_statuses:
                            # 不在标准列表中，使用默认值但不报错
                            value = 'free'
                            logging.warning(f"更新库位时状态值 '{location_data.get('status')}' 不在标准列表中，已设置为默认值 'free'")
                        values.append(value)
                    else:
                        values.append(value)

            if not fields:
                raise ValueError("没有需要更新的字段")

            values.append(location_code)  # 添加WHERE条件值

            query = f"UPDATE locations SET {', '.join(fields)} WHERE location_code = ?"
            cursor = conn.execute(query, values)

            if cursor.rowcount == 0:
                raise ValueError("库位不存在或没有数据被更新")

            return cursor.rowcount

    except Exception as e:
        raise ValueError(f"更新库位失败: {str(e)}")


def delete_location(location_code):
    """删除库位"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('DELETE FROM locations WHERE location_code = ?', (location_code,))
        return cursor.rowcount


def get_all_locations():
    """获取所有库位列表"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM locations ORDER BY location_code')
        return cursor.fetchall()


def update_location_status(location_code, status):
    """更新库位状态"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            UPDATE locations 
            SET status = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE location_code = ?
        ''', (status, location_code))
        return cursor.rowcount


def get_all_operation_records(limit=None):
    """获取所有操作记录"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        query = 'SELECT * FROM operation_records ORDER BY operation_date DESC'
        if limit:
            query += f' LIMIT {limit}'
        cursor = conn.execute(query)
        return cursor.fetchall()


def get_spare_parts_count():
    """获取备件总数"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM spare_parts')
        return cursor.fetchone()[0]


def get_locations_count():
    """获取库位总数"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM locations')
        return cursor.fetchone()[0]


def get_all_locations():
    """获取所有库位列表"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM locations ORDER BY location_code')
        return cursor.fetchall()


def get_location_stats():
    """获取库位统计信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 总库位数
        total_locations = conn.execute('SELECT COUNT(*) FROM locations').fetchone()[0]

        # 空闲库位数
        free_locations = conn.execute('SELECT COUNT(*) FROM locations WHERE status = "free"').fetchone()[0]

        # 使用中库位数
        in_use_locations = conn.execute('SELECT COUNT(*) FROM locations WHERE status = "in_use"').fetchone()[0]

        return {
            'total_locations': total_locations,
            'free_locations': free_locations,
            'in_use_locations': in_use_locations
        }


def get_recent_activities(limit=10):
    """获取最近活动记录"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT operation_type, part_no, quantity, operation_date, description 
            FROM operation_records 
            ORDER BY operation_date DESC 
            LIMIT ?
        ''', (limit,))

        activities = []
        for record in cursor.fetchall():
            activities.append({
                'type': 'inbound' if record[0].lower() == 'stock in' else 'outbound',
                'part_name': record[4] or record[1],
                'quantity': record[2],
                'time': record[3],
                'operator': '系统导入'
            })
        return activities


# 添加辅助函数
def safe_int(value, default=0):
    """安全转换为整数"""
    if value is None or value == '':
        return default
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0):
    """安全转换为浮点数"""
    if value is None or value == '':
        return default
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return default