# [file name]: app.py
# [file content begin]
from flask import Flask, render_template, redirect, url_for, request, flash, session
from models.database import init_db, get_spare_parts_count, get_locations_count, get_all_locations, get_location_stats, \
    DatabaseManager
from routes.parts_routes import setup_parts_routes
from routes.location_routes import setup_location_routes
from routes.operation_routes import setup_operation_routes
from routes.settings_routes import setup_settings_routes
from routes.import_export_routes import setup_import_export_routes
from utils.stock_utils import get_low_stock_parts, get_recent_activities
import datetime
import logging


def create_app(config_name='default'):
    """应用工厂函数，创建Flask应用实例"""
    app = Flask(__name__)

    # 加载配置
    if config_name == 'development':
        app.config['DEBUG'] = True
        app.config['SECRET_KEY'] = 'dev-secret-key'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        # 开发环境日志配置 - 减少导入时的日志输出
        logging.basicConfig(
            level=logging.INFO,  # 从DEBUG改为INFO，减少日志量
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    elif config_name == 'production':
        app.config['DEBUG'] = False
        app.config['SECRET_KEY'] = 'prod-secret-key-change-in-production'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        # 生产环境日志配置
        logging.basicConfig(
            level=logging.WARNING,  # 生产环境减少日志
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # 性能优化：配置数据库连接池和超时
    app.config.update(
        DATABASE_OPTIONS={
            'timeout': 60.0,  # 增加超时时间
            'check_same_thread': False,
            'isolation_level': None  # 自动提交模式
        }
    )

    # 配置数据库连接池
    app.config.update(
        DATABASE_OPTIONS={
            'timeout': 30.0,
            'check_same_thread': False
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

        # 如果已经是 datetime 对象，直接格式化
        if isinstance(value, datetime.datetime):
            return value.strftime(format)

        # 如果是字符串，尝试解析
        if isinstance(value, str):
            try:
                # 尝试解析 ISO 格式
                if 'T' in value:
                    dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                else:
                    # 尝试其他常见格式
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%H:%M:%S']:
                        try:
                            dt = datetime.datetime.strptime(value, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        return value  # 无法解析，返回原值
                return dt.strftime(format)
            except Exception:
                return value  # 解析失败，返回原值

        # 其他类型，尝试转换
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

    # 首页路由
    @app.route('/')
    def index():
        """系统首页 - 增加低库存分页"""
        try:
            # 获取统计数据
            total_parts = get_spare_parts_count()
            location_stats = get_location_stats()

            # 获取低库存备件（限制显示数量）
            low_stock_parts_list = get_low_stock_parts()
            low_stock_count = len(low_stock_parts_list)

            # 只显示前10个低库存备件
            displayed_low_stock_parts = low_stock_parts_list[:10]

            # 计算缺货数量
            out_of_stock_count = sum(1 for part in low_stock_parts_list if part[4] == 0)

            # 获取最近活动
            recent_activities = get_recent_activities(limit=10)  # 增加显示数量

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

    # 低库存提醒页面
    @app.route('/low_stock_alerts')
    def low_stock_alerts():
        """低库存预警页面 - 修复版本"""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = 20  # 每页显示20条记录

            # 获取所有低库存备件
            low_stock_parts_list = get_low_stock_parts()
            total_low_stock = len(low_stock_parts_list)

            # 计算分页
            total_pages = (total_low_stock + per_page - 1) // per_page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            displayed_parts = low_stock_parts_list[start_idx:end_idx]

            # 计算统计信息
            out_of_stock_count = sum(1 for part in low_stock_parts_list if part[4] == 0)
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

    # 数据库诊断路由
    @app.route('/debug/database')
    def debug_database():
        """数据库诊断页面"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 检查所有表
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                table_info = {}

                for table in tables:
                    table_name = table[0]
                    count = conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()[0]
                    columns = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
                    table_info[table_name] = {
                        'count': count,
                        'columns': [col[1] for col in columns]  # 列名
                    }

                # 检查操作记录表的前几条记录
                recent_operations = conn.execute('''
                    SELECT id, operation_type, part_no, quantity, operation_date 
                    FROM operation_records 
                    ORDER BY id DESC LIMIT 10
                ''').fetchall()

            return render_template('debug_database.html',
                                   table_info=table_info,
                                   recent_operations=recent_operations,
                                   now=datetime.datetime.now())

        except Exception as e:
            app.logger.error(f"数据库诊断失败: {str(e)}")
            return f"诊断失败: {str(e)}", 500

    # 注册错误处理器
    @app.errorhandler(404)
    def not_found(error):
        app.logger.warning(f"404错误: {request.url}")
        return render_template('error.html', error_message="页面未找到", error_code=404), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"500错误: {str(error)}")
        return render_template('error.html', error_message="服务器内部错误", error_code=500), 500

    @app.route('/debug/test_db')
    def debug_test_db():
        """测试数据库连接和基本操作"""
        try:
            db_manager = DatabaseManager()
            results = []

            with db_manager.get_connection() as conn:
                # 测试1：检查表是否存在
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                results.append(f"✅ 找到 {len(tables)} 个表: {[t[0] for t in tables]}")

                # 测试2：检查操作记录表
                if any('operation_records' in t[0] for t in tables):
                    count = conn.execute('SELECT COUNT(*) FROM operation_records').fetchone()[0]
                    results.append(f"✅ operation_records 表有 {count} 条记录")

                    # 测试3：插入测试记录
                    test_id = conn.execute('''
                        INSERT INTO operation_records 
                        (operation_type, part_no, description, quantity, operation_date)
                        VALUES (?, ?, ?, ?, ?)
                    ''', ('Stock in', 'TEST-001', '测试记录', 10, datetime.datetime.now())).lastrowid
                    results.append(f"✅ 成功插入测试记录，ID: {test_id}")

                    # 测试4：读取测试记录
                    test_record = conn.execute('SELECT * FROM operation_records WHERE id = ?', (test_id,)).fetchone()
                    if test_record:
                        results.append(f"✅ 成功读取测试记录: {test_record[1]} - {test_record[5]}")

                    # 测试5：删除测试记录
                    conn.execute('DELETE FROM operation_records WHERE id = ?', (test_id,))
                    results.append("✅ 成功删除测试记录")
                else:
                    results.append("❌ operation_records 表不存在")

                conn.commit()

            return '<br>'.join(results)

        except Exception as e:
            return f"❌ 测试失败: {str(e)}", 500

    # [在 app.py 中添加紧急修复路由]

    @app.route('/debug/recalculate_all_stock')
    def debug_recalculate_all_stock():
        """重新计算所有备件库存"""
        try:
            from models.database import recalculate_all_stock
            updated_count = recalculate_all_stock()

            return f"""
            <h1>库存重算完成</h1>
            <p>成功更新了 {updated_count} 个备件的库存</p>
            <p><a href="{url_for('parts_list')}">查看备件列表</a></p>
            <p><a href="{url_for('operation_records')}">查看操作记录</a></p>
            """
        except Exception as e:
            return f"库存重算失败: {str(e)}", 500

    @app.route('/debug/fix_operations')
    def debug_fix_operations():
        """紧急修复操作记录表"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 检查表结构
                table_info = conn.execute("PRAGMA table_info(operation_records)").fetchall()
                app.logger.info(f"operation_records 表结构: {table_info}")

                # 检查是否有数据
                count = conn.execute('SELECT COUNT(*) FROM operation_records').fetchone()[0]
                app.logger.info(f"当前操作记录数: {count}")

                # 尝试手动插入一条测试记录
                test_id = conn.execute('''
                    INSERT INTO operation_records 
                    (operation_type, operation_date, part_no, description, quantity)
                    VALUES (?, ?, ?, ?, ?)
                ''', ('Stock in', datetime.datetime.now(), 'TEST-001', '测试记录', 10)).lastrowid

                conn.commit()

                # 验证插入
                test_record = conn.execute('SELECT * FROM operation_records WHERE id = ?', (test_id,)).fetchone()

                return f"""
                <h1>紧急修复结果</h1>
                <p>表结构: {table_info}</p>
                <p>原有记录数: {count}</p>
                <p>测试记录ID: {test_id}</p>
                <p>测试记录: {test_record}</p>
                <p><a href="{url_for('operation_records')}">查看操作记录</a></p>
                """

        except Exception as e:
            app.logger.error(f"修复失败: {str(e)}")
            return f"修复失败: {str(e)}", 500

    @app.route('/debug/fix_stock_calculation')
    def debug_fix_stock_calculation():
        """紧急修复库存计算"""
        try:
            from models.database import DatabaseManager

            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取所有备件
                parts = conn.execute('SELECT id, part_no, current_stock FROM spare_parts').fetchall()
                updated_count = 0

                for part in parts:
                    part_id = part[0]
                    part_no = part[1]
                    old_stock = part[2]

                    # 重新计算库存
                    # 计算所有入库操作的总和（正数）
                    cursor = conn.execute('''
                        SELECT COALESCE(SUM(quantity), 0) 
                        FROM operation_records 
                        WHERE part_no = ? AND quantity > 0
                    ''', (part_no,))
                    total_in = cursor.fetchone()[0] or 0

                    # 计算出库操作的总和（负数，但取绝对值）
                    cursor = conn.execute('''
                        SELECT COALESCE(SUM(ABS(quantity)), 0) 
                        FROM operation_records 
                        WHERE part_no = ? AND quantity < 0
                    ''', (part_no,))
                    total_out = cursor.fetchone()[0] or 0

                    # 计算总库存：所有入库 - 所有出库
                    new_stock = total_in - total_out
                    new_stock = max(0, new_stock)

                    # 只有在库存变化时才更新
                    if new_stock != old_stock:
                        conn.execute('''
                            UPDATE spare_parts 
                            SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                            WHERE id = ?
                        ''', (new_stock, part_id))
                        updated_count += 1
                        app.logger.info(f"修复备件 {part_no} 库存: {old_stock} -> {new_stock}")

                conn.commit()

                return f"""
                <h1>库存修复完成</h1>
                <p>成功修复了 {updated_count} 个备件的库存计算</p>
                <p><a href="{url_for('parts_list')}">查看备件列表</a></p>
                <p><a href="{url_for('operation_records')}">查看操作记录</a></p>
                """

        except Exception as e:
            return f"库存修复失败: {str(e)}", 500

    # 添加上下文处理器，使now在所有模板中可用
    @app.context_processor
    def inject_now():
        return {'now': datetime.datetime.now()}

    return app
# [file content end]