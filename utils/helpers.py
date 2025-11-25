# utils/helpers.py
import os
import datetime
from werkzeug.utils import secure_filename


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


def safe_str(value, default=''):
    """安全转换为字符串"""
    if value is None:
        return default
    try:
        return str(value)
    except:
        return default


def safe_datetime(value, default=None):
    """安全转换为 datetime 对象"""
    if value is None or value == '':
        return default

    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())

    if isinstance(value, str):
        try:
            # 尝试解析 ISO 格式
            if 'T' in value:
                return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                # 尝试其他常见格式
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%H:%M:%S']:
                    try:
                        return datetime.datetime.strptime(value, fmt)
                    except ValueError:
                        continue
        except Exception:
            pass

    return default


def parse_datetime(date_string):
    """解析日期字符串为 datetime 对象"""
    return safe_datetime(date_string)


def validate_excel_file(filename):
    """
    验证上传的文件是否为有效的 Excel 文件

    Args:
        filename (str): 上传的文件名

    Returns:
        bool: 是否为有效的 Excel 文件
    """
    if not filename:
        return False

    # 安全的文件名
    safe_name = secure_filename(filename)
    if not safe_name:
        return False

    # 允许的扩展名
    allowed_extensions = {'.xlsx', '.xls', '.xlsm'}

    # 获取文件扩展名
    _, ext = os.path.splitext(safe_name.lower())

    return ext in allowed_extensions


def validate_file_extension(filename, allowed_extensions=None):
    """
    验证文件扩展名

    Args:
        filename (str): 文件名
        allowed_extensions (set): 允许的扩展名集合

    Returns:
        bool: 扩展名是否有效
    """
    if allowed_extensions is None:
        allowed_extensions = {'.xlsx', '.xls', '.xlsm'}

    if not filename:
        return False

    safe_name = secure_filename(filename)
    if not safe_name:
        return False

    _, ext = os.path.splitext(safe_name.lower())
    return ext in allowed_extensions


def format_excel_date(excel_date_value):
    """
    格式化 Excel 日期值为 Python datetime

    Args:
        excel_date_value: Excel 日期值

    Returns:
        datetime: 格式化后的日期时间对象
    """
    if excel_date_value is None:
        return None

    # 如果已经是 datetime 对象，直接返回
    if isinstance(excel_date_value, datetime.datetime):
        return excel_date_value

    # 如果是日期对象，转换为 datetime
    if isinstance(excel_date_value, datetime.date):
        return datetime.datetime.combine(excel_date_value, datetime.time())

    # 如果是字符串，尝试解析
    if isinstance(excel_date_value, str):
        return safe_datetime(excel_date_value)

    # 如果是数字（Excel 日期序列号）
    try:
        # Excel 日期序列号（从 1900-01-01 开始）
        if isinstance(excel_date_value, (int, float)):
            # 简单处理：如果数字很大，可能是时间戳
            if excel_date_value > 100000:
                return datetime.datetime.fromtimestamp(excel_date_value)
            else:
                # Excel 日期序列号转换（简化版本）
                base_date = datetime.datetime(1899, 12, 30)
                delta = datetime.timedelta(days=excel_date_value)
                return base_date + delta
    except (ValueError, TypeError):
        pass

    return None


def clean_excel_value(value):
    """
    清理 Excel 单元格值

    Args:
        value: 原始单元格值

    Returns:
        清理后的值
    """
    if value is None:
        return None

    # 如果是字符串，去除前后空格
    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return None

    return value


def get_file_size(file_path):
    """
    获取文件大小（MB）

    Args:
        file_path (str): 文件路径

    Returns:
        float: 文件大小（MB）
    """
    try:
        size_bytes = os.path.getsize(file_path)
        return round(size_bytes / (1024 * 1024), 2)
    except OSError:
        return 0