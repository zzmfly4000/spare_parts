# [file name]: stock_utils.py
# [file content begin]
from models.database import get_all_spare_parts, get_all_operation_records, safe_int
from datetime import datetime, timedelta


def calculate_stock_from_operations(part_no):
    """根据操作记录计算备件库存"""
    from models.database import calculate_stock_from_operations as db_calculate
    return db_calculate(part_no)


def update_stock_for_part(part_id, new_stock):
    """更新单个备件的库存数量"""
    from models.database import update_stock_for_part as db_update
    return db_update(part_id, new_stock)


def recalculate_all_stock():
    """重新计算所有备件的库存"""
    from models.database import recalculate_all_stock as db_recalculate
    return db_recalculate()


def calculate_stock_status(current_stock, min_stock):
    """计算备件库存状态"""
    current_stock = safe_int(current_stock)
    min_stock = safe_int(min_stock)

    if current_stock == 0:
        return 'out_of_stock'
    elif current_stock <= min_stock:
        return 'low_stock'
    else:
        return 'normal'


def is_low_stock(part_id):
    """判断备件是否处于低库存状态"""
    from models.database import is_low_stock as db_is_low_stock
    return db_is_low_stock(part_id)


def calculate_location_status(part_count, capacity, current_stock=0, min_stock=0, max_stock=0):
    """计算库位状态"""
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


def get_low_stock_parts():
    """获取低库存备件 - 修复版本"""
    from models.database import get_low_stock_parts as db_get_low_stock_parts
    return db_get_low_stock_parts()


def get_recent_activities(limit=10):
    """获取最近活动 - 修复版本"""
    from models.database import get_recent_activities as db_get_recent_activities
    return db_get_recent_activities(limit)


def calculate_rack_utilization(rack_locations):
    """计算货架利用率"""
    if not rack_locations:
        return 0

    total_capacity = sum(safe_int(loc.get('capacity', 0)) for loc in rack_locations)
    total_parts = sum(safe_int(loc.get('part_count', 0)) for loc in rack_locations)

    if total_capacity == 0:
        return 0

    return (total_parts / total_capacity) * 100


def get_location_utilization(location_code):
    """获取库位利用率"""
    from models.database import DatabaseManager, safe_int

    db_manager = DatabaseManager()
    with db_manager.get_connection() as conn:
        cursor = conn.execute('''
            SELECT l.capacity, COALESCE(SUM(p.current_stock), 0) as total_stock
            FROM locations l
            LEFT JOIN spare_parts p ON l.location_code = p.location
            WHERE l.location_code = ?
            GROUP BY l.capacity
        ''', (location_code,))

        result = cursor.fetchone()
        if result:
            capacity = safe_int(result['capacity'])
            total_stock = safe_int(result['total_stock'])

            if capacity > 0:
                return round((total_stock / capacity) * 100, 1)

        return 0