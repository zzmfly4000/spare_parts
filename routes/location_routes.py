from flask import render_template, request, redirect, url_for, flash
from models.database import (
    get_all_locations, get_location_by_code,
    create_location_fast as create_location,  # 使用别名
    update_location_fast as update_location,  # 使用别名
    delete_location,
    update_location_status
)
from utils.stock_utils import calculate_location_status


def setup_location_routes(app):
    """设置库位管理路由"""

    @app.route('/location_management')
    def location_management():
        """库位列表页面"""
        # 获取搜索参数
        search = request.args.get('search', '')
        status_filter = request.args.get('status_filter', '')

        # 获取所有库位
        locations = get_all_locations()

        # 处理搜索和筛选
        filtered_locations = []
        for location in locations:
            # 应用搜索筛选
            if search:
                search_lower = search.lower()
                location_code = str(
                    location[0] if isinstance(location, tuple) else location.get('location_code', '')).lower()
                description = str(
                    location[8] if isinstance(location, tuple) else location.get('description', '')).lower()

                if (search_lower not in location_code and
                        search_lower not in description):
                    continue

            # 应用状态筛选
            if status_filter:
                status = str(location[5] if isinstance(location, tuple) else location.get('status', '')).lower()
                if status_filter.lower() != status:
                    continue

            filtered_locations.append(location)

        return render_template('location_management.html',
                               locations=filtered_locations,
                               search=search,
                               status_filter=status_filter)

    @app.route('/add_location', methods=['GET', 'POST'])
    def add_location():
        """添加库位页面"""
        if request.method == 'POST':
            # 获取表单数据
            location_data = {
                'location_code': request.form.get('location_code', '').strip(),
                'rack': request.form.get('rack', '').strip(),
                'level': request.form.get('level', '').strip(),
                'position': request.form.get('position', '').strip(),
                'side': request.form.get('side', '').strip(),
                'status': request.form.get('status', 'free'),
                'capacity': int(request.form.get('capacity', 0)),
                'size_type': request.form.get('size_type', '').strip(),
                'description': request.form.get('description', '').strip()
            }

            # 验证数据
            if not location_data['location_code']:
                flash('库位代码不能为空', 'error')
                return render_template('add_location.html', location_data=location_data)

            # 创建库位
            try:
                create_location(location_data)  # 现在调用的是 create_location_fast
                flash('库位添加成功', 'success')
                return redirect(url_for('location_management'))
            except Exception as e:
                flash(f'库位添加失败: {str(e)}', 'error')

        return render_template('add_location.html')

    @app.route('/edit_location/<string:location_code>', methods=['GET', 'POST'])
    def edit_location(location_code):
        """编辑库位页面"""
        # 获取库位信息
        location = get_location_by_code(location_code)
        if not location:
            flash('库位不存在', 'error')
            return redirect(url_for('location_management'))

        if request.method == 'POST':
            # 获取表单数据
            location_data = {
                'rack': request.form.get('rack', '').strip(),
                'level': request.form.get('level', '').strip(),
                'position': request.form.get('position', '').strip(),
                'side': request.form.get('side', '').strip(),
                'status': request.form.get('status', 'free'),
                'capacity': int(request.form.get('capacity', 0)),
                'size_type': request.form.get('size_type', '').strip(),
                'description': request.form.get('description', '').strip()
            }

            # 更新库位
            try:
                update_location(location_code, location_data)  # 现在调用的是 update_location_fast
                flash('库位更新成功', 'success')
                return redirect(url_for('location_detail', location_code=location_code))
            except Exception as e:
                flash(f'库位更新失败: {str(e)}', 'error')

        # 将location元组转换为字典以便在模板中使用
        if isinstance(location, tuple):
            location_dict = {
                'location_code': location[0],
                'rack': location[1],
                'level': location[2],
                'position': location[3],
                'side': location[4],
                'status': location[5],
                'capacity': location[6],
                'size_type': location[7],
                'description': location[8],
                'part_count': location[9] if len(location) > 9 else 0,
                'last_updated': location[10] if len(location) > 10 else None
            }
        else:
            location_dict = location

        return render_template('edit_location.html', location=location_dict)

    @app.route('/location_detail/<string:location_code>')
    def location_detail(location_code):
        """库位详情页面"""
        location = get_location_by_code(location_code)
        if not location:
            flash('库位不存在', 'error')
            return redirect(url_for('location_management'))

        # 计算库位状态
        if isinstance(location, tuple):
            part_count = location[9] if len(location) > 9 else 0
            capacity = location[6] if len(location) > 6 else 0
        else:
            part_count = location.get('part_count', 0)
            capacity = location.get('capacity', 0)

        location_status = calculate_location_status(part_count, capacity)

        # 转换location为字典
        if isinstance(location, tuple):
            location_dict = {
                'location_code': location[0],
                'rack': location[1],
                'level': location[2],
                'position': location[3],
                'side': location[4],
                'status': location[5],
                'capacity': location[6],
                'size_type': location[7],
                'description': location[8],
                'part_count': part_count,
                'last_updated': location[10] if len(location) > 10 else None
            }
        else:
            location_dict = location

        return render_template('location_detail.html',
                               location=location_dict,
                               location_status=location_status)

    @app.route('/delete_location/<string:location_code>', methods=['POST'])
    def delete_location_route(location_code):
        """删除库位"""
        try:
            delete_location(location_code)
            flash('库位删除成功', 'success')
        except Exception as e:
            flash(f'库位删除失败: {str(e)}', 'error')

        return redirect(url_for('location_management'))