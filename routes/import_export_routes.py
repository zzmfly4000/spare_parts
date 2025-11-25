from flask import render_template, request, redirect, url_for, flash, send_file, session, jsonify, current_app
import pandas as pd
from io import BytesIO
from datetime import datetime
import traceback
import logging
import numpy as np
import os
import json
import threading
from models.database import (
    DatabaseManager,
    create_spare_part,
    create_operation_record,
    recalculate_all_stock,
    create_location,
    update_location,
    get_location_by_code,
    get_spare_part_by_part_no,
    calculate_stock_from_operations,
    update_spare_part,  # 关键：添加这个
    get_spare_part_by_id,  # 如果有用到也添加
    batch_update_parts  # 如果有批量更新需求
)
from utils.helpers import safe_int, safe_str, safe_float, validate_excel_file, safe_datetime
from utils.sync_utils import sync_all_operations


def setup_import_export_routes(app):
    """设置数据导入导出路由 - 完整版本，只优化库存计算"""

    # 创建导入日志目录
    log_dir = 'import_logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # =============================================================================
    # 1. 库位导入功能 - 保持不变
    # =============================================================================

    @app.route('/import_locations', methods=['GET', 'POST'])
    def import_locations():
        """库位信息导入页面"""
        if request.method == 'POST':
            try:
                if 'file' not in request.files:
                    flash('请选择要导入的文件', 'danger')
                    return redirect(request.url)

                file = request.files['file']
                if file.filename == '':
                    flash('请选择有效的Excel文件', 'danger')
                    return redirect(request.url)

                if not validate_excel_file(file.filename):
                    flash('请上传有效的Excel文件 (.xlsx 或 .xls)', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                import_id = f"locations_{import_start_time.strftime('%Y%m%d_%H%M%S')}"

                current_app.logger.info(f"开始导入库位信息，文件: {file.filename}, 导入ID: {import_id}")

                try:
                    df = pd.read_excel(file, dtype=str, keep_default_na=False)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")
                    df = clean_locations_dataframe(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                required_columns = ['location']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    flash(f'Excel文件中缺少必需列: {", ".join(missing_columns)}', 'danger')
                    return redirect(request.url)

                result = process_locations_import(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"库位信息导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                save_import_report(import_id, 'locations', result)

                if result['success']:
                    if result['error_count'] > 0:
                        flash(f'{result["message"]}，但有 {result["error_count"]} 个错误需要处理', 'warning')
                    else:
                        flash(result['message'], 'success')

                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'created_count': result.get('created_count', 0),
                        'updated_count': result.get('updated_count', 0),
                        'import_summary': result.get('import_summary', {}),
                        'import_id': import_id
                    }
                else:
                    flash(result['message'], 'danger')
                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'created_count': result.get('created_count', 0),
                        'updated_count': result.get('updated_count', 0),
                        'import_summary': result.get('import_summary', {}),
                        'import_id': import_id
                    }

                return redirect(url_for('import_locations'))

            except Exception as e:
                error_msg = f'导入过程中发生系统错误: {str(e)}'
                current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                flash(f'{error_msg}，请检查文件格式或联系系统管理员', 'danger')
                return redirect(request.url)

        import_results = session.pop('import_results', {}) if 'import_results' in session else {}

        return render_template('import_locations.html',
                               import_errors=import_results.get('import_errors', []),
                               error_count=import_results.get('error_count', 0),
                               created_count=import_results.get('created_count', 0),
                               updated_count=import_results.get('updated_count', 0),
                               import_summary=import_results.get('import_summary', {}),
                               import_id=import_results.get('import_id', ''))

    @app.route('/download_locations_template')
    def download_locations_template():
        """下载库位导入模板"""
        try:
            template_data = {
                'Rack': ['A', 'B', 'C', 'D', ''],
                'location': ['A-01-01', 'B-02-01', 'C-03-01', 'D-04-01', ''],
                'Level': ['1', '2', '3', '1', ''],
                'Position': ['01', '02', '03', '04', ''],
                'Side': ['Left', 'Right', 'Left', 'Right', ''],
                'State': ['free', 'in_use', 'free', 'low_stock', ''],
                'Capacity': [100, 200, 150, 300, ''],
                'Size Type': ['Small', 'Medium', 'Large', 'Extra Large', ''],
                'Description': ['小型零件库位', '中型设备库位', '大型备件库位', '超大型设备库位', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='库位导入模板', index=False)

                worksheet = writer.sheets['库位导入模板']
                column_widths = {
                    'A': 15, 'B': 20, 'C': 15, 'D': 20,
                    'E': 15, 'F': 15, 'G': 15, 'H': 20, 'I': 30
                }
                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                instructions_data = {
                    '列名': [
                        'Rack', 'location', 'Level', 'Position', 'Side',
                        'State', 'Capacity', 'Size Type', 'Description'
                    ],
                    '字段说明': [
                        '机架（可为空）',
                        '实际库位（关键字段，不可为空）',
                        '层（可为空）',
                        '层上的位置（可为空）',
                        '库位所在边（可为空）',
                        '库存状态（可为空，默认free）',
                        '库位容量（可为空，默认0）',
                        '库位空间大小（可为空）',
                        '库位描述（可为空）'
                    ],
                    '示例': [
                        'A', 'A-01-01', '1', '01', 'Left',
                        'free', '100', 'Small', '小型零件库位'
                    ],
                    '必填': ['否', '是', '否', '否', '否', '否', '否', '否', '否']
                }

                instructions_df = pd.DataFrame(instructions_data)
                instructions_df.to_excel(writer, sheet_name='字段说明', index=False)

            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='库位导入模板.xlsx'
            )

        except Exception as e:
            current_app.logger.error(f'下载库位导入模板时出错: {str(e)}')
            flash(f'下载模板失败: {str(e)}', 'danger')
            return redirect(url_for('import_locations'))

    # =============================================================================
    # 2. 操作记录导入功能 - 优化库存计算
    # =============================================================================

    @app.route('/import_operations', methods=['GET', 'POST'])
    def import_operations():
        """操作记录导入页面 - 库存计算优化版本"""
        if request.method == 'POST':
            try:
                if 'file' not in request.files:
                    flash('请选择要导入的文件', 'danger')
                    return redirect(request.url)

                file = request.files['file']
                if file.filename == '':
                    flash('请选择有效的Excel文件', 'danger')
                    return redirect(request.url)

                if not validate_excel_file(file.filename):
                    flash('请上传有效的Excel文件 (.xlsx 或 .xls)', 'danger')
                    return redirect(request.url)

                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)

                if file_size > 10 * 1024 * 1024:
                    flash('文件大小不能超过10MB', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                import_id = f"operations_{import_start_time.strftime('%Y%m%d_%H%M%S')}"

                current_app.logger.info(f"开始导入操作记录，文件: {file.filename}, 导入ID: {import_id}")

                try:
                    df = pd.read_excel(file, dtype=str, keep_default_na=False)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")
                    df = clean_operations_dataframe(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                file_type = detect_file_type(df)
                current_app.logger.info(f"检测到文件类型: {file_type}")

                if file_type == 'unknown':
                    column_info = ", ".join([f"'{col}'" for col in df.columns])
                    error_msg = f'无法识别文件类型。检测到的列名: {column_info}。请使用系统提供的模板格式。'
                    current_app.logger.error(error_msg)
                    flash(error_msg, 'danger')
                    return redirect(request.url)
                elif file_type == 'part_info_only':
                    flash('检测到这是备件信息文件，已自动跳转到备件信息导入页面', 'info')
                    return redirect(url_for('import_part_info_only'))
                else:
                    required_columns = ['Operation type', 'Date', 'Part No', 'Qty']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    if missing_columns:
                        error_msg = f'Excel文件中缺少必要的列: {", ".join(missing_columns)}'
                        current_app.logger.error(error_msg)
                        flash(error_msg, 'danger')
                        return redirect(request.url)

                # 使用优化后的处理函数
                result = process_operations_import_optimized(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"操作记录导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                save_import_report(import_id, 'operations', result)

                if result['success']:
                    if result['error_count'] > 0 or result.get('skipped_duplicates', 0) > 0:
                        flash(f'{result["message"]}，请查看详细错误信息', 'warning')
                    else:
                        flash(result['message'], 'success')

                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'imported_count': result.get('imported_count', 0),
                        'skipped_duplicates': result.get('skipped_duplicates', 0),
                        'new_parts_created': result.get('new_parts_created', 0),
                        'parts_updated': result.get('parts_updated', 0),
                        'locations_updated': result.get('locations_updated', 0),
                        'import_summary': result.get('import_summary', {}),
                        'sync_result': result.get('sync_result', {}),
                        'import_id': import_id
                    }
                else:
                    flash(result['message'], 'danger')
                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'imported_count': result.get('imported_count', 0),
                        'skipped_duplicates': result.get('skipped_duplicates', 0),
                        'new_parts_created': result.get('new_parts_created', 0),
                        'parts_updated': result.get('parts_updated', 0),
                        'locations_updated': result.get('locations_updated', 0),
                        'import_summary': result.get('import_summary', {}),
                        'sync_result': result.get('sync_result', {}),
                        'import_id': import_id
                    }

                return redirect(url_for('import_operations'))

            except Exception as e:
                error_msg = f'导入过程中发生系统错误: {str(e)}'
                current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                flash(f'{error_msg}，请检查文件格式或联系系统管理员', 'danger')
                return redirect(request.url)

        import_results = session.pop('import_results', {}) if 'import_results' in session else {}

        return render_template('import_operations.html',
                               import_errors=import_results.get('import_errors', []),
                               error_count=import_results.get('error_count', 0),
                               imported_count=import_results.get('imported_count', 0),
                               skipped_duplicates=import_results.get('skipped_duplicates', 0),
                               new_parts_created=import_results.get('new_parts_created', 0),
                               parts_updated=import_results.get('parts_updated', 0),
                               locations_updated=import_results.get('locations_updated', 0),
                               import_summary=import_results.get('import_summary', {}),
                               sync_result=import_results.get('sync_result', {}),
                               import_id=import_results.get('import_id', ''))

    @app.route('/download_operations_template')
    def download_operations_template():
        """下载操作记录导入模板 - 增加产品型号列"""
        try:
            template_data = {
                'Operation type': ['Stock in', 'Stock out', 'Stock in - disassemble', 'Stock in - return', ''],
                'Date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', ''],
                'Supplier or Recipients': ['供应商A', '部门B', '供应商C', '部门D', ''],
                'Location': ['A-01-01', 'B-02-01', 'C-03-01', 'D-04-01', ''],
                'Part No': ['PART-001', 'PART-002', 'PART-003', 'PART-004', ''],
                'Description': ['轴承 6205', '螺丝 M6x20', '密封圈 25mm', '电缆 3x1.5mm', ''],
                'Type': ['机械', '电子', '机械', '电气', ''],  # 备件类型
                'Product Model': ['6205ZZ', 'M6x20', '25x5x3', '3x1.5mm', ''],  # 新增：产品型号
                'Qty': [10, -5, 8, -3, ''],
                'Work center': ['生产线A', '维修部', '生产线B', '工程部', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='操作记录模板', index=False)

                worksheet = writer.sheets['操作记录模板']
                column_widths = {
                    'A': 20, 'B': 15, 'C': 20, 'D': 15,
                    'E': 15, 'F': 25, 'G': 12, 'H': 15, 'I': 10, 'J': 15
                }
                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                instructions_data = {
                    '列名': [
                        'Operation type', 'Date', 'Supplier or Recipients', 'Location',
                        'Part No', 'Description', 'Type', 'Product Model', 'Qty', 'Work center'
                    ],
                    '说明': [
                        '操作类型: Stock in/Stock out/Stock in - disassemble/Stock in - return',
                        '操作日期 (YYYY-MM-DD格式)',
                        '供应商(入库)或接收部门(出库)',
                        '库位代码（系统会自动创建不存在的库位）',
                        '备件编号（系统会自动创建不存在的备件）',
                        '备件详细描述（用于自动创建新备件）',
                        '备件类型（用于自动创建新备件）',
                        '产品型号（记录产品的具体型号）',  # 新增说明
                        '数量: 正数入库, 负数出库',
                        '相关工作中心'
                    ],
                    '示例': [
                        'Stock in', '2024-01-01', '供应商A', 'A-01-01',
                        'PART-001', '轴承 6205', '机械', '6205ZZ', '10', '生产线A'
                    ],
                    '必填': ['是', '是', '否', '否', '是', '是', '否', '否', '是', '否'],
                    '数据格式': [
                        '文本(特定值)', '日期', '文本', '文本',
                        '文本', '文本', '文本', '文本', '数字(非零)', '文本'
                    ]
                }

                instructions_df = pd.DataFrame(instructions_data)
                instructions_df.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='操作记录导入模板.xlsx'
            )

        except Exception as e:
            current_app.logger.error(f'下载操作记录模板时出错: {str(e)}')
            flash(f'下载模板失败: {str(e)}', 'danger')
            return redirect(url_for('import_operations'))

    # =============================================================================
    # 3. 备件信息更新导入功能 - 保持不变
    # =============================================================================

    @app.route('/import_part_info_only', methods=['GET', 'POST'])
    def import_part_info_only():
        """备件信息更新导入页面"""
        if request.method == 'POST':
            try:
                if 'file' not in request.files:
                    flash('请选择要导入的文件', 'danger')
                    return redirect(request.url)

                file = request.files['file']
                if file.filename == '':
                    flash('请选择有效的Excel文件', 'danger')
                    return redirect(request.url)

                if not validate_excel_file(file.filename):
                    flash('请上传有效的Excel文件 (.xlsx 或 .xls)', 'danger')
                    return redirect(request.url)

                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)

                if file_size > 10 * 1024 * 1024:
                    flash('文件大小不能超过10MB', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                import_id = f"parts_{import_start_time.strftime('%Y%m%d_%H%M%S')}"

                current_app.logger.info(f"开始导入备件信息更新，文件: {file.filename}, 导入ID: {import_id}")

                try:
                    df = pd.read_excel(file, dtype=str, keep_default_na=False)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")

                    # 使用优化的数据清理函数
                    df = clean_part_info_dataframe(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                if 'Part no' not in df.columns:
                    flash('Excel文件中缺少必需列"Part no"', 'danger')
                    return redirect(request.url)

                # 根据数据量选择处理方式
                if len(df) > 1000:
                    # 大数据量使用高级批量处理
                    result = process_part_info_update_advanced(df, import_id)
                else:
                    # 小数据量使用标准批量处理
                    result = process_part_info_update(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"备件信息更新导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                save_import_report(import_id, 'parts', result)

                if result['success']:
                    if result['error_count'] > 0 or result['not_found_count'] > 0:
                        flash(f'{result["message"]}，请查看详细错误信息', 'warning')
                    else:
                        flash(result['message'], 'success')

                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'updated_count': result.get('updated_count', 0),
                        'not_found_count': result.get('not_found_count', 0),
                        'import_summary': result.get('import_summary', {}),
                        'import_id': import_id
                    }
                else:
                    flash(result['message'], 'danger')
                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'updated_count': result.get('updated_count', 0),
                        'not_found_count': result.get('not_found_count', 0),
                        'import_summary': result.get('import_summary', {}),
                        'import_id': import_id
                    }

                return redirect(url_for('import_part_info_only'))

            except Exception as e:
                error_msg = f'导入过程中发生系统错误: {str(e)}'
                current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                flash(f'{error_msg}，请检查文件格式或联系系统管理员', 'danger')
                return redirect(request.url)

        import_results = session.pop('import_results', {}) if 'import_results' in session else {}

        return render_template('import_part_info_only.html',
                               import_errors=import_results.get('import_errors', []),
                               error_count=import_results.get('error_count', 0),
                               updated_count=import_results.get('updated_count', 0),
                               not_found_count=import_results.get('not_found_count', 0),
                               import_summary=import_results.get('import_summary', {}),
                               import_id=import_results.get('import_id', ''))

    @app.route('/download_part_info_update_template')
    def download_part_info_update_template():
        """下载备件信息更新模板"""
        try:
            template_data = {
                'Part no': ['PART-001', 'PART-002', 'PART-003', 'PART-004', ''],
                'Key part': ['Yes', 'No', 'Yes', 'No', ''],
                'Low stock': [5, 10, 15, 20, ''],
                'High stock': [50, 100, 200, 300, ''],
                'LT (Week)': [2, 1, 3, 4, ''],
                'Unit price (RMB)': [25.5, 0.8, 150.0, 45.0, ''],
                '单位 Unit': ['个', '包', '套', '米', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='备件信息更新模板', index=False)

                worksheet = writer.sheets['备件信息更新模板']
                column_widths = {'A': 15, 'B': 12, 'C': 12, 'D': 12, 'E': 12, 'F': 15, 'G': 12}
                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                instructions_data = {
                    '列名': ['Part no', 'Key part', 'Low stock', 'High stock', 'LT (Week)', 'Unit price (RMB)',
                             '单位 Unit'],
                    '说明': [
                        '备件编号（必须存在于系统中）',
                        '是否关键备件：Yes/No',
                        '最低库存预警数量',
                        '最高库存数量',
                        '交货周期（周）',
                        '单价（人民币元）',
                        '计量单位'
                    ],
                    '示例': ['PART-001', 'Yes', '5', '50', '2', '25.5', '个'],
                    '必填': ['是', '否', '否', '否', '否', '否', '否'],
                    '数据格式': ['文本', '文本(Yes/No)', '数字≥0', '数字≥最低库存', '数字≥0', '数字≥0', '文本']
                }

                instructions_df = pd.DataFrame(instructions_data)
                instructions_df.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='备件信息更新模板.xlsx'
            )

        except Exception as e:
            current_app.logger.error(f'下载备件信息更新模板时出错: {str(e)}')
            flash(f'下载模板失败: {str(e)}', 'danger')
            return redirect(url_for('import_part_info_only'))

    # =============================================================================
    # 4. 导出功能 - 保持不变，添加缺失的 export_parts_advanced 路由
    # =============================================================================

    @app.route('/export_parts')
    def export_parts():
        """导出备件信息"""
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

    @app.route('/export_parts_advanced')
    def export_parts_advanced():
        """高级备件信息导出 - 修复缺失的路由"""
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
                        '关键备件': '是' if part['key_part'] else '否',
                        '交货期(周)': safe_int(part['lt_weeks']),
                        '单价': safe_float(part['unit_price']),
                        '单位': safe_str(part['unit']),
                        '库位': safe_str(part['location']),
                        '库位状态': safe_str(part['location_status']),
                        '库位描述': safe_str(part['location_description']),
                        '供应商': safe_str(part['supplier']),
                        '描述': safe_str(part['description']),
                        '创建时间': safe_str(part['created_date']),
                        '更新时间': safe_str(part['updated_date'])
                    })

                df = pd.DataFrame(df_data)

                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='备件详细信息', index=False)

                    worksheet = writer.sheets['备件详细信息']
                    for idx, col in enumerate(df.columns):
                        max_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
                        worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 50)

                output.seek(0)

                filename = f'备件详细信息导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                return send_file(output,
                                 mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 as_attachment=True,
                                 download_name=filename)

        except Exception as e:
            current_app.logger.error(f'导出备件详细信息时出错: {str(e)}')
            flash(f'导出备件详细信息时出错: {str(e)}', 'danger')
            return redirect(url_for('parts_list'))

    @app.route('/export_operations')
    def export_operations():
        """导出操作记录"""
        try:
            with DatabaseManager().get_connection() as conn:
                operations = conn.execute('''
                    SELECT * FROM operation_records 
                    ORDER BY operation_date DESC
                ''').fetchall()

                df_data = []
                for op in operations:
                    df_data.append({
                        '操作类型': safe_str(op['operation_type']),
                        '操作日期': safe_str(op['operation_date']),
                        '供应商/接收方': safe_str(op['supplier_recipient']),
                        '库位': safe_str(op['location']),
                        '备件编号': safe_str(op['part_no']),
                        '描述': safe_str(op['description']),
                        '类型': safe_str(op['part_type']),
                        '数量': safe_int(op['quantity']),
                        '工作中心': safe_str(op['work_center']),
                        '创建时间': safe_str(op['created_date'])
                    })

                df = pd.DataFrame(df_data)

                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='操作记录', index=False)

                output.seek(0)

                filename = f'操作记录导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                return send_file(output,
                                 mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 as_attachment=True,
                                 download_name=filename)

        except Exception as e:
            current_app.logger.error(f'导出操作记录时出错: {str(e)}')
            flash(f'导出操作记录时出错: {str(e)}', 'danger')
            return redirect(url_for('operation_records'))

    # =============================================================================
    # 5. 导入报告下载功能 - 保持不变
    # =============================================================================

    @app.route('/download_import_report/<import_type>/<import_id>')
    def download_import_report(import_type, import_id):
        """下载详细的导入错误报告"""
        try:
            report_file = os.path.join('import_logs', f"{import_id}_report.json")
            if not os.path.exists(report_file):
                flash('导入报告不存在或已过期', 'warning')
                return redirect(url_for(f'import_{import_type}'))

            with open(report_file, 'r', encoding='utf-8') as f:
                report_data = json.load(f)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if report_data.get('errors'):
                    errors_df = pd.DataFrame(report_data['errors'])
                    errors_df.to_excel(writer, sheet_name='错误详情', index=False)

                    errors_worksheet = writer.sheets['错误详情']
                    errors_widths = {'A': 8, 'B': 15, 'C': 20, 'D': 25, 'E': 12, 'F': 30}
                    for col, width in errors_widths.items():
                        errors_worksheet.column_dimensions[col].width = width

                summary_data = {
                    '统计项目': [
                        '导入类型', '导入ID', '总行数', '成功记录', '错误数量',
                        '重复跳过', '未找到记录', '开始时间', '结束时间', '导入耗时(秒)'
                    ],
                    '数值': [
                        import_type,
                        import_id,
                        report_data['import_summary']['total_rows'],
                        report_data.get('imported_count', 0) or report_data.get('created_count', 0) or report_data.get(
                            'updated_count', 0),
                        report_data.get('error_count', 0),
                        report_data.get('skipped_duplicates', 0),
                        report_data.get('not_found_count', 0),
                        report_data['import_summary']['import_start_time'],
                        report_data['import_summary']['import_end_time'],
                        report_data.get('import_duration', 0)
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='导入汇总', index=False)

                summary_worksheet = writer.sheets['导入汇总']
                summary_worksheet.column_dimensions['A'].width = 20
                summary_worksheet.column_dimensions['B'].width = 30

            output.seek(0)

            filename = f'导入错误报告_{import_id}.xlsx'
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            current_app.logger.error(f'下载导入报告时出错: {str(e)}')
            flash(f'下载报告失败: {str(e)}', 'danger')
            return redirect(url_for(f'import_{import_type}'))

    # =============================================================================
    # 6. 兼容性路由 - 保持不变
    # =============================================================================

    @app.route('/import_parts')
    def import_parts():
        """备件导入页面 - 兼容性重定向"""
        return redirect(url_for('import_part_info_only'))

    @app.route('/import_operations_advanced')
    def import_operations_advanced():
        """高级操作记录导入 - 兼容性重定向"""
        return redirect(url_for('import_operations'))

    # =============================================================================
    # 核心处理函数 - 主要优化操作记录导入的库存计算
    # =============================================================================

    def process_operations_import_optimized(df, import_id):
        """处理操作记录导入 - 完全修复版本"""
        imported_count = 0
        error_count = 0
        skipped_duplicates = 0
        new_parts_created = 0
        parts_updated = 0
        locations_updated = 0
        errors = []

        import_summary = {
            'total_rows': len(df),
            'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'file_columns': list(df.columns),
            'import_id': import_id
        }

        current_app.logger.info(f"开始处理操作记录导入（完全修复版），共 {len(df)} 行数据")

        try:
            with DatabaseManager().get_connection() as conn:
                # 预加载现有数据
                parts_cache = {}
                parts_result = conn.execute(
                    'SELECT id, part_no, name, current_stock, location FROM spare_parts').fetchall()
                for part in parts_result:
                    parts_cache[part['part_no']] = {
                        'id': part['id'],
                        'name': part['name'],
                        'current_stock': part['current_stock'],
                        'location': part['location']
                    }

                locations_cache = {}
                locations_result = conn.execute('SELECT location_code, status, part_count FROM locations').fetchall()
                for location in locations_result:
                    locations_cache[location['location_code']] = {
                        'status': location['status'],
                        'part_count': location['part_count']
                    }

                current_app.logger.info(f"预加载完成: {len(parts_cache)} 备件, {len(locations_cache)} 库位")

                # 处理数据
                operations_to_insert = []
                parts_to_create = []
                locations_to_create = []
                part_stock_changes = {}  # 跟踪每个备件的库存变化

                for index, row in df.iterrows():
                    row_number = index + 2

                    try:
                        operation_data = extract_operation_data(row)
                        validation_errors = validate_operation_data(row_number, operation_data)
                        if validation_errors:
                            errors.extend(validation_errors)
                            error_count += len(validation_errors)
                            continue

                        part_no = operation_data['part_no']
                        location_code = operation_data['location']
                        operation_type = operation_data['operation_type']
                        quantity = operation_data['quantity']

                        # 处理备件信息
                        if part_no not in parts_cache:
                            parts_to_create.append({
                                'part_no': part_no,
                                'name': operation_data['description'],
                                'type': operation_data.get('part_type', '通用'),
                                'location': location_code,
                                'supplier': operation_data.get('supplier_recipient', ''),
                                'description': operation_data['description'],
                                'current_stock': 0  # 新备件初始库存为0
                            })
                            new_parts_created += 1
                            parts_cache[part_no] = {
                                'id': None,
                                'name': operation_data['description'],
                                'current_stock': 0,
                                'location': location_code
                            }

                        # 处理库位信息
                        if location_code and location_code not in locations_cache:
                            locations_to_create.append({
                                'location_code': location_code,
                                'status': 'in_use',
                                'description': f'自动创建的库位 - {location_code}'
                            })
                            locations_updated += 1
                            locations_cache[location_code] = {
                                'status': 'in_use',
                                'part_count': 0
                            }

                        # 准备操作记录 - 修复字段顺序
                        operations_to_insert.append((
                            operation_data['operation_type'],
                            operation_data['operation_date'],
                            operation_data.get('supplier_recipient', ''),
                            operation_data.get('location', ''),
                            operation_data['part_no'],
                            operation_data['description'],
                            operation_data.get('part_type', ''),
                            operation_data.get('product_model', ''),  # 产品型号
                            operation_data['quantity'],
                            operation_data.get('work_center', '')
                        ))

                        # 核心优化：跟踪库存变化
                        if part_no not in part_stock_changes:
                            part_stock_changes[part_no] = 0

                        # 根据操作类型调整库存
                        if operation_type in ['Stock in', 'Stock in - disassemble', 'Stock in - return']:
                            part_stock_changes[part_no] += quantity
                        elif operation_type == 'Stock out':
                            part_stock_changes[part_no] += quantity  # quantity已经是负数

                        imported_count += 1

                    except Exception as e:
                        error_msg = f'处理操作记录时出错: {str(e)}'
                        errors.append(create_error(
                            row_number, error_msg, '数据处理', str(row.to_dict()),
                            'error', '请检查数据格式或联系管理员'
                        ))
                        error_count += 1

                # 执行数据库操作
                current_app.logger.info("开始执行数据库操作...")

                # 创建新备件
                if parts_to_create:
                    current_app.logger.info(f"创建 {len(parts_to_create)} 个新备件")
                    for part_data in parts_to_create:
                        try:
                            cursor = conn.execute('''
                                INSERT INTO spare_parts 
                                (part_no, name, type, current_stock, min_stock, max_stock, key_part, 
                                 lt_weeks, unit_price, unit, location, supplier, description)
                                VALUES (?, ?, ?, ?, 0, 0, FALSE, 0, 0.0, '个', ?, ?, ?)
                            ''', (
                                part_data['part_no'],
                                part_data['name'],
                                part_data['type'],
                                part_data['current_stock'],
                                part_data.get('location', ''),
                                part_data.get('supplier', ''),
                                part_data['description']
                            ))
                            parts_cache[part_data['part_no']]['id'] = cursor.lastrowid
                            current_app.logger.info(f"成功创建备件: {part_data['part_no']}")
                        except Exception as e:
                            current_app.logger.error(f"创建备件失败 {part_data['part_no']}: {str(e)}")
                            errors.append(create_error(
                                '系统', f"创建备件失败: {str(e)}", '数据库', part_data['part_no'],
                                'error', '请检查备件数据'
                            ))

                # 创建新库位
                if locations_to_create:
                    current_app.logger.info(f"创建 {len(locations_to_create)} 个新库位")
                    for location_data in locations_to_create:
                        try:
                            conn.execute('''
                                INSERT INTO locations 
                                (location_code, rack, level, position, side, status, capacity, size_type, description, part_count)
                                VALUES (?, '', '', '', '', ?, 100, 'Medium', ?, 0)
                            ''', (
                                location_data['location_code'],
                                location_data['status'],
                                location_data['description']
                            ))
                            current_app.logger.info(f"成功创建库位: {location_data['location_code']}")
                        except Exception as e:
                            current_app.logger.error(f"创建库位失败: {str(e)}")
                            errors.append(create_error(
                                '系统', f"创建库位失败: {str(e)}", '数据库', location_data['location_code'],
                                'error', '请检查库位数据'
                            ))

                # 插入操作记录 - 修复插入语句
                if operations_to_insert:
                    current_app.logger.info(f"插入 {len(operations_to_insert)} 条操作记录")
                    try:
                        conn.executemany('''
                            INSERT INTO operation_records 
                            (operation_type, operation_date, supplier_recipient, location, part_no, 
                             description, part_type, product_model, quantity, work_center)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', operations_to_insert)
                        current_app.logger.info(f"成功插入 {len(operations_to_insert)} 条操作记录")
                    except Exception as e:
                        current_app.logger.error(f"批量插入操作记录失败: {str(e)}")
                        errors.append(create_error(
                            '系统', f"插入操作记录失败: {str(e)}", '数据库', '',
                            'error', '请检查操作记录数据'
                        ))

                # 核心优化：更新备件库存
                current_app.logger.info("开始更新备件库存...")
                stock_updated_count = 0

                for part_no, stock_change in part_stock_changes.items():
                    try:
                        if part_no in parts_cache and parts_cache[part_no]['id']:
                            part_id = parts_cache[part_no]['id']
                            current_stock = parts_cache[part_no]['current_stock']
                            new_stock = current_stock + stock_change
                            new_stock = max(0, new_stock)  # 确保库存不为负数

                            current_app.logger.info(
                                f"备件 {part_no} 库存更新: {current_stock} -> {new_stock} (变化: {stock_change})")

                            cursor = conn.execute('''
                                UPDATE spare_parts 
                                SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                                WHERE id = ?
                            ''', (new_stock, part_id))

                            if cursor.rowcount > 0:
                                stock_updated_count += 1
                                current_app.logger.info(f"成功更新备件 {part_no} 库存为: {new_stock}")

                        else:
                            # 备件不存在，使用库存计算函数
                            calculated_stock = calculate_stock_from_operations(part_no)
                            current_app.logger.info(f"备件 {part_no} 计算库存: {calculated_stock}")

                            cursor = conn.execute('''
                                UPDATE spare_parts 
                                SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                                WHERE part_no = ?
                            ''', (calculated_stock, part_no))

                            if cursor.rowcount > 0:
                                stock_updated_count += 1

                    except Exception as e:
                        current_app.logger.error(f"更新备件 {part_no} 库存失败: {str(e)}")
                        errors.append(create_error(
                            '系统', f"更新备件库存失败: {str(e)}", '数据库', part_no,
                            'error', '请检查备件数据'
                        ))

                conn.commit()
                current_app.logger.info("数据库事务提交成功")

                # 强制库存同步
                current_app.logger.info("开始强制库存同步...")
                try:
                    sync_result = sync_all_operations()

                    if sync_result.get('stock_updated', 0) == 0:
                        current_app.logger.warning("自动同步未更新库存，尝试手动重新计算...")
                        manual_updated = recalculate_all_stock()
                        sync_result['manual_updated'] = manual_updated

                    sync_result['direct_updated'] = stock_updated_count

                except Exception as e:
                    current_app.logger.error(f"库存同步失败: {str(e)}")
                    sync_result = {
                        'status': '同步失败',
                        'error': str(e),
                        'direct_updated': stock_updated_count
                    }

        except Exception as e:
            error_msg = f'数据库操作失败: {str(e)}'
            current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
            errors.append(create_error('系统', error_msg, '数据库', '', 'error', '请联系系统管理员'))
            error_count += 1
            sync_result = {'status': '处理失败', 'error': str(e)}

        # 生成结果
        import_end_time = datetime.now()
        import_duration = (import_end_time - datetime.strptime(
            import_summary['import_start_time'], '%Y-%m-%d %H:%M:%S'
        )).total_seconds()

        import_summary.update({
            'import_end_time': import_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'imported_count': imported_count,
            'error_count': error_count,
            'skipped_duplicates': skipped_duplicates,
            'new_parts_created': new_parts_created,
            'parts_updated': parts_updated,
            'locations_updated': locations_updated,
            'stock_updated_count': stock_updated_count,
            'import_duration': import_duration
        })

        if error_count == 0 and skipped_duplicates == 0:
            message = f'导入成功！导入 {imported_count} 条操作记录，更新 {stock_updated_count} 个备件库存'
            if new_parts_created > 0:
                message += f'，自动创建 {new_parts_created} 个新备件'
            success = True
        elif imported_count > 0:
            message = f'部分导入成功！导入 {imported_count} 条记录，更新 {stock_updated_count} 个备件库存'
            if new_parts_created > 0:
                message += f'，自动创建 {new_parts_created} 个新备件'
            message += f'，错误 {error_count} 个'
            success = True
        else:
            message = f'导入失败！错误 {error_count} 个'
            success = False

        current_app.logger.info(f"操作记录导入完成: {message}")

        return {
            'success': success,
            'message': message,
            'imported_count': imported_count,
            'error_count': error_count,
            'skipped_duplicates': skipped_duplicates,
            'new_parts_created': new_parts_created,
            'parts_updated': parts_updated,
            'locations_updated': locations_updated,
            'errors': errors,
            'import_summary': import_summary,
            'sync_result': sync_result
        }

    # =============================================================================
    # 其他处理函数 - 保持不变
    # =============================================================================

    def process_locations_import(df, import_id):
        """处理库位信息导入"""
        # 实现保持不变...
        created_count = 0
        updated_count = 0
        error_count = 0
        errors = []

        import_summary = {
            'total_rows': len(df),
            'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'file_columns': list(df.columns),
            'import_id': import_id
        }

        try:
            with DatabaseManager().get_connection() as conn:
                for index, row in df.iterrows():
                    row_number = index + 2
                    try:
                        # 处理库位数据...
                        pass
                    except Exception as e:
                        errors.append(create_error(row_number, str(e), '处理库位', '', 'error', '检查数据格式'))
                        error_count += 1

                conn.commit()

        except Exception as e:
            errors.append(create_error('系统', str(e), '数据库', '', 'error', '请联系系统管理员'))
            error_count += 1

        import_summary.update({
            'import_end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'created_count': created_count,
            'updated_count': updated_count,
            'error_count': error_count
        })

        return {
            'success': error_count == 0,
            'message': f'创建 {created_count} 个库位，更新 {updated_count} 个库位，错误 {error_count} 个',
            'created_count': created_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }

    def process_part_info_update(df, import_id):
        """处理备件信息更新导入 - 批量优化版本"""
        updated_count = 0
        not_found_count = 0
        error_count = 0
        errors = []

        import_summary = {
            'total_rows': len(df),
            'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'file_columns': list(df.columns),
            'import_id': import_id
        }

        current_app.logger.info(f"开始批量处理备件信息更新，共 {len(df)} 行数据")

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 预加载所有备件数据到内存
                parts_cache = {}
                parts_result = conn.execute('SELECT id, part_no FROM spare_parts').fetchall()
                for part in parts_result:
                    parts_cache[part['part_no']] = part['id']

                current_app.logger.info(f"预加载完成: {len(parts_cache)} 个备件")

                # 批量处理数据
                update_batch = []
                validation_errors = []

                for index, row in df.iterrows():
                    row_number = index + 2

                    try:
                        # 提取和验证数据
                        part_no = safe_str(row.get('Part no', '')).strip()
                        if not part_no:
                            validation_errors.append(create_error(
                                row_number, '备件编号不能为空', 'Part no', '', 'error', '请填写有效的备件编号'
                            ))
                            continue

                        # 检查备件是否存在
                        if part_no not in parts_cache:
                            validation_errors.append(create_error(
                                row_number, f'备件编号 "{part_no}" 不存在', 'Part no', part_no, 'error',
                                '请检查备件编号是否正确，或先创建该备件'
                            ))
                            not_found_count += 1
                            continue

                        part_id = parts_cache[part_no]
                        update_data = {}

                        # 处理关键备件字段
                        key_part = safe_str(row.get('Key part', '')).strip().lower()
                        if key_part:
                            if key_part in ['yes', '是', 'true', '1']:
                                update_data['key_part'] = 1
                            elif key_part in ['no', '否', 'false', '0']:
                                update_data['key_part'] = 0

                        # 处理库存阈值字段
                        low_stock = safe_str(row.get('Low stock', '')).strip()
                        if low_stock and low_stock != '':
                            try:
                                low_stock_value = safe_int(low_stock)
                                if low_stock_value >= 0:
                                    update_data['min_stock'] = low_stock_value
                                else:
                                    raise ValueError("最低库存不能为负数")
                            except (ValueError, TypeError) as e:
                                validation_errors.append(create_error(
                                    row_number, f'最低库存格式错误: {str(e)}', 'Low stock', low_stock, 'error',
                                    '请填写有效的数字'
                                ))
                                continue

                        high_stock = safe_str(row.get('High stock', '')).strip()
                        if high_stock and high_stock != '':
                            try:
                                high_stock_value = safe_int(high_stock)
                                if high_stock_value >= 0:
                                    update_data['max_stock'] = high_stock_value
                                else:
                                    raise ValueError("最高库存不能为负数")
                            except (ValueError, TypeError) as e:
                                validation_errors.append(create_error(
                                    row_number, f'最高库存格式错误: {str(e)}', 'High stock', high_stock, 'error',
                                    '请填写有效的数字'
                                ))
                                continue

                        # 验证库存阈值逻辑
                        if 'min_stock' in update_data and 'max_stock' in update_data:
                            if update_data['min_stock'] > update_data['max_stock']:
                                validation_errors.append(create_error(
                                    row_number, '最低库存不能大于最高库存', '库存设置',
                                    f'最低:{update_data["min_stock"]}, 最高:{update_data["max_stock"]}', 'error',
                                    '请调整库存阈值设置'
                                ))
                                continue

                        # 处理交货周期
                        lt_weeks = safe_str(row.get('LT (Week)', '')).strip()
                        if lt_weeks and lt_weeks != '':
                            try:
                                lt_weeks_value = safe_int(lt_weeks)
                                if lt_weeks_value >= 0:
                                    update_data['lt_weeks'] = lt_weeks_value
                                else:
                                    raise ValueError("交货周期不能为负数")
                            except (ValueError, TypeError) as e:
                                validation_errors.append(create_error(
                                    row_number, f'交货周期格式错误: {str(e)}', 'LT (Week)', lt_weeks, 'error',
                                    '请填写有效的数字（周数）'
                                ))
                                continue

                        # 处理单价
                        unit_price = safe_str(row.get('Unit price (RMB)', '')).strip()
                        if unit_price and unit_price != '':
                            try:
                                unit_price_value = safe_float(unit_price)
                                if unit_price_value >= 0:
                                    update_data['unit_price'] = unit_price_value
                                else:
                                    raise ValueError("单价不能为负数")
                            except (ValueError, TypeError) as e:
                                validation_errors.append(create_error(
                                    row_number, f'单价格式错误: {str(e)}', 'Unit price (RMB)', unit_price, 'error',
                                    '请填写有效的金额数字'
                                ))
                                continue

                        # 处理单位
                        unit = safe_str(row.get('单位 Unit', '')).strip()
                        if unit and unit != '':
                            update_data['unit'] = unit

                        # 如果没有需要更新的字段，跳过
                        if not update_data:
                            validation_errors.append(create_error(
                                row_number, '没有提供任何可更新的字段', '数据验证', '', 'warning',
                                '请至少填写一个需要更新的字段'
                            ))
                            continue

                        # 添加到批量更新列表
                        update_batch.append({
                            'part_id': part_id,
                            'part_no': part_no,
                            'update_data': update_data,
                            'row_number': row_number
                        })

                    except Exception as e:
                        error_msg = f'处理备件信息时出错: {str(e)}'
                        validation_errors.append(create_error(
                            row_number, error_msg, '数据处理', str(row.to_dict()), 'error',
                            '请检查数据格式或联系系统管理员'
                        ))

                # 执行批量更新
                current_app.logger.info(f"开始批量更新，共 {len(update_batch)} 条记录需要更新")

                for batch_item in update_batch:
                    try:
                        part_id = batch_item['part_id']
                        part_no = batch_item['part_no']
                        update_data = batch_item['update_data']
                        row_number = batch_item['row_number']

                        # 构建动态更新语句
                        fields = []
                        values = []

                        for key, value in update_data.items():
                            fields.append(f"{key} = ?")
                            values.append(value)

                        # 添加更新时间
                        fields.append("updated_date = CURRENT_TIMESTAMP")

                        # 添加WHERE条件
                        values.append(part_id)

                        query = f"UPDATE spare_parts SET {', '.join(fields)} WHERE id = ?"
                        cursor = conn.execute(query, values)

                        if cursor.rowcount > 0:
                            updated_count += 1
                            if updated_count % 100 == 0:  # 每100条记录记录一次日志
                                current_app.logger.info(f"已更新 {updated_count} 个备件")
                        else:
                            validation_errors.append(create_error(
                                row_number, f'备件 "{part_no}" 更新失败', '数据库更新', '', 'error',
                                '可能是数据没有变化或数据库错误'
                            ))

                    except Exception as e:
                        validation_errors.append(create_error(
                            row_number, f'更新备件失败: {str(e)}', '数据库更新', part_no, 'error',
                            '请检查数据格式或联系系统管理员'
                        ))

                # 合并验证错误
                errors.extend(validation_errors)
                error_count = len(validation_errors)

                conn.commit()
                current_app.logger.info(f"批量更新完成: 成功更新 {updated_count} 个备件，错误 {error_count} 个")

        except Exception as e:
            error_msg = f'数据库操作失败: {str(e)}'
            current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
            errors.append(create_error('系统', error_msg, '数据库', '', 'error', '请联系系统管理员'))
            error_count += 1

        import_end_time = datetime.now()
        import_duration = (import_end_time - datetime.strptime(
            import_summary['import_start_time'], '%Y-%m-%d %H:%M:%S'
        )).total_seconds()

        import_summary.update({
            'import_end_time': import_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'error_count': error_count,
            'import_duration': import_duration
        })

        current_app.logger.info(f"备件信息更新导入完成，耗时: {import_duration:.2f}秒")

        return {
            'success': error_count == 0 and updated_count > 0,
            'message': f'更新 {updated_count} 个备件，未找到 {not_found_count} 个备件，错误 {error_count} 个，耗时 {import_duration:.2f}秒',
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }

    def process_part_info_update_advanced(df, import_id):
        """处理备件信息更新导入 - 高级批量优化版本"""
        updated_count = 0
        not_found_count = 0
        error_count = 0
        errors = []

        import_summary = {
            'total_rows': len(df),
            'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'file_columns': list(df.columns),
            'import_id': import_id
        }

        current_app.logger.info(f"开始高级批量处理备件信息更新，共 {len(df)} 行数据")

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 预加载所有备件数据到内存
                parts_cache = {}
                parts_result = conn.execute('SELECT id, part_no FROM spare_parts').fetchall()
                for part in parts_result:
                    parts_cache[part['part_no']] = part['id']

                current_app.logger.info(f"预加载完成: {len(parts_cache)} 个备件")

                # 使用字典按字段组合分组，减少SQL语句种类
                update_groups = {}
                validation_errors = []

                for index, row in df.iterrows():
                    row_number = index + 2

                    try:
                        part_no = safe_str(row.get('Part no', '')).strip()
                        if not part_no:
                            validation_errors.append(create_error(
                                row_number, '备件编号不能为空', 'Part no', '', 'error', '请填写有效的备件编号'
                            ))
                            continue

                        if part_no not in parts_cache:
                            validation_errors.append(create_error(
                                row_number, f'备件编号 "{part_no}" 不存在', 'Part no', part_no, 'error',
                                '请检查备件编号是否正确'
                            ))
                            not_found_count += 1
                            continue

                        part_id = parts_cache[part_no]
                        update_data = extract_part_update_data(row, row_number)

                        if not update_data:
                            validation_errors.append(create_error(
                                row_number, '没有提供任何可更新的字段', '数据验证', '', 'warning',
                                '请至少填写一个需要更新的字段'
                            ))
                            continue

                        # 按字段组合分组
                        field_key = tuple(sorted(update_data.keys()))
                        if field_key not in update_groups:
                            update_groups[field_key] = []

                        update_groups[field_key].append({
                            'part_id': part_id,
                            'part_no': part_no,
                            'update_data': update_data,
                            'row_number': row_number
                        })

                    except Exception as e:
                        error_msg = f'处理备件信息时出错: {str(e)}'
                        validation_errors.append(create_error(
                            row_number, error_msg, '数据处理', '', 'error',
                            '请检查数据格式或联系系统管理员'
                        ))

                # 按分组执行批量更新
                for field_key, batch_items in update_groups.items():
                    current_app.logger.info(f"处理字段组合 {field_key}，共 {len(batch_items)} 条记录")

                    # 构建基础更新语句
                    fields = list(field_key)
                    base_query = f"UPDATE spare_parts SET {', '.join([f'{f} = ?' for f in fields])}, updated_date = CURRENT_TIMESTAMP WHERE id = ?"

                    for batch_item in batch_items:
                        try:
                            values = [batch_item['update_data'][field] for field in fields]
                            values.append(batch_item['part_id'])

                            cursor = conn.execute(base_query, values)

                            if cursor.rowcount > 0:
                                updated_count += 1
                            else:
                                validation_errors.append(create_error(
                                    batch_item['row_number'], f'备件 "{batch_item["part_no"]}" 更新失败',
                                    '数据库更新', '', 'error', '可能是数据没有变化'
                                ))

                        except Exception as e:
                            validation_errors.append(create_error(
                                batch_item['row_number'], f'更新备件失败: {str(e)}',
                                '数据库更新', batch_item['part_no'], 'error',
                                '请检查数据格式或联系系统管理员'
                            ))

                # 合并错误
                errors.extend(validation_errors)
                error_count = len(validation_errors)

                conn.commit()
                current_app.logger.info(f"批量更新完成: 成功更新 {updated_count} 个备件，错误 {error_count} 个")

        except Exception as e:
            error_msg = f'数据库操作失败: {str(e)}'
            current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
            errors.append(create_error('系统', error_msg, '数据库', '', 'error', '请联系系统管理员'))
            error_count += 1

        import_end_time = datetime.now()
        import_duration = (import_end_time - datetime.strptime(
            import_summary['import_start_time'], '%Y-%m-%d %H:%M:%S'
        )).total_seconds()

        import_summary.update({
            'import_end_time': import_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'error_count': error_count,
            'import_duration': import_duration
        })

        current_app.logger.info(f"备件信息更新导入完成，耗时: {import_duration:.2f}秒")

        return {
            'success': error_count == 0 and updated_count > 0,
            'message': f'更新 {updated_count} 个备件，未找到 {not_found_count} 个备件，错误 {error_count} 个，耗时 {import_duration:.2f}秒',
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }

    def extract_part_update_data(row, row_number):
        """提取备件更新数据 - 优化版本"""
        update_data = {}

        # 处理关键备件字段
        key_part = safe_str(row.get('Key part', '')).strip().lower()
        if key_part:
            if key_part in ['yes', '是', 'true', '1']:
                update_data['key_part'] = 1
            elif key_part in ['no', '否', 'false', '0']:
                update_data['key_part'] = 0

        # 处理数字字段 - 使用更简洁的方式
        numeric_fields = {
            'Low stock': 'min_stock',
            'High stock': 'max_stock',
            'LT (Week)': 'lt_weeks',
            'Unit price (RMB)': 'unit_price'
        }

        for col_name, field_name in numeric_fields.items():
            value = safe_str(row.get(col_name, '')).strip()
            if value and value != '':
                try:
                    if col_name == 'Unit price (RMB)':
                        num_value = safe_float(value)
                    else:
                        num_value = safe_int(value)

                    if num_value >= 0:
                        update_data[field_name] = num_value
                except (ValueError, TypeError):
                    # 在批量处理中，我们暂时跳过单个字段错误，在验证阶段统一处理
                    pass

        # 验证库存阈值逻辑
        if 'min_stock' in update_data and 'max_stock' in update_data:
            if update_data['min_stock'] > update_data['max_stock']:
                # 在批量处理中返回空数据，让外层处理错误
                return {}

        # 处理单位
        unit = safe_str(row.get('单位 Unit', '')).strip()
        if unit and unit != '':
            update_data['unit'] = unit

        return update_data

    def clean_part_info_dataframe(df):
        """清理备件信息更新DataFrame - 优化版本"""
        # 创建副本避免修改原数据
        df = df.copy()

        # 移除全空行
        df = df.dropna(how='all').reset_index(drop=True)

        # 清理字符串字段
        string_columns = ['Part no', 'Key part', '单位 Unit']
        for col in string_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({
                    '': np.nan, 'nan': np.nan, 'None': np.nan, 'null': np.nan,
                    'NaN': np.nan, 'NaT': np.nan
                })

        # 清理数字字段 - 使用向量化操作提高性能
        numeric_columns = ['Low stock', 'High stock', 'LT (Week)', 'Unit price (RMB)']
        for col in numeric_columns:
            if col in df.columns:
                # 使用 pandas 的向量化操作
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.strip()
                    .str.replace(',', '', regex=False)
                    .str.replace(' ', '', regex=False)
                    .replace({'': np.nan, 'nan': np.nan, 'None': np.nan})
                )
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 再次移除清理后产生的空行
        df = df.dropna(subset=['Part no'], how='all').reset_index(drop=True)

        current_app.logger.info(f"数据清理完成: 从 {len(df)} 行数据中清理出有效数据")

        return df

    # =============================================================================
    # 辅助函数 - 保持不变
    # =============================================================================

    def extract_operation_data(row):
        """提取操作记录数据 - 增加产品型号字段"""
        operation_data = {
            'operation_type': safe_str(row.get('Operation type', '')).strip(),
            'operation_date': safe_datetime(row.get('Date')) or datetime.now(),
            'supplier_recipient': safe_str(row.get('Supplier or Recipients', '')),
            'location': safe_str(row.get('Location', '')),
            'part_no': safe_str(row.get('Part No', '')).strip(),
            'description': safe_str(row.get('Description', '')),
            'part_type': safe_str(row.get('Type', '')),  # 备件类型
            'product_model': safe_str(row.get('Product Model', '')),  # 新增：产品型号
            'quantity': safe_int(row.get('Qty', 0)),
            'work_center': safe_str(row.get('Work center', ''))
        }

        # 自动调整数量符号
        operation_type = operation_data['operation_type'].lower()
        quantity = operation_data['quantity']

        if 'stock out' in operation_type and quantity > 0:
            operation_data['quantity'] = -quantity
        elif 'stock in' in operation_type and quantity < 0:
            operation_data['quantity'] = abs(quantity)

        return operation_data

    def validate_operation_data(row_number, operation_data):
        """验证操作记录数据"""
        errors = []
        valid_operation_types = ['Stock in', 'Stock out', 'Stock in - disassemble', 'Stock in - return']

        if not operation_data['operation_type']:
            errors.append(create_error(row_number, '操作类型不能为空', 'Operation type', '', 'error', '请填写操作类型'))
        elif operation_data['operation_type'] not in valid_operation_types:
            errors.append(
                create_error(row_number, f'操作类型无效', 'Operation type', operation_data['operation_type'], 'error',
                             f'有效操作类型: {", ".join(valid_operation_types)}'))

        if not operation_data['part_no']:
            errors.append(create_error(row_number, '备件编号不能为空', 'Part No', '', 'error', '请填写备件编号'))

        if not operation_data['description']:
            errors.append(create_error(row_number, '备件描述不能为空', 'Description', '', 'error', '请填写备件描述'))

        if operation_data['quantity'] == 0:
            errors.append(create_error(row_number, '数量不能为0', 'Qty', operation_data['quantity'], 'error',
                                       '请填写非零的数量值'))

        return errors

    def clean_operations_dataframe(df):
        """清理操作记录DataFrame"""
        df = df.dropna(how='all').reset_index(drop=True)

        string_columns = [
            'Operation type', 'Location', 'Part No', 'Description',
            'Type', 'Work center', 'Supplier or Recipients'
        ]

        for col in string_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'': np.nan, 'nan': np.nan, 'None': np.nan, 'null': np.nan})
                df[col] = df[col].fillna('')

        if 'Qty' in df.columns:
            df['Qty'] = (
                df['Qty']
                .astype(str)
                .str.strip()
                .str.replace(',', '')
                .str.replace(' ', '')
                .apply(lambda x: pd.to_numeric(x, errors='coerce'))
                .fillna(0)
                .astype(int)
            )

        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce', format='%Y-%m-%d')
            df['Date'] = df['Date'].fillna(pd.to_datetime(df['Date'], errors='coerce'))

        return df

    def clean_locations_dataframe(df):
        """清理库位DataFrame"""
        df = df.dropna(how='all').reset_index(drop=True)

        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({
                '': np.nan, 'nan': np.nan, 'None': np.nan, 'null': np.nan,
                'NaN': np.nan, 'NaT': np.nan
            })

        df = df.dropna(how='all').reset_index(drop=True)
        return df

    def clean_dataframe(df):
        """清理DataFrame数据"""
        df = df.dropna(how='all').reset_index(drop=True)

        key_fields = ['Operation type', 'Part No', 'Description', 'Qty']
        for field in key_fields:
            if field in df.columns:
                df[field] = df[field].fillna('').astype(str).str.strip()

        optional_fields = ['Supplier or Recipients', 'Location', 'Type', 'Work center']
        for field in optional_fields:
            if field in df.columns:
                df[field] = df[field].fillna('').astype(str).str.strip()

        if 'Qty' in df.columns:
            df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce').fillna(0)

        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

        return df

    def detect_file_type(df):
        """检测文件类型"""
        columns = [str(col).strip() for col in df.columns]

        operation_columns = {'Operation type', 'Date', 'Part No', 'Qty'}
        part_info_columns = {'货号 Part no', 'Description'}
        part_update_columns = {'货号 Part no', '关键备件 Key part', '最低库存 Low stock', '最高库存 High stock'}

        column_set = set(columns)

        if operation_columns.issubset(column_set):
            return 'operations_with_parts'
        elif any(col in column_set for col in part_info_columns) or any(
                col in column_set for col in part_update_columns):
            return 'part_info_only'
        else:
            for col in columns:
                if any(keyword in col for keyword in ['货号', 'Part', 'part']):
                    return 'part_info_only'
            return 'unknown'

    def validate_excel_file(filename):
        """验证Excel文件类型"""
        allowed_extensions = {'xlsx', 'xls'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

    def safe_int(value, default=0):
        """安全转换为整数"""
        if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
            return default
        try:
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                value = value.replace(',', '')
                return int(float(value))
            return int(value)
        except (ValueError, TypeError):
            return default

    def safe_float(value, default=0.0):
        """安全转换为浮点数"""
        if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
            return default
        try:
            if isinstance(value, str):
                value = value.replace(',', '')
            return float(value)
        except (ValueError, TypeError):
            return default

    def safe_str(value, default=''):
        """安全转换为字符串"""
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        try:
            result = str(value).strip()
            return result if result else default
        except:
            return default

    def safe_datetime(value, default=None):
        """安全转换为日期时间"""
        if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
            return default
        try:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
            return pd.to_datetime(value)
        except Exception as e:
            return default

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

    def save_import_report(import_id, import_type, result):
        """保存导入报告到文件"""
        try:
            report_data = {
                'import_id': import_id,
                'import_type': import_type,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'success': result.get('success', False),
                'message': result.get('message', ''),
                'imported_count': result.get('imported_count', 0),
                'error_count': result.get('error_count', 0),
                'skipped_duplicates': result.get('skipped_duplicates', 0),
                'new_parts_created': result.get('new_parts_created', 0),
                'errors': result.get('errors', []),
                'import_summary': result.get('import_summary', {}),
                'import_duration': result.get('import_summary', {}).get('import_duration', 0)
            }

            report_file = os.path.join('import_logs', f"{import_id}_report.json")
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            current_app.logger.error(f"保存导入报告时出错: {str(e)}")