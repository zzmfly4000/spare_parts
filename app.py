from flask import Flask, render_template
from models.database import init_db
from routes.parts_routes import setup_parts_routes
from routes.location_routes import setup_location_routes
from routes.operation_routes import setup_operation_routes
from routes.settings_routes import setup_settings_routes

def create_app(config_name='default'):
    """应用工厂函数，创建Flask应用实例"""
    app = Flask(__name__)

    # 加载配置
    if config_name == 'development':
        app.config['DEBUG'] = True
    elif config_name == 'production':
        app.config['DEBUG'] = False

    # 初始化数据库
    init_db()

    # 注册路由
    setup_parts_routes(app)
    setup_location_routes(app)
    setup_operation_routes(app)
    setup_settings_routes(app)

    # 添加首页路由
    @app.route('/')
    def index():
        return render_template('index.html')

    # 注册错误处理器
    @app.errorhandler(404)
    def not_found(error):
        return "页面未找到", 404

    @app.errorhandler(500)
    def internal_error(error):
        return "服务器内部错误", 500

    return app
