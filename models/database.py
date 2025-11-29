# [file name]: database.py
# [file content begin]
import sqlite3
import os
import logging
import time
import threading
from contextlib import contextmanager
from datetime import datetime


class DatabaseManager:
    """数据库管理器，负责数据库连接和操作 - 修复数据查询版本"""

    def __init__(self, db_path='spare_parts.db'):
        self.db_path = db_path
        self._init_db()
        self._lock = threading.RLock()

    def _init_db(self):
        """初始化数据库连接池和性能优化"""
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)

        with self._get_raw_connection() as conn:
            # 性能优化设置
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = 100000")
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 268435456")
            conn.execute("PRAGMA page_size = 4096")
            conn.execute("PRAGMA busy_timeout = 10000")

    @contextmanager
    def _get_raw_connection(self):
        """获取原始数据库连接（不包含线程锁）"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
                isolation_level=None
            )
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn:
                conn.close()

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器 - 修复版本"""
        max_retries = 5
        retry_delay = 0.5

        for attempt in range(max_retries):
            with self._lock:
                conn = None
                try:
                    conn = sqlite3.connect(
                        self.db_path,
                        timeout=30.0,
                        check_same_thread=False,
                        isolation_level=None
                    )
                    conn.row_factory = sqlite3.Row

                    # 设置连接级别的优化
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA busy_timeout = 10000")

                    yield conn
                    conn.commit()
                    break

                except sqlite3.OperationalError as e:
                    if conn:
                        conn.rollback()

                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        logging.warning(f"数据库被锁定，第 {attempt + 1} 次重试...")
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        raise ValueError(f"数据库操作失败: {str(e)}")

                except Exception as e:
                    if conn:
                        conn.rollback()
                    raise e

                finally:
                    if conn:
                        conn.close()


def calculate_stock_from_operations(part_no):
    """根据操作记录计算备件库存 - 修正版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 计算所有入库操作的总和（正数）
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND quantity > 0
        ''', (part_no,))
        total_in = cursor.fetchone()[0] or 0

        # 计算出库操作的总和（负数，但取绝对值）
        cursor = conn.execute('''
            SELECT COALESCE(SUM(ABS(quantity)), 0) 
            FROM operation_records 
            WHERE part_no = ? AND quantity < 0
        ''', (part_no,))
        total_out = cursor.fetchone()[0] or 0

        # 计算总库存：所有入库 - 所有出库
        total_stock = total_in - total_out
        final_stock = max(0, total_stock)

        logging.info(f"库存计算: {part_no} = {total_in}(入库) - {total_out}(出库) = {final_stock}")

        return final_stock


def calculate_stock_from_operations_with_connection(part_no, conn):
    """使用现有连接计算库存 - 修正版本"""
    # 计算所有入库操作的总和（正数）
    cursor = conn.execute('''
        SELECT COALESCE(SUM(quantity), 0) 
        FROM operation_records 
        WHERE part_no = ? AND quantity > 0
    ''', (part_no,))
    total_in = cursor.fetchone()[0] or 0

    # 计算出库操作的总和（负数，但取绝对值）
    cursor = conn.execute('''
        SELECT COALESCE(SUM(ABS(quantity)), 0) 
        FROM operation_records 
            WHERE part_no = ? AND quantity < 0
    ''', (part_no,))
    total_out = cursor.fetchone()[0] or 0

    # 计算总库存：所有入库 - 所有出库
    total_stock = total_in - total_out
    final_stock = max(0, total_stock)

    logging.info(f"库存计算(连接): {part_no} = {total_in}(入库) - {total_out}(出库) = {final_stock}")
    return final_stock


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
    """重新计算所有备件的库存 - 修正版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 获取所有备件
        cursor = conn.execute('SELECT id, part_no, current_stock FROM spare_parts')
        parts = cursor.fetchall()

        updated_count = 0
        for part in parts:
            part_id = part[0]
            part_no = part[1]
            old_stock = part[2]

            # 使用修正后的库存计算函数
            calculated_stock = calculate_stock_from_operations_with_connection(part_no, conn)

            # 只有在库存发生变化时才更新
            if calculated_stock != old_stock:
                cursor = conn.execute('''
                    UPDATE spare_parts 
                    SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (calculated_stock, part_id))

                if cursor.rowcount > 0:
                    updated_count += 1
                    logging.info(f"备件 {part_no} 库存重新计算: {old_stock} -> {calculated_stock}")

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


def get_low_stock_parts():
    """获取所有低库存备件列表 - 彻底修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT * FROM spare_parts 
            WHERE (current_stock <= min_stock OR current_stock = 0) AND current_stock >= 0
            ORDER BY current_stock ASC
        ''')
        results = cursor.fetchall()

        # 确保所有数字字段都有有效值
        processed_results = []
        for part in results:
            part_list = list(part)
            # 确保关键字段不为None
            if part_list[4] is None:  # current_stock
                part_list[4] = 0
            if part_list[6] is None:  # min_stock
                part_list[6] = 0
            if part_list[7] is None:  # max_stock
                part_list[7] = 0
            processed_results.append(tuple(part_list))

        return processed_results


def init_db():
    """初始化数据库表结构和索引"""
    db_manager = DatabaseManager()

    with db_manager.get_connection() as conn:
        # 创建备件表 - 修复版本：添加 product_model 字段
        conn.execute('''
            CREATE TABLE IF NOT EXISTS spare_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_no TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT,
                product_model TEXT,  -- 新增字段
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
                product_model TEXT,
                quantity INTEGER,
                work_center TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建库位表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                location_code TEXT PRIMARY KEY,
                rack TEXT,
                level TEXT,
                position TEXT,
                side TEXT,
                status TEXT DEFAULT 'free',
                capacity INTEGER DEFAULT 0,
                size_type TEXT,
                description TEXT,
                part_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 为现有表添加缺失的列（如果不存在）
        try:
            conn.execute('ALTER TABLE spare_parts ADD COLUMN product_model TEXT')
        except sqlite3.OperationalError:
            # 列已存在，忽略错误
            pass

        # 创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_location ON spare_parts(location)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_type ON spare_parts(type)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_stock ON spare_parts(current_stock, min_stock)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_part_no ON spare_parts(part_no)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_date ON operation_records(operation_date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_part_no ON operation_records(part_no)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_type ON operation_records(operation_type)')
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
    """创建新备件 - 修正库存计算版本"""
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
                (part_no, name, type, product_model, current_stock, min_stock, max_stock, key_part, 
                 lt_weeks, unit_price, unit, location, supplier, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                part_data['part_no'], part_data['name'],
                part_data.get('type', ''),
                part_data.get('product_model', ''),  # 新增字段
                current_stock,
                min_stock, max_stock, part_data.get('key_part', False),
                safe_int(part_data.get('lt_weeks', 0)), safe_float(part_data.get('unit_price', 0.0)),
                part_data.get('unit', ''), part_data.get('location', ''),
                part_data.get('supplier', ''), part_data.get('description', '')
            ))

            part_id = cursor.lastrowid

            # 如果设置了初始库存，创建对应的入库操作记录
            if current_stock > 0:
                operation_data = {
                    'operation_type': 'Stock in',
                    'part_no': part_data['part_no'],
                    'quantity': current_stock,
                    'description': f'初始库存设置 - {part_data.get("description", "")}',
                    'location': part_data.get('location', ''),
                    'supplier_recipient': part_data.get('supplier', '系统'),
                    'product_model': part_data.get('product_model', ''),  # 新增字段
                    'part_type': part_data.get('type', '')  # 新增字段
                }

                try:
                    create_operation_record(operation_data)
                except Exception as e:
                    logging.warning(f"创建初始库存操作记录失败: {str(e)}")

            return part_id

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError(f"备件编号 '{part_data.get('part_no')}' 已存在")
        else:
            raise ValueError(f"数据库完整性错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"创建备件失败: {str(e)}")


def update_spare_part(part_id, part_data):
    """更新备件信息"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            fields = []
            values = []

            for key, value in part_data.items():
                if key != 'id':
                    fields.append(f"{key} = ?")

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
                    elif key == 'key_part':
                        if isinstance(value, bool):
                            values.append(value)
                        elif isinstance(value, str):
                            values.append(value.lower() in ['true', 'yes', '1', '是'])
                        else:
                            values.append(bool(value))
                    else:
                        values.append(value)

            if not fields:
                raise ValueError("没有需要更新的字段")

            values.append(part_id)

            query = f"UPDATE spare_parts SET {', '.join(fields)}, updated_date = CURRENT_TIMESTAMP WHERE id = ?"
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
    """创建操作记录 - 修复版本"""
    db_manager = DatabaseManager()
    max_retries = 5
    retry_delay = 0.5

    for attempt in range(max_retries):
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

                # 插入操作记录
                cursor = conn.execute('''
                    INSERT INTO operation_records 
                    (operation_type, operation_date, supplier_recipient, location, part_no, 
                     description, part_type, product_model, quantity, work_center)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    operation_data['operation_type'],
                    operation_data.get('operation_date', datetime.now()),
                    operation_data.get('supplier_recipient', ''),
                    operation_data.get('location', ''),
                    operation_data['part_no'],
                    operation_data.get('description', ''),
                    operation_data.get('part_type', ''),
                    operation_data.get('product_model', ''),
                    quantity,
                    operation_data.get('work_center', '')
                ))

                record_id = cursor.lastrowid

                # 重新计算并更新备件库存
                part_no = operation_data['part_no']
                new_stock = calculate_stock_from_operations_with_connection(part_no, conn)

                # 更新备件库存
                conn.execute('''
                    UPDATE spare_parts 
                    SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                    WHERE part_no = ?
                ''', (new_stock, part_no))

                logging.info(f"操作记录创建后更新备件 {part_no} 库存为: {new_stock}")

                return record_id

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logging.warning(f"数据库锁定，第 {attempt + 1} 次重试...")
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                raise ValueError(f"数据库操作错误: {str(e)}")
        except Exception as e:
            raise ValueError(f"创建操作记录失败: {str(e)}")

    raise ValueError("创建操作记录失败：数据库繁忙，请稍后重试")


def create_location_fast(location_data, conn=None):
    """创建新库位"""
    try:
        if conn is None:
            db_manager = DatabaseManager()
            conn = db_manager.get_connection()

        if not location_data.get('location_code'):
            raise ValueError("实际库位不能为空")

        capacity = safe_int(location_data.get('capacity', 0))
        if capacity < 0:
            raise ValueError("库位容量不能为负数")

        valid_statuses = ['free', 'in_use', 'low_stock']
        status = location_data.get('status', 'free')
        if status not in valid_statuses:
            status = 'free'

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
        return True

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError(f"实际库位代码 '{location_data.get('location_code')}' 已存在")
        else:
            raise ValueError(f"数据库完整性错误: {str(e)}")
    except Exception as e:
        pass


def get_location_by_code(location_code):
    """根据库位代码获取库位信息 - 修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM locations WHERE location_code = ?', (location_code,))
        row = cursor.fetchone()
        if row:
            if hasattr(row, '_fields'):  # sqlite3.Row 对象
                location_dict = {}
                for i, field in enumerate(row._fields):
                    location_dict[field] = row[i]
                return location_dict
            else:  # 元组
                return {
                    'location_code': row[0] if len(row) > 0 else '',
                    'rack': row[1] if len(row) > 1 else '',
                    'level': row[2] if len(row) > 2 else '',
                    'position': row[3] if len(row) > 3 else '',
                    'side': row[4] if len(row) > 4 else '',
                    'status': row[5] if len(row) > 5 else 'free',
                    'capacity': row[6] if len(row) > 6 else 0,
                    'size_type': row[7] if len(row) > 7 else '',
                    'description': row[8] if len(row) > 8 else '',
                    'part_count': row[9] if len(row) > 9 else 0,
                    'last_updated': row[10] if len(row) > 10 else None
                }
        return None


def update_location_fast(location_code, location_data, conn=None):
    """更新库位信息"""
    try:
        if conn is None:
            db_manager = DatabaseManager()
            conn = db_manager.get_connection()

        fields = []
        values = []
        for key, value in location_data.items():
            if key != 'location_code':
                fields.append(f"{key} = ?")

                if key == 'capacity':
                    validated_value = safe_int(value)
                    if validated_value < 0:
                        raise ValueError("容量不能为负数")
                    values.append(validated_value)
                elif key == 'status':
                    valid_statuses = ['free', 'in_use', 'low_stock']
                    if value not in valid_statuses:
                        value = 'free'
                    values.append(value)
                else:
                    values.append(value)

        if not fields:
            raise ValueError("没有需要更新的字段")

        values.append(location_code)

        query = f"UPDATE locations SET {', '.join(fields)} WHERE location_code = ?"
        cursor = conn.execute(query, values)

        if cursor.rowcount == 0:
            return False

        return True

    except Exception as e:
        raise ValueError(f"更新库位失败: {str(e)}")


def delete_location(location_code):
    """删除库位"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('DELETE FROM locations WHERE location_code = ?', (location_code,))
        return cursor.rowcount


def get_all_locations():
    """获取所有库位列表 - 修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM locations ORDER BY location_code')
        # 返回列表而不是 sqlite3.Row 对象
        results = cursor.fetchall()
        # 转换为字典列表
        locations = []
        for row in results:
            if hasattr(row, '_fields'):  # sqlite3.Row 对象
                location_dict = {}
                for i, field in enumerate(row._fields):
                    location_dict[field] = row[i]
                locations.append(location_dict)
            else:  # 元组
                locations.append({
                    'location_code': row[0] if len(row) > 0 else '',
                    'rack': row[1] if len(row) > 1 else '',
                    'level': row[2] if len(row) > 2 else '',
                    'position': row[3] if len(row) > 3 else '',
                    'side': row[4] if len(row) > 4 else '',
                    'status': row[5] if len(row) > 5 else 'free',
                    'capacity': row[6] if len(row) > 6 else 0,
                    'size_type': row[7] if len(row) > 7 else '',
                    'description': row[8] if len(row) > 8 else '',
                    'part_count': row[9] if len(row) > 9 else 0,
                    'last_updated': row[10] if len(row) > 10 else None
                })
        return locations


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
        query = '''
            SELECT id, operation_type, operation_date, supplier_recipient, location, 
                   part_no, description, part_type, product_model, quantity, work_center, created_date
            FROM operation_records 
            ORDER BY operation_date DESC
        '''
        if limit:
            query += f' LIMIT {limit}'
        cursor = conn.execute(query)
        return cursor.fetchall()


def get_spare_parts_count():
    """获取备件总数 - 修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM spare_parts')
        result = cursor.fetchone()
        return result[0] if result else 0


def get_locations_count():
    """获取库位总数 - 修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM locations')
        result = cursor.fetchone()
        return result[0] if result else 0


def get_location_stats():
    """获取库位统计信息 - 彻底修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 总库位数
        total_result = conn.execute('SELECT COUNT(*) FROM locations').fetchone()
        total_locations = total_result[0] if total_result else 0

        # 空闲库位数
        free_result = conn.execute('SELECT COUNT(*) FROM locations WHERE status = "free"').fetchone()
        free_locations = free_result[0] if free_result else 0

        # 使用中库位数
        in_use_result = conn.execute('SELECT COUNT(*) FROM locations WHERE status = "in_use"').fetchone()
        in_use_locations = in_use_result[0] if in_use_result else 0

        # 低库存库位数
        low_stock_result = conn.execute('SELECT COUNT(*) FROM locations WHERE status = "low_stock"').fetchone()
        low_stock_locations = low_stock_result[0] if low_stock_result else 0

        return {
            'total_locations': total_locations,
            'free_locations': free_locations,
            'in_use_locations': in_use_locations,
            'low_stock_locations': low_stock_locations
        }


def get_recent_activities(limit=10):
    """获取最近活动记录 - 彻底修复版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT operation_type, part_no, quantity, operation_date, description, supplier_recipient
            FROM operation_records 
            ORDER BY operation_date DESC 
            LIMIT ?
        ''', (limit,))

        activities = []
        for record in cursor.fetchall():
            operation_type = record[0]
            part_no = record[1]
            quantity = record[2]
            operation_date = record[3]
            description = record[4]
            supplier_recipient = record[5]

            # 调试日志 - 记录原始数据类型
            logging.info(f"原始数据 - 操作类型: {operation_type}, 数量: {quantity} (类型: {type(quantity)})")

            # 安全转换数量为整数 - 彻底修复
            try:
                if isinstance(quantity, (int, float)):
                    quantity = int(quantity)
                elif isinstance(quantity, str):
                    # 处理可能的字符串格式
                    quantity_str = quantity.strip()
                    if quantity_str == '':
                        quantity = 0
                    else:
                        quantity = int(float(quantity_str))  # 先转浮点再转整数
                else:
                    quantity = 0
            except (ValueError, TypeError) as e:
                logging.warning(f"数量转换失败: {quantity}, 错误: {str(e)}")
                quantity = 0

            # 处理日期格式
            if isinstance(operation_date, str):
                try:
                    if 'T' in operation_date:
                        operation_date = datetime.fromisoformat(operation_date.replace('Z', '+00:00'))
                    else:
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%H:%M:%S']:
                            try:
                                operation_date = datetime.strptime(operation_date, fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            operation_date = datetime.now()
                except Exception as e:
                    logging.warning(f"日期解析失败: {operation_date}, 错误: {str(e)}")
                    operation_date = datetime.now()
            elif not isinstance(operation_date, datetime):
                operation_date = datetime.now()

            # 确定操作类型和显示名称
            if any(in_type in operation_type.lower() for in_type in ['stock in', 'disassemble', 'return']):
                activity_type = 'inbound'
                operator = supplier_recipient or '供应商'
            else:
                activity_type = 'outbound'
                operator = supplier_recipient or '内部领用'

            activities.append({
                'type': activity_type,
                'part_name': description or part_no,
                'quantity': quantity,  # 现在quantity是整数
                'time': operation_date,
                'operator': operator
            })

            # 调试日志 - 记录转换后的数据
            logging.info(f"转换后 - 操作类型: {activity_type}, 数量: {quantity} (类型: {type(quantity)})")

        return activities


def batch_update_parts(update_data_list):
    """批量更新备件信息"""
    db_manager = DatabaseManager()
    updated_count = 0
    errors = []

    with db_manager.get_connection() as conn:
        for update_data in update_data_list:
            try:
                part_id = update_data.get('id')
                if not part_id:
                    errors.append(f"缺少备件ID: {update_data}")
                    continue

                fields = []
                values = []
                for key, value in update_data.items():
                    if key != 'id':
                        fields.append(f"{key} = ?")
                        if key in ['current_stock', 'min_stock', 'max_stock', 'lt_weeks']:
                            values.append(safe_int(value))
                        elif key == 'unit_price':
                            values.append(safe_float(value))
                        else:
                            values.append(value)

                if fields:
                    values.append(part_id)
                    query = f"UPDATE spare_parts SET {', '.join(fields)}, updated_date = CURRENT_TIMESTAMP WHERE id = ?"
                    cursor = conn.execute(query, values)
                    if cursor.rowcount > 0:
                        updated_count += 1

            except Exception as e:
                errors.append(f"更新备件 {update_data.get('id')} 失败: {str(e)}")

    return updated_count, errors


def batch_delete_parts(part_ids):
    """批量删除备件"""
    db_manager = DatabaseManager()
    deleted_count = 0

    with db_manager.get_connection() as conn:
        for part_id in part_ids:
            try:
                cursor = conn.execute('DELETE FROM spare_parts WHERE id = ?', (part_id,))
                if cursor.rowcount > 0:
                    deleted_count += 1
            except Exception:
                continue

    return deleted_count


def get_operation_statistics(part_no):
    """获取备件的操作统计信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        stats = {}

        # 全新件入库统计
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND operation_type = 'Stock in'
        ''', (part_no,))
        stats['new_parts_in'] = cursor.fetchone()[0]

        # 拆机件入库统计
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND operation_type = 'Stock in - disassemble'
        ''', (part_no,))
        stats['disassemble_parts_in'] = cursor.fetchone()[0]

        # 返库件入库统计
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND operation_type = 'Stock in - return'
        ''', (part_no,))
        stats['return_parts_in'] = cursor.fetchone()[0]

        # 出库统计
        cursor = conn.execute('''
            SELECT COALESCE(SUM(quantity), 0) 
            FROM operation_records 
            WHERE part_no = ? AND operation_type = 'Stock out'
        ''', (part_no,))
        stats['parts_out'] = cursor.fetchone()[0]

        return stats


def batch_create_locations(locations_data, conn=None):
    """批量创建库位"""
    if not locations_data:
        return 0

    created_count = 0

    try:
        if conn is None:
            db_manager = DatabaseManager()
            conn = db_manager.get_connection()

        for location_data in locations_data:
            try:
                create_location_fast(location_data, conn)
                created_count += 1
            except Exception:
                continue

        if conn is None:
            conn.commit()

        return created_count

    except Exception as e:
        if conn is None:
            conn.rollback()
        raise e


def batch_update_locations(update_list, conn=None):
    """批量更新库位"""
    if not update_list:
        return 0

    updated_count = 0

    try:
        if conn is None:
            db_manager = DatabaseManager()
            conn = db_manager.get_connection()

        for update_item in update_list:
            try:
                update_location_fast(update_item['location_code'], update_item['update_data'], conn)
                updated_count += 1
            except Exception:
                continue

        if conn is None:
            conn.commit()

        return updated_count

    except Exception as e:
        if conn is None:
            conn.rollback()
        raise e


def safe_int(value, default=0):
    """安全转换为整数"""
    if value is None or value == '':
        return default
    try:
        return int(float(str(value)))  # 先转字符串，再转浮点，最后转整数
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
# [file content end]