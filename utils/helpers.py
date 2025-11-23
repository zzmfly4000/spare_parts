import pandas as pd
import numpy as np
from datetime import datetime
import re

def validate_excel_file(filename):
    """验证Excel文件类型"""
    allowed_extensions = {'xlsx', 'xls'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def safe_int(value, default=0):
    """安全转换为整数 - 增强版本"""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        # 处理浮点数
        if isinstance(value, float):
            return int(value)
        # 处理字符串
        if isinstance(value, str):
            # 移除可能存在的逗号（千位分隔符）
            value = value.replace(',', '')
            # 尝试直接转换
            return int(float(value))
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_float(value, default=0.0):
    """安全转换为浮点数 - 增强版本"""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        if isinstance(value, str):
            value = value.replace(',', '')
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_str(value, default=''):
    """安全转换为字符串 - 增强版本"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        result = str(value).strip()
        return result if result else default
    except:
        return default

def safe_datetime(value, default=None):
    """安全转换为日期时间 - 增强版本"""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # 尝试多种日期格式
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        # 使用pandas的日期解析作为后备
        return pd.to_datetime(value)
    except:
        return default

def clean_dataframe(df):
    """清理DataFrame数据 - 根据新的字段描述修正"""
    import time
    start_time = time.time()

    # 定义替换字典，用于将各种空值表示替换为空字符串
    replacement_dict = {
        'nan': '', 'None': '', 'null': '', 'NaN': '', 'NULL': '',
        'none': '', 'NONE': ''
    }

    # 删除全空行
    df = df.dropna(how='all')
    df = df.reset_index(drop=True)

    # 预处理关键字段：location（实际库位，不可为空）
    if 'location' in df.columns:
        df['location'] = df['location'].fillna('').astype(str).str.strip()
        df['location'] = df['location'].replace(replacement_dict)

    # 预处理其他可为空字段
    optional_fields = ['Rack', 'Level', 'Position', 'Side', 'State', 'Size Type', 'Description']
    for field in optional_fields:
        if field in df.columns:
            df[field] = df[field].fillna('').astype(str).str.strip()
            df[field] = df[field].replace(replacement_dict)

    # 预处理状态列
    if 'State' in df.columns:
        state_mapping = {
            '': 'free', 'nan': 'free', 'none': 'free', 'null': 'free',
            '空闲': 'free', '使用中': 'in_use', '低库存': 'low_stock',
            'free': 'free', 'in_use': 'in_use', 'low_stock': 'low_stock'
        }
        df['State'] = df['State'].map(state_mapping).fillna('free')

    # 预处理容量列
    if 'Capacity' in df.columns:
        df['Capacity'] = pd.to_numeric(df['Capacity'], errors='coerce').fillna(0)
        df['Capacity'] = df['Capacity'].clip(lower=0)

    end_time = time.time()

    return df