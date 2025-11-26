# [file name]: operation_routes.py
# [file content begin]
from flask import render_template, request, redirect, url_for, flash, jsonify, make_response, session
from models.database import (
    create_operation_record, get_spare_part_by_id, get_spare_part_by_part_no,
    get_all_operation_records, get_operation_statistics, create_spare_part,
    get_all_spare_parts, get_all_locations, DatabaseManager
)
from utils.helpers import safe_int, safe_float, safe_str, safe_datetime
import datetime
import logging


def setup_operation_routes(app):
    """设置操作记录路由 - 完整修复版本"""

    def parse_operation_date(date_value):
        """解析操作日期"""
        if date_value is None:
            return None

        if isinstance(date_value, datetime.datetime):
            return date_value

        if isinstance(date_value, str):
            try:
                # 尝试解析 ISO 格式
                if 'T' in date_value:
                    return datetime.datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                else:
                    # 尝试其他常见格式
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%H:%M:%S']:
                        try:
                            return datetime.datetime.strptime(date_value, fmt)
                        except ValueError:
                            continue
            except Exception as e:
                logging.warning(f"日期解析失败: {date_value}, 错误: {str(e)}")

        return None

    @app.route('/operation_records')
    def operation_records():
        """操作记录列表页面 - 实时数据库查询版本"""
        try:
            # 获取筛选参数
            operation_type = request.args.get('operation_type', '')
            date_from = request.args.get('date_from', '')
            date_to = request.args.get('date_to', '')
            part_no = request.args.get('part_no', '')
            page = safe_int(request.args.get('page', 1))
            per_page = safe_int(request.args.get('per_page', 20))

            app.logger.info(
                f"操作记录查询参数: operation_type={operation_type}, date_from={date_from}, date_to={date_to}, part_no={part_no}, page={page}, per_page={per_page}")

            # 直接从数据库实时查询
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 构建查询
                query = '''
                    SELECT id, operation_type, operation_date, supplier_recipient, location, 
                           part_no, description, part_type, product_model, quantity, work_center, created_date
                    FROM operation_records 
                    WHERE 1=1
                '''
                params = []

                # 添加筛选条件
                if operation_type:
                    query += ' AND operation_type = ?'
                    params.append(operation_type)

                if part_no:
                    query += ' AND part_no LIKE ?'
                    params.append(f'%{part_no}%')

                if date_from:
                    query += ' AND DATE(operation_date) >= ?'
                    params.append(date_from)

                if date_to:
                    query += ' AND DATE(operation_date) <= ?'
                    params.append(date_to)

                # 排序 - 最新的在前面
                query += ' ORDER BY operation_date DESC, id DESC'

                app.logger.info(f"执行查询: {query}")
                app.logger.info(f"查询参数: {params}")

                # 获取总数
                count_query = f'SELECT COUNT(*) FROM ({query})'
                total_operations = conn.execute(count_query, params).fetchone()[0]
                app.logger.info(f"总操作记录数: {total_operations}")

                # 添加分页
                query += ' LIMIT ? OFFSET ?'
                params.extend([per_page, (page - 1) * per_page])

                # 执行查询
                cursor = conn.execute(query, params)
                operations = cursor.fetchall()
                app.logger.info(f"查询到 {len(operations)} 条记录")

                # 如果查询结果为空，检查数据库表是否存在数据
                if len(operations) == 0:
                    # 检查表是否存在数据
                    total_count = conn.execute('SELECT COUNT(*) FROM operation_records').fetchone()[0]
                    app.logger.info(f"operation_records 表总记录数: {total_count}")

                    # 检查表结构
                    table_info = conn.execute("PRAGMA table_info(operation_records)").fetchall()
                    app.logger.info(f"operation_records 表结构: {table_info}")

            # 检查是否有导入成功的标记
            import_success = None
            if 'import_success' in session:
                import_success = session.pop('import_success')
                app.logger.info(f"检测到导入成功标记: {import_success} 条记录")
                flash(f'导入成功！新增 {import_success} 条操作记录', 'success')

            # 渲染模板
            response = make_response(render_template('operation_records.html',
                                                     operations=operations,
                                                     total_operations=total_operations,
                                                     page=page,
                                                     per_page=per_page,
                                                     operation_type=operation_type,
                                                     date_from=date_from,
                                                     date_to=date_to,
                                                     part_no=part_no,
                                                     now=datetime.datetime.now()))

            # 设置缓存控制头，确保实时显示
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

            return response

        except Exception as e:
            app.logger.error(f"加载操作记录失败: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
            flash('加载操作记录失败', 'danger')
            return render_template('operation_records.html',
                                   operations=[],
                                   total_operations=0,
                                   page=1,
                                   per_page=20,
                                   operation_type='',
                                   date_from='',
                                   date_to='',
                                   part_no='',
                                   now=datetime.datetime.now())

    @app.route('/smart_inbound', methods=['GET', 'POST'])
    def smart_inbound():
        """智能入库页面 - 修复版本"""
        parts = get_all_spare_parts()
        locations = get_all_locations()

        if request.method == 'POST':
            try:
                operation_data = {
                    'operation_type': request.form.get('operation_type', 'Stock in'),
                    'supplier_recipient': request.form.get('supplier', ''),
                    'location': request.form.get('location', ''),
                    'part_no': request.form.get('part_no', '').strip(),
                    'description': request.form.get('description', ''),
                    'part_type': request.form.get('part_type', ''),
                    'product_model': request.form.get('product_model', ''),
                    'quantity': safe_int(request.form.get('quantity', 0)),
                    'work_center': request.form.get('work_center', '')
                }

                # 验证数据
                if not operation_data['part_no']:
                    flash('备件编号不能为空', 'danger')
                    return render_template('smart_inbound.html',
                                           parts=parts,
                                           locations=locations,
                                           prefill_part=None,
                                           now=datetime.datetime.now())

                if operation_data['quantity'] <= 0:
                    flash('入库数量必须大于0', 'danger')
                    return render_template('smart_inbound.html',
                                           parts=parts,
                                           locations=locations,
                                           prefill_part=None,
                                           now=datetime.datetime.now())

                # 创建操作记录
                operation_id = create_operation_record(operation_data)
                flash(f'入库操作成功！操作记录ID: {operation_id}', 'success')

                # 重定向到操作记录页面第一页，显示最新记录
                return redirect(url_for('operation_records', page=1))

            except ValueError as e:
                error_msg = str(e)
                if "database is locked" in error_msg.lower():
                    flash('系统繁忙，请稍后重试', 'danger')
                else:
                    flash(error_msg, 'danger')

                return render_template('smart_inbound.html',
                                       parts=parts,
                                       locations=locations,
                                       prefill_part=None,
                                       now=datetime.datetime.now())

            except Exception as e:
                app.logger.error(f"智能入库操作失败: {str(e)}")
                flash(f'入库操作失败: {str(e)}', 'danger')
                return render_template('smart_inbound.html',
                                       parts=parts,
                                       locations=locations,
                                       prefill_part=None,
                                       now=datetime.datetime.now())

        # GET请求
        try:
            part_no = request.args.get('part_no', '')
            part = None
            if part_no:
                part = get_spare_part_by_part_no(part_no)

            return render_template('smart_inbound.html',
                                   parts=parts,
                                   locations=locations,
                                   prefill_part=part,
                                   now=datetime.datetime.now())

        except Exception as e:
            app.logger.error(f"加载智能入库页面失败: {str(e)}")
            flash('加载页面失败', 'danger')
            return render_template('smart_inbound.html',
                                   parts=parts,
                                   locations=locations,
                                   prefill_part=None,
                                   now=datetime.datetime.now())

    @app.route('/smart_outbound', methods=['GET', 'POST'])
    def smart_outbound():
        """智能出库页面 - 修复版本"""
        parts = get_all_spare_parts()
        locations = get_all_locations()

        if request.method == 'POST':
            try:
                operation_data = {
                    'operation_type': 'Stock out',
                    'supplier_recipient': request.form.get('recipient', ''),
                    'location': request.form.get('location', ''),
                    'part_no': request.form.get('part_no', '').strip(),
                    'description': request.form.get('description', ''),
                    'part_type': request.form.get('part_type', ''),
                    'product_model': request.form.get('product_model', ''),
                    'quantity': -abs(safe_int(request.form.get('quantity', 0))),
                    'work_center': request.form.get('work_center', '')
                }

                # 验证数据
                if not operation_data['part_no']:
                    flash('备件编号不能为空', 'danger')
                    return render_template('smart_outbound.html',
                                           parts=parts,
                                           locations=locations,
                                           prefill_part=None,
                                           now=datetime.datetime.now())

                if operation_data['quantity'] >= 0:
                    flash('出库数量必须大于0', 'danger')
                    return render_template('smart_outbound.html',
                                           parts=parts,
                                           locations=locations,
                                           prefill_part=None,
                                           now=datetime.datetime.now())

                # 检查库存是否充足
                part = get_spare_part_by_part_no(operation_data['part_no'])
                if part:
                    current_stock = safe_int(part[4])
                    outbound_quantity = abs(operation_data['quantity'])

                    if current_stock < outbound_quantity:
                        flash(f'库存不足！当前库存: {current_stock}，出库数量: {outbound_quantity}', 'danger')
                        return render_template('smart_outbound.html',
                                               parts=parts,
                                               locations=locations,
                                               prefill_part=part,
                                               now=datetime.datetime.now())

                # 创建操作记录
                operation_id = create_operation_record(operation_data)
                flash(f'出库操作成功！操作记录ID: {operation_id}', 'success')

                return redirect(url_for('operation_records', page=1))

            except Exception as e:
                app.logger.error(f"智能出库操作失败: {str(e)}")
                flash(f'出库操作失败: {str(e)}', 'danger')
                return render_template('smart_outbound.html',
                                       parts=parts,
                                       locations=locations,
                                       prefill_part=None,
                                       now=datetime.datetime.now())

        # GET请求
        try:
            part_no = request.args.get('part_no', '')
            part_id = request.args.get('part_id', '')
            part = None

            if part_no:
                part = get_spare_part_by_part_no(part_no)
            elif part_id:
                part = get_spare_part_by_id(safe_int(part_id))

            return render_template('smart_outbound.html',
                                   parts=parts,
                                   locations=locations,
                                   prefill_part=part,
                                   now=datetime.datetime.now())

        except Exception as e:
            app.logger.error(f"加载智能出库页面失败: {str(e)}")
            flash('加载页面失败', 'danger')
            return render_template('smart_outbound.html',
                                   parts=parts,
                                   locations=locations,
                                   prefill_part=None,
                                   now=datetime.datetime.now())

    # 其他路由保持不变...
    @app.route('/outbound_part/<int:part_id>')
    def outbound_part(part_id):
        """备件出库页面 - 重定向到智能出库"""
        return redirect(url_for('smart_outbound', part_id=part_id))

    @app.route('/api/part_info/<string:part_no>')
    def get_part_info(part_no):
        """获取备件信息API"""
        try:
            part = get_spare_part_by_part_no(part_no)
            if part:
                return jsonify({
                    'success': True,
                    'part': {
                        'id': part[0],
                        'part_no': part[1],
                        'name': part[2],
                        'type': part[3],
                        'current_stock': part[4],
                        'min_stock': part[5],
                        'max_stock': part[6],
                        'location': part[11],
                        'unit': part[10]
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '备件不存在'
                })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': str(e)
            })

    @app.route('/api/operation_stats/<string:part_no>')
    def get_operation_stats(part_no):
        """获取备件操作统计API"""
        try:
            stats = get_operation_statistics(part_no)
            return jsonify({
                'success': True,
                'stats': stats
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': str(e)
            })

    @app.route('/quick_inbound', methods=['POST'])
    def quick_inbound():
        """快速入库API"""
        try:
            data = request.get_json()
            operation_data = {
                'operation_type': 'Stock in',
                'part_no': data.get('part_no'),
                'quantity': safe_int(data.get('quantity', 0)),
                'description': data.get('description', '快速入库'),
                'location': data.get('location', '')
            }

            if not operation_data['part_no'] or operation_data['quantity'] <= 0:
                return jsonify({'success': False, 'message': '参数错误'})

            operation_id = create_operation_record(operation_data)
            return jsonify({'success': True, 'operation_id': operation_id})

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/quick_outbound', methods=['POST'])
    def quick_outbound():
        """快速出库API"""
        try:
            data = request.get_json()
            operation_data = {
                'operation_type': 'Stock out',
                'part_no': data.get('part_no'),
                'quantity': -abs(safe_int(data.get('quantity', 0))),
                'description': data.get('description', '快速出库'),
                'location': data.get('location', '')
            }

            if not operation_data['part_no'] or operation_data['quantity'] >= 0:
                return jsonify({'success': False, 'message': '参数错误'})

            # 检查库存
            part = get_spare_part_by_part_no(operation_data['part_no'])
            if part and safe_int(part[4]) < abs(operation_data['quantity']):
                return jsonify({'success': False, 'message': '库存不足'})

            operation_id = create_operation_record(operation_data)
            return jsonify({'success': True, 'operation_id': operation_id})

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
# [file content end]