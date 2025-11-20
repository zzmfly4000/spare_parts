from flask import session
import hashlib
import sqlite3
from models.database import DatabaseManager

class UserManager:
    """用户管理服务，负责用户认证和权限管理功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self._init_user_table()
    
    def _init_user_table(self):
        """初始化用户表"""
        with self.db_manager.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
    
    def hash_password(self, password):
        """密码哈希处理"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def authenticate_user(self, username, password):
        """用户身份验证"""
        password_hash = self.hash_password(password)
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT id, username, role FROM users 
                WHERE username = ? AND password_hash = ?
            ''', (username, password_hash))
            user = cursor.fetchone()
            
            if user:
                # 将用户信息存储到会话中
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[2]
                return True
        return False
    
    def logout_user(self):
        """用户注销"""
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('role', None)
    
    def is_logged_in(self):
        """检查用户是否已登录"""
        return 'user_id' in session
    
    def check_permission(self, required_role):
        """检查用户权限"""
        if not self.is_logged_in():
            return False
        
        user_role = session.get('role', 'user')
        # 简单的权限控制：admin角色可以访问所有功能
        if user_role == 'admin':
            return True
        # user角色只能访问基本功能
        return user_role == required_role
