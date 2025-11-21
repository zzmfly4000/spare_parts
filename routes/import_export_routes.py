from flask import render_template, request, redirect, url_for, flash, send_file, session, jsonify, current_app
import pandas as pd
from io import BytesIO
from datetime import datetime
import traceback
import logging
import numpy as np
from models.database import DatabaseManager, create_spare_part, create_operation_record, recalculate_all_stock
from utils.helpers import safe_int, safe_str, safe_float, validate_excel_file, safe_datetime
from utils.sync_utils import sync_all_operations

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

    # =============================================================================
    # 新增功能：高级数据导入导出
    # =============================================================================

    @app.route('/import_part_info_only', methods=['GET', 'POST'])
    def import_part_info_only():
        """仅更新备件信息的导入页面"""
        if request.method == 'POST':
            try:
                if 'file' not in request.files:
                    flash('请选择文件', 'danger')
                    return redirect(request.url)

                file = request.files['file']
                if file.filename == '':
                    flash('请选择文件', 'danger')
                    return redirect(request.url)

                if not validate_excel_file(file.filename):
                    flash('请上传有效的Excel文件 (.xlsx 或 .xls)', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                logging.info(f"开始导入备件信息更新，文件: {file.filename}, 时间: {import_start_time}")

                try:
                    df = pd.read_excel(file)
                    df = clean_operations_dataframe(df)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")

                    # 添加调试信息
                    debug_column_names(df)

                except Exception as e:
                    current_app.logger.error(f'读取Excel文件失败: {str(e)}')
                    current_app.logger.error(traceback.format_exc())
                    flash(f'读取Excel文件失败: {str(e)}', 'danger')
                    return redirect(request.url)

                # 处理备件信息更新
                result = process_part_info_only_update(df)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()
                logging.info(f"备件信息更新导入完成，耗时: {import_duration:.2f}秒")

                if result['success']:
                    flash(result['message'], 'success')
                    session_keys = ['import_errors', 'error_count', 'updated_count', 'not_found_count',
                                    'import_summary']
                    for key in session_keys:
                        if key in session:
                            session.pop(key)
                else:
                    flash(result['message'], 'warning' if result.get('updated_count', 0) > 0 else 'danger')
                    session['import_errors'] = result.get('errors', [])
                    session['error_count'] = result.get('error_count', 0)
                    session['updated_count'] = result.get('updated_count', 0)
                    session['not_found_count'] = result.get('not_found_count', 0)
                    session['import_summary'] = result.get('import_summary', {})

                return redirect(url_for('import_part_info_only'))

            except Exception as e:
                current_app.logger.error(f'导入备件信息更新时发生错误: {str(e)}')
                current_app.logger.error(traceback.format_exc())
                flash(f'导入文件时发生系统错误: {str(e)}', 'danger')
                return redirect(request.url)

        # GET 请求处理
        import_errors = session.get('import_errors', [])
        error_count = session.get('error_count', 0)
        updated_count = session.get('updated_count', 0)
        not_found_count = session.get('not_found_count', 0)
        import_summary = session.get('import_summary', {})

        # 清除session中的导入数据
        session_keys = ['import_errors', 'error_count', 'updated_count', 'not_found_count', 'import_summary']
        for key in session_keys:
            if key in session:
                session.pop(key)

        return render_template('import_part_info_only.html',
                               import_errors=import_errors,
                               error_count=error_count,
                               updated_count=updated_count,
                               not_found_count=not_found_count,
                               import_summary=import_summary)

    @app.route('/download_part_info_update_template')
    def download_part_info_update_template():
        """下载备件信息更新模板（仅更新指定字段）"""
        try:
            template_data = {
                '货号 Part no': ['PART-001', 'PART-002', 'PART-003', ''],
                '关键备件 Key part': ['是', '否', '是', ''],
                '最低库存 Low stock': [5, 10, 15, ''],
                '最高库存 High stock': [50, 100, 200, ''],
                '交货期 LT (Week)': [2, 1, 3, ''],
                '单价 Unit price (RMB)': [25.5, 0.8, 150.0, ''],
                '单位 Unit': ['个', '包', '套', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='备件信息更新模板', index=False)

                instructions = pd.DataFrame({
                    '列名': [
                        '货号 Part no',
                        '关键备件 Key part',
                        '最低库存 Low stock',
                        '最高库存 High stock',
                        '交货期 LT (Week)',
                        '单价 Unit price (RMB)',
                        '单位 Unit'
                    ],
                    '说明': [
                        '备件编号（必填，根据此字段查找对应备件）',
                        '是否关键备件',
                        '最低库存数量',
                        '最高库存数量',
                        '交货期（周）',
                        '单价（人民币）',
                        '计量单位'
                    ],
                    '示例': [
                        'PART-001',
                        '是',
                        '5',
                        '50',
                        '2',
                        '25.5',
                        '个'
                    ],
                    '备注': [
                        '必须存在的备件编号',
                        '是/否',
                        '数字，>=0',
                        '数字，>=最低库存',
                        '数字，>=0',
                        '数字，可带小数',
                        '如：个、包、米等'
                    ]
                })
                instructions.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(output,
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             as_attachment=True,
                             download_name='备件信息更新模板.xlsx')

        except Exception as e:
            current_app.logger.error(f'下载备件信息更新模板时出错: {str(e)}')
            flash(f'下载备件信息更新模板时出错: {str(e)}', 'danger')
            return redirect(url_for('import_part_info_only'))

    @app.route('/import_operations_advanced', methods=['GET', 'POST'])
    def import_operations_advanced():
        """高级操作记录导入页面"""
        if request.method == 'POST':
            try:
                if 'file' not in request.files:
                    flash('请选择文件', 'danger')
                    return redirect(request.url)

                file = request.files['file']
                if file.filename == '':
                    flash('请选择文件', 'danger')
                    return redirect(request.url)

                if not validate_excel_file(file.filename):
                    flash('请上传有效的Excel文件 (.xlsx 或 .xls)', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                logging.info(f"开始导入操作记录，文件: {file.filename}, 时间: {import_start_time}")

                try:
                    df = pd.read_excel(file)
                    df = clean_operations_dataframe(df)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")

                    # 添加详细的调试信息
                    debug_column_names(df)

                except Exception as e:
                    current_app.logger.error(f'读取Excel文件失败: {str(e)}')
                    current_app.logger.error(traceback.format_exc())
                    flash(f'读取Excel文件失败: {str(e)}', 'danger')
                    return redirect(request.url)

                # 首先检测文件类型
                file_type = detect_file_type(df)
                logging.info(f"检测到文件类型: {file_type}")

                if file_type == 'unknown':
                    # 提供更详细的错误信息
                    column_info = ", ".join([f"'{col}'" for col in df.columns])
                    error_msg = f'无法识别文件类型。检测到的列名: {column_info}。请使用系统提供的模板格式。'
                    current_app.logger.error(error_msg)
                    flash(error_msg, 'danger')
                    return redirect(request.url)

                # 根据文件类型处理
                if file_type == 'part_info_only':
                    # 如果是备件信息文件，重定向到专门的备件信息导入页面
                    flash('检测到这是备件信息文件，已自动跳转到备件信息导入页面', 'info')
                    return redirect(url_for('import_part_info_only'))
                else:  # operations_with_parts
                    # 检查操作记录必需的列
                    required_columns = ['Operation type', 'Date', 'Part No', 'Qty']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    if missing_columns:
                        error_msg = f'Excel文件中缺少必要的列: {", ".join(missing_columns)}'
                        current_app.logger.error(error_msg)
                        flash(error_msg, 'danger')
                        return redirect(request.url)

                    result = process_operations_with_parts_import(df)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()
                logging.info(f"导入完成，耗时: {import_duration:.2f}秒")

                if result['success']:
                    flash(result['message'], 'success')
                    session_keys = ['import_errors', 'error_count', 'imported_count', 'updated_parts_count',
                                    'import_summary']
                    for key in session_keys:
                        if key in session:
                            session.pop(key)
                else:
                    flash(result['message'], 'warning' if result.get('imported_count', 0) > 0 else 'danger')
                    session['import_errors'] = result.get('errors', [])
                    session['error_count'] = result.get('error_count', 0)
                    session['imported_count'] = result.get('imported_count', 0)
                    session['updated_parts_count'] = result.get('updated_parts_count', 0)
                    session['import_summary'] = result.get('import_summary', {})

                return redirect(url_for('import_operations_advanced'))

            except Exception as e:
                current_app.logger.error(f'导入操作记录时发生错误: {str(e)}')
                current_app.logger.error(traceback.format_exc())
                flash(f'导入文件时发生系统错误: {str(e)}', 'danger')
                return redirect(request.url)

        import_errors = session.get('import_errors', [])
        error_count = session.get('error_count', 0)
        imported_count = session.get('imported_count', 0)
        updated_parts_count = session.get('updated_parts_count', 0)
        updated_parts_info_count = session.get('updated_parts_info_count', 0)
        import_summary = session.get('import_summary', {})
        sync_result = session.get('sync_result', {})
        detailed_report = session.get('detailed_report', '')

        session_keys = ['import_errors', 'error_count', 'imported_count',
                        'updated_parts_count', 'updated_parts_info_count',
                        'import_summary', 'sync_result', 'detailed_report']
        for key in session_keys:
            if key in session:
                session.pop(key)

        return render_template('import_operations_advanced.html',
                               import_errors=import_errors,
                               error_count=error_count,
                               imported_count=imported_count,
                               updated_parts_count=updated_parts_count,
                               updated_parts_info_count=updated_parts_info_count,
                               import_summary=import_summary,
                               sync_result=sync_result,
                               detailed_report=detailed_report)

    @app.route('/export_parts_advanced')
    def export_parts_advanced():
        """高级备件信息导出"""
        try:
            with DatabaseManager().get_connection() as conn:
                parts = conn.execute('''
                    SELECT p.*, l.status as location_status, l.description as location_description
                    FROM spare_parts p 
                    LEFT JOIN locations l ON p.location = l.location_code
                    ORDER BY p.part_no
                ''').fetchall()

                df_data = []
                for part in parts:
                    df_data.append({
                        '备件编号': safe_str(part['part_no']),
                        '备件名称': safe_str(part['name']),
                        '类型': safe_str(part['type']),
                        '当前库存': safe_int(part['current_stock']),
                        '最低库存': safe_int(part['min_stock']),
                        '最高库存': safe_int(part['max_stock']),
                        '库位': safe_str(part['location']),
                        '库位状态': safe_str(part['location_status']),
                        '库位描述': safe_str(part['location_description']),
                        '供应商': safe_str(part['supplier']),
                        '单价': safe_float(part['unit_price']),
                        '描述': safe_str(part['description']),
                        '创建时间': safe_str(part['created_date']),
                        '更新时间': safe_str(part['updated_date'])
                    })

                df = pd.DataFrame(df_data)

                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='备件信息', index=False)

                    worksheet = writer.sheets['备件信息']
                    for idx, col in enumerate(df.columns):
                        max_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
                        worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 50)

                output.seek(0)

                filename = f'备件信息导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                return send_file(output,
                                 mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 as_attachment=True,
                                 download_name=filename)

        except Exception as e:
            current_app.logger.error(f'导出备件信息时出错: {str(e)}')
            flash(f'导出备件信息时出错: {str(e)}', 'danger')
            return redirect(url_for('parts_list'))

    # 在 setup_import_export_routes 函数中添加以下路由：

    @app.route('/download_template')
    def download_template():
        """下载备件导入模板"""
        try:
            template_data = {
                'part_no': ['PART-001', 'PART-002', ''],
                'name': ['轴承 6205', '螺丝 M6', ''],
                'type': ['机械', '电子', ''],
                'current_stock': [50, 200, ''],
                'min_stock': [5, 10, ''],
                'max_stock': [100, 500, ''],
                'unit_price': [25.5, 0.8, ''],
                'location': ['A-01-01', 'B-02-01', ''],
                'description': ['深沟球轴承 6205', '不锈钢螺丝 M6*20', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='备件导入模板', index=False)

                instructions = pd.DataFrame({
                    '列名': ['part_no', 'name', 'type', 'current_stock', 'min_stock', 'max_stock', 'unit_price',
                             'location', 'description'],
                    '说明': [
                        '备件编号（必填，唯一）',
                        '备件名称（必填）',
                        '备件类型',
                        '当前库存数量',
                        '最低库存阈值',
                        '最高库存阈值',
                        '单价',
                        '库位代码',
                        '备件描述'
                    ],
                    '示例': [
                        'PART-001',
                        '轴承 6205',
                        '机械',
                        '50',
                        '5',
                        '100',
                        '25.5',
                        'A-01-01',
                        '深沟球轴承 6205'
                    ],
                    '备注': [
                        '不能重复',
                        '详细描述备件',
                        '如：机械、电子等',
                        '数字，当前库存量',
                        '数字，>=0',
                        '数字，>=最低库存',
                        '数字，可带小数',
                        '必须存在的库位代码',
                        '可选'
                    ]
                })
                instructions.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(output,
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             as_attachment=True,
                             download_name='备件导入模板.xlsx')

        except Exception as e:
            current_app.logger.error(f'下载备件模板时出错: {str(e)}')
            flash(f'下载备件模板时出错: {str(e)}', 'danger')
            return redirect(url_for('import_parts'))

    @app.route('/download_operations_template')
    def download_operations_template():
        """下载操作记录导入模板"""
        try:
            template_data = {
                'Operation type': ['Stock in', 'Stock out', ''],
                'Date': ['2024-01-01', '2024-01-02', ''],
                'Supplier or Recipients': ['供应商A', '部门B', ''],
                'Location': ['A-01-01', 'B-02-01', ''],
                'Part No': ['PART-001', 'PART-002', ''],
                '货号 Part no': ['PART-001', 'PART-002', ''],
                'Description': ['轴承 6205', '螺丝 M6', ''],
                'Type': ['机械', '电子', ''],
                'Qty': [10, -5, ''],
                'Work center': ['生产线A', '维修部', ''],
                '关键备件 Key part': ['是', '否', ''],
                '最低库存 Low stock': [10, 5, ''],
                '最高库存 High stock': [100, 50, ''],
                '交货期 LT (Week)': [2, 1, ''],
                '单价 Unit price (RMB)': [25.5, 0.8, ''],
                '单位 Unit': ['个', '包', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='操作记录模板', index=False)

                instructions = pd.DataFrame({
                    '列名': [
                        'Operation type', 'Date', 'Supplier or Recipients', 'Location',
                        'Part No', '货号 Part no', 'Description', 'Type', 'Qty', 'Work center',
                        '关键备件 Key part', '最低库存 Low stock', '最高库存 High stock',
                        '交货期 LT (Week)', '单价 Unit price (RMB)', '单位 Unit'
                    ],
                    '说明': [
                        '操作类型 (Stock in/Stock out)',
                        '操作日期',
                        '供应商或接收方',
                        '库位代码',
                        '备件编号（操作记录用）',
                        '备件编号（备件信息用）',
                        '备件描述',
                        '备件类型',
                        '数量 (正数入库，负数出库)',
                        '工作中心',
                        '是否关键备件',
                        '最低库存数量',
                        '最高库存数量',
                        '交货期（周）',
                        '单价（人民币）',
                        '计量单位'
                    ],
                    '示例': [
                        'Stock in',
                        '2024-01-01',
                        '供应商A',
                        'A-01-01',
                        'PART-001',
                        'PART-001',
                        '轴承 6205',
                        '机械',
                        '10',
                        '生产线A',
                        '是',
                        '10',
                        '100',
                        '2',
                        '25.5',
                        '个'
                    ],
                    '备注': [
                        '必填',
                        '必填，格式: YYYY-MM-DD',
                        '可选',
                        '必填',
                        '必填（用于操作记录）',
                        '必填（用于备件信息）',
                        '必填',
                        '可选',
                        '必填，不能为0',
                        '可选',
                        '是/否',
                        '数字，>=0',
                        '数字，>=最低库存',
                        '数字，>=0',
                        '数字，可带小数',
                        '如：个、包、米等'
                    ]
                })
                instructions.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(output,
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             as_attachment=True,
                             download_name='操作记录导入模板.xlsx')

        except Exception as e:
            current_app.logger.error(f'下载操作记录模板时出错: {str(e)}')
            flash(f'下载操作记录模板时出错: {str(e)}', 'danger')
            return redirect(url_for('import_operations_advanced'))


# =============================================================================
# 辅助函数
# =============================================================================

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}


def debug_column_names(df):
    """调试函数：打印DataFrame的列名信息"""
    logging.info("=== 列名调试信息 ===")
    logging.info(f"DataFrame列名: {list(df.columns)}")
    logging.info(f"列名类型: {[type(col) for col in df.columns]}")
    logging.info(f"列名详情:")
    for i, col in enumerate(df.columns):
        logging.info(f"  列 {i}: '{col}' (类型: {type(col)})")

    # 检查是否有包含关键词的列
    keywords = ['货号', 'Part', 'part']
    for keyword in keywords:
        matching_cols = [col for col in df.columns if keyword in str(col)]
        if matching_cols:
            logging.info(f"包含 '{keyword}' 的列: {matching_cols}")

    logging.info("=== 结束调试信息 ===")


def process_part_info_only_update(df):
    """处理仅更新备件信息的导入（不创建操作记录）"""
    updated_count = 0
    not_found_count = 0
    error_count = 0
    errors = []
    import_summary = {
        'total_rows': len(df),
        'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'file_columns': list(df.columns),
        'data_statistics': {}
    }

    try:
        with DatabaseManager().get_connection() as conn:
            for index, row in df.iterrows():
                row_number = index + 2
                try:
                    # 跳过空行 - 修复：使用正确的列名
                    part_no = None

                    # 尝试多种可能的列名格式
                    possible_column_names = [
                        '货号 Part no',
                        '货号 Part No',
                        '货号Part no',
                        '货号Part No',
                        'Part No',
                        'Part no',
                        'part_no',
                        '货号'
                    ]

                    for col_name in possible_column_names:
                        if col_name in row and pd.notna(row[col_name]):
                            part_no = safe_str(row[col_name]).strip()
                            if part_no:
                                break

                    # 如果仍然找不到，尝试检查其他可能的列
                    if not part_no:
                        # 检查是否有任何包含"货号"或"Part"的列
                        for col in row.index:
                            if any(keyword in str(col) for keyword in ['货号', 'Part', 'part']):
                                if pd.notna(row[col]):
                                    candidate = safe_str(row[col]).strip()
                                    if candidate:
                                        part_no = candidate
                                        break

                    # 如果还是找不到，记录错误
                    if not part_no:
                        errors.append({
                            'row': row_number,
                            'error': '无法找到备件编号列，请确保Excel文件包含"货号 Part no"列',
                            'field': '货号 Part no',
                            'value': '',
                            'severity': 'error',
                            'suggestion': '请使用系统提供的模板格式'
                        })
                        error_count += 1
                        continue

                    # 检查备件是否存在
                    part = conn.execute(
                        'SELECT id, name FROM spare_parts WHERE part_no = ?',
                        (part_no,)
                    ).fetchone()

                    if not part:
                        errors.append({
                            'row': row_number,
                            'error': f'备件不存在: {part_no}',
                            'field': '货号 Part no',
                            'value': part_no,
                            'severity': 'warning',
                            'suggestion': '请检查备件编号是否正确，或先在系统中添加该备件'
                        })
                        not_found_count += 1
                        continue

                    # 提取要更新的信息
                    part_info = extract_update_info_from_row(row)

                    # 更新备件信息
                    success, message = update_part_specific_fields(conn, part['id'], part_info)
                    if success:
                        updated_count += 1
                        logging.info(f"成功更新备件信息: {part_no} - {part['name']}")
                    else:
                        errors.append({
                            'row': row_number,
                            'error': f'备件信息更新失败: {message}',
                            'field': '备件信息',
                            'value': f"{part_no} - {part['name']}",
                            'severity': 'warning',
                            'suggestion': '请检查数据格式'
                        })

                except Exception as e:
                    errors.append({
                        'row': row_number,
                        'error': f'处理备件信息时出错: {str(e)}',
                        'field': 'General',
                        'value': str(e),
                        'severity': 'error',
                        'suggestion': '请检查数据格式或联系系统管理员'
                    })
                    error_count += 1
                    logging.error(f"处理第 {row_number} 行备件信息时出错: {str(e)}")

            conn.commit()

            # 更新导入摘要
            import_summary.update({
                'import_end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'updated_count': updated_count,
                'not_found_count': not_found_count,
                'error_count': error_count,
                'skipped_rows': len(df) - updated_count - not_found_count - error_count
            })

            # 生成详细的导入报告
            detailed_report = generate_part_info_update_report(
                updated_count, not_found_count, error_count, errors
            )

            logging.info(f"备件信息更新完成: {detailed_report}")

            return {
                'success': True,
                'message': detailed_report,
                'updated_count': updated_count,
                'not_found_count': not_found_count,
                'error_count': error_count,
                'errors': errors,
                'import_summary': import_summary,
                'detailed_report': detailed_report
            }

    except Exception as e:
        logging.error(f'导入备件信息更新时发生系统错误: {str(e)}')
        import_summary['import_end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return {
            'success': False,
            'message': f'导入备件信息更新时发生系统错误: {str(e)}',
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }


def update_part_specific_fields(conn, part_id, part_info):
    """仅更新备件信息的特定字段 - 确保不修改其他字段"""
    try:
        update_fields = []
        params = []

        updated_fields = []

        # 只更新指定的字段，其他字段保持不变
        if 'key_part' in part_info and part_info['key_part'] is not None:
            update_fields.append('key_part = ?')
            params.append(part_info['key_part'])
            updated_fields.append(f"关键备件: {'是' if part_info['key_part'] else '否'}")

        if 'min_stock' in part_info and part_info['min_stock'] is not None:
            update_fields.append('min_stock = ?')
            params.append(part_info['min_stock'])
            updated_fields.append(f"最低库存: {part_info['min_stock']}")

        if 'max_stock' in part_info and part_info['max_stock'] is not None:
            update_fields.append('max_stock = ?')
            params.append(part_info['max_stock'])
            updated_fields.append(f"最高库存: {part_info['max_stock']}")

        if 'lt_weeks' in part_info and part_info['lt_weeks'] is not None:
            update_fields.append('lt_weeks = ?')
            params.append(part_info['lt_weeks'])
            updated_fields.append(f"交货期: {part_info['lt_weeks']}周")

        if 'unit_price' in part_info and part_info['unit_price'] is not None:
            update_fields.append('unit_price = ?')
            params.append(part_info['unit_price'])
            updated_fields.append(f"单价: {part_info['unit_price']}")

        if 'unit' in part_info and part_info['unit']:
            update_fields.append('unit = ?')
            params.append(part_info['unit'])
            updated_fields.append(f"单位: {part_info['unit']}")

        if update_fields:
            update_fields.append('updated_date = CURRENT_TIMESTAMP')
            params.append(part_id)

            # 记录更新前的状态用于调试
            old_part = conn.execute(
                'SELECT part_no, name, type, current_stock, location FROM spare_parts WHERE id = ?',
                (part_id,)
            ).fetchone()

            conn.execute(f'''
                UPDATE spare_parts 
                SET {', '.join(update_fields)}
                WHERE id = ?
            ''', params)

            # 验证关键字段没有被意外修改
            new_part = conn.execute(
                'SELECT part_no, name, type, current_stock, location FROM spare_parts WHERE id = ?',
                (part_id,)
            ).fetchone()

            # 检查关键字段是否被修改
            field_changes = []
            if old_part['part_no'] != new_part['part_no']:
                field_changes.append(f"备件编号: {old_part['part_no']} -> {new_part['part_no']}")
            if old_part['name'] != new_part['name']:
                field_changes.append(f"备件名称: {old_part['name']} -> {new_part['name']}")
            if old_part['type'] != new_part['type']:
                field_changes.append(f"类型: {old_part['type']} -> {new_part['type']}")
            if old_part['current_stock'] != new_part['current_stock']:
                field_changes.append(f"当前库存: {old_part['current_stock']} -> {new_part['current_stock']}")
            if old_part['location'] != new_part['location']:
                field_changes.append(f"库位: {old_part['location']} -> {new_part['location']}")

            if field_changes:
                logging.warning(f"警告: 备件ID {part_id} 的关键字段被意外修改: {', '.join(field_changes)}")

            message = f"更新了 {len(updated_fields)} 个字段: {', '.join(updated_fields)}"
            logging.info(f"备件信息更新成功: {message}")
            return True, message
        else:
            return False, "没有需要更新的字段"

    except Exception as e:
        error_msg = f"更新备件信息时出错: {str(e)}"
        logging.error(error_msg)
        return False, error_msg


def extract_update_info_from_row(row):
    """从行数据中提取需要更新的备件信息"""
    part_info = {}

    # 关键备件
    key_part = row.get('关键备件 Key part')
    if key_part is not None:
        if isinstance(key_part, str):
            key_part = key_part.strip().lower() in ['是', 'yes', 'true', '1', 'y']
        part_info['key_part'] = bool(key_part)

    # 最低库存
    min_stock = safe_int(row.get('最低库存 Low stock') or row.get('Min stock', None))
    if min_stock is not None:
        part_info['min_stock'] = max(0, min_stock)

    # 最高库存
    max_stock = safe_int(row.get('最高库存 High stock') or row.get('Max stock', None))
    if max_stock is not None:
        part_info['max_stock'] = max(0, max_stock)

    # 交货期
    lt_weeks = safe_int(row.get('交货期 LT (Week)') or row.get('LT', None))
    if lt_weeks is not None:
        part_info['lt_weeks'] = max(0, lt_weeks)

    # 单价
    unit_price = safe_float(row.get('单价 Unit price (RMB)') or row.get('Unit price', None))
    if unit_price is not None:
        part_info['unit_price'] = max(0, unit_price)

    # 单位
    unit = safe_str(row.get('单位 Unit') or row.get('Unit', ''))
    if unit:
        part_info['unit'] = unit.strip()

    return part_info


def generate_part_info_update_report(updated_count, not_found_count, error_count, errors):
    """生成备件信息更新的详细报告"""

    report_parts = []

    if updated_count > 0:
        report_parts.append(f"✅ 成功更新 {updated_count} 个备件的信息")

    if not_found_count > 0:
        report_parts.append(f"⚠️ 未找到 {not_found_count} 个备件")

    if error_count > 0:
        report_parts.append(f"❌ 遇到 {error_count} 个错误")

    # 错误详情
    error_types = {}
    for error in errors:
        error_type = error.get('error', '未知错误')
        error_types[error_type] = error_types.get(error_type, 0) + 1

    for error_type, count in error_types.items():
        if count > 0:
            report_parts.append(f"   - {error_type}: {count} 次")

    return " | ".join(report_parts)


def detect_file_type(df):
    """检测上传文件的类型 - 增强版本"""
    columns = [str(col).strip() for col in df.columns]

    logging.info(f"检测文件类型，列名: {columns}")

    # 检查是否是操作记录文件
    operation_columns = ['Operation type', 'Date', 'Part No', 'Qty']
    has_operation_columns = all(col in columns for col in operation_columns)

    # 检查是否是备件信息文件
    part_info_columns = ['货号 Part no', 'Description']
    has_part_info_columns = any(col in columns for col in part_info_columns)

    # 检查是否是备件信息更新文件（只有关键字段）
    part_update_columns = ['货号 Part no', '关键备件 Key part', '最低库存 Low stock', '最高库存 High stock']
    has_part_update_columns = any(col in columns for col in part_update_columns)

    logging.info(f"包含操作记录列: {has_operation_columns}")
    logging.info(f"包含备件信息列: {has_part_info_columns}")
    logging.info(f"包含备件更新列: {has_part_update_columns}")

    if has_operation_columns:
        return 'operations_with_parts'
    elif has_part_info_columns or has_part_update_columns:
        return 'part_info_only'
    else:
        # 如果标准列名都不匹配，尝试模糊匹配
        for col in columns:
            if '货号' in col or 'Part' in col or 'part' in col:
                logging.info(f"通过模糊匹配找到备件编号列: {col}")
                return 'part_info_only'

        logging.warning(f"无法识别文件类型，列名: {columns}")
        return 'unknown'


def clean_operations_dataframe(df):
    """清理操作记录DataFrame"""
    df = df.dropna(how='all')

    string_columns = [
        'Operation type', 'Location', 'Part No', 'Description',
        'Type', 'Work center', 'Supplier or Recipients', 'Unit',
        '货号 Part no', '关键备件 Key part', '单位 Unit'
    ]
    for col in string_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({'': np.nan, 'nan': np.nan, 'None': np.nan, 'null': np.nan})
            df[col] = df[col].fillna('')

    numeric_columns = [
        'Qty', '最低库存 Low stock', '最高库存 High stock',
        '交货期 LT (Week)', '单价 Unit price (RMB)'
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].str.replace(',', '').str.replace(' ', '')
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].fillna(0)

    if '关键备件 Key part' in df.columns:
        df['关键备件 Key part'] = df['关键备件 Key part'].astype(str).str.strip().str.lower()
        df['关键备件 Key part'] = df['关键备件 Key part'].isin(['是', 'yes', 'true', '1', 'y'])

    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce', format='%Y-%m-%d')
        if df['Date'].isna().any():
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Date'] = df['Date'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else '')

    logging.info(f"数据清理完成，有效数据 {len(df)} 行")
    return df


def process_operations_with_parts_import(df):
    """处理包含操作记录的导入"""
    imported_count = 0
    error_count = 0
    updated_parts_count = 0
    updated_parts_info_count = 0
    skipped_duplicates = 0
    errors = []
    import_summary = {
        'total_rows': len(df),
        'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'file_columns': list(df.columns),
        'data_statistics': {}
    }

    try:
        with DatabaseManager().get_connection() as conn:
            affected_parts = set()

            for index, row in df.iterrows():
                row_number = index + 2
                try:
                    # 首先检查是否有备件信息需要处理
                    part_info = extract_part_info_from_row(row)
                    part_no_from_info = part_info.get('part_no')

                    # 处理备件信息（如果有）
                    part_info_updated = False
                    if part_no_from_info:
                        description = safe_str(row.get('Description') or row.get('描述', ''))
                        part_type = safe_str(row.get('Type') or row.get('类型', ''))
                        location = safe_str(row.get('Location') or row.get('库位', ''))

                        if description:
                            success, message = update_or_create_part_info(conn, part_no_from_info, description,
                                                                          part_type, location, part_info)
                            if success:
                                updated_parts_info_count += 1
                                part_info_updated = True
                                logging.info(f"成功更新备件信息: {part_no_from_info} - {description}")
                            else:
                                errors.append({
                                    'row': row_number,
                                    'error': f'备件信息更新失败: {message}',
                                    'field': '备件信息',
                                    'value': f"{part_no_from_info} - {description}",
                                    'severity': 'warning',
                                    'suggestion': '请检查备件编号和描述是否正确'
                                })

                    # 处理操作记录
                    operation_type = safe_str(row.get('Operation type', ''))
                    part_no_operation = safe_str(row.get('Part No', ''))

                    # 如果没有操作类型和操作相关的Part No，跳过操作记录处理
                    if not operation_type and not part_no_operation:
                        if part_info_updated:
                            continue
                        else:
                            continue

                    # 如果只有操作类型但没有Part No，记录错误
                    if operation_type and not part_no_operation:
                        errors.append({
                            'row': row_number,
                            'error': '有操作类型但没有备件编号',
                            'field': 'Part No',
                            'value': '',
                            'severity': 'error',
                            'suggestion': '请填写备件编号'
                        })
                        error_count += 1
                        continue

                    # 处理操作记录
                    operation_date = safe_datetime(row.get('Date'))
                    location = str(safe_str(row.get('Location', ''))).strip()
                    part_no = str(safe_str(row.get('Part No', ''))).strip()
                    description = str(safe_str(row.get('Description', ''))).strip()
                    part_type = str(safe_str(row.get('Type', '')))
                    quantity = safe_int(row.get('Qty', 0))
                    supplier_recipient = str(safe_str(row.get('Supplier or Recipients', '')))
                    work_center = str(safe_str(row.get('Work center', '')))

                    # 验证操作记录
                    validation_errors = validate_operation_row(
                        row_number, operation_type, operation_date, location,
                        part_no, description, quantity, supplier_recipient, work_center
                    )

                    if validation_errors:
                        errors.extend(validation_errors)
                        error_count += len(validation_errors)
                        continue

                    # 修复日期格式
                    if hasattr(operation_date, 'strftime'):
                        operation_date_str = operation_date.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        operation_date_str = str(operation_date)

                    # 检查备件是否存在，如果不存在则创建
                    part = conn.execute(
                        'SELECT id, current_stock FROM spare_parts WHERE part_no = ? AND name = ?',
                        (part_no, description)
                    ).fetchone()

                    part_id = None
                    if not part:
                        part_id = create_or_update_part_from_import(conn, part_no, description, part_type, location,
                                                                    part_info)
                        if part_id:
                            updated_parts_count += 1
                            logging.info(f"创建新备件: {part_no} - {description}")
                        else:
                            errors.append({
                                'row': row_number,
                                'error': '无法创建备件',
                                'field': '备件创建',
                                'value': f"{part_no} - {description}",
                                'severity': 'error',
                                'suggestion': '请检查备件数据是否完整'
                            })
                            error_count += 1
                            continue
                    else:
                        part_id = part['id']
                        # 如果之前没有更新过备件信息，现在更新
                        if not part_info_updated and part_info:
                            success, message = update_or_create_part_info(conn, part_no, description, part_type,
                                                                          location, part_info)
                            if success:
                                updated_parts_info_count += 1
                                logging.info(f"更新现有备件信息: {part_no} - {description}")

                    # 检查重复操作记录
                    is_duplicate, duplicate_details = is_duplicate_operation(
                        conn, operation_type, operation_date_str, part_no, description,
                        quantity, supplier_recipient, work_center, location
                    )

                    if is_duplicate:
                        errors.append({
                            'row': row_number,
                            'error': '跳过重复记录',
                            'field': 'Multiple',
                            'value': f"{operation_type} - {part_no} - {description}",
                            'severity': 'warning',
                            'suggestion': duplicate_details
                        })
                        skipped_duplicates += 1
                        continue

                    # 插入操作记录
                    conn.execute('''
                        INSERT INTO operation_records 
                        (operation_type, operation_date, supplier_recipient, location, part_no, description, part_type, quantity, work_center)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        operation_type,
                        operation_date_str,
                        supplier_recipient,
                        location,
                        part_no,
                        description,
                        part_type,
                        quantity,
                        work_center
                    ))

                    imported_count += 1
                    affected_parts.add((part_no, description))
                    logging.info(f"导入操作记录: {operation_type} - {part_no} - {description} - 数量: {quantity}")

                except Exception as e:
                    if 'UNIQUE constraint failed' in str(e):
                        errors.append({
                            'row': row_number,
                            'error': '唯一约束冲突',
                            'field': 'Database',
                            'value': str(e),
                            'severity': 'warning',
                            'suggestion': '记录可能已存在，已跳过'
                        })
                        skipped_duplicates += 1
                    else:
                        errors.append({
                            'row': row_number,
                            'error': f'处理数据时出错: {str(e)}',
                            'field': 'General',
                            'value': str(e),
                            'severity': 'error',
                            'suggestion': '请检查数据格式或联系系统管理员'
                        })
                        error_count += 1
                        logging.error(f"处理第 {row_number} 行数据时出错: {str(e)}")
                    continue

            conn.commit()
            if imported_count > 0:
                logging.info("开始强制同步操作记录...")
                sync_result = sync_all_operations()

                if sync_result['inbound_synced'] == 0 and sync_result['outbound_synced'] == 0:
                    logging.warning("自动同步未找到记录，尝试手动重新计算...")
                    stock_updated = recalculate_all_stock()
                    sync_result['stock_updated'] = stock_updated

            # 同步操作记录（只有有操作记录时才需要同步）
            if imported_count > 0:
                logging.info("开始强制同步操作记录...")
                sync_result = sync_all_operations()

                if sync_result['inbound_synced'] == 0 and sync_result['outbound_synced'] == 0:
                    logging.warning("自动同步未找到记录，尝试手动重新计算...")
                    stock_updated = recalculate_all_stock()
                    sync_result['stock_updated'] = stock_updated
            else:
                sync_result = {'inbound_synced': 0, 'outbound_synced': 0, 'stock_updated': 0}

            # 更新导入摘要
            import_summary.update({
                'import_end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'imported_count': imported_count,
                'error_count': error_count,
                'skipped_duplicates': skipped_duplicates,
                'updated_parts_count': updated_parts_count,
                'updated_parts_info_count': updated_parts_info_count,
                'sync_result': sync_result,
                'affected_parts_count': len(affected_parts)
            })

            # 生成详细的导入报告
            detailed_report = generate_detailed_import_report(
                imported_count, error_count, skipped_duplicates,
                updated_parts_count, updated_parts_info_count,
                sync_result, errors
            )

            logging.info(f"操作记录导入完成: {detailed_report}")

            return {
                'success': True,
                'message': detailed_report,
                'imported_count': imported_count,
                'updated_parts_count': updated_parts_count,
                'updated_parts_info_count': updated_parts_info_count,
                'error_count': error_count,
                'skipped_duplicates': skipped_duplicates,
                'errors': errors,
                'sync_result': sync_result,
                'import_summary': import_summary,
                'detailed_report': detailed_report
            }

    except Exception as e:
        logging.error(f'导入操作记录时发生系统错误: {str(e)}')
        import_summary['import_end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return {
            'success': False,
            'message': f'导入过程中发生系统错误: {str(e)}',
            'imported_count': imported_count,
            'updated_parts_count': updated_parts_count,
            'updated_parts_info_count': updated_parts_info_count,
            'error_count': error_count,
            'skipped_duplicates': skipped_duplicates,
            'errors': errors,
            'import_summary': import_summary
        }


def update_or_create_part_info(conn, part_no, description, part_type, location, part_info):
    """更新或创建备件信息"""
    try:
        part = conn.execute(
            'SELECT id FROM spare_parts WHERE part_no = ? AND name = ?',
            (part_no, description)
        ).fetchone()

        if part:
            success, message = update_existing_part_info(conn, part['id'], part_info)
            if success:
                return True, f"成功更新备件信息: {part_no} - {description}"
            else:
                return False, f"更新备件信息失败: {message}"
        else:
            part_id = create_part_info_only(conn, part_no, description, part_type, location, part_info)
            if part_id:
                return True, f"成功创建备件信息: {part_no} - {description}"
            else:
                return False, f"创建备件信息失败: {part_no} - {description}"

    except Exception as e:
        error_msg = f"更新或创建备件信息时出错: {str(e)}"
        logging.error(error_msg)
        return False, error_msg


def create_part_info_only(conn, part_no, description, part_type, location, part_info):
    """仅创建备件信息"""
    try:
        cursor = conn.execute('''
            INSERT INTO spare_parts 
            (part_no, name, type, current_stock, min_stock, max_stock, 
             key_part, lt_weeks, unit_price, unit, location, supplier, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            part_no,
            description,
            part_type,
            0,
            part_info.get('min_stock', 0),
            part_info.get('max_stock', 0),
            part_info.get('key_part', False),
            part_info.get('lt_weeks', 0),
            part_info.get('unit_price', 0),
            part_info.get('unit', ''),
            location,
            '',
            description
        ))

        part_id = cursor.lastrowid
        logging.info(f"创建新备件（仅信息）: {part_no} - {description}")
        return part_id

    except Exception as e:
        logging.error(f"创建备件信息时出错: {str(e)}")
        return None


def create_or_update_part_from_import(conn, part_no, description, part_type, location, part_info):
    """从导入数据创建或更新备件信息"""
    try:
        existing_part = conn.execute(
            'SELECT id FROM spare_parts WHERE part_no = ? AND name = ?',
            (part_no, description)
        ).fetchone()

        if existing_part:
            part_id = existing_part['id']
            update_existing_part_info(conn, part_id, part_info)
            logging.info(f"更新备件信息: {part_no} - {description}")
            return part_id
        else:
            cursor = conn.execute('''
                INSERT INTO spare_parts 
                (part_no, name, type, current_stock, min_stock, max_stock, 
                 key_part, lt_weeks, unit_price, unit, location, supplier, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                part_no,
                description,
                part_type,
                0,
                part_info.get('min_stock', 0),
                part_info.get('max_stock', 0),
                part_info.get('key_part', False),
                part_info.get('lt_weeks', 0),
                part_info.get('unit_price', 0),
                part_info.get('unit', ''),
                location,
                '',
                description
            ))

            part_id = cursor.lastrowid
            logging.info(f"创建新备件: {part_no} - {description}")
            return part_id

    except Exception as e:
        logging.error(f"创建或更新备件时出错: {str(e)}")
        raise


def update_existing_part_info(conn, part_id, part_info):
    """更新现有备件信息 - 只更新特定字段，不影响其他字段"""
    try:
        update_fields = []
        params = []

        updated_fields = []

        # 只更新指定的字段，其他字段保持不变
        if 'key_part' in part_info and part_info['key_part'] is not None:
            update_fields.append('key_part = ?')
            params.append(part_info['key_part'])
            updated_fields.append(f"关键备件: {'是' if part_info['key_part'] else '否'}")

        if 'min_stock' in part_info and part_info['min_stock'] is not None:
            update_fields.append('min_stock = ?')
            params.append(part_info['min_stock'])
            updated_fields.append(f"最低库存: {part_info['min_stock']}")

        if 'max_stock' in part_info and part_info['max_stock'] is not None:
            update_fields.append('max_stock = ?')
            params.append(part_info['max_stock'])
            updated_fields.append(f"最高库存: {part_info['max_stock']}")

        if 'lt_weeks' in part_info and part_info['lt_weeks'] is not None:
            update_fields.append('lt_weeks = ?')
            params.append(part_info['lt_weeks'])
            updated_fields.append(f"交货期: {part_info['lt_weeks']}周")

        if 'unit_price' in part_info and part_info['unit_price'] is not None:
            update_fields.append('unit_price = ?')
            params.append(part_info['unit_price'])
            updated_fields.append(f"单价: {part_info['unit_price']}")

        if 'unit' in part_info and part_info['unit'] is not None:
            update_fields.append('unit = ?')
            params.append(part_info['unit'])
            updated_fields.append(f"单位: {part_info['unit']}")

        if update_fields:
            update_fields.append('updated_date = CURRENT_TIMESTAMP')
            params.append(part_id)

            # 记录更新前的状态用于调试
            old_part = conn.execute(
                'SELECT part_no, name, type, current_stock, location FROM spare_parts WHERE id = ?',
                (part_id,)
            ).fetchone()

            conn.execute(f'''
                UPDATE spare_parts 
                SET {', '.join(update_fields)}
                WHERE id = ?
            ''', params)

            # 记录更新后的状态用于调试
            new_part = conn.execute(
                'SELECT part_no, name, type, current_stock, location FROM spare_parts WHERE id = ?',
                (part_id,)
            ).fetchone()

            # 验证关键字段没有被意外修改
            if (old_part['part_no'] != new_part['part_no'] or
                    old_part['name'] != new_part['name'] or
                    old_part['type'] != new_part['type'] or
                    old_part['current_stock'] != new_part['current_stock'] or
                    old_part['location'] != new_part['location']):
                logging.warning(f"警告: 备件ID {part_id} 的关键字段被意外修改!")
                logging.warning(f"更新前: {dict(old_part)}")
                logging.warning(f"更新后: {dict(new_part)}")

            message = f"更新了 {len(updated_fields)} 个字段: {', '.join(updated_fields)}"
            logging.info(f"备件信息更新成功: {message}")
            return True, message
        else:
            return False, "没有需要更新的字段"

    except Exception as e:
        error_msg = f"更新备件信息时出错: {str(e)}"
        logging.error(error_msg)
        return False, error_msg


def generate_detailed_import_report(imported_count, error_count, skipped_duplicates,
                                    updated_parts_count, updated_parts_info_count,
                                    sync_result, errors):
    """生成详细的导入报告"""

    report_parts = []

    if imported_count > 0:
        report_parts.append(f"✅ 成功导入 {imported_count} 条操作记录")

    if updated_parts_count > 0:
        report_parts.append(f"✅ 创建了 {updated_parts_count} 个新备件")

    if updated_parts_info_count > 0:
        report_parts.append(f"✅ 更新了 {updated_parts_info_count} 个备件的信息（包括最低库存等）")

    if sync_result.get('inbound_synced', 0) > 0:
        report_parts.append(f"🔄 同步了 {sync_result['inbound_synced']} 条入库记录")

    if sync_result.get('outbound_synced', 0) > 0:
        report_parts.append(f"🔄 同步了 {sync_result['outbound_synced']} 条出库记录")

    if sync_result.get('stock_updated', 0) > 0:
        report_parts.append(f"📊 更新了 {sync_result['stock_updated']} 个备件的库存")

    if skipped_duplicates > 0:
        report_parts.append(f"⚠️ 跳过了 {skipped_duplicates} 条重复记录")

    if error_count > 0:
        report_parts.append(f"❌ 遇到 {error_count} 个错误")

    error_types = {}
    for error in errors:
        error_type = error.get('error', '未知错误')
        error_types[error_type] = error_types.get(error_type, 0) + 1

    for error_type, count in error_types.items():
        if count > 0:
            report_parts.append(f"   - {error_type}: {count} 次")

    return " | ".join(report_parts)


def extract_part_info_from_row(row):
    """从行数据中提取备件信息 - 只提取允许更新的字段"""
    part_info = {}

    # 只提取允许更新的字段，忽略其他字段
    part_no = safe_int(row.get('货号 Part no') or row.get('Part no', None))
    if part_no is not None:
        part_info['part_no '] = max(0, part_no)

    key_part = row.get('关键备件 Key part')
    if key_part is not None:
        if isinstance(key_part, str):
            key_part = key_part.strip().lower() in ['是', 'yes', 'true', '1', 'y']
        part_info['key_part'] = bool(key_part)

    min_stock = safe_int(row.get('最低库存 Low stock') or row.get('Min stock', None))
    if min_stock is not None:
        part_info['min_stock'] = max(0, min_stock)

    max_stock = safe_int(row.get('最高库存 High stock') or row.get('Max stock', None))
    if max_stock is not None:
        part_info['max_stock'] = max(0, max_stock)

    lt_weeks = safe_int(row.get('交货期 LT (Week)') or row.get('LT', None))
    if lt_weeks is not None:
        part_info['lt_weeks'] = max(0, lt_weeks)

    unit_price = safe_float(row.get('单价 Unit price (RMB)') or row.get('Unit price', None))
    if unit_price is not None:
        part_info['unit_price'] = max(0, unit_price)

    unit = safe_str(row.get('单位 Unit') or row.get('Unit', ''))
    if unit:
        part_info['unit'] = unit.strip()

    # 明确不提取以下字段，确保它们不会被更新：
    # - part_no (仅用于查找)
    # - name (备件名称)
    # - type (类型)
    # - current_stock (当前库存)
    # - location (库位)
    # - supplier (供应商)
    # - description (描述)

    return part_info


def validate_operation_row(row_number, operation_type, operation_date, location, part_no, description, quantity,
                           supplier_recipient, work_center):
    """验证操作记录行的数据"""
    errors = []

    if not operation_type:
        errors.append(create_error(row_number, '操作类型不能为空', 'Operation type', operation_type, 'error',
                                   '请填写操作类型，如：Stock in, Stock out等'))

    valid_operation_types = ['Stock in', 'Stock out', 'Stock in - disassemble', 'Stock in - return']
    if operation_type and operation_type not in valid_operation_types:
        errors.append(
            create_error(row_number, f'操作类型无效: {operation_type}', 'Operation type', operation_type, 'error',
                         f'有效的操作类型包括: {", ".join(valid_operation_types)}'))

    if not operation_date:
        errors.append(create_error(row_number, '操作日期格式不正确', 'Date', str(operation_date), 'error',
                                   '请使用有效的日期格式，如: YYYY-MM-DD'))

    if not location:
        errors.append(create_error(row_number, '库位不能为空', 'Location', location, 'error', '请填写有效的库位代码'))

    if not part_no:
        errors.append(create_error(row_number, '备件编号不能为空', 'Part No', part_no, 'error', '请填写备件编号'))

    if not description:
        errors.append(
            create_error(row_number, '备件描述不能为空', 'Description', description, 'error', '请填写备件描述'))

    if quantity == 0:
        errors.append(create_error(row_number, '数量不能为0', 'Qty', quantity, 'error', '请填写非零的数量值'))

    if operation_type == 'Stock out' and quantity > 0:
        errors.append(create_error(row_number, '出库操作数量应为负数', 'Qty', quantity, 'warning',
                                   '出库操作数量建议使用负数，系统将自动处理'))
    elif operation_type in ['Stock in', 'Stock in - disassemble', 'Stock in - return'] and quantity < 0:
        errors.append(create_error(row_number, '入库操作数量应为正数', 'Qty', quantity, 'warning',
                                   '入库操作数量建议使用正数，系统将自动处理'))

    return errors


def create_error(row_number, error, field, value, severity, suggestion):
    """创建标准化的错误信息"""
    return {
        'row': row_number,
        'error': error,
        'field': field,
        'value': str(value) if value is not None else '',
        'severity': severity,
        'suggestion': suggestion
    }


def is_duplicate_operation(conn, operation_type, operation_date, part_no, description, quantity,
                           supplier_recipient, work_center, location, threshold=0.95):
    """检查是否为重复操作记录"""
    try:
        exact_duplicates = conn.execute('''
            SELECT id, operation_type, operation_date, part_no, description, quantity, 
                   supplier_recipient, work_center, location
            FROM operation_records 
            WHERE part_no = ? AND description = ? AND operation_date = ? AND quantity = ?
        ''', (part_no, description, operation_date, quantity)).fetchall()

        if exact_duplicates:
            for dup_op in exact_duplicates:
                if (dup_op['operation_type'] == operation_type and
                        dup_op['supplier_recipient'] == supplier_recipient and
                        dup_op['work_center'] == work_center and
                        dup_op['location'] == location):
                    return True, f"与记录ID {dup_op['id']} 完全重复"

        similar_operations = conn.execute('''
            SELECT id, operation_type, operation_date, part_no, description, quantity, 
                   supplier_recipient, work_center, location
            FROM operation_records 
            WHERE part_no = ? AND description = ? AND operation_type = ?
            AND date(operation_date) = date(?)
        ''', (part_no, description, operation_type, operation_date)).fetchall()

        max_similarity = 0.0
        most_similar_id = None

        for similar_op in similar_operations:
            similarity = calculate_operation_similarity(
                operation_type, operation_date, part_no, description,
                quantity, supplier_recipient, work_center, location,
                similar_op['operation_type'], similar_op['operation_date'],
                similar_op['part_no'], similar_op['description'],
                similar_op['quantity'], similar_op['supplier_recipient'],
                similar_op['work_center'], similar_op['location']
            )

            if similarity > max_similarity:
                max_similarity = similarity
                most_similar_id = similar_op['id']

        if max_similarity >= threshold:
            return True, f"与记录ID {most_similar_id} 高度相似 (相似度: {max_similarity:.2f})"

        return False, ""

    except Exception as e:
        logging.error(f"检查重复记录时出错: {str(e)}")
        return False, ""

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}

def calculate_operation_similarity(op1_type, op1_date, op1_part_no, op1_desc, op1_qty,
                                   op1_supplier, op1_work_center, op1_location,
                                   op2_type, op2_date, op2_part_no, op2_desc, op2_qty,
                                   op2_supplier, op2_work_center, op2_location):
    """计算两个操作记录的相似度"""
    similarity_score = 0.0

    if op1_type == op2_type:
        similarity_score += 0.30
    else:
        return similarity_score * 0.1

    if op1_part_no == op2_part_no:
        similarity_score += 0.25
    else:
        return similarity_score * 0.1

    if op1_desc == op2_desc:
        similarity_score += 0.20
    else:
        return similarity_score * 0.1

    if op1_qty == op2_qty:
        similarity_score += 0.15
    else:
        similarity_score *= 0.3

    try:
        if op1_date and op2_date:
            date1 = datetime.strptime(op1_date, '%Y-%m-%d %H:%M:%S').date()
            date2 = datetime.strptime(op2_date, '%Y-%m-%d %H:%M:%S').date()
            if date1 == date2:
                similarity_score += 0.05
            else:
                similarity_score *= 0.8
    except:
        pass

    if op1_location == op2_location:
        similarity_score += 0.03
    else:
        similarity_score *= 0.7

    if op1_supplier == op2_supplier:
        similarity_score += 0.01

    if op1_work_center == op2_work_center:
        similarity_score += 0.01

    return min(similarity_score, 1.0)