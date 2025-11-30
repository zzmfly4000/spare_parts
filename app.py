# [file name]: app.py
# [file content begin]
from flask import Flask, render_template, redirect, url_for, request, flash, session
from models.database import init_db, get_spare_parts_count, get_locations_count, get_all_locations, get_location_stats, \
    DatabaseManager, safe_int
from routes.parts_routes import setup_parts_routes
from routes.location_routes import setup_location_routes
from routes.operation_routes import setup_operation_routes
from routes.settings_routes import setup_settings_routes
from routes.import_export_routes import setup_import_export_routes
from utils.stock_utils import get_low_stock_parts, get_recent_activities
import datetime
import logging
from routes.database_routes import setup_database_routes


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
    init_db()

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
            app.logger.info(f"首页数据统计 - 总备件: {total_parts}, 低库存: {low_stock_count}, 缺货: {out_of_stock_count}")

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

    # 添加上下文处理器，使now在所有模板中可用
    @app.context_processor
    def inject_now():
        return {'now': datetime.datetime.now()}

    # 在 app.py 的 create_app 函数中添加以下代码（在注册模板过滤器的地方）

    # 注册自定义模板过滤器
    @app.template_filter('date')
    def date_filter(value, format='%Y-%m-%d %H:%M:%S'):
        """自定义日期格式化过滤器"""
        # 保持原有的 date_filter 代码不变
        # ...

    # 在 app.py 的 create_app 函数中添加以下模板过滤器

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
                return abs(float(value_str))
            else:
                return 0
        except (ValueError, TypeError):
            return 0

    return app
# [file content end]