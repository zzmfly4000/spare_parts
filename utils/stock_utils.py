from models.database import get_all_spare_parts, get_all_operation_records
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


def get_low_stock_parts():
    """获取所有低库存备件列表"""
    from models.database import get_low_stock_parts as db_get_low_stock
    return db_get_low_stock()


def get_recent_activities(limit=10):
    """获取最近活动记录"""
    operations = get_all_operation_records(limit=limit)
    recent_activities = []

    for op in operations:
        # op结构: (id, operation_type, operation_date, supplier_recipient, location, part_no, description, part_type, quantity, work_center, created_date)
        operation_type = op[1] if len(op) > 1 else 'Unknown'
        operation_date = op[2] if len(op) > 2 else datetime.now()
        description = op[6] if len(op) > 6 else '未知备件'
        quantity = op[8] if len(op) > 8 else 0

        # 处理日期格式
        if isinstance(operation_date, str):
            try:
                operation_date = datetime.strptime(operation_date, '%Y-%m-%d %H:%M:%S')
            except:
                operation_date = datetime.now()

        activity = {
            'type': 'inbound' if 'in' in operation_type.lower() else 'outbound',
            'part_name': description,
            'quantity': quantity,
            'time': operation_date.strftime('%H:%M') if isinstance(operation_date, datetime) else '未知',
            'operator': '系统'
        }
        recent_activities.append(activity)

    return recent_activities


def calculate_location_status(part_count, capacity):
    """计算库位状态"""
    if part_count == 0:
        return 'free'
    elif capacity > 0 and part_count >= capacity:
        return 'full'
    elif capacity > 0 and part_count / capacity >= 0.8:
        return 'low_stock'
    else:
        return 'in_use'