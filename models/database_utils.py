import sqlite3
import os
import logging
from datetime import datetime


def optimize_database(db_path='spare_parts.db'):
    """优化数据库性能"""
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)

        # 执行优化命令
        conn.execute("PRAGMA optimize")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")

        conn.close()
        logging.info("数据库优化完成")
        return True
    except Exception as e:
        logging.error(f"数据库优化失败: {str(e)}")
        return False


def check_database_health(db_path='spare_parts.db'):
    """检查数据库健康状态"""
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)

        # 检查表状态
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

        health_info = {
            'table_count': len(tables),
            'tables': [table[0] for table in tables],
            'integrity_check': True,
            'file_size': os.path.getsize(db_path) if os.path.exists(db_path) else 0
        }

        # 完整性检查
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            health_info['integrity_check'] = integrity[0] == 'ok'
        except:
            health_info['integrity_check'] = False

        conn.close()
        return health_info
    except Exception as e:
        logging.error(f"数据库健康检查失败: {str(e)}")
        return None