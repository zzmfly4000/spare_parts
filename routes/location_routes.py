from flask import render_template, request, redirect, url_for, flash, jsonify
from models.database import (
    get_all_locations, get_location_by_code,
    create_location_fast as create_location,
    update_location_fast as update_location,
    delete_location,
    update_location_status,
    get_location_stats,
    batch_update_locations,
    get_rack_layout,
    save_rack_layout,
    get_all_rack_layouts,
    get_spare_parts_count,
    get_accurate_location_stats,
    get_rack_statistics
)
from utils.stock_utils import calculate_location_status
import json


def setup_location_routes(app):
    """设置库位管理路由"""

    @app.route('/location_management')
    def location_management():
        """库位列表页面 - 优化版本"""
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
                if isinstance(location, tuple):
                    location_code = str(location[0]).lower()
                    description = str(location[8] if len(location) > 8 else '').lower()
                else:
                    location_code = str(location.get('location_code', '')).lower()
                    description = str(location.get('description', '')).lower()

                if (search_lower not in location_code and
                        search_lower not in description):
                    continue

            # 应用状态筛选 - 优化状态判断
            if status_filter:
                loc_dict = location_to_dict(location)
                part_count = loc_dict.get('part_count', 0)

                # 优化状态判断逻辑
                if status_filter == 'in_use':
                    # in_use 包括所有分配了备件的库位
                    if part_count == 0:
                        continue
                elif status_filter == 'not_use':
                    # not_use 仅包括未分配备件的库位
                    if part_count > 0:
                        continue
                else:
                    # 具体状态筛选
                    current_status = loc_dict.get('status', 'not_use')
                    if status_filter != current_status:
                        continue

            filtered_locations.append(location)

        # 获取准确的库位统计信息
        stats = get_accurate_location_stats()

        return render_template('location_management.html',
                               locations=filtered_locations,
                               search=search,
                               status_filter=status_filter,
                               stats=stats)

    def get_accurate_location_stats():
        """获取准确的库位统计信息 - 优化版本"""
        locations = get_all_locations()

        total_locations = len(locations)
        free_locations = 0
        in_use_locations = 0
        low_stock_locations = 0
        out_of_stock_locations = 0
        high_stock_locations = 0
        not_use_locations = 0

        for location in locations:
            loc_dict = location_to_dict(location)
            part_count = loc_dict.get('part_count', 0)
            status = loc_dict.get('status', 'not_use')

            # 优化统计逻辑
            if part_count == 0:
                not_use_locations += 1
            else:
                in_use_locations += 1
                if status == 'free':
                    free_locations += 1
                elif status == 'low_stock':
                    low_stock_locations += 1
                elif status == 'out_of_stock':
                    out_of_stock_locations += 1
                elif status == 'high_stock':
                    high_stock_locations += 1

        return {
            'total_locations': total_locations,
            'in_use_locations': in_use_locations,
            'not_use_locations': not_use_locations,
            'free_locations': free_locations,
            'low_stock_locations': low_stock_locations,
            'out_of_stock_locations': out_of_stock_locations,
            'high_stock_locations': high_stock_locations
        }

    def location_to_dict(location):
        """将位置数据转换为字典格式 - 修复 sqlite3.Row 问题"""
        if isinstance(location, dict):
            return location

        # 处理 sqlite3.Row 对象
        if hasattr(location, '_fields'):
            return {field: location[i] for i, field in enumerate(location._fields)}

        # 处理元组格式
        if isinstance(location, tuple):
            return {
                'location_code': location[0] if len(location) > 0 else '',
                'rack': location[1] if len(location) > 1 else '',
                'level': location[2] if len(location) > 2 else '',
                'position': location[3] if len(location) > 3 else '',
                'side': location[4] if len(location) > 4 else '',
                'status': location[5] if len(location) > 5 else 'not_use',
                'capacity': location[6] if len(location) > 6 else 0,
                'size_type': location[7] if len(location) > 7 else '',
                'description': location[8] if len(location) > 8 else '',
                'part_count': location[9] if len(location) > 9 else 0,
                'last_updated': location[10] if len(location) > 10 else None
            }

        return {}

    @app.route('/api/locations/rack_layout', methods=['GET'])
    def get_rack_layout_api():
        """获取货架布局数据 - API接口 - 优化版本"""
        try:
            locations = get_all_locations()
            rack_layouts = get_all_rack_layouts()
            rack_stats = get_rack_statistics()

            # 按货架分组
            rack_groups = {}
            for location in locations:
                # 统一转换为字典格式
                loc_dict = location_to_dict(location)

                rack = loc_dict.get('rack', '')
                location_code = loc_dict.get('location_code', '')
                capacity = loc_dict.get('capacity', 0)
                part_count = loc_dict.get('part_count', 0)
                description = loc_dict.get('description', '')
                level = loc_dict.get('level', '')
                position = loc_dict.get('position', '')
                side = loc_dict.get('side', '')

                if not rack:
                    rack = '未分类'

                if rack not in rack_groups:
                    # 获取货架布局
                    layout = rack_layouts.get(rack, {
                        'x': 100 + len(rack_groups) * 50,
                        'y': 100 + len(rack_groups) * 30,
                        'width': 300,
                        'height': 200,
                        'rotation': 0
                    })

                    # 获取货架统计
                    stats = rack_stats.get(rack, {
                        'total_locations': 0,
                        'in_use_locations': 0,
                        'not_use_locations': 0,
                        'total_parts': 0,
                        'total_capacity': 0,
                        'utilization': 0
                    })

                    rack_groups[rack] = {
                        'rack': rack,
                        'locations': [],
                        'stats': {
                            'total': stats['total_locations'],
                            'in_use': stats['in_use_locations'],
                            'not_use': stats['not_use_locations'],
                            'utilization': stats['utilization']
                        },
                        'levels': set(),
                        'positions': set(),
                        'sides': set(),
                        'layout': layout
                    }

                # 计算库位状态 - 根据 part_count 判断
                location_status = 'in_use' if part_count > 0 else 'not_use'

                location_data = {
                    'location_code': location_code,
                    'status': location_status,
                    'capacity': capacity,
                    'part_count': part_count,
                    'description': description,
                    'level': level,
                    'position': position,
                    'side': side
                }

                rack_groups[rack]['locations'].append(location_data)

                # 收集结构信息
                if level:
                    rack_groups[rack]['levels'].add(level)
                if position:
                    rack_groups[rack]['positions'].add(position)
                if side:
                    rack_groups[rack]['sides'].add(side)

            # 转换集合为排序列表
            for rack in rack_groups.values():
                rack['levels'] = sorted(list(rack['levels']))
                rack['positions'] = sorted(list(rack['positions']))
                rack['sides'] = sorted(list(rack['sides']))

            return jsonify({
                'success': True,
                'racks': list(rack_groups.values())
            })

        except Exception as e:
            app.logger.error(f"获取货架布局失败: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/locations/update_layout', methods=['POST'])
    def update_rack_layout():
        """更新货架布局 - 支持位置和尺寸"""
        try:
            data = request.get_json()
            rack_layouts = data.get('rack_layouts', {})

            # 保存布局到数据库
            for rack, layout in rack_layouts.items():
                save_rack_layout(rack, layout)

            app.logger.info(f"成功保存 {len(rack_layouts)} 个货架布局")

            return jsonify({
                'success': True,
                'message': '布局保存成功',
                'data': rack_layouts
            })

        except Exception as e:
            app.logger.error(f"更新货架布局失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/rack_detail/<string:rack_code>')
    def rack_detail(rack_code):
        """货架详情页面 - 显示内部结构"""
        locations = get_all_locations()
        rack_locations = []

        for location in locations:
            loc_dict = location_to_dict(location)
            current_rack = loc_dict.get('rack', '')

            if current_rack == rack_code:
                rack_locations.append(loc_dict)

        # 按层级、侧面和位置排序
        def sort_key(loc):
            level = loc.get('level', '')
            side = loc.get('side', '')
            position = loc.get('position', '')
            return (level, side, position)

        rack_locations.sort(key=sort_key)

        # 计算货架统计
        total_locations = len(rack_locations)
        free_count = sum(1 for loc in rack_locations if loc.get('status') == 'free')
        in_use_count = sum(1 for loc in rack_locations if loc.get('status') == 'in_use')
        low_stock_count = sum(1 for loc in rack_locations if loc.get('status') == 'low_stock')

        # 获取层级、侧面、位置信息
        levels = sorted(set(loc.get('level', '') for loc in rack_locations if loc.get('level')))
        sides = sorted(set(loc.get('side', '') for loc in rack_locations if loc.get('side')))
        positions = sorted(set(loc.get('position', '') for loc in rack_locations if loc.get('position')))

        return render_template('rack_detail.html',
                               rack_code=rack_code,
                               locations=rack_locations,
                               total_locations=total_locations,
                               free_count=free_count,
                               in_use_count=in_use_count,
                               low_stock_count=low_stock_count,
                               levels=levels,
                               sides=sides,
                               positions=positions)

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
                'status': 'not_use',  # 默认未使用
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
                create_location(location_data)
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
                'capacity': int(request.form.get('capacity', 0)),
                'size_type': request.form.get('size_type', '').strip(),
                'description': request.form.get('description', '').strip()
            }

            # 更新库位
            try:
                update_location(location_code, location_data)
                flash('库位更新成功', 'success')
                return redirect(url_for('location_detail', location_code=location_code))
            except Exception as e:
                flash(f'库位更新失败: {str(e)}', 'error')

        # 将location转换为字典以便在模板中使用
        location_dict = location_to_dict(location)

        return render_template('edit_location.html', location=location_dict)

    @app.route('/location_detail/<string:location_code>')
    def location_detail(location_code):
        """库位详情页面"""
        location = get_location_by_code(location_code)
        if not location:
            flash('库位不存在', 'error')
            return redirect(url_for('location_management'))

        # 将location转换为字典
        location_dict = location_to_dict(location)

        # 计算库位状态 - 使用新的状态定义
        part_count = location_dict.get('part_count', 0)
        location_status = 'in_use' if part_count > 0 else 'not_use'

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
# [file content end]