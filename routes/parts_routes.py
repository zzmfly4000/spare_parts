from flask import render_template, request, redirect, url_for, flash
from models.database import (get_all_spare_parts, get_spare_part_by_id,
                             create_spare_part, update_spare_part, delete_spare_part)
# 修复导入问题
from utils.stock_utils import calculate_stock_status


def setup_parts_routes(app):
    """设置备件管理路由"""

    @app.route('/parts')
    def parts_list():
        """备件列表页面"""
        # 获取搜索参数
        search = request.args.get('search', '')
        type_filter = request.args.get('type_filter', '')
        location_filter = request.args.get('location_filter', '')
        stock_status = request.args.get('stock_status', '')

        # 获取所有备件
        parts = get_all_spare_parts()

        # 处理搜索和筛选
        filtered_parts = []
        for part in parts:
            # 这里应该实现实际的搜索和筛选逻辑
            # 为简化示例，直接添加所有备件
            filtered_parts.append(part)

        return render_template('parts_list.html', parts=filtered_parts)

    @app.route('/add_part', methods=['GET', 'POST'])
    def add_part():
        """添加备件页面"""
        if request.method == 'POST':
            # 获取表单数据
            part_data = {
                'part_no': request.form.get('part_no', ''),
                'name': request.form.get('name', ''),
                'type': request.form.get('type', ''),
                'current_stock': int(request.form.get('current_stock', 0)),
                'min_stock': int(request.form.get('min_stock', 0)),
                'max_stock': int(request.form.get('max_stock', 0)),
                'key_part': bool(request.form.get('key_part', False)),
                'lt_weeks': int(request.form.get('lt_weeks', 0)),
                'unit_price': float(request.form.get('unit_price', 0.0)),
                'unit': request.form.get('unit', ''),
                'location': request.form.get('location', ''),
                'supplier': request.form.get('supplier', ''),
                'description': request.form.get('description', '')
            }

            # 创建备件
            try:
                create_spare_part(part_data)
                flash('备件添加成功', 'success')
                return redirect(url_for('parts_list'))
            except Exception as e:
                flash(f'备件添加失败: {str(e)}', 'error')

        return render_template('add_part.html')

    @app.route('/edit_part/<int:part_id>', methods=['GET', 'POST'])
    def edit_part(part_id):
        """编辑备件页面"""
        if request.method == 'POST':
            # 获取表单数据
            part_data = {
                'part_no': request.form.get('part_no', ''),
                'name': request.form.get('name', ''),
                'type': request.form.get('type', ''),
                'min_stock': int(request.form.get('min_stock', 0)),
                'max_stock': int(request.form.get('max_stock', 0)),
                'key_part': bool(request.form.get('key_part', False)),
                'lt_weeks': int(request.form.get('lt_weeks', 0)),
                'unit_price': float(request.form.get('unit_price', 0.0)),
                'unit': request.form.get('unit', ''),
                'location': request.form.get('location', ''),
                'supplier': request.form.get('supplier', ''),
                'description': request.form.get('description', '')
            }

            # 更新备件
            try:
                update_spare_part(part_id, part_data)
                flash('备件更新成功', 'success')
                return redirect(url_for('part_detail', part_id=part_id))
            except Exception as e:
                flash(f'备件更新失败: {str(e)}', 'error')

        # 获取备件信息
        part = get_spare_part_by_id(part_id)
        if not part:
            flash('备件不存在', 'error')
            return redirect(url_for('parts_list'))

        return render_template('edit_part.html', part=part)

    @app.route('/part/<int:part_id>')
    def part_detail(part_id):
        """备件详情页面"""
        part = get_spare_part_by_id(part_id)
        if not part:
            flash('备件不存在', 'error')
            return redirect(url_for('parts_list'))

        # 计算库存状态
        stock_status = calculate_stock_status(part[4], part[5])  # current_stock, min_stock

        return render_template('part_detail.html', part=part, stock_status=stock_status)

    @app.route('/delete_part/<int:part_id>')
    def delete_part_route(part_id):
        """删除备件"""
        try:
            delete_spare_part(part_id)
            flash('备件删除成功', 'success')
        except Exception as e:
            flash(f'备件删除失败: {str(e)}', 'error')

        return redirect(url_for('parts_list'))