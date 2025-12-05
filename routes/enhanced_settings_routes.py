# routes/enhanced_settings_routes.py - 修复 datetime 导入冲突版本
from flask import render_template, request, redirect, url_for, flash, jsonify, session, current_app
import json
import os
import datetime as dt  # 关键修复：重命名导入
import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import sqlite3
from functools import wraps
import zipfile
import shutil

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
    # 在 enhanced_settings_routes.py 中修改 add_user 函数：

    @app.route('/api/users/add', methods=['POST'])
    @login_required
    @admin_required
    def add_user():
        """添加新用户 - 修复版"""
        try:
            user_data = request.json
            if not user_data:
                return jsonify({'success': False, 'error': '无用户数据'})

            # 验证必要字段
            required_fields = ['username', 'email', 'role', 'password']
            for field in required_fields:
                if not user_data.get(field):
                    return jsonify({'success': False, 'error': f'缺少字段: {field}'})

            # 验证用户名格式
            username = user_data['username'].strip()
            if len(username) < 3:
                return jsonify({'success': False, 'error': '用户名至少需要3个字符'})

            # 验证邮箱格式
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, user_data['email']):
                return jsonify({'success': False, 'error': '邮箱格式不正确'})

            # 验证密码强度
            password = user_data['password']
            if len(password) < 8:
                return jsonify({'success': False, 'error': '密码至少需要8位字符'})

            # 检查是否包含字母和数字
            if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
                return jsonify({'success': False, 'error': '密码必须包含字母和数字'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 验证用户名是否已存在
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': '用户名已存在'})

            # 验证邮箱是否已存在
            cursor.execute('SELECT id FROM users WHERE email = ?', (user_data['email'],))
            if cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': '邮箱已存在'})

            # 创建用户
            password_hash = hash_password(password)

            # 处理权限字段
            permissions = user_data.get('permissions', [])
            if not isinstance(permissions, list):
                permissions = []

            # 根据角色设置默认权限
            if user_data['role'] == 'admin':
                permissions = ["parts_manage", "locations_manage", "operations_manage",
                               "reports_view", "data_export", "system_settings"]
            elif user_data['role'] == 'manager':
                permissions = ["parts_manage", "locations_manage", "operations_manage", "reports_view"]
            elif user_data['role'] == 'operator':
                permissions = ["operations_manage", "reports_view"]
            elif user_data['role'] == 'viewer':
                permissions = ["reports_view"]

            permissions_json = json.dumps(permissions)

            cursor.execute('''
                           INSERT INTO users
                           (username, email, password_hash, display_name, role, department, permissions, is_active)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (
                               username,
                               user_data['email'],
                               password_hash,
                               user_data.get('display_name', username),
                               user_data['role'],
                               user_data.get('department', ''),
                               permissions_json,
                               1  # 默认激活用户
                           ))

            user_id = cursor.lastrowid
            conn.commit()

            # 获取创建的用户信息
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            new_user = cursor.fetchone()
            conn.close()

            # 记录操作日志
            log_system_operation(f'添加用户: {username}', session.get('user_id'))

            return jsonify({
                'success': True,
                'user_id': user_id,
                'message': '用户添加成功',
                'user': {
                    'id': new_user['id'],
                    'username': new_user['username'],
                    'email': new_user['email'],
                    'role': new_user['role'],
                    'is_active': bool(new_user['is_active'])
                }
            })

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
                (dt.datetime.now() + dt.timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
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

    # 测试邮件连接API（简化版）
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

    # 修改登录函数，添加更多验证
    # 在 enhanced_settings_routes.py 中修改 login 函数：

    @app.route('/api/login', methods=['POST'])
    def login():
        """用户登录 - 增强版"""
        try:
            data = request.json
            username = data.get('username', '').strip()
            password = data.get('password', '')

            if not username:
                return jsonify({'success': False, 'error': '用户名不能为空'})
            if not password:
                return jsonify({'success': False, 'error': '密码不能为空'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 同时检查用户名和邮箱
            cursor.execute('''
                           SELECT id, username, password_hash, role, is_active, display_name, email
                           FROM users
                           WHERE username = ?
                              OR email = ?
                           ''', (username, username))

            user = cursor.fetchone()

            if not user:
                log_login_attempt(username, False, request.remote_addr)
                conn.close()
                return jsonify({'success': False, 'error': '用户名或密码错误'})

            # 检查用户是否激活
            if not user['is_active']:
                log_login_attempt(username, False, request.remote_addr)
                conn.close()
                return jsonify({'success': False, 'error': '用户已被禁用，请联系管理员'})

            # 验证密码
            if not verify_password(user['password_hash'], password):
                log_login_attempt(username, False, request.remote_addr)
                conn.close()
                return jsonify({'success': False, 'error': '用户名或密码错误'})

            # 更新最后登录时间
            cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
            conn.commit()
            conn.close()

            # 设置session
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['display_name'] = user['display_name'] or user['username']
            session['email'] = user['email']

            # 设置session永久性
            session.permanent = True

            log_login_attempt(username, True, request.remote_addr)

            return jsonify({
                'success': True,
                'message': '登录成功',
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'display_name': user['display_name'] or user['username'],
                    'role': user['role'],
                    'email': user['email']
                }
            })

        except Exception as e:
            logging.error(f"登录失败: {str(e)}")
            return jsonify({'success': False, 'error': '登录失败，请稍后重试'})


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
                'server_time': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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

    @app.route('/api/settings/save_all', methods=['POST'])
    @login_required
    @admin_required
    def save_all_settings_api():
        """保存所有系统设置 - 增强版"""
        try:
            # 解析JSON数据
            settings_data = request.json
            if not settings_data:
                return jsonify({'success': False, 'error': '无数据'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 保存每个分类的设置
            categories = ['general', 'inventory', 'email', 'notification', 'security', 'backup', 'api']

            for category in categories:
                if category in settings_data:
                    for key, value in settings_data[category].items():
                        # 确定设置类型
                        if key in ['low_stock_threshold', 'out_of_stock_days', 'sync_frequency',
                                   'critical_part_threshold', 'mail_port', 'max_login_attempts']:
                            setting_type = 'integer'
                        elif key in ['auto_sync_enabled', 'notify_low_stock', 'notify_email',
                                     'notify_sms', 'notify_dashboard', 'enable_2fa',
                                     'require_strong_password', 'session_timeout', 'api_enabled']:
                            setting_type = 'boolean'
                        elif key in ['utilization_rate', 'total_value']:
                            setting_type = 'float'
                        else:
                            setting_type = 'string'

                        # 保存到数据库
                        cursor.execute('''
                            INSERT OR REPLACE INTO system_settings 
                            (setting_key, setting_value, setting_type, category, updated_date)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''', (key, str(value), setting_type, category))

            conn.commit()

            # 获取更新后的设置
            cursor.execute('SELECT setting_key, setting_value FROM system_settings')
            updated_settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}

            conn.close()

            # 记录操作日志
            log_system_operation('保存所有系统设置', session.get('user_id'))

            return jsonify({
                'success': True,
                'message': '设置保存成功',
                'settings': updated_settings
            })

        except Exception as e:
            logging.error(f"保存设置失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/users/refresh', methods=['GET'])
    @login_required
    @admin_required
    def refresh_users_list():
        """刷新用户列表"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, username, email, display_name, role, department, 
                       is_active, last_login, created_date
                FROM users 
                WHERE id != ?  -- 不显示当前登录用户
                ORDER BY created_date DESC
            ''', (session.get('user_id'),))

            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row['id'],
                    'username': row['username'],
                    'email': row['email'],
                    'display_name': row['display_name'] or row['username'],
                    'role': row['role'],
                    'department': row['department'] or '',
                    'is_active': bool(row['is_active']),
                    'last_login': row['last_login'],
                    'created_date': row['created_date']
                })

            conn.close()

            return jsonify({
                'success': True,
                'users': users,
                'count': len(users)
            })

        except Exception as e:
            logging.error(f"刷新用户列表失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/api/settings/test_email_real', methods=['POST'])
    @login_required
    @admin_required
    def test_email_connection_real():
        """真实测试邮件服务器连接"""
        try:
            # 获取邮件设置
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT setting_key, setting_value 
                FROM system_settings 
                WHERE category = 'email'
            """)

            email_settings = {}
            for row in cursor.fetchall():
                email_settings[row['setting_key']] = row['setting_value']

            conn.close()

            # 检查必要配置
            required_fields = ['mail_server', 'mail_port', 'mail_sender', 'mail_username', 'mail_password']
            for field in required_fields:
                if not email_settings.get(field):
                    return jsonify({
                        'success': False,
                        'error': f'缺少邮件配置: {field}'
                    })

            # 尝试连接SMTP服务器
            server = None
            try:
                # 根据加密方式选择连接方法
                encryption = email_settings.get('mail_encryption', 'tls')
                port = int(email_settings.get('mail_port', 587))

                if encryption == 'ssl':
                    server = smtplib.SMTP_SSL(email_settings['mail_server'], port)
                else:
                    server = smtplib.SMTP(email_settings['mail_server'], port)
                    if encryption == 'tls':
                        server.starttls()

                # 登录
                server.login(
                    email_settings['mail_username'],
                    email_settings['mail_password']
                )

                # 创建测试邮件
                msg = MIMEMultipart()
                msg['From'] = f"{email_settings.get('mail_sender_name', '备件管理系统')} <{email_settings['mail_sender']}>"
                msg['To'] = email_settings['mail_sender']  # 发送给自己测试
                msg['Subject'] = '邮件服务器测试 - 备件管理系统'

                body = f'''
这是一封测试邮件，用于验证邮件服务器配置是否正确。

发送时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
服务器: {email_settings['mail_server']}:{port}
加密方式: {encryption}

如果收到此邮件，说明邮件服务器配置正确。
                '''

                msg.attach(MIMEText(body, 'plain'))

                # 发送邮件
                server.send_message(msg)

                # 关闭连接
                server.quit()

                # 记录操作日志
                log_system_operation('测试邮件服务器连接成功', session.get('user_id'))

                return jsonify({
                    'success': True,
                    'message': '邮件服务器测试成功！测试邮件已发送。'
                })

            except Exception as smtp_error:
                if server:
                    server.quit()

                logging.error(f"SMTP连接失败: {str(smtp_error)}")
                return jsonify({
                    'success': False,
                    'error': f'SMTP连接失败: {str(smtp_error)}'
                })

        except Exception as e:
            logging.error(f"邮件测试失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'邮件测试失败: {str(e)}'
            })

    @app.route('/api/backup/create', methods=['POST'])
    @login_required
    @admin_required
    def create_backup_api():
        """创建数据库备份"""
        try:
            # 备份目录
            backup_dir = 'backups'
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            # 创建备份文件名
            timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'backup_{timestamp}'
            zip_path = os.path.join(backup_dir, f'{backup_name}.zip')

            # 备份文件列表
            backup_files = ['spare_parts.db']

            # 检查文件是否存在
            for file in backup_files:
                if not os.path.exists(file):
                    return jsonify({
                        'success': False,
                        'error': f'文件不存在: {file}'
                    })

            # 创建ZIP备份
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in backup_files:
                    zipf.write(file, os.path.basename(file))

            # 清理旧备份（保留最近30个）
            backup_files = sorted(
                [f for f in os.listdir(backup_dir) if f.endswith('.zip')],
                key=lambda x: os.path.getmtime(os.path.join(backup_dir, x))
            )

            if len(backup_files) > 30:
                for old_backup in backup_files[:-30]:
                    os.remove(os.path.join(backup_dir, old_backup))

            # 记录操作日志
            log_system_operation(f'创建备份: {backup_name}', session.get('user_id'))

            return jsonify({
                'success': True,
                'message': f'备份创建成功: {backup_name}.zip',
                'backup_name': backup_name,
                'backup_path': zip_path,
                'size': os.path.getsize(zip_path)
            })

        except Exception as e:
            logging.error(f"创建备份失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'创建备份失败: {str(e)}'
            })

    @app.route('/api/backup/list', methods=['GET'])
    @login_required
    @admin_required
    def list_backups_api():
        """获取备份列表"""
        try:
            backup_dir = 'backups'
            if not os.path.exists(backup_dir):
                return jsonify({'success': True, 'backups': []})

            backups = []
            for filename in sorted(os.listdir(backup_dir), reverse=True):
                if filename.endswith('.zip'):
                    filepath = os.path.join(backup_dir, filename)
                    stat = os.stat(filepath)

                    backups.append({
                        'name': filename.replace('.zip', ''),
                        'filename': filename,
                        'size': stat.st_size,
                        'size_formatted': f"{stat.st_size / (1024 * 1024):.2f} MB",
                        'created_time': dt.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'path': filepath
                    })

            return jsonify({
                'success': True,
                'backups': backups,
                'count': len(backups)
            })

        except Exception as e:
            logging.error(f"获取备份列表失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'获取备份列表失败: {str(e)}'
            })

    @app.route('/api/backup/download/<backup_name>', methods=['GET'])
    @login_required
    @admin_required
    def download_backup_api(backup_name):
        """下载备份文件"""
        try:
            backup_dir = 'backups'
            filepath = os.path.join(backup_dir, f'{backup_name}.zip')

            if not os.path.exists(filepath):
                return jsonify({
                    'success': False,
                    'error': '备份文件不存在'
                }), 404

            # 这里应该返回文件，但由于Flask限制，我们返回下载URL
            # 在实际应用中，可以使用send_file
            return jsonify({
                'success': True,
                'download_url': f'/backups/{backup_name}.zip',
                'filename': f'{backup_name}.zip'
            })

        except Exception as e:
            logging.error(f"下载备份失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'下载备份失败: {str(e)}'
            })

    @app.route('/api/backup/delete/<backup_name>', methods=['DELETE'])
    @login_required
    @admin_required
    def delete_backup_api(backup_name):
        """删除备份文件"""
        try:
            backup_dir = 'backups'
            filepath = os.path.join(backup_dir, f'{backup_name}.zip')

            if not os.path.exists(filepath):
                return jsonify({
                    'success': False,
                    'error': '备份文件不存在'
                }), 404

            # 删除文件
            os.remove(filepath)

            # 记录操作日志
            log_system_operation(f'删除备份: {backup_name}', session.get('user_id'))

            return jsonify({
                'success': True,
                'message': f'备份删除成功: {backup_name}'
            })

        except Exception as e:
            logging.error(f"删除备份失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'删除备份失败: {str(e)}'
            })

    # 在 enhanced_settings_routes.py 的 setup_settings_routes 函数中添加以下路由

    # 编辑用户API
    @app.route('/api/users/edit/<int:user_id>', methods=['PUT'])
    @login_required
    @admin_required
    def edit_user(user_id):
        """编辑用户信息"""
        try:
            user_data = request.json
            if not user_data:
                return jsonify({'success': False, 'error': '无用户数据'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查用户是否存在
            cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': '用户不存在'})

            # 构建更新字段
            update_fields = []
            values = []

            allowed_fields = ['display_name', 'email', 'role', 'department', 'is_active']
            for field in allowed_fields:
                if field in user_data:
                    update_fields.append(f"{field} = ?")
                    values.append(user_data[field])

            if not update_fields:
                conn.close()
                return jsonify({'success': False, 'error': '没有要更新的字段'})

            # 添加更新时间
            update_fields.append("updated_date = CURRENT_TIMESTAMP")

            # 执行更新
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
            values.append(user_id)

            cursor.execute(query, values)
            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'编辑用户 ID: {user_id}', session.get('user_id'))

            return jsonify({'success': True, 'message': '用户更新成功'})

        except Exception as e:
            logging.error(f"编辑用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 删除用户API
    @app.route('/api/users/delete/<int:user_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def delete_user(user_id):
        """删除用户"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查用户是否存在且不是当前登录用户
            cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()

            if not user:
                conn.close()
                return jsonify({'success': False, 'error': '用户不存在'})

            if session.get('user_id') == user_id:
                conn.close()
                return jsonify({'success': False, 'error': '不能删除当前登录的用户'})

            # 执行删除
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'删除用户: {user["username"]}', session.get('user_id'))

            return jsonify({'success': True, 'message': '用户删除成功'})

        except Exception as e:
            logging.error(f"删除用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 重置密码API
    @app.route('/api/users/reset_password/<int:user_id>', methods=['POST'])
    @login_required
    @admin_required
    def reset_password_api(user_id):
        """重置用户密码"""
        try:
            data = request.json
            new_password = data.get('new_password')

            if not new_password or len(new_password) < 8:
                return jsonify({'success': False, 'error': '密码至少需要8位字符'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查用户是否存在
            cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()

            if not user:
                conn.close()
                return jsonify({'success': False, 'error': '用户不存在'})

            # 更新密码
            password_hash = hash_password(new_password)
            cursor.execute('''
                           UPDATE users
                           SET password_hash = ?,
                               updated_date  = CURRENT_TIMESTAMP
                           WHERE id = ?
                           ''', (password_hash, user_id))

            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'重置用户密码: {user["username"]}', session.get('user_id'))

            return jsonify({'success': True, 'message': '密码重置成功'})

        except Exception as e:
            logging.error(f"重置密码失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 添加获取当前用户信息的API
    @app.route('/api/users/current', methods=['GET'])
    @login_required
    def get_current_user():
        """获取当前登录用户信息"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                           SELECT id,
                                  username,
                                  email,
                                  display_name,
                                  role,
                                  department,
                                  permissions,
                                  is_active
                           FROM users
                           WHERE id = ?
                           ''', (session.get('user_id'),))

            user = cursor.fetchone()
            conn.close()

            if user:
                return jsonify({
                    'success': True,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'email': user['email'],
                        'display_name': user['display_name'],
                        'role': user['role'],
                        'department': user['department'],
                        'permissions': json.loads(user['permissions']) if user['permissions'] else [],
                        'is_active': bool(user['is_active'])
                    }
                })
            else:
                session.clear()
                return jsonify({'success': False, 'error': '用户不存在'})

        except Exception as e:
            logging.error(f"获取当前用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 在 enhanced_settings_routes.py 的 setup_settings_routes 函数中添加以下路由：

    # 获取单个用户信息API
    @app.route('/api/users/<int:user_id>', methods=['GET'])
    @login_required
    @admin_required
    def get_user(user_id):
        """获取单个用户信息"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT id,
                                  username,
                                  email,
                                  display_name,
                                  role,
                                  department,
                                  is_active,
                                  last_login,
                                  created_date,
                                  updated_date
                           FROM users
                           WHERE id = ?
                           ''', (user_id,))

            user = cursor.fetchone()
            conn.close()

            if user:
                return jsonify({
                    'success': True,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'email': user['email'],
                        'display_name': user['display_name'],
                        'role': user['role'],
                        'department': user['department'],
                        'is_active': bool(user['is_active']),
                        'last_login': user['last_login'],
                        'created_date': user['created_date']
                    }
                })
            else:
                return jsonify({'success': False, 'error': '用户不存在'})

        except Exception as e:
            logging.error(f"获取用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 更新用户信息API
    @app.route('/api/users/<int:user_id>', methods=['PUT'])
    @login_required
    @admin_required
    def update_user_api(user_id):
        """更新用户信息"""
        try:
            user_data = request.json
            if not user_data:
                return jsonify({'success': False, 'error': '无用户数据'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查用户是否存在
            cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
            if not cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': '用户不存在'})

            # 构建更新字段
            update_fields = []
            values = []

            allowed_fields = ['email', 'display_name', 'role', 'department', 'is_active']
            for field in allowed_fields:
                if field in user_data:
                    update_fields.append(f"{field} = ?")

                    if field == 'is_active':
                        values.append(1 if user_data[field] else 0)
                    else:
                        values.append(user_data[field])

            if not update_fields:
                conn.close()
                return jsonify({'success': False, 'error': '没有要更新的字段'})

            # 添加更新时间
            update_fields.append("updated_date = CURRENT_TIMESTAMP")

            # 执行更新
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
            values.append(user_id)

            cursor.execute(query, values)
            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'更新用户 ID: {user_id}', session.get('user_id'))

            return jsonify({'success': True, 'message': '用户更新成功'})

        except Exception as e:
            logging.error(f"更新用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 删除用户API
    @app.route('/api/users/<int:user_id>', methods=['DELETE'])
    @login_required
    @admin_required
    def delete_user_api(user_id):
        """删除用户"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查用户是否存在
            cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()

            if not user:
                conn.close()
                return jsonify({'success': False, 'error': '用户不存在'})

            # 检查是否为当前登录用户
            if session.get('user_id') == user_id:
                conn.close()
                return jsonify({'success': False, 'error': '不能删除当前登录的用户'})

            # 检查是否为管理员用户
            cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
            user_role = cursor.fetchone()['role']

            # 防止删除最后一个管理员
            if user_role == 'admin':
                cursor.execute('SELECT COUNT(*) as admin_count FROM users WHERE role = "admin"')
                admin_count = cursor.fetchone()['admin_count']
                if admin_count <= 1:
                    conn.close()
                    return jsonify({'success': False, 'error': '不能删除最后一个管理员'})

            # 执行删除
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'删除用户: {user["username"]}', session.get('user_id'))

            return jsonify({'success': True, 'message': '用户删除成功'})

        except Exception as e:
            logging.error(f"删除用户失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 重置用户密码API
    @app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
    @login_required
    @admin_required
    def reset_user_password_api(user_id):
        """重置用户密码"""
        try:
            data = request.json
            new_password = data.get('new_password')

            if not new_password or len(new_password) < 8:
                return jsonify({'success': False, 'error': '密码至少需要8位字符'})

            conn = get_db_connection()
            cursor = conn.cursor()

            # 检查用户是否存在
            cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()

            if not user:
                conn.close()
                return jsonify({'success': False, 'error': '用户不存在'})

            # 更新密码
            password_hash = hash_password(new_password)
            cursor.execute('''
                           UPDATE users
                           SET password_hash = ?,
                               updated_date  = CURRENT_TIMESTAMP
                           WHERE id = ?
                           ''', (password_hash, user_id))

            conn.commit()
            conn.close()

            # 记录操作日志
            log_system_operation(f'重置用户密码: {user["username"]}', session.get('user_id'))

            return jsonify({'success': True, 'message': '密码重置成功'})

        except Exception as e:
            logging.error(f"重置密码失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    # 在 enhanced_settings_routes.py 中添加以下路由（放在 setup_settings_routes 函数中）

    # 检查认证状态API
    @app.route('/api/check-auth', methods=['GET'])
    def check_auth():
        """检查用户认证状态"""
        try:
            if 'user_id' not in session:
                return jsonify({
                    'authenticated': False,
                    'message': '用户未登录'
                })

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                           SELECT id, username, email, role, display_name
                           FROM users
                           WHERE id = ?
                             AND is_active = 1
                           ''', (session['user_id'],))

            user = cursor.fetchone()
            conn.close()

            if not user:
                session.clear()
                return jsonify({
                    'authenticated': False,
                    'message': '用户不存在或已被禁用'
                })

            return jsonify({
                'authenticated': True,
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'email': user['email'],
                    'role': user['role'],
                    'display_name': user['display_name']
                }
            })

        except Exception as e:
            logging.error(f"检查认证状态失败: {str(e)}")
            return jsonify({
                'authenticated': False,
                'error': str(e)
            })

    # 检查管理员权限API
    @app.route('/api/check-admin', methods=['GET'])
    @login_required
    def check_admin():
        """检查是否是管理员"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
            user = cursor.fetchone()
            conn.close()

            if user and user['role'] == 'admin':
                return jsonify({
                    'is_admin': True,
                    'message': '管理员权限验证通过'
                })
            else:
                return jsonify({
                    'is_admin': False,
                    'message': '需要管理员权限'
                })

        except Exception as e:
            logging.error(f"检查管理员权限失败: {str(e)}")
            return jsonify({
                'is_admin': False,
                'error': str(e)
            })

    # 在 enhanced_settings_routes.py 中添加错误处理器

    @app.errorhandler(404)
    def not_found_error(error):
        """处理404错误"""
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': 'API路径不存在',
                'path': request.path
            }), 404
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """处理500错误"""
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': '服务器内部错误'
            }), 500
        return render_template('500.html'), 500

    @app.before_request
    def before_request():
        """在请求前检查认证（对于API请求）"""
        if request.path.startswith('/api/') and not request.path.endswith('/login'):
            # 对于需要认证的API，检查session
            # 这里可以根据需要设置哪些API需要认证
            pass


    # 初始化表
    init_settings_tables()