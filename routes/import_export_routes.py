from flask import render_template, request, redirect, url_for, flash, send_file
import pandas as pd
import os
from werkzeug.utils import secure_filename
from models.database import create_spare_part, create_operation_record

def setup_import_export_routes(app):
    """设置数据导入导出路由"""
    
    @app.route('/import_parts', methods=['GET', 'POST'])
    def import_parts():
        """备件信息导入页面"""
        if request.method == 'POST':
            # 检查是否有文件上传
            if 'file' not in request.files:
                flash('未选择文件', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('未选择文件', 'error')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                try:
                    # 读取Excel文件
                    df = pd.read_excel(file)
                    
                    # 处理导入数据
                    imported_count = 0
                    for index, row in df.iterrows():
                        part_data = {
                            'part_no': str(row.get('part_no', '')),
                            'name': str(row.get('name', '')),
                            'type': str(row.get('type', '')),
                            'current_stock': int(row.get('current_stock', 0)),
                            'min_stock': int(row.get('min_stock', 0)),
                            'max_stock': int(row.get('max_stock', 0)),
                            'unit_price': float(row.get('unit_price', 0.0)),
                            'location': str(row.get('location', '')),
                            'description': str(row.get('description', ''))
                        }
                        
                        # 创建备件
                        create_spare_part(part_data)
                        imported_count += 1
                    
                    flash(f'成功导入 {imported_count} 条备件信息', 'success')
                except Exception as e:
                    flash(f'导入失败: {str(e)}', 'error')
            else:
                flash('不支持的文件格式，请上传Excel文件', 'error')
        
        return render_template('import_parts.html')
    
    @app.route('/import_operations', methods=['GET', 'POST'])
    def import_operations():
        """操作记录导入页面"""
        if request.method == 'POST':
            # 检查是否有文件上传
            if 'file' not in request.files:
                flash('未选择文件', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('未选择文件', 'error')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                try:
                    # 读取Excel文件
                    df = pd.read_excel(file)
                    
                    # 处理导入数据
                    imported_count = 0
                    for index, row in df.iterrows():
                        operation_data = {
                            'operation_type': str(row.get('operation_type', '')),
                            'supplier_recipient': str(row.get('supplier_recipient', '')),
                            'location': str(row.get('location', '')),
                            'part_no': str(row.get('part_no', '')),
                            'description': str(row.get('description', '')),
                            'part_type': str(row.get('part_type', '')),
                            'quantity': int(row.get('quantity', 0)),
                            'work_center': str(row.get('work_center', ''))
                        }
                        
                        # 创建操作记录
                        create_operation_record(operation_data)
                        imported_count += 1
                    
                    flash(f'成功导入 {imported_count} 条操作记录', 'success')
                except Exception as e:
                    flash(f'导入失败: {str(e)}', 'error')
            else:
                flash('不支持的文件格式，请上传Excel文件', 'error')
        
        return render_template('import_operations.html')
    
    @app.route('/export_data')
    def export_data():
        """数据导出功能"""
        try:
            # 这里应该实现实际的数据导出逻辑
            # 为简化示例，创建一个简单的Excel文件
            data = {
                'part_no': ['PART001', 'PART002'],
                'name': ['备件1', '备件2'],
                'current_stock': [10, 5]
            }
            df = pd.DataFrame(data)
            
            # 保存到临时文件并返回
            filename = 'spare_parts_export.xlsx'
            df.to_excel(filename, index=False)
            
            return send_file(filename, as_attachment=True)
        except Exception as e:
            flash(f'导出失败: {str(e)}', 'error')
            return redirect(url_for('parts_list'))

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}
