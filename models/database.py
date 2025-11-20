import sqlite3
import os
import logging
from contextlib import contextmanager

class DatabaseManager:
    """数据库管理器，负责数据库连接和操作"""
    
    def __init__(self, db_path='spare_parts.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库连接池和性能优化"""
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # 配置SQLite性能优化参数
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = 10000")
            conn.execute("PRAGMA temp_store = MEMORY")
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
        else:
            conn.commit()
        finally:
            conn.close()

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

        # 创建库位表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                location_code TEXT PRIMARY KEY,
                description TEXT,
                status TEXT DEFAULT 'free',
                part_count INTEGER DEFAULT 0,
                capacity INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引以提高查询性能
        # 为备件表创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_location ON spare_parts(location)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_type ON spare_parts(type)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_stock ON spare_parts(current_stock, min_stock)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spare_parts_part_no ON spare_parts(part_no)')

        # 为操作记录表创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_date ON operation_records(operation_date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_records_part_no ON operation_records(part_no)')

        # 为库位表创建索引
        conn.execute('CREATE INDEX IF NOT EXISTS idx_locations_status ON locations(status)')

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
    """创建新备件"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO spare_parts 
            (part_no, name, type, current_stock, min_stock, max_stock, key_part, 
             lt_weeks, unit_price, unit, location, supplier, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            part_data['part_no'], part_data['name'], part_data.get('type', ''),
            part_data.get('current_stock', 0), part_data.get('min_stock', 0),
            part_data.get('max_stock', 0), part_data.get('key_part', False),
            part_data.get('lt_weeks', 0), part_data.get('unit_price', 0.0),
            part_data.get('unit', ''), part_data.get('location', ''),
            part_data.get('supplier', ''), part_data.get('description', '')
        ))
        return cursor.lastrowid

def update_spare_part(part_id, part_data):
    """更新备件信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 构建动态更新语句
        fields = []
        values = []
        for key, value in part_data.items():
            if key != 'id':  # 排除ID字段
                fields.append(f"{key} = ?")
                values.append(value)

        values.append(part_id)  # 添加WHERE条件值

        query = f"UPDATE spare_parts SET {', '.join(fields)} WHERE id = ?"
        cursor = conn.execute(query, values)
        return cursor.rowcount

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
    """创建操作记录"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO operation_records 
            (operation_type, supplier_recipient, location, part_no, description, 
             part_type, quantity, work_center)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            operation_data['operation_type'], operation_data.get('supplier_recipient', ''),
            operation_data.get('location', ''), operation_data['part_no'],
            operation_data['description'], operation_data.get('part_type', ''),
            operation_data['quantity'], operation_data.get('work_center', '')
        ))
        return cursor.lastrowid

def create_location(location_data):
    """创建新库位"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO locations 
            (location_code, description, status, part_count, capacity)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            location_data['location_code'],
            location_data.get('description', ''),
            location_data.get('status', 'free'),
            location_data.get('part_count', 0),
            location_data.get('capacity', 0)
        ))
        return cursor.lastrowid

def get_location_by_code(location_code):
    """根据库位代码获取库位信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('SELECT * FROM locations WHERE location_code = ?', (location_code,))
        return cursor.fetchone()

def update_location(location_code, location_data):
    """更新库位信息"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 构建动态更新语句
        fields = []
        values = []
        for key, value in location_data.items():
            if key != 'location_code':  # 排除主键字段
                fields.append(f"{key} = ?")
                values.append(value)

        values.append(location_code)  # 添加WHERE条件值

        query = f"UPDATE locations SET {', '.join(fields)} WHERE location_code = ?"
        cursor = conn.execute(query, values)
        return cursor.rowcount

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

def calculate_location_status(part_count, capacity):
    """计算库位状态"""
    if part_count == 0:
        return 'free'
    elif capacity > 0 and part_count / capacity >= 0.8:
        return 'low_stock'
    else:
        return 'in_use'
