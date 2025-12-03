# [file name]: app.py
# [file content begin]
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from models.database import init_db, get_spare_parts_count, get_locations_count, get_all_locations, get_location_stats, \
    DatabaseManager, safe_int, update_all_location_metrics
from routes.parts_routes import setup_parts_routes
from routes.location_routes import setup_location_routes
from routes.operation_routes import setup_operation_routes
from routes.settings_routes import setup_settings_routes
from routes.import_export_routes import setup_import_export_routes
from utils.stock_utils import get_low_stock_parts, get_recent_activities
import datetime
import logging
import threading
import time
from routes.database_routes import setup_database_routes
from routes.enhanced_settings_routes import setup_settings_routes
import os
import zipfile
import shutil



def create_app(config_name='default'):
    """应用工厂函数，创建Flask应用实例"""
    app = Flask(__name__)

    # 加载配置
    if config_name == 'development':
        app.config['DEBUG'] = True
        app.config['SECRET_KEY'] = 'dev-secret-key'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('app_debug.log'),  # 同时记录到文件
                logging.StreamHandler()  # 同时输出到控制台
            ]
        )
    elif config_name == 'production':
        app.config['DEBUG'] = False
        app.config['SECRET_KEY'] = 'prod-secret-key-change-in-production'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        logging.basicConfig(
            level=logging.WARNING,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # 性能优化配置
    app.config.update(
        DATABASE_OPTIONS={
            'timeout': 60.0,
            'check_same_thread': False,
            'isolation_level': None
        }
    )

    # 初始化数据库
    try:
        init_db()

        # 验证表是否创建成功
        db_manager = DatabaseManager()
        with db_manager.get_connection() as conn:
            # 检查关键表是否存在
            tables = ['spare_parts', 'locations', 'operation_records', 'system_settings']
            missing_tables = []

            for table in tables:
                try:
                    conn.execute(f'SELECT 1 FROM {table} LIMIT 1')
                    app.logger.info(f"表 {table} 检查通过")
                except sqlite3.OperationalError:
                    missing_tables.append(table)

            if missing_tables:
                app.logger.error(f"以下表不存在: {missing_tables}")
                # 尝试重新创建表
                app.logger.info("尝试重新创建缺失的表...")
                init_db()  # 再次初始化

                # 再次检查
                for table in missing_tables:
                    try:
                        conn.execute(f'SELECT 1 FROM {table} LIMIT 1')
                        app.logger.info(f"表 {table} 重新创建成功")
                    except sqlite3.OperationalError:
                        app.logger.error(f"表 {table} 仍然不存在，可能需要手动修复数据库")

        app.logger.info("数据库初始化成功，所有表都存在")

    except Exception as e:
        app.logger.error(f"数据库初始化失败: {str(e)}")
        app.logger.error(traceback.format_exc())

    # 注册自定义模板过滤器
    @app.template_filter('date')
    def date_filter(value, format='%Y-%m-%d %H:%M:%S'):
        """自定义日期格式化过滤器"""
        if value is None:
            return ""

        if isinstance(value, datetime.datetime):
            return value.strftime(format)

        if isinstance(value, str):
            try:
                if 'T' in value:
                    dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                else:
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%H:%M:%S']:
                        try:
                            dt = datetime.datetime.strptime(value, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        return value
                return dt.strftime(format)
            except Exception:
                return value

        try:
            return str(value)
        except:
            return ""

    # 注册路由
    setup_parts_routes(app)
    setup_location_routes(app)
    setup_operation_routes(app)
    setup_settings_routes(app)
    setup_import_export_routes(app)
    setup_database_routes(app)

    # 首页路由 - 修复版本
    @app.route('/')
    def index():
        """系统首页 - 修复数据展示问题"""
        try:
            # 获取统计数据 - 确保使用修复后的函数
            total_parts = get_spare_parts_count()
            location_stats = get_location_stats()

            # 获取低库存备件
            low_stock_parts_list = get_low_stock_parts()
            low_stock_count = len(low_stock_parts_list) if low_stock_parts_list else 0

            # 只显示前10个低库存备件
            displayed_low_stock_parts = low_stock_parts_list[:10] if low_stock_parts_list else []

            # 计算缺货数量 - 使用 safe_int 确保类型安全
            out_of_stock_count = 0
            if low_stock_parts_list:
                out_of_stock_count = sum(1 for part in low_stock_parts_list if safe_int(part[4]) == 0)

            # 获取最近活动 - 增加实时性
            recent_activities = get_recent_activities(limit=15)

            # 调试日志
            app.logger.info(
                f"首页数据统计 - 总备件: {total_parts}, 低库存: {low_stock_count}, 缺货: {out_of_stock_count}")

            return render_template('index.html',
                                   total_parts=total_parts,
                                   location_stats=location_stats,
                                   low_stock_count=low_stock_count,
                                   out_of_stock_count=out_of_stock_count,
                                   low_stock_parts=displayed_low_stock_parts,
                                   recent_activities=recent_activities,
                                   load_time=0.5,
                                   now=datetime.datetime.now())
        except Exception as e:
            app.logger.error(f"首页加载失败: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())  # 打印完整堆栈信息
            # 如果出现错误，返回基础页面
            return render_template('index.html',
                                   total_parts=0,
                                   location_stats={'total_locations': 0, 'free_locations': 0, 'in_use_locations': 0},
                                   low_stock_count=0,
                                   out_of_stock_count=0,
                                   low_stock_parts=[],
                                   recent_activities=[],
                                   load_time=0,
                                   now=datetime.datetime.now())

    # 低库存提醒页面 - 修复版本
    @app.route('/low_stock_alerts')
    def low_stock_alerts():
        """低库存预警页面"""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = 20

            # 获取所有低库存备件
            low_stock_parts_list = get_low_stock_parts()
            total_low_stock = len(low_stock_parts_list) if low_stock_parts_list else 0

            # 计算分页
            total_pages = (total_low_stock + per_page - 1) // per_page if total_low_stock > 0 else 1
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            displayed_parts = low_stock_parts_list[start_idx:end_idx] if low_stock_parts_list else []

            # 计算统计信息 - 使用 safe_int 确保类型安全
            out_of_stock_count = 0
            if low_stock_parts_list:
                out_of_stock_count = sum(1 for part in low_stock_parts_list if safe_int(part[4]) == 0)
            low_stock_count = total_low_stock - out_of_stock_count

            # 计算预警比例
            total_parts = get_spare_parts_count()
            warning_percentage = round((total_low_stock / total_parts * 100), 1) if total_parts > 0 else 0

            return render_template('low_stock_alerts.html',
                                   low_stock_parts=displayed_parts,
                                   total_low_stock=total_low_stock,
                                   out_of_stock_count=out_of_stock_count,
                                   low_stock_count=low_stock_count,
                                   warning_percentage=warning_percentage,
                                   page=page,
                                   total_pages=total_pages,
                                   now=datetime.datetime.now())
        except Exception as e:
            app.logger.error(f"低库存页面加载失败: {str(e)}")
            flash('加载低库存信息失败', 'danger')
            return redirect(url_for('index'))

    # 数据库健康检查API - 使用不同的端点名称避免冲突
    @app.route('/api/app_health', methods=['GET'])
    def app_health_check():
        """应用健康检查"""
        try:
            from models.database import DatabaseManager
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 检查关键表是否存在
                tables = ['locations', 'rack_layouts', 'spare_parts', 'operation_records']
                table_status = {}

                for table in tables:
                    try:
                        conn.execute(f'SELECT 1 FROM {table} LIMIT 1')
                        table_status[table] = 'OK'
                    except Exception as e:
                        table_status[table] = f'Error: {str(e)}'

                return jsonify({
                    'success': True,
                    'database': 'Connected',
                    'tables': table_status,
                    'timestamp': datetime.datetime.now().isoformat()
                })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'database': 'Disconnected'
            }), 500

    # 系统状态API - 使用不同的端点名称
    @app.route('/api/app_status', methods=['GET'])
    def app_status():
        """系统状态检查"""
        try:
            # 获取基本统计
            total_parts = get_spare_parts_count()
            total_locations = get_locations_count()
            low_stock_parts = get_low_stock_parts()
            low_stock_count = len(low_stock_parts) if low_stock_parts else 0

            # 检查数据库连接
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                conn.execute('SELECT 1')
                db_status = 'healthy'

            return jsonify({
                'success': True,
                'status': 'operational',
                'database': db_status,
                'statistics': {
                    'total_parts': total_parts,
                    'total_locations': total_locations,
                    'low_stock_count': low_stock_count
                },
                'timestamp': datetime.datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'status': 'degraded',
                'error': str(e)
            }), 500

    # 手动更新库位指标
    @app.route('/api/locations/update_all_metrics', methods=['POST'])
    def update_all_location_metrics_api():
        """手动更新所有库位指标"""
        try:
            updated_count = update_all_location_metrics()
            return jsonify({
                'success': True,
                'updated_count': updated_count,
                'message': f'成功更新 {updated_count} 个库位的统计指标'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    # 添加上下文处理器，使now在所有模板中可用
    @app.context_processor
    def inject_now():
        return {'now': datetime.datetime.now()}

    # 添加安全的比较过滤器
    @app.template_filter('safe_compare')
    def safe_compare_filter(value1, value2, operator='eq'):
        """安全的比较过滤器，处理 None 值和不同类型"""
        try:
            # 处理 None 值
            if value1 is None:
                value1 = 0
            if value2 is None:
                value2 = 0

            # 转换为数值类型进行比较
            try:
                val1 = float(value1)
                val2 = float(value2)
            except (ValueError, TypeError):
                # 如果无法转换为数值，使用字符串比较
                val1 = str(value1)
                val2 = str(value2)

            if operator == 'eq':
                return val1 == val2
            elif operator == 'ne':
                return val1 != val2
            elif operator == 'lt':
                return val1 < val2
            elif operator == 'le':
                return val1 <= val2
            elif operator == 'gt':
                return val1 > val2
            elif operator == 'ge':
                return val1 >= val2
            else:
                return False
        except Exception:
            return False

    # 添加默认值过滤器
    @app.template_filter('default')
    def default_filter(value, default_value=0):
        """提供默认值的过滤器"""
        if value is None:
            return default_value
        return value

    # 添加安全的 abs 过滤器
    @app.template_filter('safe_abs')
    def safe_abs_filter(value):
        """安全的绝对值过滤器，处理字符串和数字"""
        try:
            if isinstance(value, (int, float)):
                return abs(value)
            elif isinstance(value, str):
                # 处理字符串
                value_str = value.strip()
                if value_str == '':
                    return 0
                return abs(float(value_str))  # 先转浮点再转整数
            else:
                return 0
        except (ValueError, TypeError):
            return 0

    # 添加安全的除法过滤器
    @app.template_filter('safe_divide')
    def safe_divide_filter(value, divisor, default=0):
        """安全的除法过滤器，避免除零错误"""
        try:
            if divisor == 0:
                return default
            return value / divisor
        except (ValueError, TypeError, ZeroDivisionError):
            return default

    # 添加数字格式化过滤器
    @app.template_filter('format_number')
    def format_number_filter(value, precision=2):
        """数字格式化过滤器"""
        try:
            if value is None:
                return "0"
            num = float(value)
            if num == int(num):
                return str(int(num))
            else:
                return f"{num:.{precision}f}"
        except (ValueError, TypeError):
            return str(value)

    # 在 app.py 的适当位置添加登录页面路由
    @app.route('/login')
    def login_page():
        """登录页面"""
        # 如果用户已登录，重定向到首页
        if 'user_id' in session:
            return redirect(url_for('index'))
        return render_template('login.html')

    @app.route('/api/logout')
    def logout_api():
        """退出登录API"""
        session.clear()
        flash('已成功退出登录', 'success')
        return redirect(url_for('login_page'))

    # 在增强设置路由中，确保未登录用户无法访问设置页面
    @app.route('/settings')
    def settings_page():
        """系统设置页面"""
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login_page'))

        # 检查是否是管理员
        from routes.enhanced_settings_routes import check_admin_permission
        if not check_admin_permission(session.get('user_id')):
            flash('需要管理员权限', 'danger')
            return redirect(url_for('index'))

        # 获取当前设置
        from models.database import get_system_settings
        current_settings = get_system_settings()
        return render_template('settings.html', settings=current_settings)

    # 在 app.py 的 create_app 函数中，添加以下路由
    # 放在合适的位置，比如在 index 路由之后

    @app.route('/api/settings/save_all', methods=['POST'], endpoint='app_save_all_settings')
    def save_all_settings():
        """保存所有系统设置"""
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        try:
            # 获取前端发送的数据
            settings_data = request.json
            if not settings_data:
                return jsonify({'success': False, 'error': '无数据'})

            app.logger.info(f"收到设置数据: {settings_data}")  # 添加日志

            # 连接数据库
            import sqlite3
            conn = sqlite3.connect('spare_parts.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 保存通用设置
            if 'general' in settings_data:
                for key, value in settings_data['general'].items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO system_settings 
                        (setting_key, setting_value, setting_type, category, updated_date)
                        VALUES (?, ?, 'string', 'general', CURRENT_TIMESTAMP)
                    ''', (key, str(value)))
                    app.logger.info(f"保存通用设置: {key} = {value}")

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
                    app.logger.info(f"保存库存设置: {key} = {value} (类型: {setting_type})")

            # 保存邮件设置 - 确保保存所有字段
            if 'email' in settings_data:
                email_data = settings_data['email']
                app.logger.info(f"邮件设置数据: {email_data}")

                # 确保所有邮件字段都被保存
                email_fields = {
                    'mail_server': ('string', 'SMTP服务器'),
                    'mail_port': ('integer', 'SMTP端口'),
                    'mail_encryption': ('string', '邮件加密方式'),
                    'mail_sender': ('string', '发件人邮箱'),
                    'mail_sender_name': ('string', '发件人名称'),
                    'mail_username': ('string', 'SMTP用户名'),
                    'mail_password': ('string', 'SMTP密码')
                }

                for key, (setting_type, description) in email_fields.items():
                    value = email_data.get(key, '')
                    cursor.execute('''
                        INSERT OR REPLACE INTO system_settings 
                        (setting_key, setting_value, setting_type, category, description, updated_date)
                        VALUES (?, ?, ?, 'email', ?, CURRENT_TIMESTAMP)
                    ''', (key, str(value), setting_type, description))
                    app.logger.info(f"保存邮件设置: {key} = {value}")

            conn.commit()
            conn.close()

            app.logger.info("所有设置保存成功")

            return jsonify({
                'success': True,
                'message': '设置保存成功'
            })

        except Exception as e:
            app.logger.error(f"保存设置失败: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500


    # 在 app.py 中添加
    @app.route('/api/settings/init_email_config', methods=['POST'], endpoint='app_init_email_config')
    def init_email_config():
        """初始化邮件配置"""
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        try:
            # 连接数据库
            import sqlite3
            conn = sqlite3.connect('spare_parts.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 检查邮件配置是否存在
            cursor.execute("SELECT setting_key FROM system_settings WHERE category = 'email'")
            existing_configs = cursor.fetchall()

            if not existing_configs:
                # 初始化默认邮件配置
                default_email_configs = [
                    ('mail_server', 'smtp.example.com', 'string', 'email', 'SMTP服务器'),
                    ('mail_port', '587', 'integer', 'email', 'SMTP端口'),
                    ('mail_encryption', 'tls', 'string', 'email', '邮件加密方式'),
                    ('mail_sender', 'noreply@example.com', 'string', 'email', '发件人邮箱'),
                    ('mail_sender_name', '备件管理系统', 'string', 'email', '发件人名称'),
                    ('mail_username', '', 'string', 'email', 'SMTP用户名'),
                    ('mail_password', '', 'string', 'email', 'SMTP密码')
                ]

                for config in default_email_configs:
                    cursor.execute('''
                        INSERT OR IGNORE INTO system_settings 
                        (setting_key, setting_value, setting_type, category, description)
                        VALUES (?, ?, ?, ?, ?)
                    ''', config)

            conn.commit()
            conn.close()

            return jsonify({
                'success': True,
                'message': '邮件配置初始化完成'
            })

        except Exception as e:
            app.logger.error(f"初始化邮件配置失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # 修改测试邮件API，先从数据库获取配置
    @app.route('/api/settings/test_email', methods=['POST'], endpoint='app_test_email')
    def test_email_connection():
        """测试邮件服务器连接"""
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        try:
            app.logger.info("开始测试邮件连接...")

            # 先初始化邮件配置（确保有默认配置）
            init_response = init_email_config()

            # 获取邮件配置
            import sqlite3
            conn = sqlite3.connect('spare_parts.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT setting_key, setting_value FROM system_settings WHERE category = 'email'")
            rows = cursor.fetchall()
            conn.close()

            email_settings = {}
            for row in rows:
                email_settings[row['setting_key']] = row['setting_value']

            app.logger.info(f"邮件配置: {email_settings}")

            # 检查必要配置
            required_fields = ['mail_server', 'mail_port']
            missing_fields = []
            for field in required_fields:
                if not email_settings.get(field):
                    missing_fields.append(field)

            if missing_fields:
                app.logger.error(f"缺少邮件配置: {missing_fields}")
                return jsonify({
                    'success': False,
                    'error': f'缺少邮件配置: {", ".join(missing_fields)}。请先保存邮件设置。'
                })

            # 如果缺少可选配置，使用默认值
            if not email_settings.get('mail_sender'):
                email_settings['mail_sender'] = 'noreply@example.com'
            if not email_settings.get('mail_sender_name'):
                email_settings['mail_sender_name'] = '备件管理系统'
            if not email_settings.get('mail_encryption'):
                email_settings['mail_encryption'] = 'tls'

            # 尝试连接SMTP服务器
            try:
                import smtplib

                # 检查端口
                try:
                    port = int(email_settings['mail_port'])
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': f'端口号无效: {email_settings["mail_port"]}'
                    })

                app.logger.info(f"尝试连接SMTP服务器: {email_settings['mail_server']}:{port}")

                # 根据加密方式选择连接方法
                if email_settings.get('mail_encryption') == 'ssl':
                    server = smtplib.SMTP_SSL(email_settings['mail_server'], port, timeout=10)
                    app.logger.info("使用SSL加密连接")
                else:
                    server = smtplib.SMTP(email_settings['mail_server'], port, timeout=10)
                    if email_settings.get('mail_encryption') == 'tls':
                        server.starttls()  # 启用TLS
                        app.logger.info("使用TLS加密连接")
                    else:
                        app.logger.info("无加密连接")

                # 如果有用户名和密码，尝试登录
                if email_settings.get('mail_username') and email_settings.get('mail_password'):
                    app.logger.info("尝试登录SMTP服务器...")
                    server.login(
                        email_settings['mail_username'],
                        email_settings['mail_password']
                    )
                    app.logger.info("SMTP登录成功")

                server.quit()
                app.logger.info("邮件服务器连接测试成功")

                return jsonify({
                    'success': True,
                    'message': '邮件服务器连接成功！',
                    'config': {
                        'server': email_settings['mail_server'],
                        'port': port,
                        'encryption': email_settings.get('mail_encryption', 'tls')
                    }
                })

            except smtplib.SMTPException as smtp_error:
                app.logger.error(f"SMTP连接失败: {str(smtp_error)}")
                error_msg = str(smtp_error)

                # 提供更友好的错误信息
                if "connection refused" in error_msg.lower():
                    error_msg = "连接被拒绝，请检查服务器地址和端口"
                elif "authentication failed" in error_msg.lower():
                    error_msg = "认证失败，请检查用户名和密码"
                elif "timed out" in error_msg.lower():
                    error_msg = "连接超时，请检查网络连接"

                return jsonify({
                    'success': False,
                    'error': f'SMTP连接失败: {error_msg}'
                })

            except Exception as smtp_error:
                app.logger.error(f"SMTP连接失败: {str(smtp_error)}")
                return jsonify({
                    'success': False,
                    'error': f'SMTP连接失败: {str(smtp_error)}'
                })

        except Exception as e:
            app.logger.error(f"邮件测试失败: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/backup/create', methods=['POST'], endpoint='app_create_backup')
    def create_backup():
        """创建数据库备份"""
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        try:
            # 创建备份目录
            backup_dir = 'backups'
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            # 备份文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'backup_{timestamp}'
            zip_path = os.path.join(backup_dir, f'{backup_name}.zip')

            # 要备份的文件
            backup_files = ['spare_parts.db']

            # 创建ZIP文件
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in backup_files:
                    if os.path.exists(file):
                        zipf.write(file, os.path.basename(file))
                    else:
                        app.logger.warning(f"备份文件不存在: {file}")

            # 清理旧备份（保留最近10个）
            backup_files_list = sorted(
                [f for f in os.listdir(backup_dir) if f.endswith('.zip')],
                key=lambda x: os.path.getmtime(os.path.join(backup_dir, x))
            )

            if len(backup_files_list) > 10:
                for old_backup in backup_files_list[:-10]:
                    os.remove(os.path.join(backup_dir, old_backup))

            # 计算文件大小
            file_size = os.path.getsize(zip_path)
            file_size_mb = file_size / (1024 * 1024)

            app.logger.info(f"备份创建成功: {backup_name}.zip, 大小: {file_size_mb:.2f} MB")

            return jsonify({
                'success': True,
                'message': f'备份创建成功！文件大小: {file_size_mb:.2f} MB',
                'backup_name': backup_name,
                'file_size': file_size,
                'file_size_mb': f'{file_size_mb:.2f} MB',
                'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        except Exception as e:
            app.logger.error(f"创建备份失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/backup/list', methods=['GET'], endpoint='app_list_backups')
    def list_backups():
        """获取备份列表"""
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        try:
            backup_dir = 'backups'
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
                return jsonify({'success': True, 'backups': []})

            backups = []
            for filename in sorted(os.listdir(backup_dir), reverse=True):
                if filename.endswith('.zip'):
                    filepath = os.path.join(backup_dir, filename)
                    stat = os.stat(filepath)

                    # 计算文件大小
                    file_size = stat.st_size
                    file_size_mb = file_size / (1024 * 1024)

                    backups.append({
                        'name': filename.replace('.zip', ''),
                        'filename': filename,
                        'size': file_size,
                        'size_formatted': f'{file_size_mb:.2f} MB',
                        'created_time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'download_url': f'/backups/{filename}'
                    })

            return jsonify({
                'success': True,
                'backups': backups,
                'count': len(backups)
            })

        except Exception as e:
            app.logger.error(f"获取备份列表失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # 添加静态文件路由用于下载备份
    @app.route('/backups/<filename>', endpoint='app_download_backup')
    def download_backup(filename):
        """下载备份文件"""
        if 'user_id' not in session:
            return redirect(url_for('login_page'))

        backup_dir = 'backups'
        filepath = os.path.join(backup_dir, filename)

        if not os.path.exists(filepath):
            flash('备份文件不存在', 'danger')
            return redirect(url_for('settings_page'))

        try:
            from flask import send_from_directory
            return send_from_directory(
                backup_dir,
                filename,
                as_attachment=True,
                download_name=filename
            )
        except Exception as e:
            app.logger.error(f"下载备份失败: {str(e)}")
            flash(f'下载失败: {str(e)}', 'danger')
            return redirect(url_for('settings_page'))

    @app.route('/api/backup/delete/<backup_name>', methods=['DELETE'], endpoint='app_delete_backup')
    def delete_backup(backup_name):
        """删除备份文件"""
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        try:
            backup_dir = 'backups'
            filepath = os.path.join(backup_dir, f'{backup_name}.zip')

            if not os.path.exists(filepath):
                return jsonify({'success': False, 'error': '备份文件不存在'}), 404

            # 删除文件
            os.remove(filepath)

            app.logger.info(f"备份删除成功: {backup_name}")

            return jsonify({
                'success': True,
                'message': f'备份删除成功: {backup_name}'
            })

        except Exception as e:
            app.logger.error(f"删除备份失败: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # 同时需要更新 base.html 中的登录链接

    # 启动后台任务（如果不在调试模式）
    if not app.config.get('DEBUG'):
        start_background_tasks(app)

    return app


def start_background_tasks(app):
    """启动后台定时任务"""

    def background_metrics_updater():
        """后台定时更新库位指标"""
        with app.app_context():
            from models.database import update_all_location_metrics
            while True:
                try:
                    # 每30分钟自动更新一次所有库位指标
                    time.sleep(1800)  # 30分钟
                    updated_count = update_all_location_metrics()
                    app.logger.info(f"定时任务: 自动更新了 {updated_count} 个库位指标")
                except Exception as e:
                    app.logger.error(f"定时更新库位指标失败: {str(e)}")

    def background_health_check():
        """后台健康检查"""
        with app.app_context():
            while True:
                try:
                    # 每5分钟执行一次健康检查
                    time.sleep(300)  # 5分钟

                    # 检查数据库连接
                    from models.database import DatabaseManager
                    db_manager = DatabaseManager()
                    with db_manager.get_connection() as conn:
                        conn.execute('SELECT 1')

                    # 检查关键表
                    tables = ['locations', 'spare_parts', 'operation_records']
                    for table in tables:
                        try:
                            with db_manager.get_connection() as conn:
                                conn.execute(f'SELECT COUNT(*) FROM {table}')
                        except Exception as e:
                            app.logger.warning(f"健康检查: 表 {table} 访问异常: {str(e)}")

                    app.logger.info("健康检查: 系统运行正常")

                except Exception as e:
                    app.logger.error(f"健康检查失败: {str(e)}")

    # 启动后台线程
    try:
        metrics_thread = threading.Thread(target=background_metrics_updater, daemon=True)
        metrics_thread.start()

        health_thread = threading.Thread(target=background_health_check, daemon=True)
        health_thread.start()

        app.logger.info("后台任务已启动")
    except Exception as e:
        app.logger.error(f"启动后台任务失败: {str(e)}")


# 应用启动入口
if __name__ == '__main__':
    # 创建应用实例
    app = create_app('development')

    # 启动Flask开发服务器
    app.run(
        host='0.0.0.0',  # 允许外部访问
        port=5000,
        debug=True,
        threaded=True  # 启用多线程处理请求
    )
# [file content end]