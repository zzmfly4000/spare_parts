from flask import render_template, request, redirect, url_for, flash, jsonify
from models.database import (
    create_operation_record, get_spare_part_by_id, get_spare_part_by_part_no,
    get_all_operation_records, get_operation_statistics, create_spare_part,
    get_all_spare_parts, get_all_locations
)
from utils.helpers import safe_int, safe_float, safe_str, safe_datetime
import datetime
import logging


def setup_operation_routes(app):
    """设置操作记录路由 - 修复版本"""

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

        return None  # 无法解析返回 None

    @app.route('/operation_records')
    def operation_records():
        """操作记录列表页面 - 修复日期处理版本"""
        try:
            # 获取筛选参数
            operation_type = request.args.get('operation_type', '')
            date_from = request.args.get('date_from', '')
            date_to = request.args.get('date_to', '')
            part_no = request.args.get('part_no', '')
            page = safe_int(request.args.get('page', 1))
            per_page = safe_int(request.args.get('per_page', 20))

            # 获取所有操作记录
            all_operations = get_all_operation_records()

            # 应用筛选
            filtered_operations = []
            for operation in all_operations:
                # 类型筛选
                if operation_type and operation[1] != operation_type:
                    continue

                # 备件编号筛选
                if part_no and part_no.lower() not in safe_str(operation[5]).lower():
                    continue

                # 日期筛选 - 使用安全的日期解析
                op_date = parse_operation_date(operation[2])

                if date_from:
                    try:
                        date_from_dt = datetime.datetime.strptime(date_from, '%Y-%m-%d')
                        if op_date is None or op_date < date_from_dt:
                            continue
                    except ValueError:
                        pass  # 日期格式错误，跳过筛选

                if date_to:
                    try:
                        date_to_dt = datetime.datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                        if op_date is None or op_date > date_to_dt:
                            continue
                    except ValueError:
                        pass  # 日期格式错误，跳过筛选

                filtered_operations.append(operation)

            # 分页
            total_operations = len(filtered_operations)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_operations = filtered_operations[start_idx:end_idx]

            return render_template('operation_records.html',
                                   operations=paginated_operations,
                                   total_operations=total_operations,
                                   page=page,
                                   per_page=per_page,
                                   operation_type=operation_type,
                                   date_from=date_from,
                                   date_to=date_to,
                                   part_no=part_no,
                                   now=datetime.datetime.now())

        except Exception as e:
            app.logger.error(f"加载操作记录失败: {str(e)}")
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
        # 提前获取必要的数据，确保在所有返回路径中都可用
        parts = get_all_spare_parts()
        locations = get_all_locations()

        if request.method == 'POST':
            try:
                # 获取表单数据
                operation_data = {
                    'operation_type': request.form.get('operation_type', 'Stock in'),
                    'supplier_recipient': request.form.get('supplier', ''),
                    'location': request.form.get('location', ''),
                    'part_no': request.form.get('part_no', '').strip(),
                    'description': request.form.get('description', ''),
                    'part_type': request.form.get('part_type', ''),
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
                return redirect(url_for('operation_records'))

            except ValueError as e:
                error_msg = str(e)
                if "database is locked" in error_msg.lower():
                    flash('系统繁忙，请稍后重试', 'danger')
                else:
                    flash(error_msg, 'danger')

                # 确保返回有效的响应
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

        # GET请求 - 准备数据
        try:
            # 获取预填参数
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
        # 提前获取必要的数据
        parts = get_all_spare_parts()
        locations = get_all_locations()

        if request.method == 'POST':
            try:
                # 获取表单数据
                operation_data = {
                    'operation_type': 'Stock out',
                    'supplier_recipient': request.form.get('recipient', ''),
                    'location': request.form.get('location', ''),
                    'part_no': request.form.get('part_no', '').strip(),
                    'description': request.form.get('description', ''),
                    'part_type': request.form.get('part_type', ''),
                    'quantity': -abs(safe_int(request.form.get('quantity', 0))),  # 出库为负数
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
                return redirect(url_for('operation_records'))

            except Exception as e:
                app.logger.error(f"智能出库操作失败: {str(e)}")
                flash(f'出库操作失败: {str(e)}', 'danger')
                return render_template('smart_outbound.html',
                                       parts=parts,
                                       locations=locations,
                                       prefill_part=None,
                                       now=datetime.datetime.now())

        # GET请求 - 准备数据
        try:
            # 获取预填参数
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