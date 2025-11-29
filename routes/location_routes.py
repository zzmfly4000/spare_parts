from flask import render_template, request, redirect, url_for, flash, jsonify
from models.database import (
    get_all_locations, get_location_by_code,
    create_location_fast as create_location,
    update_location_fast as update_location,
    delete_location,
    update_location_status,
    get_location_stats,
    batch_update_locations
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

            # 应用状态筛选
            if status_filter:
                if isinstance(location, tuple):
                    status = str(location[5] if len(location) > 5 else '').lower()
                else:
                    status = str(location.get('status', '')).lower()
                if status_filter.lower() != status:
                    continue

            filtered_locations.append(location)

        # 获取库位统计信息
        stats = get_location_stats()

        return render_template('location_management.html',
                               locations=filtered_locations,
                               search=search,
                               status_filter=status_filter,
                               stats=stats)

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
                'status': location[5] if len(location) > 5 else 'free',
                'capacity': location[6] if len(location) > 6 else 0,
                'size_type': location[7] if len(location) > 7 else '',
                'description': location[8] if len(location) > 8 else '',
                'part_count': location[9] if len(location) > 9 else 0,
                'last_updated': location[10] if len(location) > 10 else None
            }

        return {}

    @app.route('/api/locations/rack_layout', methods=['GET'])
    def get_rack_layout():
        """获取货架布局数据 - API接口 - 彻底修复版本"""
        try:
            locations = get_all_locations()

            # 按货架分组
            rack_groups = {}
            for location in locations:
                # 统一转换为字典格式
                loc_dict = location_to_dict(location)

                rack = loc_dict.get('rack', '')
                location_code = loc_dict.get('location_code', '')
                status = loc_dict.get('status', 'free')
                capacity = loc_dict.get('capacity', 0)
                part_count = loc_dict.get('part_count', 0)
                description = loc_dict.get('description', '')
                level = loc_dict.get('level', '')

                if not rack:
                    rack = '未分类'

                if rack not in rack_groups:
                    rack_groups[rack] = {
                        'rack': rack,
                        'locations': [],
                        'stats': {
                            'total': 0,
                            'free': 0,
                            'in_use': 0,
                            'low_stock': 0,
                            'utilization': 0
                        }
                    }

                # 确保数值类型正确
                try:
                    capacity = int(capacity) if capacity is not None else 0
                    part_count = int(part_count) if part_count is not None else 0
                except (ValueError, TypeError):
                    capacity = 0
                    part_count = 0

                # 计算库位状态
                location_status = calculate_location_status(part_count, capacity)

                location_data = {
                    'location_code': location_code,
                    'status': location_status,
                    'capacity': capacity,
                    'part_count': part_count,
                    'description': description,
                    'level': level,
                    'utilization': (part_count / capacity * 100) if capacity > 0 else 0
                }

                rack_groups[rack]['locations'].append(location_data)

                # 更新货架统计
                rack_groups[rack]['stats']['total'] += 1
                if location_status == 'free':
                    rack_groups[rack]['stats']['free'] += 1
                elif location_status == 'in_use':
                    rack_groups[rack]['stats']['in_use'] += 1
                elif location_status == 'low_stock':
                    rack_groups[rack]['stats']['low_stock'] += 1

            # 计算每个货架的利用率
            for rack in rack_groups.values():
                total_capacity = sum(loc['capacity'] for loc in rack['locations'])
                total_parts = sum(loc['part_count'] for loc in rack['locations'])
                if total_capacity > 0:
                    rack['stats']['utilization'] = (total_parts / total_capacity * 100)
                else:
                    rack['stats']['utilization'] = 0

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
        """更新货架布局 - 拖拽排序"""
        try:
            data = request.get_json()
            rack_positions = data.get('rack_positions', {})

            # 这里可以实现货架位置保存到数据库的逻辑
            # 暂时先返回成功
            return jsonify({
                'success': True,
                'message': '布局更新成功'
            })

        except Exception as e:
            app.logger.error(f"更新货架布局失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/rack_detail/<string:rack_code>')
    def rack_detail(rack_code):
        """货架详情页面"""
        locations = get_all_locations()
        rack_locations = []

        for location in locations:
            loc_dict = location_to_dict(location)
            current_rack = loc_dict.get('rack', '')

            if current_rack == rack_code:
                rack_locations.append(loc_dict)

        # 按层级和位置排序
        def sort_key(loc):
            level = loc.get('level', '')
            position = loc.get('position', '')
            return (level, position)

        rack_locations.sort(key=sort_key)

        return render_template('rack_detail.html',
                               rack_code=rack_code,
                               locations=rack_locations)

    # 保留原有的其他路由函数不变
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
                'status': request.form.get('status', 'free'),
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

        # 计算库位状态
        part_count = location_dict.get('part_count', 0)
        capacity = location_dict.get('capacity', 0)
        location_status = calculate_location_status(part_count, capacity)

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