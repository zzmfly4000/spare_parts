"""辅助函数模块"""

def safe_int(value, default=0):
    """安全转换为整数"""
    try:
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default

def safe_str(value, default=''):
    """安全转换为字符串"""
    try:
        if value is None:
            return default
        return str(value).strip()
    except:
        return default

def safe_float(value, default=0.0):
    """安全转换为浮点数"""
    try:
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_datetime(value):
    """安全转换为日期时间"""
    from datetime import datetime
    try:
        if value is None:
            return None
        if isinstance(value, str):
            return datetime.strptime(value, '%Y-%m-%d')
        return value
    except:
        return None

def validate_excel_file(filename):
    """验证Excel文件"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}