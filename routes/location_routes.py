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
    DatabaseManager,
    get_rack_statistics
)
from utils.stock_utils import calculate_location_status
import json
from datetime import datetime
import logging


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
                variety_count = loc_dict.get('variety_count', 0)

                # 优化状态判断逻辑
                if status_filter == 'in_use':
                    # in_use 包括所有分配了备件的库位
                    if variety_count == 0:
                        continue
                elif status_filter == 'not_use':
                    # not_use 仅包括未分配备件的库位
                    if variety_count > 0:
                        continue
                else:
                    # 具体状态筛选
                    current_status = loc_dict.get('status', 'not_use')
                    if status_filter != current_status:
                        continue

            filtered_locations.append(location)

        # 获取准确的库位统计信息
        stats = get_accurate_location_stats()

        # 获取货架列表用于筛选
        locations = get_all_locations()
        rack_set = set()
        for location in locations:
            loc_dict = location_to_dict(location)
            rack = loc_dict.get('rack')
            if rack:
                rack_set.add(rack)

        return render_template('location_management.html',
                               locations=filtered_locations,
                               search=search,
                               status_filter=status_filter,
                               stats=stats,
                               rack_list=sorted(list(rack_set)))  # 添加货架列表

    def get_accurate_location_stats():
        """获取准确的库位统计信息 - 专业版本"""
        db_manager = DatabaseManager()
        with db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_locations,
                    SUM(CASE WHEN status_category = 'empty' THEN 1 ELSE 0 END) as empty_locations,
                    SUM(CASE WHEN status_category = 'all_out_of_stock' THEN 1 ELSE 0 END) as all_out_of_stock_locations,
                    SUM(CASE WHEN status_category = 'partial_out_of_stock' THEN 1 ELSE 0 END) as partial_out_of_stock_locations,
                    SUM(CASE WHEN status_category = 'all_low_stock' THEN 1 ELSE 0 END) as all_low_stock_locations,
                    SUM(CASE WHEN status_category = 'partial_low_stock' THEN 1 ELSE 0 END) as partial_low_stock_locations,
                    SUM(CASE WHEN status_category = 'full' THEN 1 ELSE 0 END) as full_locations,
                    SUM(CASE WHEN status_category = 'high_utilization' THEN 1 ELSE 0 END) as high_utilization_locations,
                    SUM(CASE WHEN status_category = 'normal' THEN 1 ELSE 0 END) as normal_locations,
                    AVG(utilization_rate) as avg_utilization_rate,
                    SUM(total_value) as total_inventory_value
                FROM locations
            ''')

            result = cursor.fetchone()
            return {
                'total_locations': result['total_locations'] or 0,
                'empty_locations': result['empty_locations'] or 0,
                'all_out_of_stock_locations': result['all_out_of_stock_locations'] or 0,
                'partial_out_of_stock_locations': result['partial_out_of_stock_locations'] or 0,
                'all_low_stock_locations': result['all_low_stock_locations'] or 0,
                'partial_low_stock_locations': result['partial_low_stock_locations'] or 0,
                'full_locations': result['full_locations'] or 0,
                'high_utilization_locations': result['high_utilization_locations'] or 0,
                'normal_locations': result['normal_locations'] or 0,
                'avg_utilization_rate': round(result['avg_utilization_rate'] or 0, 2),
                'total_inventory_value': result['total_inventory_value'] or 0
            }

    # 添加手动刷新统计的路由
    @app.route('/api/locations/refresh_metrics', methods=['POST'])
    def refresh_location_metrics():
        """手动刷新库位统计指标"""
        try:
            from models.database import update_all_location_metrics
            updated_count = update_all_location_metrics()
            return jsonify({
                'success': True,
                'updated_count': updated_count,
                'message': f'成功更新 {updated_count} 个库位的统计指标'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/locations/<location_code>/refresh_metrics', methods=['POST'])
    def refresh_single_location_metrics(location_code):
        """手动刷新单个库位统计指标"""
        try:
            from models.database import update_single_location_metrics
            success = update_single_location_metrics(location_code)
            return jsonify({
                'success': success,
                'message': f'库位 {location_code} 统计指标刷新{"成功" if success else "失败"}'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    def location_to_dict(location):
        """将位置数据转换为字典格式 - 修复 sqlite3.Row 问题"""
        if isinstance(location, dict):
            # 确保数值字段是整数
            for key in ['capacity', 'variety_count', 'total_quantity']:
                if key in location and location[key] is not None:
                    try:
                        if isinstance(location[key], str):
                            location[key] = int(location[key]) if location[key].strip() else 0
                        else:
                            location[key] = int(location[key])
                    except (ValueError, TypeError):
                        location[key] = 0
            return location

        # 处理 sqlite3.Row 对象
        if hasattr(location, '_fields'):
            result = {}
            for i, field in enumerate(location._fields):
                value = location[i]
                # 转换数值字段
                if field in ['capacity', 'variety_count', 'total_quantity']:
                    try:
                        if isinstance(value, str):
                            value = int(value) if value.strip() else 0
                        else:
                            value = int(value)
                    except (ValueError, TypeError):
                        value = 0
                result[field] = value
            return result

        # 处理元组格式
        if isinstance(location, tuple):
            loc_dict = {
                'location_code': location[0] if len(location) > 0 else '',
                'rack': location[1] if len(location) > 1 else '',
                'level': location[2] if len(location) > 2 else '',
                'position': location[3] if len(location) > 3 else '',
                'side': location[4] if len(location) > 4 else '',
                'status': location[5] if len(location) > 5 else 'free',
                'capacity': location[6] if len(location) > 6 else 0,
                'size_type': location[7] if len(location) > 7 else '',
                'description': location[8] if len(location) > 8 else '',
                'last_updated': location[9] if len(location) > 9 else None,
                # 新增字段 - 移除 part_count
                'variety_count': location[10] if len(location) > 10 else 0,
                'total_quantity': location[11] if len(location) > 11 else 0,
                'utilization_rate': location[12] if len(location) > 12 else 0.0,
                'low_stock_varieties': location[13] if len(location) > 13 else 0,
                'out_of_stock_varieties': location[14] if len(location) > 14 else 0,
                'total_value': location[15] if len(location) > 15 else 0.0,
                'status_category': location[16] if len(location) > 16 else 'empty'
            }

            # 确保数值字段是整数
            for key in ['capacity', 'variety_count', 'total_quantity']:
                if loc_dict[key] is not None:
                    try:
                        if isinstance(loc_dict[key], str):
                            loc_dict[key] = int(loc_dict[key]) if loc_dict[key].strip() else 0
                        else:
                            loc_dict[key] = int(loc_dict[key])
                    except (ValueError, TypeError):
                        loc_dict[key] = 0

            return loc_dict

        return {}

    @app.route('/api/locations/rack_layout', methods=['GET'])
    def get_rack_layout_api():
        """获取货架布局数据 - 移除 part_count 版本"""
        try:
            # 使用简单的查询避免复杂统计
            locations = get_all_locations()
            rack_layouts = get_all_rack_layouts()

            # 按货架分组 - 简化版本
            rack_groups = {}
            for location in locations:
                loc_dict = location_to_dict(location)
                rack = loc_dict.get('rack', '')

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

                    # 简化统计 - 使用 variety_count 替代 part_count
                    rack_locations = [loc for loc in locations if location_to_dict(loc).get('rack') == rack]
                    total_locations = len(rack_locations)

                    # 使用 variety_count 判断是否使用中
                    in_use_locations = sum(
                        1 for loc in rack_locations
                        if location_to_dict(loc).get('variety_count', 0) > 0
                    )

                    rack_groups[rack] = {
                        'rack': rack,
                        'locations': [],
                        'stats': {
                            'total': total_locations,
                            'in_use': in_use_locations,
                            'not_use': total_locations - in_use_locations,
                            'utilization': 0
                        },
                        'levels': set(),
                        'positions': set(),
                        'sides': set(),
                        'layout': layout
                    }

                # 添加库位信息 - 使用 variety_count 替代 part_count
                location_data = {
                    'location_code': loc_dict.get('location_code', ''),
                    'status': loc_dict.get('status', 'free'),
                    'capacity': loc_dict.get('capacity', 0),
                    'variety_count': loc_dict.get('variety_count', 0),
                    'total_quantity': loc_dict.get('total_quantity', 0),
                    'description': loc_dict.get('description', ''),
                    'level': loc_dict.get('level', ''),
                    'position': loc_dict.get('position', ''),
                    'side': loc_dict.get('side', '')
                }

                rack_groups[rack]['locations'].append(location_data)

                # 收集结构信息
                if location_data['level']:
                    rack_groups[rack]['levels'].add(location_data['level'])
                if location_data['position']:
                    rack_groups[rack]['positions'].add(location_data['position'])
                if location_data['side']:
                    rack_groups[rack]['sides'].add(location_data['side'])

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
            logging.error(f"获取货架布局失败: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'error': str(e),
                'message': '获取货架布局数据失败，请检查数据库连接'
            }), 500

    @app.route('/api/health', methods=['GET'])
    def health_check():
        """数据库健康检查"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 检查关键表是否存在
                tables = ['locations', 'rack_layouts', 'spare_parts']
                table_status = {}

                for table in tables:
                    try:
                        conn.execute(f'SELECT 1 FROM {table} LIMIT 1')
                        table_status[table] = 'OK'
                    except Exception as e:
                        table_status[table] = f'Error: {str(e)}'

                return jsonify({
                    'success': True,
                    'database': 'Connected',
                    'tables': table_status,
                    'timestamp': datetime.now().isoformat()
                })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'database': 'Disconnected'
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
        """货架详情页面 - 修复统计量计算"""
        try:
            locations = get_all_locations()
            rack_locations = []

            for location in locations:
                loc_dict = location_to_dict(location)
                current_rack = loc_dict.get('rack', '')

                if current_rack == rack_code:
                    # 确保所有必需的字段都有默认值
                    loc_dict.setdefault('total_quantity', 0)
                    loc_dict.setdefault('variety_count', 0)
                    loc_dict.setdefault('capacity', 0)
                    rack_locations.append(loc_dict)

            # 按层级、侧面和位置排序
            def sort_key(loc):
                level = loc.get('level', '')
                side = loc.get('side', '')
                position = loc.get('position', '')
                return (level, side, position)

            rack_locations.sort(key=sort_key)

            # 修复统计量计算 - 使用正确的字段
            total_locations = len(rack_locations)

            # 使用 variety_count 判断空闲和使用中
            free_count = sum(1 for loc in rack_locations if loc.get('variety_count', 0) == 0)
            in_use_count = total_locations - free_count

            # 修复低库存统计 - 使用 status_category 字段
            low_stock_count = sum(1 for loc in rack_locations if
                                  loc.get('status_category') in ['all_low_stock', 'partial_low_stock', 'low_stock'])

            # 获取层级、侧面、位置信息
            levels = sorted(set(loc.get('level', '') for loc in rack_locations if loc.get('level')))
            sides = sorted(set(loc.get('side', '') for loc in rack_locations if loc.get('side')))
            positions = sorted(set(loc.get('position', '') for loc in rack_locations if loc.get('position')))

            # 添加分页支持
            page = request.args.get('page', 1, type=int)
            per_page = 20  # 每页显示20个库位

            # 计算分页
            total_pages = (total_locations + per_page - 1) // per_page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_locations = rack_locations[start_idx:end_idx]

            # 计算更多统计信息
            total_capacity = sum(loc.get('capacity', 0) for loc in rack_locations)
            total_quantity = sum(loc.get('total_quantity', 0) for loc in rack_locations)
            total_varieties = sum(loc.get('variety_count', 0) for loc in rack_locations)

            utilization_rate = (total_quantity / total_capacity * 100) if total_capacity > 0 else 0

            return render_template('rack_detail.html',
                                   rack_code=rack_code,
                                   locations=paginated_locations,
                                   total_locations=total_locations,
                                   free_count=free_count,
                                   in_use_count=in_use_count,
                                   low_stock_count=low_stock_count,
                                   levels=levels,
                                   sides=sides,
                                   positions=positions,
                                   # 分页信息
                                   page=page,
                                   total_pages=total_pages,
                                   # 额外统计信息
                                   total_capacity=total_capacity,
                                   total_quantity=total_quantity,
                                   total_varieties=total_varieties,
                                   utilization_rate=round(utilization_rate, 1))

        except Exception as e:
            logging.error(f"加载货架详情失败: {str(e)}")
            flash(f'加载货架详情失败: {str(e)}', 'error')
            return redirect(url_for('location_management'))

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
        """库位详情页面 - 优化版本"""
        try:
            # 获取来源页面，用于返回按钮
            referer = request.headers.get('Referer')
            return_url = referer if referer and '/location_detail' not in referer else url_for('location_management')

            # 获取库位信息
            location = get_location_by_code(location_code)
            if not location:
                flash('库位不存在', 'error')
                return redirect(url_for('location_management'))

            # 将location转换为字典
            location_dict = location_to_dict(location)

            # 获取该库位的备件列表
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取该库位的所有备件 - 确保包含 id 字段
                cursor = conn.execute('''
                    SELECT id, part_no, name, current_stock, min_stock, max_stock, 
                           unit_price, type, product_model, supplier, description
                    FROM spare_parts 
                    WHERE location = ?
                    ORDER BY part_no
                ''', (location_code,))

                parts_in_location = []
                for row in cursor.fetchall():
                    if hasattr(row, '_fields'):
                        part_dict = {}
                        for i, field in enumerate(row._fields):
                            part_dict[field] = row[i]
                        parts_in_location.append(part_dict)
                    else:
                        parts_in_location.append({
                            'id': row[0],
                            'part_no': row[1],
                            'name': row[2],
                            'current_stock': row[3],
                            'min_stock': row[4],
                            'max_stock': row[5],
                            'unit_price': row[6],
                            'type': row[7],
                            'product_model': row[8],
                            'supplier': row[9],
                            'description': row[10]
                        })

                # 计算更精确的统计信息
                cursor = conn.execute('''
                    SELECT 
                        COUNT(*) as part_count,
                        SUM(current_stock) as total_stock,
                        SUM(CASE WHEN current_stock <= min_stock AND current_stock > 0 THEN 1 ELSE 0 END) as low_stock_count,
                        SUM(CASE WHEN current_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_count,
                        SUM(current_stock * unit_price) as total_value
                    FROM spare_parts 
                    WHERE location = ?
                ''', (location_code,))

                stats_result = cursor.fetchone()
                if stats_result:
                    exact_stats = {
                        'part_count': stats_result['part_count'] or 0,
                        'total_stock': stats_result['total_stock'] or 0,
                        'low_stock_count': stats_result['low_stock_count'] or 0,
                        'out_of_stock_count': stats_result['out_of_stock_count'] or 0,
                        'total_value': stats_result['total_value'] or 0.0
                    }
                else:
                    exact_stats = {
                        'part_count': 0,
                        'total_stock': 0,
                        'low_stock_count': 0,
                        'out_of_stock_count': 0,
                        'total_value': 0.0
                    }

            # 计算库位状态
            variety_count = exact_stats['part_count']
            location_status = 'in_use' if variety_count > 0 else 'not_use'

            # 计算利用率
            capacity = location_dict.get('capacity', 0)
            if capacity > 0:
                utilization_rate = round((exact_stats['total_stock'] / capacity) * 100, 1)
            else:
                utilization_rate = 0

            # 计算健康状态
            health_status = 'healthy'
            if exact_stats['out_of_stock_count'] > 0:
                if exact_stats['out_of_stock_count'] == exact_stats['part_count']:
                    health_status = 'all_out_of_stock'
                else:
                    health_status = 'partial_out_of_stock'
            elif exact_stats['low_stock_count'] > 0:
                if exact_stats['low_stock_count'] == exact_stats['part_count']:
                    health_status = 'all_low_stock'
                else:
                    health_status = 'partial_low_stock'
            elif exact_stats['part_count'] == 0:
                health_status = 'empty'

            # 检查系统中可用的路由
            from flask import url_for
            available_routes = {
                'has_add_part': check_route_exists('add_part'),
                'has_edit_part': check_route_exists('edit_part'),
                'has_part_detail': check_route_exists('part_detail'),
                'has_parts_management': check_route_exists('parts_management'),
                'has_stock_in': check_route_exists('stock_in'),
                'has_stock_out': check_route_exists('stock_out'),
                'has_add_operation': check_route_exists('add_operation'),
                'has_operation_management': check_route_exists('operation_management'),
                'has_low_stock_alerts': check_route_exists('low_stock_alerts'),
            }

            return render_template('location_detail.html',
                                   location=location_dict,
                                   parts=parts_in_location,
                                   exact_stats=exact_stats,
                                   location_status=location_status,
                                   utilization_rate=utilization_rate,
                                   health_status=health_status,
                                   return_url=return_url,
                                   available_routes=available_routes)

        except Exception as e:
            logging.error(f"加载库位详情失败: {str(e)}")
            flash(f'加载库位详情失败: {str(e)}', 'error')
            return redirect(url_for('location_management'))

    def check_route_exists(endpoint):
        """检查路由是否存在"""
        from flask import current_app
        try:
            return endpoint in current_app.view_functions
        except:
            return False

    @app.route('/delete_location/<string:location_code>', methods=['POST'])
    def delete_location_route(location_code):
        """删除库位"""
        try:
            delete_location(location_code)
            flash('库位删除成功', 'success')
        except Exception as e:
            flash(f'库位删除失败: {str(e)}', 'error')

        return redirect(url_for('location_management'))

    # 在现有路由基础上添加以下专业功能路由

    @app.route('/api/locations/filter', methods=['POST'])
    def filter_locations():
        """高级筛选库位"""
        try:
            filters = request.get_json()
            locations = get_all_locations()
            filtered_locations = []

            for location in locations:
                loc_dict = location_to_dict(location)
                match = True

                # 状态筛选
                if filters.get('status') and filters['status'] != 'all':
                    if filters['status'] == 'in_use':
                        if loc_dict.get('part_count', 0) == 0:
                            match = False
                    elif filters['status'] == 'not_use':
                        if loc_dict.get('part_count', 0) > 0:
                            match = False
                    elif loc_dict.get('status') != filters['status']:
                        match = False

                # 货架筛选
                if filters.get('rack') and loc_dict.get('rack') != filters['rack']:
                    match = False

                # 容量范围筛选
                capacity = loc_dict.get('capacity', 0)
                if filters.get('min_capacity') and capacity < filters['min_capacity']:
                    match = False
                if filters.get('max_capacity') and capacity > filters['max_capacity']:
                    match = False

                # 搜索文本
                search_text = filters.get('search', '').lower()
                if search_text:
                    location_code = loc_dict.get('location_code', '').lower()
                    description = loc_dict.get('description', '').lower()
                    if search_text not in location_code and search_text not in description:
                        match = False

                if match:
                    filtered_locations.append(loc_dict)

            return jsonify({
                'success': True,
                'locations': filtered_locations,
                'total': len(filtered_locations)
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/locations/batch_update', methods=['POST'])
    def batch_update_locations_api():
        """批量更新库位"""
        try:
            updates = request.get_json()
            updated_count = 0

            for update in updates.get('locations', []):
                location_code = update['location_code']
                update_data = update['update_data']

                try:
                    update_location(location_code, update_data)
                    updated_count += 1
                except Exception:
                    continue

            return jsonify({
                'success': True,
                'updated_count': updated_count,
                'message': f'成功更新 {updated_count} 个库位'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/locations/export', methods=['POST'])
    def export_locations_api():
        """导出库位数据"""
        try:
            filters = request.get_json()
            locations = get_all_locations()

            # 应用筛选条件
            filtered_locations = []
            for location in locations:
                loc_dict = location_to_dict(location)

                # 这里可以添加筛选逻辑
                if filters.get('selected_locations'):
                    if loc_dict['location_code'] not in filters['selected_locations']:
                        continue

                filtered_locations.append(loc_dict)

            return jsonify({
                'success': True,
                'data': filtered_locations,
                'export_time': datetime.now().isoformat()
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/locations/statistics')
    def get_locations_statistics():
        """获取库位统计详情"""
        try:
            locations = get_all_locations()

            stats = {
                'total': len(locations),
                'by_status': {},
                'by_rack': {},
                'capacity_stats': {
                    'total_capacity': 0,
                    'used_capacity': 0,
                    'average_utilization': 0
                }
            }

            total_utilization = 0
            utilization_count = 0

            for location in locations:
                loc_dict = location_to_dict(location)
                status = loc_dict.get('status', 'not_use')
                rack = loc_dict.get('rack', '未分类')
                capacity = loc_dict.get('capacity', 0)
                part_count = loc_dict.get('part_count', 0)

                # 按状态统计
                stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

                # 按货架统计
                if rack not in stats['by_rack']:
                    stats['by_rack'][rack] = {
                        'total': 0,
                        'in_use': 0,
                        'not_use': 0
                    }
                stats['by_rack'][rack]['total'] += 1
                if part_count > 0:
                    stats['by_rack'][rack]['in_use'] += 1
                else:
                    stats['by_rack'][rack]['not_use'] += 1

                # 容量统计
                stats['capacity_stats']['total_capacity'] += capacity
                stats['capacity_stats']['used_capacity'] += part_count

                # 利用率计算
                if capacity > 0:
                    utilization = (part_count / capacity) * 100
                    total_utilization += utilization
                    utilization_count += 1

            if utilization_count > 0:
                stats['capacity_stats']['average_utilization'] = round(total_utilization / utilization_count, 2)

            return jsonify({
                'success': True,
                'statistics': stats
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/locations/test', methods=['GET'])
    def test_locations_api():
        """测试库位API是否正常工作"""
        try:
            # 简单的测试查询
            from models.database import get_all_locations
            locations = get_all_locations()

            return jsonify({
                'success': True,
                'message': f'API测试成功，找到 {len(locations)} 个库位',
                'sample_data': locations[:2] if locations else []  # 返回前2个作为样本
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'message': 'API测试失败'
            }), 500

    # 在 location_routes.py 中添加一个简化版本的API

    @app.route('/api/locations/simple_rack_layout', methods=['GET'])
    def get_simple_rack_layout():
        """简化版货架布局API - 确保能工作"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 简单查询，只获取必要字段
                cursor = conn.execute('''
                    SELECT location_code, rack, level, position, side, 
                           status, capacity, description
                    FROM locations 
                    WHERE rack IS NOT NULL AND rack != ''
                    ORDER BY rack, level, position
                ''')
                locations = cursor.fetchall()

                # 获取货架布局
                cursor = conn.execute('SELECT rack, x, y, width, height, rotation FROM rack_layouts')
                rack_layouts = {}
                for row in cursor.fetchall():
                    rack_layouts[row[0]] = {
                        'x': row[1], 'y': row[2], 'width': row[3],
                        'height': row[4], 'rotation': row[5]
                    }

                # 按货架分组
                rack_groups = {}
                for loc in locations:
                    rack = loc[1]  # rack字段
                    if not rack:
                        continue

                    if rack not in rack_groups:
                        layout = rack_layouts.get(rack, {
                            'x': 100 + len(rack_groups) * 60,
                            'y': 100 + len(rack_groups) * 40,
                            'width': 300,
                            'height': 200,
                            'rotation': 0
                        })

                        rack_groups[rack] = {
                            'rack': rack,
                            'locations': [],
                            'stats': {
                                'total': 0,
                                'in_use': 0,
                                'not_use': 0,
                                'utilization': 0
                            },
                            'levels': set(),
                            'positions': set(),
                            'sides': set(),
                            'layout': layout
                        }

                    # 更新统计
                    rack_groups[rack]['stats']['total'] += 1

                    # 简单的使用状态判断（可以根据实际情况调整）
                    if loc[5] == 'in_use':  # status字段
                        rack_groups[rack]['stats']['in_use'] += 1
                    else:
                        rack_groups[rack]['stats']['not_use'] += 1

                    # 添加库位信息
                    location_data = {
                        'location_code': loc[0],
                        'status': loc[5],
                        'capacity': loc[6],
                        'description': loc[7],
                        'level': loc[2],
                        'position': loc[3],
                        'side': loc[4]
                    }

                    rack_groups[rack]['locations'].append(location_data)

                    # 收集结构信息
                    if loc[2]:  # level
                        rack_groups[rack]['levels'].add(loc[2])
                    if loc[3]:  # position
                        rack_groups[rack]['positions'].add(loc[3])
                    if loc[4]:  # side
                        rack_groups[rack]['sides'].add(loc[4])

                # 转换集合为排序列表
                for rack in rack_groups.values():
                    rack['levels'] = sorted(list(rack['levels']))
                    rack['positions'] = sorted(list(rack['positions']))
                    rack['sides'] = sorted(list(rack['sides']))

                return jsonify({
                    'success': True,
                    'racks': list(rack_groups.values()),
                    'message': f'成功加载 {len(rack_groups)} 个货架'
                })

        except Exception as e:
            logging.error(f"获取简化货架布局失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e),
                'message': '获取货架布局数据失败'
            }), 500

    # 在 location_routes.py 中添加以下路由

    @app.route('/api/racks/<string:rack_code>/detail')
    def get_rack_detail_api(rack_code):
        """获取货架详情数据的API端点"""
        try:
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
            free_count = sum(1 for loc in rack_locations if loc.get('variety_count', 0) == 0)
            in_use_count = sum(1 for loc in rack_locations if loc.get('variety_count', 0) > 0)
            low_stock_count = sum(1 for loc in rack_locations if loc.get('status') == 'low_stock')

            # 获取层级、侧面、位置信息
            levels = sorted(set(loc.get('level', '') for loc in rack_locations if loc.get('level')))
            sides = sorted(set(loc.get('side', '') for loc in rack_locations if loc.get('side')))
            positions = sorted(set(loc.get('position', '') for loc in rack_locations if loc.get('position')))

            rack_data = {
                'rack_code': rack_code,
                'locations': rack_locations,
                'stats': {
                    'total_locations': total_locations,
                    'free_count': free_count,
                    'in_use_count': in_use_count,
                    'low_stock_count': low_stock_count
                },
                'levels': levels,
                'sides': sides,
                'positions': positions
            }

            return jsonify({
                'success': True,
                'rack': rack_data,
                'message': f'成功获取货架 {rack_code} 的详细信息'
            })

        except Exception as e:
            logging.error(f"获取货架详情失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e),
                'message': '获取货架详情数据失败'
            }), 500

    @app.route('/rack_list')
    def rack_list():
        """货架列表页面"""
        try:
            # 获取所有货架
            locations = get_all_locations()
            rack_set = set()

            for location in locations:
                loc_dict = location_to_dict(location)
                rack = loc_dict.get('rack')
                if rack:
                    rack_set.add(rack)

            # 获取每个货架的统计信息
            racks_with_stats = []
            for rack in sorted(rack_set):
                rack_locations = [loc for loc in locations if location_to_dict(loc).get('rack') == rack]
                total_locations = len(rack_locations)
                in_use_locations = sum(1 for loc in rack_locations if location_to_dict(loc).get('variety_count', 0) > 0)
                free_locations = total_locations - in_use_locations

                # 计算利用率
                total_capacity = sum(location_to_dict(loc).get('capacity', 0) for loc in rack_locations)
                total_quantity = sum(location_to_dict(loc).get('total_quantity', 0) for loc in rack_locations)
                utilization = round((total_quantity / total_capacity * 100) if total_capacity > 0 else 0, 1)

                racks_with_stats.append({
                    'rack_code': rack,
                    'total_locations': total_locations,
                    'in_use_locations': in_use_locations,
                    'free_locations': free_locations,
                    'utilization': utilization,
                    'total_capacity': total_capacity,
                    'total_quantity': total_quantity
                })

            return render_template('rack_list.html',
                                   racks=racks_with_stats,
                                   total_racks=len(racks_with_stats))

        except Exception as e:
            logging.error(f"加载货架列表失败: {str(e)}")
            flash(f'加载货架列表失败: {str(e)}', 'error')
            return redirect(url_for('location_management'))


# [file content end]