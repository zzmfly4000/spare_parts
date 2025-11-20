from flask import render_template, request, redirect, url_for, flash
from models.database import (get_all_locations, get_location_by_code, 
                           create_location, update_location, delete_location,
                           update_location_status)
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
            # 这里应该实现实际的搜索和筛选逻辑
            # 为简化示例，直接添加所有库位
            filtered_locations.append(location)
        
        return render_template('location_management.html', locations=filtered_locations)
    
    @app.route('/add_location', methods=['GET', 'POST'])
    def add_location():
        """添加库位页面"""
        if request.method == 'POST':
            # 获取表单数据
            location_data = {
                'location_code': request.form.get('location_code', ''),
                'description': request.form.get('description', ''),
                'capacity': int(request.form.get('capacity', 0)),
                'status': request.form.get('status', 'free')
            }
            
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
        if request.method == 'POST':
            # 获取表单数据
            location_data = {
                'description': request.form.get('description', ''),
                'capacity': int(request.form.get('capacity', 0)),
                'status': request.form.get('status', 'free')
            }
            
            # 更新库位
            try:
                update_location(location_code, location_data)
                flash('库位更新成功', 'success')
                return redirect(url_for('location_detail', location_code=location_code))
            except Exception as e:
                flash(f'库位更新失败: {str(e)}', 'error')
        
        # 获取库位信息
        location = get_location_by_code(location_code)
        if not location:
            flash('库位不存在', 'error')
            return redirect(url_for('location_management'))
        
        return render_template('edit_location.html', location=location)
    
    @app.route('/location_detail/<string:location_code>')
    def location_detail(location_code):
        """库位详情页面"""
        location = get_location_by_code(location_code)
        if not location:
            flash('库位不存在', 'error')
            return redirect(url_for('location_management'))
        
        # 计算库位状态
        location_status = calculate_location_status(location[3], location[4])  # part_count, capacity
        
        return render_template('location_detail.html', location=location, location_status=location_status)
    
    @app.route('/delete_location/<string:location_code>')
    def delete_location_route(location_code):
        """删除库位"""
        try:
            delete_location(location_code)
            flash('库位删除成功', 'success')
        except Exception as e:
            flash(f'库位删除失败: {str(e)}', 'error')
        
        return redirect(url_for('location_management'))
