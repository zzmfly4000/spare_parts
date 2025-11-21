from flask import render_template, request, redirect, url_for, flash
from models.database import (create_operation_record, get_spare_part_by_id, 
                           update_stock_for_part)
import datetime

def setup_operation_routes(app):
    """设置操作记录路由"""
    
    @app.route('/operation_records')
    def operation_records():
        """操作记录列表页面"""
        # 获取筛选参数
        operation_type = request.args.get('operation_type', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        part_no = request.args.get('part_no', '')
        
        # 这里应该实现实际的操作记录查询逻辑
        # 为简化示例，使用空列表
        operations = []
        
        return render_template('operation_records.html', operations=operations)
    
    @app.route('/smart_inbound', methods=['GET', 'POST'])
    def smart_inbound():
        """智能入库页面"""
        if request.method == 'POST':
            # 获取表单数据
            operation_data = {
                'operation_type': 'Stock in',
                'supplier_recipient': request.form.get('supplier', ''),
                'location': request.form.get('location', ''),
                'part_no': request.form.get('part_no', ''),
                'description': request.form.get('part_name', ''),
                'part_type': request.form.get('part_type', ''),
                'quantity': int(request.form.get('quantity', 0)),
                'work_center': request.form.get('work_center', '')
            }
            
            try:
                # 创建操作记录
                create_operation_record(operation_data)
                
                # 更新备件库存
                # 这里需要根据part_no查找备件ID
                # 为简化示例，假设已获取到part_id
                # update_stock_for_part(part_id)
                
                flash('入库操作记录创建成功', 'success')
                return redirect(url_for('operation_records'))
            except Exception as e:
                flash(f'入库操作失败: {str(e)}', 'error')
        
        return render_template('smart_inbound.html')
    
    @app.route('/outbound_part/<int:part_id>')
    def outbound_part(part_id):
        """备件出库页面"""
        # 获取备件信息
        part = get_spare_part_by_id(part_id)
        if not part:
            flash('备件不存在', 'error')
            return redirect(url_for('parts_list'))
        
        return render_template('outbound_part.html', part=part)
