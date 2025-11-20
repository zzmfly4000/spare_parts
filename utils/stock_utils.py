from models.database import DatabaseManager
import sqlite3

def calculate_stock_from_operations(part_no):
    """根据操作记录计算备件库存"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        # 计算总入库数量
        inbound_cursor = conn.execute('''
            SELECT SUM(quantity) FROM operation_records 
            WHERE part_no = ? AND quantity > 0
        ''', (part_no,))
        total_inbound = inbound_cursor.fetchone()[0] or 0
        
        # 计算总出库数量
        outbound_cursor = conn.execute('''
            SELECT SUM(ABS(quantity)) FROM operation_records 
            WHERE part_no = ? AND quantity < 0
        ''', (part_no,))
        total_outbound = outbound_cursor.fetchone()[0] or 0
        
        # 计算当前库存
        current_stock = total_inbound - total_outbound
        return max(0, current_stock)  # 确保库存不为负数

def update_stock_for_part(part_id, new_stock=None):
    """更新单个备件的库存数量"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        if new_stock is None:
            # 从操作记录重新计算库存
            part_cursor = conn.execute('SELECT part_no FROM spare_parts WHERE id = ?', (part_id,))
            part_no = part_cursor.fetchone()[0]
            new_stock = calculate_stock_from_operations(part_no)
        
        # 更新备件库存
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
        cursor = conn.execute('SELECT id, part_no FROM spare_parts')
        parts = cursor.fetchall()
        
        updated_count = 0
        for part_id, part_no in parts:
            # 计算并更新库存
            new_stock = calculate_stock_from_operations(part_no)
            update_cursor = conn.execute('''
                UPDATE spare_parts 
                SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (new_stock, part_id))
            if update_cursor.rowcount > 0:
                updated_count += 1
        
        return updated_count

def calculate_stock_status(current_stock, min_stock):
    """计算备件库存状态"""
    if current_stock == 0:
        return 'out_of_stock'  # 缺货
    elif current_stock <= min_stock:
        return 'low_stock'     # 低库存
    else:
        return 'normal'        # 正常

def is_low_stock(part_id):
    """判断备件是否处于低库存状态"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT current_stock, min_stock FROM spare_parts WHERE id = ?
        ''', (part_id,))
        result = cursor.fetchone()
        if result:
            current_stock, min_stock = result
            return current_stock <= min_stock
        return False

def get_low_stock_parts():
    """获取所有低库存备件列表"""
    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT * FROM spare_parts 
            WHERE current_stock <= min_stock 
            ORDER BY current_stock
        ''')
        return cursor.fetchall()
