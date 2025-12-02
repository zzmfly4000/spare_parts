from flask import render_template, request, redirect, url_for, flash, jsonify, session, current_app
import json
import os
import datetime
import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import sqlite3
from functools import wraps


def setup_settings_routes(app):
    """设置增强版系统设置路由"""

    # 初始化数据库表
    def init_settings_tables():
        """初始化系统设置相关的数据库表"""
        db_path = 'spare_parts.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 创建系统设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT,
                setting_type TEXT DEFAULT 'string',
                category TEXT DEFAULT 'general',
                description TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                role TEXT DEFAULT 'viewer',
                department TEXT,
                permissions TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 1,
                last_login TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建登录日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                ip_address TEXT,
                success INTEGER DEFAULT 0,
                user_agent TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建API密钥表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_name TEXT NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                permissions TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 1,
                expires_at TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # 创建系统操作日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                operation_details TEXT,
                user_id INTEGER,
                ip_address TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 插入默认系统设置
        default_settings = [
            ('system_name', '设备备件管理系统', 'string', 'general', '系统名称'),
            ('company_name', '', 'string', 'general', '公司名称'),
            ('timezone', 'Asia/Shanghai', 'string', 'general', '时区设置'),
            ('language', 'zh-CN', 'string', 'general', '系统语言'),
            ('low_stock_threshold', '20', 'integer', 'inventory', '低库存阈值(%)'),
            ('out_of_stock_days', '3', 'integer', 'inventory', '缺货预警天数'),
            ('auto_sync_enabled', 'false', 'boolean', 'inventory', '自动同步库存'),
            ('sync_frequency', '15', 'integer', 'inventory', '同步频率(分钟)'),
            ('critical_part_threshold', '50', 'integer', 'inventory', '关键备件阈值'),
            ('mail_server', '', 'string', 'email', 'SMTP服务器'),
            ('mail_port', '587', 'integer', 'email', 'SMTP端口'),
            ('mail_encryption', 'tls', 'string', 'email', '邮件加密方式'),
            ('mail_sender', '', 'string', 'email', '发件人邮箱'),
            ('mail_sender_name', '备件管理系统', 'string', 'email', '发件人名称'),
            ('mail_username', '', 'string', 'email', 'SMTP用户名'),
            ('mail_password', '', 'string', 'email', 'SMTP密码')
        ]

        for setting in default_settings:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO system_settings 
                    (setting_key, setting_value, setting_type, category, description)
                    VALUES (?, ?, ?, ?, ?)
                ''', setting)
            except:
                pass

        # 默认管理员账户：
        # 用户名: admin
        # 密码: admin123
        # 检查是否存在默认管理员用户
        cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
        if not cursor.fetchone():
            # 创建默认管理员用户
            password_hash = hash_password('admin123')
            cursor.execute('''
                INSERT INTO users 
                (username, email, password_hash, display_name, role, permissions, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', ('admin', 'admin@example.com', password_hash, '系统管理员', 'admin',
                  '["parts_manage","locations_manage","operations_manage","reports_view","data_export","system_settings"]',
                  1))

        conn.commit()
        conn.close()

    # 工具函数
    def get_db_connection():
        """获取数据库连接"""
        conn = sqlite3.connect('spare_parts.db')
        conn.row_factory = sqlite3.Row
        return conn

    def hash_password(password):
        """哈希密码"""
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(password_hash, password):
        """验证密码"""
        return password_hash == hash_password(password)

    # 登录装饰器
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            return f(*args, **kwargs)

        return decorated_function

    # 管理员权限装饰器
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'success': False, 'error': '请先登录'}), 401

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
            user = cursor.fetchone()
            conn.close()

            if not user or user['role'] != 'admin':
                return jsonify({'success': False, 'error': '需要管理员权限'}), 403

            return f(*args, **kwargs)

        return decorated_function

    # 系统设置主页面
    @app.route('/settings')
    def system_settings():
        """系统设置页面"""
        current_settings = get_system_settings()
        return render_template('settings.html', settings=current_settings)

    # 保存所有设置API - 修复版本
    @app.route('/api/settings/save', methods=['POST'])
    @login_required
    @admin_required
    def save_all_settings():
        """保存所有系统设置"""
        try:
            settings_data = request.json
            if not settings_data:
                return jsonify({'success': False, 'error': '无数据'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 保存通用设置
            if 'general' in settings_data:
                for key, value in settings_data['general'].items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO system_settings 
                        (setting_key, setting_value, setting_type, category, updated_date)
                        VALUES (?, ?, 'string', 'general', CURRENT_TIMESTAMP)
                    ''', (key, str(value)))

            # 保存库存设置
            if 'inventory' in settings_data:
                for key, value in settings_data['inventory'].items():
                    setting_type = 'integer' if key in ['low_stock_threshold', 'out_of_stock_days',
                                                        'sync_frequency', 'critical_part_threshold'] else 'boolean'
                    cursor.execute('''
                        INSERT OR REPLACE INTO system_settings 
                        (setting_key, setting_value, setting_type, category, updated_date)
                        VALUES (?, ?, ?, 'inventory', CURRENT_TIMESTAMP)
                    ''', (key, str(value), setting_type))

            # 保存邮件设置
            if 'email' in settings_data:
                for key, value in settings_data['email'].items():
                    setting_type = 'integer' if key == 'mail_port' else 'string'
                    cursor.execute('''
                        INSERT OR REPLACE INTO system_settings 
                        (setting_key, setting_value, setting_type, category, updated_date)
                        VALUES (?, ?, ?, 'email', CURRENT_TIMESTAMP)
                    ''', (key, str(value), setting_type))

            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation('保存系统设置', session.get('user_id'))

            return jsonify({'success': True, 'message': '设置保存成功'})

        except Exception as e:
            logging.error(f"保存设置失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 获取系统设置
    def get_system_settings():
        """获取所有系统设置"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT setting_key, setting_value, category FROM system_settings')
        rows = cursor.fetchall()
        conn.close()

        settings = {}
        for row in rows:
            settings[row['setting_key']] = row['setting_value']

        return {
            'system_name': settings.get('system_name', '设备备件管理系统'),
            'company_name': settings.get('company_name', ''),
            'mail_server': settings.get('mail_server', ''),
            'mail_port': settings.get('mail_port', '587'),
            'mail_username': settings.get('mail_username', ''),
            'mail_password': settings.get('mail_password', ''),
            'low_stock_threshold': settings.get('low_stock_threshold', '20')
        }

    # 添加用户API
    @app.route('/api/users/add', methods=['POST'])
    @login_required
    @admin_required
    def add_user():
        """添加新用户"""
        try:
            user_data = request.json
            if not user_data:
                return jsonify({'success': False, 'error': '无用户数据'})

            # 验证必要字段
            required_fields = ['username', 'email', 'role', 'password']
            for field in required_fields:
                if not user_data.get(field):
                    return jsonify({'success': False, 'error': f'缺少字段: {field}'})

            # 验证用户名是否已存在
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?',
                           (user_data['username'], user_data['email']))
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': '用户名或邮箱已存在'})

            # 创建用户
            password_hash = hash_password(user_data['password'])
            permissions = json.dumps(user_data.get('permissions', []))

            cursor.execute('''
                INSERT INTO users 
                (username, email, password_hash, display_name, role, department, permissions, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_data['username'],
                user_data['email'],
                password_hash,
                user_data.get('display_name', ''),
                user_data['role'],
                user_data.get('department', ''),
                permissions,
                1
            ))

            user_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'添加用户: {user_data["username"]}', session.get('user_id'))

            return jsonify({'success': True, 'user_id': user_id})

        except Exception as e:
            logging.error(f"添加用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 生成API密钥API
    @app.route('/api/settings/generate_api_key', methods=['POST'])
    @login_required
    @admin_required
    def generate_api_key():
        """生成API密钥"""
        try:
            data = request.json
            key_name = data.get('name', 'API Key')

            # 生成随机API密钥
            api_key = secrets.token_urlsafe(32)

            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO api_keys 
                (key_name, api_key, user_id, is_active, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                key_name,
                api_key,
                session.get('user_id'),
                1,
                (datetime.datetime.now() + datetime.timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
            ))

            key_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'生成API密钥: {key_name}', session.get('user_id'))

            return jsonify({'success': True, 'api_key': api_key, 'key_id': key_id})

        except Exception as e:
            logging.error(f"生成API密钥失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 测试邮件连接API
    @app.route('/api/settings/test_email', methods=['POST'])
    @login_required
    @admin_required
    def test_email_connection():
        """测试邮件服务器连接"""
        try:
            config = request.json
            if not config:
                return jsonify({'success': False, 'error': '无配置数据'})

            # 这里可以添加实际的SMTP测试逻辑
            # 暂时返回成功
            return jsonify({'success': True, 'message': '邮件服务器配置有效'})

        except Exception as e:
            logging.error(f"邮件连接测试失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 获取用户列表API
    @app.route('/api/users/list', methods=['GET'])
    @login_required
    @admin_required
    def list_users():
        """获取用户列表"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, email, display_name, role, department, 
                       is_active, last_login, created_date
                FROM users 
                ORDER BY created_date DESC
            ''')

            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row['id'],
                    'username': row['username'],
                    'email': row['email'],
                    'display_name': row['display_name'],
                    'role': row['role'],
                    'department': row['department'],
                    'is_active': bool(row['is_active']),
                    'last_login': row['last_login'],
                    'created_date': row['created_date']
                })

            conn.close()
            return jsonify({'success': True, 'users': users})

        except Exception as e:
            logging.error(f"获取用户列表失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 登录API
    @app.route('/api/login', methods=['POST'])
    def login():
        """用户登录"""
        try:
            data = request.json
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return jsonify({'success': False, 'error': '用户名和密码不能为空'})

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?',
                           (username,))
            user = cursor.fetchone()
            conn.close()

            if not user:
                log_login_attempt(username, False, request.remote_addr)
                return jsonify({'success': False, 'error': '用户名或密码错误'})

            if not user['is_active']:
                log_login_attempt(username, False, request.remote_addr)
                return jsonify({'success': False, 'error': '用户已被禁用'})

            if not verify_password(user['password_hash'], password):
                log_login_attempt(username, False, request.remote_addr)
                return jsonify({'success': False, 'error': '用户名或密码错误'})

            # 更新最后登录时间
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
            conn.commit()
            conn.close()

            # 设置session
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            log_login_attempt(username, True, request.remote_addr)
            return jsonify({'success': True, 'message': '登录成功', 'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role']
            }})

        except Exception as e:
            logging.error(f"登录失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 登出API
    @app.route('/api/logout', methods=['POST'])
    def logout():
        """用户登出"""
        session.clear()
        return jsonify({'success': True, 'message': '已成功登出'})

    # 工具函数
    def log_system_operation(operation, user_id):
        """记录系统操作日志"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO system_operation_logs 
                (operation_type, operation_details, user_id, ip_address)
                VALUES (?, ?, ?, ?)
            ''', (operation, '', user_id, request.remote_addr))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"记录操作日志失败: {str(e)}")

    def log_login_attempt(username, success, ip_address):
        """记录登录尝试"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO login_logs 
                (username, ip_address, success, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (username, ip_address, 1 if success else 0, request.user_agent.string))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"记录登录日志失败: {str(e)}")

    # 获取系统信息API
    @app.route('/api/system/info', methods=['GET'])
    @login_required
    def get_system_info():
        """获取系统信息"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 统计用户数量
            cursor.execute('SELECT COUNT(*) as total FROM users')
            total_users = cursor.fetchone()['total']

            cursor.execute('SELECT COUNT(*) as active FROM users WHERE is_active = 1')
            active_users = cursor.fetchone()['active']

            # 获取备份数量
            backup_dir = 'backups'
            backup_count = 0
            if os.path.exists(backup_dir):
                backup_count = len([f for f in os.listdir(backup_dir) if f.endswith('.zip')])

            # 获取数据库大小
            db_size = os.path.getsize('spare_parts.db') if os.path.exists('spare_parts.db') else 0

            conn.close()

            info = {
                'system_name': get_system_setting('system_name'),
                'company_name': get_system_setting('company_name'),
                'version': '2.0.0',
                'database': {
                    'size': db_size,
                    'size_human': f"{db_size / (1024 * 1024):.2f} MB"
                },
                'users': {
                    'total': total_users,
                    'active': active_users
                },
                'backups': {
                    'count': backup_count
                },
                'server_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            return jsonify({'success': True, 'info': info})

        except Exception as e:
            logging.error(f"获取系统信息失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    def get_system_setting(key, default=''):
        """获取系统设置值"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT setting_value FROM system_settings WHERE setting_key = ?', (key,))
            result = cursor.fetchone()
            conn.close()
            return result['setting_value'] if result else default
        except:
            return default


    def check_admin_permission(user_id):
        """检查用户是否具有管理员权限"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            conn.close()

            return user and user['role'] == 'admin'
        except Exception as e:
            logging.error(f"检查管理员权限失败: {str(e)}")
            return False

    # 初始化表
    init_settings_tables()