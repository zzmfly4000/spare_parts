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
    """数据库管理器，负责数据库连接和操作 - 优化版本"""

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
        """获取数据库连接的上下文管理器 - 优化版本"""
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
    """使用现有连接计算库存 - 彻底修复版本"""
    try:
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
        final_stock = max(0, total_stock)  # 库存不能为负数

        logging.info(f"库存计算(连接): {part_no} = {total_in}(入库) - {total_out}(出库) = {final_stock}")
        return final_stock
    except Exception as e:
        logging.error(f"库存计算失败: {str(e)}")
        return 0


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


def get_current_stock_for_part(part_no):
    """直接获取备件的当前库存 - 新增函数"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT current_stock FROM spare_parts WHERE part_no = ?
        ''', (part_no,))
        result = cursor.fetchone()
        return result[0] if result else 0


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
            if hasattr(part, '_fields'):  # sqlite3.Row 对象
                part_dict = {}
                for i, field in enumerate(part._fields):
                    value = part[i]
                    # 处理数值字段的 None 值
                    if field in ['current_stock', 'min_stock', 'max_stock', 'lt_weeks']:
                        value = value if value is not None else 0
                    elif field == 'unit_price':
                        value = value if value is not None else 0.0
                    elif field == 'key_part':
                        value = value if value is not None else False
                    part_dict[field] = value
                processed_results.append(part_dict)
            else:  # 元组格式
                part_list = list(part)
                # 确保关键字段不为None
                if len(part_list) > 4 and part_list[4] is None:  # current_stock
                    part_list[4] = 0
                if len(part_list) > 6 and part_list[6] is None:  # min_stock
                    part_list[6] = 0
                if len(part_list) > 7 and part_list[7] is None:  # max_stock
                    part_list[7] = 0
                processed_results.append(tuple(part_list))

        return processed_results


def init_db():
    """初始化数据库表结构和索引"""
    db_manager = DatabaseManager()

    with db_manager.get_connection() as conn:
        # 创建货架布局表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS rack_layouts (
                rack TEXT PRIMARY KEY,
                x INTEGER DEFAULT 100,
                y INTEGER DEFAULT 100,
                width INTEGER DEFAULT 300,
                height INTEGER DEFAULT 200,
                rotation INTEGER DEFAULT 0,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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

        # 创建数据库操作日志表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS database_operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                operation_details TEXT,
                status TEXT NOT NULL,
                execution_time REAL,
                affected_rows INTEGER DEFAULT 0,
                error_message TEXT,
                operator TEXT DEFAULT 'system',
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
        conn.execute('CREATE INDEX IF NOT EXISTS idx_rack_layouts_rack ON rack_layouts(rack)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_db_operation_logs_type ON database_operation_logs(operation_type)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_db_operation_logs_date ON database_operation_logs(created_date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_db_operation_logs_status ON database_operation_logs(status)')


def get_rack_layout(rack):
    """获取货架布局"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM rack_layouts WHERE rack = ?', (rack,))
        result = cursor.fetchone()
        if result:
            return {
                'rack': result[0],
                'x': result[1],
                'y': result[2],
                'width': result[3],
                'height': result[4],
                'rotation': result[5]
            }
        return None


def save_rack_layout(rack, layout_data):
    """保存货架布局"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO rack_layouts (rack, x, y, width, height, rotation, updated_date)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (rack, layout_data['x'], layout_data['y'], layout_data['width'],
              layout_data['height'], layout_data['rotation']))
        return True


def get_all_rack_layouts():
    """获取所有货架布局"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM rack_layouts')
        layouts = {}
        for row in cursor.fetchall():
            layouts[row[0]] = {
                'x': row[1],
                'y': row[2],
                'width': row[3],
                'height': row[4],
                'rotation': row[5]
            }
        return layouts


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
    """获取所有备件列表 - 修复 None 值问题"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM spare_parts ORDER BY part_no')
        results = cursor.fetchall()

        # 确保所有数字字段都有有效值
        processed_results = []
        for part in results:
            if hasattr(part, '_fields'):  # sqlite3.Row 对象
                part_dict = {}
                for i, field in enumerate(part._fields):
                    value = part[i]
                    # 处理数值字段的 None 值
                    if field in ['current_stock', 'min_stock', 'max_stock', 'lt_weeks']:
                        value = value if value is not None else 0
                    elif field == 'unit_price':
                        value = value if value is not None else 0.0
                    elif field == 'key_part':
                        value = value if value is not None else False
                    part_dict[field] = value
                processed_results.append(part_dict)
            else:  # 元组格式
                part_list = list(part)
                # 确保关键字段不为None
                if len(part_list) > 4 and part_list[4] is None:  # current_stock
                    part_list[4] = 0
                if len(part_list) > 6 and part_list[6] is None:  # min_stock
                    part_list[6] = 0
                if len(part_list) > 7 and part_list[7] is None:  # max_stock
                    part_list[7] = 0
                if len(part_list) > 9 and part_list[9] is None:  # lt_weeks
                    part_list[9] = 0
                if len(part_list) > 10 and part_list[10] is None:  # unit_price
                    part_list[10] = 0.0
                processed_results.append(tuple(part_list))

        return processed_results


def create_operation_record(operation_data):
    """创建操作记录 - 彻底修复字段保存版本"""
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

                # 确保所有字段都有值 - 彻底修复
                operation_type = operation_data.get('operation_type', 'Stock in')
                supplier_recipient = operation_data.get('supplier_recipient', '')
                location = operation_data.get('location', '')
                part_no = operation_data.get('part_no', '')
                description = operation_data.get('description', '')
                part_type = operation_data.get('part_type', '')
                product_model = operation_data.get('product_model', '')
                work_center = operation_data.get('work_center', '')

                # 使用当前时间作为操作日期
                operation_date = operation_data.get('operation_date', datetime.now())

                # 调试：打印要插入的数据
                logging.info(f"插入操作记录数据: operation_type={operation_type}, "
                             f"supplier_recipient={supplier_recipient}, location={location}, "
                             f"part_no={part_no}, quantity={quantity}")

                # 插入操作记录 - 确保所有字段都正确插入
                cursor = conn.execute('''
                    INSERT INTO operation_records 
                    (operation_type, operation_date, supplier_recipient, location, part_no, 
                     description, part_type, product_model, quantity, work_center, created_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    operation_type,
                    operation_date,
                    supplier_recipient,
                    location,
                    part_no,
                    description,
                    part_type,
                    product_model,
                    quantity,
                    work_center
                ))

                record_id = cursor.lastrowid

                # 重新计算并更新备件库存
                new_stock = calculate_stock_from_operations_with_connection(part_no, conn)

                # 更新备件库存
                conn.execute('''
                    UPDATE spare_parts 
                    SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                    WHERE part_no = ?
                ''', (new_stock, part_no))

                logging.info(f"操作记录创建成功: ID={record_id}, 备件={part_no}, "
                             f"供应商={supplier_recipient}, 数量={quantity}, 新库存={new_stock}")

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
        # 使用实时计算状态，确保数据准确
        cursor = conn.execute('SELECT part_count, capacity FROM locations')
        locations = cursor.fetchall()

        total_locations = len(locations)
        free_locations = 0
        in_use_locations = 0
        low_stock_locations = 0

        for location in locations:
            part_count = safe_int(location[0])
            capacity = safe_int(location[1])

            # 实时计算状态
            if capacity == 0:
                status = 'free'
            else:
                utilization = part_count / capacity
                if utilization == 0:
                    status = 'free'
                elif utilization < 0.3:
                    status = 'low_stock'
                else:
                    status = 'in_use'

            if status == 'free':
                free_locations += 1
            elif status == 'in_use':
                in_use_locations += 1
            elif status == 'low_stock':
                low_stock_locations += 1

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


def get_accurate_location_stats():
    """获取准确的库位统计信息 - 优化版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT 
                COUNT(*) as total_locations,
                SUM(CASE WHEN part_count > 0 THEN 1 ELSE 0 END) as in_use_locations,
                SUM(CASE WHEN part_count = 0 THEN 1 ELSE 0 END) as not_use_locations
            FROM locations
        ''')
        result = cursor.fetchone()

        if result:
            return {
                'total_locations': result[0] or 0,
                'in_use_locations': result[1] or 0,
                'not_use_locations': result[2] or 0
            }
        return {
            'total_locations': 0,
            'in_use_locations': 0,
            'not_use_locations': 0
        }


def calculate_location_status(part_count, capacity, current_stock=0, min_stock=0, max_stock=0):
    """计算库位状态 - 优化版本"""
    # 如果库位没有分配给任何备件存储
    if part_count == 0:
        return 'not_use'

    # 如果库位分配了备件存储
    if current_stock == 0:
        return 'out_of_stock'  # 缺货
    elif current_stock <= min_stock:
        return 'low_stock'  # 低库存
    elif max_stock > 0 and current_stock > max_stock:
        return 'high_stock'  # 库存过高
    else:
        return 'free'  # 库存充足


def update_location_status_by_part(part_no):
    """根据备件信息更新相关库位状态"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 获取备件信息
        cursor = conn.execute('''
            SELECT location, current_stock, min_stock, max_stock 
            FROM spare_parts 
            WHERE part_no = ?
        ''', (part_no,))
        part = cursor.fetchone()

        if part and part['location']:
            location_code = part['location']
            current_stock = safe_int(part['current_stock'])
            min_stock = safe_int(part['min_stock'])
            max_stock = safe_int(part['max_stock'])

            # 计算新的状态
            new_status = calculate_location_status(1, 0, current_stock, min_stock, max_stock)

            # 更新库位状态
            conn.execute('''
                UPDATE locations 
                SET status = ?, last_updated = CURRENT_TIMESTAMP 
                WHERE location_code = ?
            ''', (new_status, location_code))

            return True
    return False


def batch_update_location_statuses():
    """批量更新所有库位状态"""
    db_manager = DatabaseManager()
    updated_count = 0

    with db_manager.get_connection() as conn:
        # 获取所有库位及其关联的备件信息
        cursor = conn.execute('''
            SELECT l.location_code, l.part_count,
                   COALESCE(SUM(p.current_stock), 0) as total_stock,
                   COALESCE(MIN(p.min_stock), 0) as min_stock,
                   COALESCE(MAX(p.max_stock), 0) as max_stock
            FROM locations l
            LEFT JOIN spare_parts p ON l.location_code = p.location
            GROUP BY l.location_code, l.part_count
        ''')

        locations = cursor.fetchall()

        for location in locations:
            location_code = location['location_code']
            part_count = safe_int(location['part_count'])
            total_stock = safe_int(location['total_stock'])
            min_stock = safe_int(location['min_stock'])
            max_stock = safe_int(location['max_stock'])

            # 计算新的状态
            if part_count == 0:
                new_status = 'not_use'
            else:
                new_status = calculate_location_status(part_count, 0, total_stock, min_stock, max_stock)

            # 更新库位状态
            cursor = conn.execute('''
                UPDATE locations 
                SET status = ?, last_updated = CURRENT_TIMESTAMP 
                WHERE location_code = ?
            ''', (new_status, location_code))

            if cursor.rowcount > 0:
                updated_count += 1

        conn.commit()

    return updated_count


def get_rack_statistics():
    """获取货架统计信息 - 优化版本"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT 
                rack,
                COUNT(*) as total_locations,
                SUM(CASE WHEN part_count > 0 THEN 1 ELSE 0 END) as in_use_locations,
                SUM(CASE WHEN part_count = 0 THEN 1 ELSE 0 END) as not_use_locations,
                SUM(part_count) as total_parts,
                SUM(capacity) as total_capacity
            FROM locations 
            WHERE rack IS NOT NULL AND rack != ''
            GROUP BY rack
        ''')

        rack_stats = {}
        for row in cursor.fetchall():
            rack = row[0]
            total_locations = row[1] or 0
            in_use_locations = row[2] or 0
            not_use_locations = row[3] or 0
            total_parts = row[4] or 0
            total_capacity = row[5] or 0

            utilization = (total_parts / total_capacity * 100) if total_capacity > 0 else 0

            rack_stats[rack] = {
                'total_locations': total_locations,
                'in_use_locations': in_use_locations,
                'not_use_locations': not_use_locations,
                'total_parts': total_parts,
                'total_capacity': total_capacity,
                'utilization': utilization
            }

        return rack_stats


def safe_float(value, default=0.0):
    """安全转换为浮点数"""
    if value is None or value == '':
        return default
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return default


def log_database_operation(operation_type, operation_details, status, execution_time=None, affected_rows=0,
                           error_message=None, operator='system'):
    """记录数据库操作日志"""
    db_manager = DatabaseManager()
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO database_operation_logs 
                (operation_type, operation_details, status, execution_time, affected_rows, error_message, operator)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                operation_type,
                operation_details,
                status,
                execution_time,
                affected_rows,
                error_message,
                operator
            ))
            return cursor.lastrowid
    except Exception as e:
        logging.error(f"记录数据库操作日志失败: {str(e)}")
        return None


def get_database_operation_logs(limit=50, operation_type=None):
    """获取数据库操作日志"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        query = '''
            SELECT * FROM database_operation_logs 
            WHERE 1=1
        '''
        params = []

        if operation_type:
            query += ' AND operation_type = ?'
            params.append(operation_type)

        query += ' ORDER BY created_date DESC LIMIT ?'
        params.append(limit)

        cursor = conn.execute(query, params)
        logs = []
        for row in cursor.fetchall():
            if hasattr(row, '_fields'):
                log_dict = {}
                for i, field in enumerate(row._fields):
                    log_dict[field] = row[i]
                logs.append(log_dict)
            else:
                logs.append({
                    'id': row[0],
                    'operation_type': row[1],
                    'operation_details': row[2],
                    'status': row[3],
                    'execution_time': row[4],
                    'affected_rows': row[5],
                    'error_message': row[6],
                    'operator': row[7],
                    'created_date': row[8]
                })
        return logs


def perform_integrity_check():
    """执行数据库完整性检查"""
    db_manager = DatabaseManager()
    start_time = time.time()

    try:
        with db_manager.get_connection() as conn:
            # 执行完整性检查
            cursor = conn.execute('PRAGMA integrity_check')
            result = cursor.fetchall()

            # 检查外键约束
            cursor = conn.execute('PRAGMA foreign_key_check')
            foreign_key_errors = cursor.fetchall()

            # 检查页大小和扇区大小
            cursor = conn.execute('PRAGMA page_size')
            page_size = cursor.fetchone()[0]

            cursor = conn.execute('PRAGMA page_count')
            page_count = cursor.fetchone()[0]

            execution_time = time.time() - start_time

            # 记录操作日志
            log_database_operation(
                operation_type='integrity_check',
                operation_details='执行数据库完整性检查',
                status='success',
                execution_time=execution_time,
                affected_rows=0
            )

            return {
                'success': True,
                'integrity_check': result,
                'foreign_key_errors': foreign_key_errors,
                'page_size': page_size,
                'page_count': page_count,
                'database_size': page_size * page_count,
                'execution_time': execution_time
            }

    except Exception as e:
        execution_time = time.time() - start_time
        log_database_operation(
            operation_type='integrity_check',
            operation_details='执行数据库完整性检查',
            status='error',
            execution_time=execution_time,
            error_message=str(e)
        )
        return {
            'success': False,
            'error': str(e),
            'execution_time': execution_time
        }


def perform_performance_analysis():
    """执行数据库性能分析"""
    db_manager = DatabaseManager()
    start_time = time.time()

    try:
        with db_manager.get_connection() as conn:
            stats = {}

            # 基础性能指标
            cursor = conn.execute('PRAGMA optimize')
            stats['optimize'] = cursor.fetchall()

            # 缓存统计
            cursor = conn.execute('PRAGMA cache_stats')
            stats['cache_stats'] = cursor.fetchall()

            # 编译选项
            cursor = conn.execute('PRAGMA compile_options')
            stats['compile_options'] = [row[0] for row in cursor.fetchall()]

            # 表统计信息
            cursor = conn.execute("""
                SELECT name, 
                       (SELECT COUNT(*) FROM sqlite_master WHERE type='table') as table_count,
                       (SELECT COUNT(*) FROM sqlite_master WHERE type='index') as index_count,
                       (SELECT COUNT(*) FROM sqlite_master WHERE type='trigger') as trigger_count
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            stats['schema_info'] = cursor.fetchall()

            # 索引使用统计（需要SQLite 3.9.0+）
            try:
                cursor = conn.execute('PRAGMA index_list(sqlite_master)')
                stats['index_list'] = cursor.fetchall()
            except:
                stats['index_list'] = []

            # 数据库大小信息
            cursor = conn.execute('PRAGMA page_size')
            page_size = cursor.fetchone()[0]
            cursor = conn.execute('PRAGMA page_count')
            page_count = cursor.fetchone()[0]
            cursor = conn.execute('PRAGMA freelist_count')
            freelist_count = cursor.fetchone()[0]

            stats['size_info'] = {
                'page_size': page_size,
                'page_count': page_count,
                'freelist_count': freelist_count,
                'total_size': page_size * page_count,
                'used_size': page_size * (page_count - freelist_count),
                'usage_percentage': ((page_count - freelist_count) / page_count * 100) if page_count > 0 else 0
            }

            # 性能建议
            suggestions = []
            if stats['size_info']['usage_percentage'] < 70:
                suggestions.append("数据库空间利用率较低，建议执行VACUUM优化")
            if freelist_count > page_count * 0.3:
                suggestions.append("空闲页面较多，建议执行VACUUM回收空间")

            stats['suggestions'] = suggestions
            execution_time = time.time() - start_time

            # 记录操作日志
            log_database_operation(
                operation_type='performance_analysis',
                operation_details='执行数据库性能分析',
                status='success',
                execution_time=execution_time,
                affected_rows=0
            )

            return {
                'success': True,
                'stats': stats,
                'execution_time': execution_time
            }

    except Exception as e:
        execution_time = time.time() - start_time
        log_database_operation(
            operation_type='performance_analysis',
            operation_details='执行数据库性能分析',
            status='error',
            execution_time=execution_time,
            error_message=str(e)
        )
        return {
            'success': False,
            'error': str(e),
            'execution_time': execution_time
        }


def vacuum_database():
    """执行数据库VACUUM操作"""
    db_manager = DatabaseManager()
    start_time = time.time()

    try:
        with db_manager.get_connection() as conn:
            # 执行VACUUM前记录大小
            cursor = conn.execute('PRAGMA page_size')
            old_page_size = cursor.fetchone()[0]
            cursor = conn.execute('PRAGMA page_count')
            old_page_count = cursor.fetchone()[0]
            old_size = old_page_size * old_page_count

            # 执行VACUUM
            conn.execute('VACUUM')

            # 执行VACUUM后记录大小
            cursor = conn.execute('PRAGMA page_size')
            new_page_size = cursor.fetchone()[0]
            cursor = conn.execute('PRAGMA page_count')
            new_page_count = cursor.fetchone()[0]
            new_size = new_page_size * new_page_count

            execution_time = time.time() - start_time

            # 记录操作日志
            log_database_operation(
                operation_type='vacuum',
                operation_details=f'执行数据库VACUUM优化，大小从 {old_size} 字节优化到 {new_size} 字节',
                status='success',
                execution_time=execution_time,
                affected_rows=0
            )

            return {
                'success': True,
                'old_size': old_size,
                'new_size': new_size,
                'reclaimed_space': old_size - new_size,
                'execution_time': execution_time
            }

    except Exception as e:
        execution_time = time.time() - start_time
        log_database_operation(
            operation_type='vacuum',
            operation_details='执行数据库VACUUM优化',
            status='error',
            execution_time=execution_time,
            error_message=str(e)
        )
        return {
            'success': False,
            'error': str(e),
            'execution_time': execution_time
        }


# [file content end]