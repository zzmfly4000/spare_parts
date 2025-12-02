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


def create_app(config_name='default'):
    """应用工厂函数，创建Flask应用实例"""
    app = Flask(__name__)

    # 加载配置
    if config_name == 'development':
        app.config['DEBUG'] = True
        app.config['SECRET_KEY'] = 'dev-secret-key'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
        app.logger.info("数据库初始化成功")
    except Exception as e:
        app.logger.error(f"数据库初始化失败: {str(e)}")
        # 不退出，让应用继续运行，但记录错误

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