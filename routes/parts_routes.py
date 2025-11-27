from flask import render_template, request, redirect, url_for, flash, jsonify
from models.database import (
    DatabaseManager,
    create_spare_part,
    update_spare_part,
    delete_spare_part,
    get_spare_part_by_id,
    get_spare_part_by_part_no,
    get_all_spare_parts,
    get_low_stock_parts,
    recalculate_all_stock,
    batch_update_parts,
    batch_delete_parts,
    get_operation_statistics
)
import logging
from utils.helpers import safe_int, safe_float, safe_str
import datetime  # 添加这行导入


def setup_parts_routes(app):
    """设置备件管理路由 - 增强版本"""

    @app.route('/parts')
    def parts_list():
        """备件列表页面 - 增强版本"""
        try:
            # 获取搜索和筛选参数
            search = request.args.get('search', '')
            type_filter = request.args.get('type_filter', '')
            stock_status = request.args.get('stock_status', '')
            page = safe_int(request.args.get('page', 1))
            per_page = safe_int(request.args.get('per_page', 20))

            # 获取所有备件
            parts = get_all_spare_parts()

            # 应用搜索筛选
            filtered_parts = []
            for part in parts:
                # 搜索过滤
                if search:
                    search_lower = search.lower()
                    if (search_lower not in safe_str(part[1]).lower() and  # part_no
                            search_lower not in safe_str(part[2]).lower() and  # name
                            search_lower not in safe_str(part[4]).lower()):  # product_model
                        continue

                # 类型过滤
                if type_filter and safe_str(part[3]) != type_filter:
                    continue

                # 库存状态过滤
                if stock_status:
                    current_stock = safe_int(part[5])
                    min_stock = safe_int(part[6])

                    if stock_status == 'low' and current_stock > min_stock:
                        continue
                    elif stock_status == 'out' and current_stock > 0:
                        continue
                    elif stock_status == 'normal' and current_stock <= min_stock:
                        continue

                filtered_parts.append(part)

            # 分页
            total_parts = len(filtered_parts)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_parts = filtered_parts[start_idx:end_idx]

            return render_template('parts_list.html',
                                   parts=paginated_parts,
                                   total_parts=total_parts,
                                   page=page,
                                   per_page=per_page,
                                   search=search,
                                   type_filter=type_filter,
                                   stock_status=stock_status,
                                   now=datetime.datetime.now())

        except Exception as e:
            app.logger.error(f"加载备件列表失败: {str(e)}")
            flash('加载备件列表失败', 'danger')
            return render_template('parts_list.html',
                                   parts=[],
                                   total_parts=0,
                                   page=1,
                                   per_page=20,
                                   search='',
                                   type_filter='',
                                   stock_status='',
                                   now=datetime.datetime.now())

    @app.route('/part/<int:part_id>')
    def part_detail(part_id):
        """备件详情页面"""
        try:
            part = get_spare_part_by_id(part_id)
            if not part:
                flash('备件不存在', 'danger')
                return redirect(url_for('parts_list'))

            return render_template('part_detail.html', part=part)

        except Exception as e:
            app.logger.error(f"加载备件详情失败: {str(e)}")
            flash('加载备件详情失败', 'danger')
            return redirect(url_for('parts_list'))

    @app.route('/part/add', methods=['GET', 'POST'])
    def add_part():
        """添加新备件"""
        if request.method == 'POST':
            try:
                part_data = {
                    'part_no': request.form.get('part_no', '').strip(),
                    'name': request.form.get('name', '').strip(),
                    'type': request.form.get('type', '').strip(),
                    'product_model': request.form.get('product_model', '').strip(),  # 新增字段
                    'current_stock': safe_int(request.form.get('current_stock', 0)),
                    'min_stock': safe_int(request.form.get('min_stock', 0)),
                    'max_stock': safe_int(request.form.get('max_stock', 0)),
                    'key_part': bool(request.form.get('key_part')),
                    'lt_weeks': safe_int(request.form.get('lt_weeks', 0)),
                    'unit_price': safe_float(request.form.get('unit_price', 0.0)),
                    'unit': request.form.get('unit', '').strip(),
                    'location': request.form.get('location', '').strip(),
                    'supplier': request.form.get('supplier', '').strip(),
                    'description': request.form.get('description', '').strip()
                }

                part_id = create_spare_part(part_data)
                flash('备件添加成功', 'success')
                return redirect(url_for('part_detail', part_id=part_id))

            except ValueError as e:
                flash(str(e), 'danger')
            except Exception as e:
                app.logger.error(f"添加备件失败: {str(e)}")
                flash('添加备件失败', 'danger')

        return render_template('add_part.html')

    @app.route('/part/<int:part_id>/edit', methods=['GET', 'POST'])
    def edit_part(part_id):
        """编辑备件信息"""
        part = get_spare_part_by_id(part_id)
        if not part:
            flash('备件不存在', 'danger')
            return redirect(url_for('parts_list'))

        if request.method == 'POST':
            try:
                update_data = {
                    'part_no': request.form.get('part_no', '').strip(),
                    'name': request.form.get('name', '').strip(),
                    'type': request.form.get('type', '').strip(),
                    'product_model': request.form.get('product_model', '').strip(),  # 新增字段
                    'min_stock': safe_int(request.form.get('min_stock', 0)),
                    'max_stock': safe_int(request.form.get('max_stock', 0)),
                    'key_part': bool(request.form.get('key_part')),
                    'lt_weeks': safe_int(request.form.get('lt_weeks', 0)),
                    'unit_price': safe_float(request.form.get('unit_price', 0.0)),
                    'unit': request.form.get('unit', '').strip(),
                    'location': request.form.get('location', '').strip(),
                    'supplier': request.form.get('supplier', '').strip(),
                    'description': request.form.get('description', '').strip()
                }

                # 移除空值
                update_data = {k: v for k, v in update_data.items() if v is not None and v != ''}

                update_spare_part(part_id, update_data)
                flash('备件更新成功', 'success')
                return redirect(url_for('part_detail', part_id=part_id))

            except ValueError as e:
                flash(str(e), 'danger')
            except Exception as e:
                app.logger.error(f"更新备件失败: {str(e)}")
                flash('更新备件失败', 'danger')

        return render_template('edit_part.html', part=part)

    @app.route('/part/<int:part_id>/delete', methods=['POST'])
    def delete_part(part_id):
        """删除备件"""
        try:
            deleted_count = delete_spare_part(part_id)
            if deleted_count > 0:
                flash('备件删除成功', 'success')
            else:
                flash('备件不存在', 'warning')
        except Exception as e:
            app.logger.error(f"删除备件失败: {str(e)}")
            flash('删除备件失败', 'danger')

        return redirect(url_for('parts_list'))

    @app.route('/parts/batch_update', methods=['POST'])
    def batch_update_parts_route():
        """批量更新备件"""
        try:
            update_data = request.get_json()
            if not update_data:
                return jsonify({'success': False, 'message': '没有提供更新数据'})

            updated_count, errors = batch_update_parts(update_data)

            if errors:
                return jsonify({
                    'success': False,
                    'message': f'部分更新失败',
                    'updated_count': updated_count,
                    'errors': errors
                })

            return jsonify({
                'success': True,
                'message': f'成功更新 {updated_count} 个备件',
                'updated_count': updated_count
            })

        except Exception as e:
            app.logger.error(f"批量更新备件失败: {str(e)}")
            return jsonify({'success': False, 'message': f'批量更新失败: {str(e)}'})

    @app.route('/parts/batch_delete', methods=['POST'])
    def batch_delete_parts_route():
        """批量删除备件"""
        try:
            part_ids = request.get_json()
            if not part_ids:
                return jsonify({'success': False, 'message': '没有选择备件'})

            deleted_count = batch_delete_parts(part_ids)

            return jsonify({
                'success': True,
                'message': f'成功删除 {deleted_count} 个备件',
                'deleted_count': deleted_count
            })

        except Exception as e:
            app.logger.error(f"批量删除备件失败: {str(e)}")
            return jsonify({'success': False, 'message': f'批量删除失败: {str(e)}'})

    @app.route('/parts/recalculate_stock', methods=['POST'])
    def recalculate_stock():
        """重新计算所有备件库存"""
        try:
            updated_count = recalculate_all_stock()
            flash(f'成功重新计算 {updated_count} 个备件的库存', 'success')
        except Exception as e:
            app.logger.error(f"重新计算库存失败: {str(e)}")
            flash('重新计算库存失败', 'danger')

        return redirect(url_for('parts_list'))

    from flask import jsonify, request
    import logging

    # 在 setup_parts_routes 函数中添加以下路由

    @app.route('/api/search_parts')
    def api_search_parts():
        """智能搜索备件API"""
        keyword = request.args.get('keyword', '').strip()
        if not keyword:
            return jsonify({'success': False, 'message': '请输入搜索关键词'})

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 在备件编号、名称、类型、描述、供应商、产品型号中搜索
                search_pattern = f'%{keyword}%'
                parts = conn.execute('''
                    SELECT id, part_no, name, type, product_model, current_stock, min_stock, 
                           location, description, supplier, unit
                    FROM spare_parts 
                    WHERE part_no LIKE ? OR name LIKE ? OR type LIKE ? OR description LIKE ? 
                          OR supplier LIKE ? OR product_model LIKE ?
                    ORDER BY 
                        CASE 
                            WHEN part_no = ? THEN 1
                            WHEN part_no LIKE ? THEN 2
                            WHEN name LIKE ? THEN 3
                            ELSE 4
                        END,
                        part_no
                    LIMIT 20
                ''', (search_pattern, search_pattern, search_pattern, search_pattern,
                      search_pattern, search_pattern, keyword, f'{keyword}%', f'{keyword}%')).fetchall()

                results = []
                for part in parts:
                    results.append({
                        'id': part[0],
                        'part_no': part[1],
                        'name': part[2],
                        'type': part[3],
                        'product_model': part[4],
                        'current_stock': part[5],
                        'min_stock': part[6],
                        'location': part[7],
                        'description': part[8],
                        'supplier': part[9],
                        'unit': part[10]
                    })

                return jsonify({
                    'success': True,
                    'results': results,
                    'count': len(results)
                })

        except Exception as e:
            logging.error(f'搜索备件失败: {str(e)}')
            return jsonify({'success': False, 'message': f'搜索失败: {str(e)}'})

    @app.route('/api/part_info/<part_no>')
    def api_part_info(part_no):
        """获取备件详细信息API"""
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
                        'product_model': part[4],
                        'current_stock': part[5],
                        'min_stock': part[6],
                        'max_stock': part[7],
                        'key_part': part[8],
                        'lt_weeks': part[9],
                        'unit_price': part[10],
                        'unit': part[11],
                        'location': part[12],
                        'supplier': part[13],
                        'description': part[14]
                    }
                })
            else:
                return jsonify({'success': False, 'message': '备件不存在'})
        except Exception as e:
            logging.error(f'获取备件信息失败: {str(e)}')
            return jsonify({'success': False, 'message': f'获取备件信息失败: {str(e)}'})

    @app.route('/api/operation_stats/<part_no>')
    def api_operation_stats(part_no):
        """获取备件操作统计API"""
        try:
            stats = get_operation_statistics(part_no)
            return jsonify({
                'success': True,
                'stats': stats
            })
        except Exception as e:
            logging.error(f'获取操作统计失败: {str(e)}')
            return jsonify({
                'success': True,
                'stats': {
                    'new_parts_in': 0,
                    'disassemble_parts_in': 0,
                    'return_parts_in': 0,
                    'parts_out': 0
                }
            })

    @app.route('/api/create_part', methods=['POST'])
    def api_create_part():
        """创建新备件API"""
        try:
            data = request.get_json()
            if not data.get('part_no') or not data.get('name'):
                return jsonify({'success': False, 'message': '备件编号和名称不能为空'})

            part_data = {
                'part_no': data['part_no'],
                'name': data['name'],
                'type': data.get('type', ''),
                'product_model': data.get('product_model', ''),  # 新增字段
                'current_stock': data.get('current_stock', 0),
                'min_stock': data.get('min_stock', 0),
                'max_stock': data.get('max_stock', 0),
                'unit': data.get('unit', ''),
                'location': data.get('location', ''),
                'supplier': data.get('supplier', ''),
                'description': data.get('description', '')
            }

            part_id = create_spare_part(part_data)
            return jsonify({
                'success': True,
                'message': '备件创建成功',
                'part_id': part_id
            })

        except Exception as e:
            logging.error(f'创建备件失败: {str(e)}')
            return jsonify({'success': False, 'message': f'创建备件失败: {str(e)}'})