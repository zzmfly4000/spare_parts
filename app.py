from flask import Flask, render_template
from models.database import init_db, get_spare_parts_count, get_locations_count
from routes.parts_routes import setup_parts_routes
from routes.location_routes import setup_location_routes
from routes.operation_routes import setup_operation_routes
from routes.settings_routes import setup_settings_routes
from routes.import_export_routes import setup_import_export_routes
from utils.stock_utils import get_low_stock_parts, get_recent_activities
import datetime


def create_app(config_name='default'):
    """应用工厂函数，创建Flask应用实例"""
    app = Flask(__name__)

    # 加载配置
    if config_name == 'development':
        app.config['DEBUG'] = True
        app.config['SECRET_KEY'] = 'dev-secret-key'
    elif config_name == 'production':
        app.config['DEBUG'] = False
        app.config['SECRET_KEY'] = 'prod-secret-key-change-in-production'

    # 初始化数据库
    init_db()

    # 注册路由
    setup_parts_routes(app)
    setup_location_routes(app)
    setup_operation_routes(app)
    setup_settings_routes(app)
    setup_import_export_routes(app)

    # 首页路由
    @app.route('/')
    def index():
        """系统首页"""
        try:
            # 获取统计数据
            total_parts = get_spare_parts_count()
            total_locations = get_locations_count()

            # 获取低库存备件
            low_stock_parts_list = get_low_stock_parts()
            low_stock_count = len(low_stock_parts_list)

            # 计算缺货数量
            out_of_stock_count = sum(1 for part in low_stock_parts_list if part[4] == 0)

            # 获取最近活动
            recent_activities = get_recent_activities(limit=5)

            # 库位统计
            location_stats = {
                'total_locations': total_locations,
                'free_locations': len([loc for loc in get_all_locations() if loc[2] == 'free']),
                'in_use_locations': len([loc for loc in get_all_locations() if loc[2] == 'in_use'])
            }

            return render_template('index.html',
                                   total_parts=total_parts,
                                   location_stats=location_stats,
                                   low_stock_count=low_stock_count,
                                   out_of_stock_count=out_of_stock_count,
                                   low_stock_parts=low_stock_parts_list,
                                   recent_activities=recent_activities,
                                   load_time=0.5,
                                   now=datetime.datetime.now())
        except Exception as e:
            # 如果出现错误，返回基础页面
            return render_template('index.html',
                                   total_parts=0,
                                   location_stats={'total_locations': 0},
                                   low_stock_count=0,
                                   out_of_stock_count=0,
                                   low_stock_parts=[],
                                   recent_activities=[],
                                   load_time=0,
                                   now=datetime.datetime.now())

    # 低库存提醒页面
    @app.route('/low_stock_alerts')
    def low_stock_alerts():
        """低库存提醒页面"""
        low_stock_parts = get_low_stock_parts()
        return render_template('low_stock_alerts.html',
                               low_stock_parts=low_stock_parts,
                               now=datetime.datetime.now())

    # 注册错误处理器
    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html', error_message="页面未找到", error_code=404), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', error_message="服务器内部错误", error_code=500), 500

    # 添加上下文处理器，使now在所有模板中可用
    @app.context_processor
    def inject_now():
        return {'now': datetime.datetime.now()}

    return app