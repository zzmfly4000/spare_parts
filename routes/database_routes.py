# [file name]: database_routes.py
# [file content begin]
from flask import render_template, request, redirect, url_for, flash, jsonify
from models.database import DatabaseManager, init_db, get_all_spare_parts, get_all_locations, get_all_operation_records
from models.database import get_spare_parts_count, get_locations_count, get_accurate_location_stats
import sqlite3
import os
import json
from datetime import datetime


def setup_database_routes(app):
    """设置数据库管理路由"""

    @app.route('/database_management')
    def database_management():
        """数据库管理主页面"""
        try:
            # 获取数据库基本信息
            db_path = 'spare_parts.db'
            db_size = 0
            if os.path.exists(db_path):
                db_size = os.path.getsize(db_path)

            # 获取表统计信息
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取所有表的信息
                cursor = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """)
                tables = [row[0] for row in cursor.fetchall()]

                # 获取每个表的记录数
                table_stats = {}
                for table in tables:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    cursor = conn.execute(f"PRAGMA table_info({table})")
                    columns = len(cursor.fetchall())
                    table_stats[table] = {
                        'count': count,
                        'columns': columns
                    }

            # 获取系统性能信息
            performance_stats = get_performance_stats()

            return render_template('database_management.html',
                                   db_size=db_size,
                                   tables=tables,
                                   table_stats=table_stats,
                                   performance_stats=performance_stats)

        except Exception as e:
            app.logger.error(f"数据库管理页面加载失败: {str(e)}")
            flash('加载数据库信息失败', 'danger')
            return redirect(url_for('index'))

    @app.route('/database/table/<table_name>')
    def view_table_data(table_name):
        """查看表数据"""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = 50
            search = request.args.get('search', '')

            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取表结构
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                columns = [{'name': row[1], 'type': row[2]} for row in cursor.fetchall()]

                # 构建查询
                query = f"SELECT * FROM {table_name}"
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                params = []

                if search:
                    search_conditions = []
                    for col in columns:
                        search_conditions.append(f"{col['name']} LIKE ?")
                        params.append(f"%{search}%")
                    query += " WHERE " + " OR ".join(search_conditions)
                    count_query += " WHERE " + " OR ".join(search_conditions)

                # 获取总数
                cursor = conn.execute(count_query, params)
                total_count = cursor.fetchone()[0]

                # 分页查询
                query += " LIMIT ? OFFSET ?"
                params.extend([per_page, (page - 1) * per_page])
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                # 转换为字典列表
                data = []
                for row in rows:
                    if hasattr(row, '_fields'):
                        row_dict = {}
                        for i, field in enumerate(row._fields):
                            row_dict[field] = row[i]
                        data.append(row_dict)
                    else:
                        row_dict = {}
                        for i, col in enumerate(columns):
                            row_dict[col['name']] = row[i] if i < len(row) else None
                        data.append(row_dict)

                total_pages = (total_count + per_page - 1) // per_page

            return render_template('table_view.html',
                                   table_name=table_name,
                                   columns=columns,
                                   data=data,
                                   page=page,
                                   total_pages=total_pages,
                                   total_count=total_count,
                                   search=search)

        except Exception as e:
            app.logger.error(f"查看表数据失败: {str(e)}")
            flash(f'查看表数据失败: {str(e)}', 'danger')
            return redirect(url_for('database_management'))

    @app.route('/database/query', methods=['GET', 'POST'])
    def database_query():
        """SQL查询界面"""
        if request.method == 'POST':
            try:
                sql_query = request.form.get('sql_query', '').strip()
                if not sql_query:
                    flash('请输入SQL查询语句', 'warning')
                    return redirect(url_for('database_query'))

                # 安全检查：禁止危险操作
                dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE']
                if any(keyword in sql_query.upper() for keyword in dangerous_keywords):
                    flash('出于安全考虑，禁止执行数据修改操作', 'danger')
                    return redirect(url_for('database_query'))

                db_manager = DatabaseManager()
                with db_manager.get_connection() as conn:
                    cursor = conn.execute(sql_query)

                    # 如果是SELECT查询
                    if sql_query.upper().startswith('SELECT'):
                        rows = cursor.fetchall()
                        columns = [description[0] for description in cursor.description] if cursor.description else []

                        # 转换为字典列表
                        data = []
                        for row in rows:
                            if hasattr(row, '_fields'):
                                row_dict = {}
                                for i, field in enumerate(row._fields):
                                    row_dict[field] = row[i]
                                data.append(row_dict)
                            else:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[col] = row[i] if i < len(row) else None
                                data.append(row_dict)

                        return render_template('query_results.html',
                                               sql_query=sql_query,
                                               columns=columns,
                                               data=data,
                                               row_count=len(data))
                    else:
                        # 其他查询（PRAGMA等）
                        result = cursor.fetchall()
                        return render_template('query_results.html',
                                               sql_query=sql_query,
                                               result=result)

            except Exception as e:
                flash(f'查询执行失败: {str(e)}', 'danger')
                return redirect(url_for('database_query'))

        return render_template('database_query.html')

    @app.route('/database/backup')
    def database_backup():
        """数据库备份"""
        try:
            backup_path = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 简单的备份方式：复制数据库文件
                import shutil
                shutil.copy2('spare_parts.db', backup_path)

            flash(f'数据库备份成功: {backup_path}', 'success')

        except Exception as e:
            flash(f'数据库备份失败: {str(e)}', 'danger')

        return redirect(url_for('database_management'))

    @app.route('/database/optimize')
    def database_optimize():
        """数据库优化"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 执行优化命令
                conn.execute("VACUUM")
                conn.execute("PRAGMA optimize")
                conn.execute("PRAGMA analysis_limit=400")
                conn.execute("PRAGMA cache_size=-64000")

            flash('数据库优化完成', 'success')

        except Exception as e:
            flash(f'数据库优化失败: {str(e)}', 'danger')

        return redirect(url_for('database_management'))

    @app.route('/database/stats')
    def database_statistics():
        """数据库统计信息"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取数据库统计
                stats = {}

                # 表大小统计
                cursor = conn.execute("""
                    SELECT name, 
                           (SELECT COUNT(*) FROM sqlite_master WHERE type='table') as table_count,
                           (SELECT COUNT(*) FROM sqlite_master WHERE type='index') as index_count
                    FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                stats['schema'] = cursor.fetchone()

                # 各表记录数
                cursor = conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row[0] for row in cursor.fetchall()]

                table_counts = {}
                for table in tables:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    table_counts[table] = cursor.fetchone()[0]

                stats['table_counts'] = table_counts

                # 索引信息
                cursor = conn.execute("""
                    SELECT m.name as table_name, il.name as index_name
                    FROM sqlite_master m
                    JOIN pragma_index_list(m.name) il
                    WHERE m.type = 'table' AND m.name NOT LIKE 'sqlite_%'
                """)
                stats['indexes'] = cursor.fetchall()

            return jsonify(stats)

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/database/record/edit', methods=['POST'])
    def edit_table_record():
        """编辑表记录"""
        try:
            table_name = request.form.get('table_name')
            record_id = request.form.get('record_id')
            field_name = request.form.get('field_name')
            new_value = request.form.get('new_value')

            if not all([table_name, record_id, field_name]):
                return jsonify({'success': False, 'error': '缺少必要参数'})

            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取主键字段名
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                pk_column = None
                for col in columns:
                    if col[5] == 1:  # pk字段
                        pk_column = col[1]
                        break

                if not pk_column:
                    pk_column = 'id'  # 默认使用id作为主键

                # 更新记录
                query = f"UPDATE {table_name} SET {field_name} = ? WHERE {pk_column} = ?"
                cursor = conn.execute(query, (new_value, record_id))

                if cursor.rowcount > 0:
                    return jsonify({'success': True})
                else:
                    return jsonify({'success': False, 'error': '记录未找到或未更新'})

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/database/record/delete', methods=['POST'])
    def delete_table_record():
        """删除表记录"""
        try:
            table_name = request.form.get('table_name')
            record_id = request.form.get('record_id')

            if not all([table_name, record_id]):
                return jsonify({'success': False, 'error': '缺少必要参数'})

            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取主键字段名
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                pk_column = None
                for col in columns:
                    if col[5] == 1:  # pk字段
                        pk_column = col[1]
                        break

                if not pk_column:
                    pk_column = 'id'  # 默认使用id作为主键

                # 删除记录
                query = f"DELETE FROM {table_name} WHERE {pk_column} = ?"
                cursor = conn.execute(query, (record_id,))

                if cursor.rowcount > 0:
                    return jsonify({'success': True})
                else:
                    return jsonify({'success': False, 'error': '记录未找到或未删除'})

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


def get_performance_stats():
    """获取性能统计信息"""
    try:
        db_manager = DatabaseManager()
        with db_manager.get_connection() as conn:
            stats = {}

            # 获取数据库大小信息
            cursor = conn.execute("PRAGMA page_size")
            stats['page_size'] = cursor.fetchone()[0]

            cursor = conn.execute("PRAGMA page_count")
            stats['page_count'] = cursor.fetchone()[0]

            cursor = conn.execute("PRAGMA freelist_count")
            stats['freelist_count'] = cursor.fetchone()[0]

            cursor = conn.execute("PRAGMA cache_size")
            stats['cache_size'] = cursor.fetchone()[0]

            cursor = conn.execute("PRAGMA journal_mode")
            stats['journal_mode'] = cursor.fetchone()[0]

            return stats

    except Exception as e:
        return {}
# [file content end]