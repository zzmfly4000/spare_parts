from flask import render_template, request, redirect, url_for, flash, send_file, session, jsonify, current_app
import pandas as pd
from io import BytesIO
from datetime import datetime
import traceback
import logging
import numpy as np
import os
import json
from models.database import DatabaseManager, create_spare_part, create_operation_record, recalculate_all_stock, \
    create_location, update_location, get_location_by_code
from utils.helpers import safe_int, safe_str, safe_float, validate_excel_file, safe_datetime
from utils.sync_utils import sync_all_operations


def setup_import_export_routes(app):
    """设置数据导入导出路由"""
    # 创建导入日志目录
    log_dir = 'import_logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 配置导入日志
    import_logger = logging.getLogger('import_export')
    import_logger.setLevel(logging.INFO)

    # =============================================================================
    # 1. 库位导入功能 - 增强版本
    # =============================================================================

    @app.route('/import_locations', methods=['GET', 'POST'])
    def import_locations():
        """库位信息导入页面 - 增强错误处理版本"""
        if request.method == 'POST':
            try:
                # 验证文件存在性
                if 'file' not in request.files:
                    flash('请选择要导入的文件', 'danger')
                    return redirect(request.url)

                file = request.files['file']
                if file.filename == '':
                    flash('请选择有效的Excel文件', 'danger')
                    return redirect(request.url)

                # 验证文件类型
                if not validate_excel_file(file.filename):
                    flash('请上传有效的Excel文件 (.xlsx 或 .xls)', 'danger')
                    return redirect(request.url)

                # 验证文件大小 (最大10MB)
                file.seek(0, 2)  # 移动到文件末尾
                file_size = file.tell()
                file.seek(0)  # 重置文件指针

                if file_size > 10 * 1024 * 1024:  # 10MB
                    flash('文件大小不能超过10MB', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                import_id = f"locations_{import_start_time.strftime('%Y%m%d_%H%M%S')}"

                current_app.logger.info(
                    f"开始导入库位信息，文件: {file.filename}, 大小: {file_size}字节, 导入ID: {import_id}")

                try:
                    # 读取Excel文件
                    df = pd.read_excel(file)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据，列名: {list(df.columns)}")

                    # 清理数据
                    df = clean_dataframe(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                # 验证必需列 - 根据实际列名调整
                required_columns = ['location']  # 只验证 location 列
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    flash(f'Excel文件中缺少必需列: {", ".join(missing_columns)}', 'danger')
                    return redirect(request.url)

                # 根据数据量选择处理方式 - 将这部分移到 df 定义之后
                if len(df) > 5000:  # 大数据量使用分块处理
                    current_app.logger.info("数据量较大，使用分块处理")
                    # 注意：需要先实现 process_locations_import_large 函数
                    result = process_locations_import(df, import_id)  # 暂时使用标准处理
                elif len(df) > 1000:  # 中等数据量使用批量处理
                    current_app.logger.info("数据量中等，使用批量处理")
                    result = process_locations_import(df, import_id)
                else:  # 小数据量使用标准处理
                    current_app.logger.info("数据量较小，使用标准处理")
                    result = process_locations_import(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"库位信息导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                # 保存导入报告
                save_import_report(import_id, 'locations', result)

                # 处理导入结果
                if result['success']:
                    if result['error_count'] > 0:
                        flash(f'{result["message"]}，但有 {result["error_count"]} 个错误需要处理', 'warning')
                    else:
                        flash(result['message'], 'success')

                    # 保存结果到session用于显示
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

        # GET 请求处理 - 显示导入结果
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
        """下载库位导入模板 - 更新字段描述"""
        try:
            # 创建模板数据
            template_data = {
                'Rack': ['A', 'B', 'C', 'D', ''],  # 机架（可为空）
                'location': ['A-01-01', 'B-02-01', 'C-03-01', 'D-04-01', ''],  # 实际库位（关键字段，不可为空）
                'Level': ['1', '2', '3', '1', ''],  # 层（可为空）
                'Position': ['01', '02', '03', '04', ''],  # 层上的位置（可为空）
                'Side': ['Left', 'Right', 'Left', 'Right', ''],  # 库位所在边（可为空）
                'State': ['free', 'in_use', 'free', 'low_stock', ''],  # 库存状态（可为空，默认free）
                'Capacity': [100, 200, 150, 300, ''],  # 库位容量（可为空，默认0）
                'Size Type': ['Small', 'Medium', 'Large', 'Extra Large', ''],  # 库位空间大小（可为空）
                'Description': ['小型零件库位', '中型设备库位', '大型备件库位', '超大型设备库位', '']  # 库位描述（可为空）
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 主模板工作表
                df.to_excel(writer, sheet_name='库位导入模板', index=False)

                # 获取工作表对象用于设置列宽
                worksheet = writer.sheets['库位导入模板']
                column_widths = {
                    'A': 15, 'B': 20, 'C': 15, 'D': 20,
                    'E': 15, 'F': 15, 'G': 15, 'H': 20, 'I': 30
                }
                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                # 导入说明工作表
                instructions_data = {
                    '列名': [
                        'Rack',
                        'location',
                        'Level',
                        'Position',
                        'Side',
                        'State',
                        'Capacity',
                        'Size Type',
                        'Description'
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
                        'A',
                        'A-01-01',
                        '1',
                        '01',
                        'Left',
                        'free',
                        '100',
                        'Small',
                        '小型零件库位'
                    ],
                    '必填': [
                        '否',
                        '是',
                        '否',
                        '否',
                        '否',
                        '否',
                        '否',
                        '否',
                        '否'
                    ]
                }

                instructions_df = pd.DataFrame(instructions_data)
                instructions_df.to_excel(writer, sheet_name='字段说明', index=False)

            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='库位导入模板_字段修正版.xlsx'
            )

        except Exception as e:
            current_app.logger.error(f'下载库位导入模板时出错: {str(e)}\n{traceback.format_exc()}')
            flash(f'下载模板失败: {str(e)}', 'danger')
            return redirect(url_for('import_locations'))

    # =============================================================================
    # 2. 备件信息更新导入功能 - 增强版本
    # =============================================================================

    @app.route('/import_part_info_only', methods=['GET', 'POST'])
    def import_part_info_only():
        """备件信息更新导入页面 - 增强错误处理版本"""
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

                # 验证文件大小
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
                    df = pd.read_excel(file)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据，列名: {list(df.columns)}")

                    df = clean_dataframe(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                # 验证必需列
                if 'Part no' not in df.columns:
                    flash('Excel文件中缺少必需列"Part no"', 'danger')
                    return redirect(request.url)

                # 处理备件信息更新导入
                result = process_part_info_update(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"备件信息更新导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                # 保存导入报告
                save_import_report(import_id, 'parts', result)

                # 处理导入结果
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

        # GET 请求处理
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
        """下载备件信息更新模板 - 增强版本"""
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
                # 主模板
                df.to_excel(writer, sheet_name='备件信息更新模板', index=False)

                worksheet = writer.sheets['备件信息更新模板']
                column_widths = {'A': 15, 'B': 12, 'C': 12, 'D': 12, 'E': 12, 'F': 15, 'G': 12}
                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                # 导入说明
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
                    '数据格式': ['文本', '文本(Yes/No)', '数字≥0', '数字≥最低库存', '数字≥0', '数字≥0', '文本'],
                    '注意事项': [
                        '必须已在系统中存在',
                        '不区分大小写',
                        '为空则保持原值',
                        '为空则保持原值',
                        '为空则保持原值',
                        '为空则保持原值',
                        '为空则保持原值'
                    ]
                }

                instructions_df = pd.DataFrame(instructions_data)
                instructions_df.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='备件信息更新模板_详细版.xlsx'
            )

        except Exception as e:
            current_app.logger.error(f'下载备件信息更新模板时出错: {str(e)}')
            flash(f'下载模板失败: {str(e)}', 'danger')
            return redirect(url_for('import_part_info_only'))

    # =============================================================================
    # 3. 操作记录导入功能 - 增强版本
    # =============================================================================

    @app.route('/import_operations', methods=['GET', 'POST'])
    def import_operations():
        """操作记录导入页面 - 增强错误处理版本"""
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

                # 验证文件大小
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
                    df = pd.read_excel(file)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据，列名: {list(df.columns)}")

                    df = clean_dataframe(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                # 验证必需列
                required_columns = ['Operation type', 'Date', 'Part No', 'Description', 'Qty']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    flash(f'Excel文件中缺少必需列: {", ".join(missing_columns)}', 'danger')
                    return redirect(request.url)

                # 处理操作记录导入
                result = process_operations_import(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"操作记录导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                # 保存导入报告
                save_import_report(import_id, 'operations', result)

                # 处理导入结果
                if result['success']:
                    if result['error_count'] > 0 or result['skipped_duplicates'] > 0:
                        flash(f'{result["message"]}，请查看详细错误信息', 'warning')
                    else:
                        flash(result['message'], 'success')

                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'imported_count': result.get('imported_count', 0),
                        'skipped_duplicates': result.get('skipped_duplicates', 0),
                        'import_summary': result.get('import_summary', {}),
                        'import_id': import_id
                    }
                else:
                    flash(result['message'], 'danger')
                    session['import_results'] = {
                        'import_errors': result.get('errors', []),
                        'error_count': result.get('error_count', 0),
                        'imported_count': result.get('imported_count', 0),
                        'skipped_duplicates': result.get('skipped_duplicates', 0),
                        'import_summary': result.get('import_summary', {}),
                        'import_id': import_id
                    }

                return redirect(url_for('import_operations'))

            except Exception as e:
                error_msg = f'导入过程中发生系统错误: {str(e)}'
                current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                flash(f'{error_msg}，请检查文件格式或联系系统管理员', 'danger')
                return redirect(request.url)

        # GET 请求处理
        import_results = session.pop('import_results', {}) if 'import_results' in session else {}

        return render_template('import_operations.html',
                               import_errors=import_results.get('import_errors', []),
                               error_count=import_results.get('error_count', 0),
                               imported_count=import_results.get('imported_count', 0),
                               skipped_duplicates=import_results.get('skipped_duplicates', 0),
                               import_summary=import_results.get('import_summary', {}),
                               import_id=import_results.get('import_id', ''))

    @app.route('/download_operations_template')
    def download_operations_template():
        """下载操作记录导入模板 - 增强版本"""
        try:
            template_data = {
                'Operation type': ['Stock in', 'Stock out', 'Stock in - disassemble', 'Stock in - return', ''],
                'Date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', ''],
                'Supplier or Recipients': ['供应商A', '部门B', '供应商C', '部门D', ''],
                'Location': ['A-01-01', 'B-02-01', 'C-03-01', 'D-04-01', ''],
                'Part No': ['PART-001', 'PART-002', 'PART-003', 'PART-004', ''],
                'Description': ['轴承 6205', '螺丝 M6x20', '密封圈 25mm', '电缆 3x1.5mm', ''],
                'Type': ['机械', '电子', '机械', '电气', ''],
                'Qty': [10, -5, 8, -3, ''],
                'Work center': ['生产线A', '维修部', '生产线B', '工程部', '']
            }

            df = pd.DataFrame(template_data)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 主模板
                df.to_excel(writer, sheet_name='操作记录模板', index=False)

                worksheet = writer.sheets['操作记录模板']
                column_widths = {
                    'A': 20, 'B': 15, 'C': 20, 'D': 15,
                    'E': 15, 'F': 25, 'G': 12, 'H': 10, 'I': 15
                }
                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                # 导入说明
                instructions_data = {
                    '列名': [
                        'Operation type', 'Date', 'Supplier or Recipients', 'Location',
                        'Part No', 'Description', 'Type', 'Qty', 'Work center'
                    ],
                    '说明': [
                        '操作类型: Stock in/Stock out/Stock in - disassemble/Stock in - return',
                        '操作日期 (YYYY-MM-DD格式)',
                        '供应商(入库)或接收部门(出库)',
                        '库位代码（必须存在于系统中）',
                        '备件编号（必须存在于系统中）',
                        '备件详细描述',
                        '备件类型',
                        '数量: 正数入库, 负数出库',
                        '相关工作中心'
                    ],
                    '示例': [
                        'Stock in', '2024-01-01', '供应商A', 'A-01-01',
                        'PART-001', '轴承 6205', '机械', '10', '生产线A'
                    ],
                    '必填': ['是', '是', '否', '是', '是', '是', '否', '是', '否'],
                    '数据格式': [
                        '文本(特定值)', '日期', '文本', '文本',
                        '文本', '文本', '文本', '数字(非零)', '文本'
                    ]
                }

                instructions_df = pd.DataFrame(instructions_data)
                instructions_df.to_excel(writer, sheet_name='导入说明', index=False)

            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='操作记录导入模板_详细版.xlsx'
            )

        except Exception as e:
            current_app.logger.error(f'下载操作记录模板时出错: {str(e)}')
            flash(f'下载模板失败: {str(e)}', 'danger')
            return redirect(url_for('import_operations'))

    # =============================================================================
    # 导入报告下载功能
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

            # 创建详细的错误报告Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 错误详情表
                if report_data.get('errors'):
                    errors_df = pd.DataFrame(report_data['errors'])
                    errors_df.to_excel(writer, sheet_name='错误详情', index=False)

                    # 设置错误详情表的列宽
                    errors_worksheet = writer.sheets['错误详情']
                    errors_widths = {'A': 8, 'B': 15, 'C': 20, 'D': 25, 'E': 12, 'F': 30}
                    for col, width in errors_widths.items():
                        errors_worksheet.column_dimensions[col].width = width

                # 导入汇总表
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

                # 设置汇总表的列宽
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
    # 兼容性路由
    # =============================================================================

    @app.route('/import_parts')
    def import_parts():
        """备件导入页面 - 兼容性重定向"""
        return redirect(url_for('import_part_info_only'))

    @app.route('/import_operations_advanced')
    def import_operations_advanced():
        """高级操作记录导入 - 兼容性重定向"""
        return redirect(url_for('import_operations'))

    @app.route('/export_data')
    def export_data():
        """数据导出功能 - 基础版本"""
        try:
            with DatabaseManager().get_connection() as conn:
                parts = conn.execute('SELECT * FROM spare_parts ORDER BY part_no').fetchall()

                data = {
                    'part_no': [part[1] for part in parts],
                    'name': [part[2] for part in parts],
                    'current_stock': [part[4] for part in parts],
                    'min_stock': [part[5] for part in parts],
                    'max_stock': [part[6] for part in parts],
                    'location': [part[11] for part in parts]
                }
                df = pd.DataFrame(data)

                # 保存到临时文件并返回
                filename = f'spare_parts_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
                df.to_excel(filename, index=False)

                return send_file(filename, as_attachment=True)
        except Exception as e:
            flash(f'导出失败: {str(e)}', 'error')
            return redirect(url_for('parts_list'))

    # =============================================================================
    # 高级导出功能
    # =============================================================================

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
# 增强的辅助函数
# =============================================================================

def process_locations_import(df, import_id):
    """处理库位信息导入 - 彻底修复版本"""
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

    current_app.logger.info(f"开始处理库位导入，共 {len(df)} 行数据")
    current_app.logger.info(f"DataFrame 列名: {list(df.columns)}")

    # 数据质量统计 - 使用正确的列名 'location'
    total_rows = len(df)
    if 'location' in df.columns:
        empty_locations = df['location'].isna().sum()
        current_app.logger.info(f"数据质量统计 - 总行数: {total_rows}, 空库位: {empty_locations}")
    else:
        current_app.logger.error(f"DataFrame 中缺少 'location' 列！")
        errors.append(create_error(
            '系统', "Excel文件中缺少 'location' 列", 'location', '',
            'error', '请确保Excel文件包含 location 列'
        ))
        error_count += 1
        return {
            'success': False,
            'message': "Excel文件中缺少 'location' 列",
            'created_count': 0,
            'updated_count': 0,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }

    try:
        with DatabaseManager().get_connection() as conn:
            # 加载现有库位
            current_app.logger.info("正在加载现有库位数据...")
            existing_locations = {}
            cursor = conn.execute(
                'SELECT location_code, rack, level, position, side, status, capacity, size_type, description FROM locations')
            for row in cursor.fetchall():
                existing_locations[row[0]] = {
                    'rack': row[1],
                    'level': row[2],
                    'position': row[3],
                    'side': row[4],
                    'status': row[5],
                    'capacity': row[6],
                    'size_type': row[7],
                    'description': row[8]
                }
            current_app.logger.info(f"已加载 {len(existing_locations)} 个现有库位")

            # 处理数据
            locations_to_create = []
            locations_to_update = []
            processed_locations = set()

            current_app.logger.info("开始处理导入数据...")

            for index, row in df.iterrows():
                row_number = index + 2

                # 跳过全空行
                if row.isna().all():
                    continue

                try:
                    # 提取库位数据
                    location_data = extract_location_data(row)

                    # 验证数据
                    validation_errors = validate_location_data(row_number, location_data)
                    if validation_errors:
                        errors.extend(validation_errors)
                        error_count += len(validation_errors)
                        continue

                    location_code = location_data['location_code']

                    # 检查重复处理
                    if location_code in processed_locations:
                        errors.append(create_error(
                            row_number, '库位在本次导入中重复', 'location', location_code,
                            'warning', '跳过重复的库位'
                        ))
                        error_count += 1
                        continue

                    processed_locations.add(location_code)

                    # 检查库位是否已存在
                    if location_code in existing_locations:
                        # 更新现有库位
                        locations_to_update.append((
                            location_data['rack'],
                            location_data['level'],
                            location_data['position'],
                            location_data['side'],
                            location_data['status'],
                            location_data['capacity'],
                            location_data['size_type'],
                            location_data['description'],
                            location_code
                        ))
                    else:
                        # 创建新库位
                        locations_to_create.append((
                            location_code,
                            location_data['rack'],
                            location_data['level'],
                            location_data['position'],
                            location_data['side'],
                            location_data['status'],
                            location_data['capacity'],
                            location_data['size_type'],
                            location_data['description'],
                            0  # part_count
                        ))

                except Exception as e:
                    error_msg = f'处理库位数据时发生错误: {str(e)}'
                    errors.append(create_error(
                        row_number, error_msg, '数据处理', '行数据解析失败',
                        'error', '请检查数据格式或联系管理员'
                    ))
                    error_count += 1

            # 执行数据库操作
            current_app.logger.info(f"准备创建 {len(locations_to_create)} 个新库位，更新 {len(locations_to_update)} 个现有库位")

            # 批量创建新库位
            if locations_to_create:
                try:
                    cursor = conn.executemany('''
                        INSERT INTO locations 
                        (location_code, rack, level, position, side, status, capacity, size_type, description, part_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', locations_to_create)
                    created_count = cursor.rowcount if cursor.rowcount != -1 else len(locations_to_create)
                    current_app.logger.info(f"批量创建 {created_count} 个新库位完成")
                except Exception as e:
                    current_app.logger.error(f"批量创建库位失败: {str(e)}")
                    created_count = create_locations_individually(conn, locations_to_create, errors)

            # 批量更新现有库位
            if locations_to_update:
                try:
                    cursor = conn.executemany('''
                        UPDATE locations 
                        SET rack = ?, level = ?, position = ?, side = ?, status = ?, 
                            capacity = ?, size_type = ?, description = ?, last_updated = CURRENT_TIMESTAMP
                        WHERE location_code = ?
                    ''', locations_to_update)
                    updated_count = cursor.rowcount if cursor.rowcount != -1 else len(locations_to_update)
                    current_app.logger.info(f"批量更新 {updated_count} 个库位完成")
                except Exception as e:
                    current_app.logger.error(f"批量更新库位失败: {str(e)}")
                    updated_count = update_locations_individually(conn, locations_to_update, errors)

            conn.commit()

    except Exception as e:
        error_msg = f'数据库操作失败: {str(e)}'
        current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
        errors.append(create_error(
            '系统', error_msg, '数据库', '', 'error', '请联系系统管理员'
        ))
        error_count += 1

    # 生成结果
    import_end_time = datetime.now()
    import_duration = (import_end_time - datetime.strptime(
        import_summary['import_start_time'], '%Y-%m-%d %H:%M:%S'
    )).total_seconds()

    import_summary.update({
        'import_end_time': import_end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'created_count': created_count,
        'updated_count': updated_count,
        'error_count': error_count,
        'import_duration': import_duration
    })

    if error_count == 0:
        message = f'导入成功！创建 {created_count} 个库位，更新 {updated_count} 个库位'
        success = True
    elif created_count > 0 or updated_count > 0:
        message = f'部分导入成功！创建 {created_count} 个库位，更新 {updated_count} 个库位，发现 {error_count} 个错误'
        success = True
    else:
        message = f'导入失败！共发现 {error_count} 个错误'
        success = False

    current_app.logger.info(f"库位导入完成: {message}")

    return {
        'success': success,
        'message': message,
        'created_count': created_count,
        'updated_count': updated_count,
        'error_count': error_count,
        'errors': errors,
        'import_summary': import_summary
    }

def create_locations_individually(conn, locations_to_create, errors):
    """逐行创建库位（批量创建失败时的备用方案）"""
    created_count = 0
    for location_data in locations_to_create:
        try:
            cursor = conn.execute('''
                INSERT INTO locations 
                (location_code, description, status, part_count, capacity)
                VALUES (?, ?, ?, ?, ?)
            ''', location_data)
            created_count += 1
        except Exception as e:
            errors.append(create_error(
                '批量', f'创建库位失败: {str(e)}', 'Location', location_data[0],
                'error', '库位代码可能已存在'
            ))
    return created_count

def update_locations_individually(conn, locations_to_update, errors):
    """逐行更新库位（批量更新失败时的备用方案）"""
    updated_count = 0
    for location_data in locations_to_update:
        try:
            cursor = conn.execute('''
                UPDATE locations 
                SET description = ?, status = ?, capacity = ?, last_updated = CURRENT_TIMESTAMP
                WHERE location_code = ?
            ''', location_data)
            if cursor.rowcount > 0:
                updated_count += 1
        except Exception as e:
            errors.append(create_error(
                '批量', f'更新库位失败: {str(e)}', 'Location', location_data[3],
                'error', '请检查数据格式'
            ))
    return updated_count

def extract_location_data(row):
    """从行数据中提取库位信息 - 根据新的字段描述修正"""
    location_data = {
        'location_code': safe_str(row.get('location', '')).strip(),  # 实际库位（关键字段，不可为空）
        'rack': safe_str(row.get('Rack', '')).strip(),              # 机架（可为空）
        'level': safe_str(row.get('Level', '')).strip(),            # 层（可为空）
        'position': safe_str(row.get('Position', '')).strip(),      # 层上的位置（可为空）
        'side': safe_str(row.get('Side', '')).strip(),              # 库位所在边（可为空）
        'status': safe_str(row.get('State', 'free')).strip().lower(),  # 库存状态（可为空，默认free）
        'capacity': safe_int(row.get('Capacity', 0)),               # 库位容量（可为空，默认0）
        'size_type': safe_str(row.get('Size Type', '')).strip(),    # 库位空间大小（可为空）
        'description': safe_str(row.get('Description', '')).strip(),  # 库位描述（可为空）
        'part_count': 0
    }

    # 处理空状态值
    if not location_data['status']:
        location_data['status'] = 'free'

    return location_data

def validate_location_data(row_number, location_data):
    """验证库位数据 - 只验证关键字段"""
    errors = []

    # 只验证关键字段：location（实际库位）
    if not location_data['location_code']:
        errors.append(create_error(
            row_number, '实际库位不能为空', 'location', '', 'error', '请填写实际库位'
        ))

    # 验证容量 - 只检查是否为负数
    if location_data['capacity'] < 0:
        errors.append(create_error(
            row_number, '容量不能为负数', 'Capacity', location_data['capacity'],
            'error', '容量必须 ≥ 0'
        ))

    return errors

def is_valid_location_code(location_code):
    """验证库位代码格式 - 大幅放宽规则"""
    if not location_code or not isinstance(location_code, str):
        return False

    # 大幅放宽验证规则，允许各种常见格式：
    # - 纯数字: "09", "37"
    # - 字母数字组合: "A1-01-01", "5号柜"
    # - 中文: "工具柜", "直接领用"
    # - 混合格式: "A1-01-01", "B2-02-02"

    import re

    # 允许任何非空字符串，只要长度合理
    if location_code.strip() and len(location_code) <= 100:
        return True

    return False


def process_part_info_update(df, import_id):
    """处理备件信息更新导入 - 增强错误处理和报告"""
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

    current_app.logger.info(f"开始处理备件信息更新导入，共 {len(df)} 行数据")

    try:
        with DatabaseManager().get_connection() as conn:
            for index, row in df.iterrows():
                row_number = index + 2

                try:
                    # 提取备件编号
                    part_no = safe_str(row.get('Part no', '')).strip()
                    if not part_no:
                        errors.append(create_error(
                            row_number, '备件编号不能为空', 'Part no', '', 'error', '请填写备件编号'
                        ))
                        error_count += 1
                        continue

                    # 检查备件是否存在
                    part = conn.execute(
                        'SELECT id, name FROM spare_parts WHERE part_no = ?',
                        (part_no,)
                    ).fetchone()

                    if not part:
                        errors.append(create_error(
                            row_number, f'备件不存在: {part_no}', 'Part no', part_no,
                            'warning', '请先在系统中添加该备件'
                        ))
                        not_found_count += 1
                        continue

                    # 提取更新信息
                    update_data = extract_part_update_data(row)

                    # 验证更新数据
                    validation_errors = validate_part_update_data(row_number, update_data)
                    if validation_errors:
                        errors.extend(validation_errors)
                        error_count += len(validation_errors)
                        continue

                    # 更新备件信息
                    success, message = update_part_info(conn, part['id'], update_data)
                    if success:
                        updated_count += 1
                        current_app.logger.info(f"成功更新备件: {part_no} - {part['name']}")
                    else:
                        errors.append(create_error(
                            row_number, f'更新失败: {message}', '备件更新', part_no,
                            'error', '请检查数据格式或联系管理员'
                        ))
                        error_count += 1

                except Exception as e:
                    error_msg = f'处理备件信息时出错: {str(e)}'
                    errors.append(create_error(
                        row_number, error_msg, '数据处理', str(row.to_dict()),
                        'error', '请检查数据格式或联系管理员'
                    ))
                    error_count += 1
                    current_app.logger.error(f"处理第 {row_number} 行时出错: {str(e)}")

            conn.commit()

    except Exception as e:
        error_msg = f'数据库操作失败: {str(e)}'
        current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
        errors.append(create_error(
            '系统', error_msg, '数据库', '', 'error', '请联系系统管理员'
        ))
        error_count += 1

    # 生成导入报告
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

    # 生成结果消息
    if error_count == 0 and not_found_count == 0:
        message = f'导入成功！更新 {updated_count} 个备件的信息'
        success = True
    elif updated_count > 0:
        message = f'部分导入成功！更新 {updated_count} 个备件，未找到 {not_found_count} 个备件，错误 {error_count} 个'
        success = True
    else:
        message = f'导入失败！未找到 {not_found_count} 个备件，错误 {error_count} 个'
        success = False

    current_app.logger.info(f"备件信息更新导入完成: {message}")

    return {
        'success': success,
        'message': message,
        'updated_count': updated_count,
        'not_found_count': not_found_count,
        'error_count': error_count,
        'errors': errors,
        'import_summary': import_summary
    }


def extract_part_update_data(row):
    """从行数据中提取备件更新信息 - 增强版本"""
    update_data = {}

    # 关键备件
    key_part = row.get('Key part')
    if key_part is not None:
        if isinstance(key_part, str):
            key_part = key_part.strip().lower() in ['yes', 'true', '1', 'y', '是', '真']
        update_data['key_part'] = bool(key_part)

    # 最低库存
    low_stock = row.get('Low stock')
    if low_stock is not None and str(low_stock).strip() != '':
        update_data['min_stock'] = max(0, safe_int(low_stock))

    # 最高库存
    high_stock = row.get('High stock')
    if high_stock is not None and str(high_stock).strip() != '':
        update_data['max_stock'] = max(0, safe_int(high_stock))

    # 交货期
    lt_weeks = row.get('LT (Week)')
    if lt_weeks is not None and str(lt_weeks).strip() != '':
        update_data['lt_weeks'] = max(0, safe_int(lt_weeks))

    # 单价
    unit_price = row.get('Unit price (RMB)')
    if unit_price is not None and str(unit_price).strip() != '':
        update_data['unit_price'] = max(0, safe_float(unit_price))

    # 单位
    unit = safe_str(row.get('单位 Unit') or row.get('Unit', ''))
    if unit and unit.strip():
        update_data['unit'] = unit.strip()

    return update_data


def validate_part_update_data(row_number, update_data):
    """验证备件更新数据"""
    errors = []

    # 验证库存范围
    if 'min_stock' in update_data and 'max_stock' in update_data:
        if update_data['min_stock'] > update_data['max_stock']:
            errors.append(create_error(
                row_number, '最低库存不能大于最高库存', '库存设置',
                f"min: {update_data['min_stock']}, max: {update_data['max_stock']}",
                'error', '请确保最低库存 ≤ 最高库存'
            ))

    # 验证单价
    if 'unit_price' in update_data and update_data['unit_price'] < 0:
        errors.append(create_error(
            row_number, '单价不能为负数', 'Unit price', update_data['unit_price'],
            'error', '单价必须 ≥ 0'
        ))

    return errors


def update_part_info(conn, part_id, update_data):
    """更新备件信息 - 增强版本"""
    try:
        if not update_data:
            return False, "没有需要更新的字段"

        update_fields = []
        params = []

        for key, value in update_data.items():
            update_fields.append(f"{key} = ?")
            params.append(value)

        update_fields.append('updated_date = CURRENT_TIMESTAMP')
        params.append(part_id)

        query = f"UPDATE spare_parts SET {', '.join(update_fields)} WHERE id = ?"
        cursor = conn.execute(query, params)

        if cursor.rowcount == 0:
            return False, "备件不存在或没有数据被更新"

        return True, f"成功更新 {len(update_data)} 个字段"

    except Exception as e:
        error_msg = f"更新备件信息时出错: {str(e)}"
        current_app.logger.error(f"{error_msg}\n{traceback.format_exc()}")
        return False, error_msg


def process_operations_import(df, import_id):
    """处理操作记录导入 - 增强错误处理和报告"""
    imported_count = 0
    error_count = 0
    skipped_duplicates = 0
    errors = []

    import_summary = {
        'total_rows': len(df),
        'import_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'file_columns': list(df.columns),
        'import_id': import_id
    }

    current_app.logger.info(f"开始处理操作记录导入，共 {len(df)} 行数据")

    try:
        with DatabaseManager().get_connection() as conn:
            for index, row in df.iterrows():
                row_number = index + 2

                try:
                    # 提取操作记录数据
                    operation_data = extract_operation_data(row)

                    # 验证数据
                    validation_errors = validate_operation_data(row_number, operation_data)
                    if validation_errors:
                        errors.extend(validation_errors)
                        error_count += len(validation_errors)
                        continue

                    # 检查备件是否存在
                    part = conn.execute(
                        'SELECT id FROM spare_parts WHERE part_no = ?',
                        (operation_data['part_no'],)
                    ).fetchone()

                    if not part:
                        errors.append(create_error(
                            row_number, f'备件不存在: {operation_data["part_no"]}', 'Part No',
                            operation_data['part_no'], 'error', '请先在系统中添加该备件'
                        ))
                        error_count += 1
                        continue

                    # 检查库位是否存在
                    if operation_data['location']:
                        location = get_location_by_code(operation_data['location'])
                        if not location:
                            errors.append(create_error(
                                row_number, f'库位不存在: {operation_data["location"]}', 'Location',
                                operation_data['location'], 'warning', '操作将继续，但库位信息不会关联'
                            ))

                    # 检查重复记录
                    is_duplicate, duplicate_info = check_duplicate_operation(conn, operation_data)
                    if is_duplicate:
                        errors.append(create_error(
                            row_number, '跳过重复记录', '重复检查',
                            f"{operation_data['operation_type']} - {operation_data['part_no']}",
                            'warning', duplicate_info
                        ))
                        skipped_duplicates += 1
                        continue

                    # 创建操作记录
                    try:
                        create_operation_record(operation_data)
                        imported_count += 1
                        current_app.logger.info(
                            f"导入操作记录: {operation_data['operation_type']} - {operation_data['part_no']} - 数量: {operation_data['quantity']}"
                        )
                    except Exception as e:
                        error_msg = f'创建操作记录失败: {str(e)}'
                        errors.append(create_error(
                            row_number, error_msg, '记录创建', str(operation_data),
                            'error', '请检查数据格式或联系管理员'
                        ))
                        error_count += 1

                except Exception as e:
                    error_msg = f'处理操作记录时出错: {str(e)}'
                    errors.append(create_error(
                        row_number, error_msg, '数据处理', str(row.to_dict()),
                        'error', '请检查数据格式或联系管理员'
                    ))
                    error_count += 1
                    current_app.logger.error(f"处理第 {row_number} 行时出错: {str(e)}")

            conn.commit()

            # 同步库存
            if imported_count > 0:
                current_app.logger.info("开始同步操作记录到库存...")
                sync_result = sync_all_operations()
                import_summary['sync_result'] = sync_result

    except Exception as e:
        error_msg = f'数据库操作失败: {str(e)}'
        current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
        errors.append(create_error(
            '系统', error_msg, '数据库', '', 'error', '请联系系统管理员'
        ))
        error_count += 1

    # 生成导入报告
    import_end_time = datetime.now()
    import_duration = (import_end_time - datetime.strptime(
        import_summary['import_start_time'], '%Y-%m-%d %H:%M:%S'
    )).total_seconds()

    import_summary.update({
        'import_end_time': import_end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'imported_count': imported_count,
        'error_count': error_count,
        'skipped_duplicates': skipped_duplicates,
        'import_duration': import_duration
    })

    # 生成结果消息
    if error_count == 0 and skipped_duplicates == 0:
        message = f'导入成功！导入 {imported_count} 条操作记录'
        success = True
    elif imported_count > 0:
        message = f'部分导入成功！导入 {imported_count} 条记录，跳过 {skipped_duplicates} 条重复记录，错误 {error_count} 个'
        success = True
    else:
        message = f'导入失败！跳过 {skipped_duplicates} 条重复记录，错误 {error_count} 个'
        success = False

    current_app.logger.info(f"操作记录导入完成: {message}")

    return {
        'success': success,
        'message': message,
        'imported_count': imported_count,
        'error_count': error_count,
        'skipped_duplicates': skipped_duplicates,
        'errors': errors,
        'import_summary': import_summary
    }


def extract_operation_data(row):
    """从行数据中提取操作记录信息 - 增强版本"""
    operation_data = {
        'operation_type': safe_str(row.get('Operation type', '')).strip(),
        'operation_date': safe_datetime(row.get('Date')) or datetime.now(),
        'supplier_recipient': safe_str(row.get('Supplier or Recipients', '')),
        'location': safe_str(row.get('Location', '')),
        'part_no': safe_str(row.get('Part No', '')).strip(),
        'description': safe_str(row.get('Description', '')),
        'part_type': safe_str(row.get('Type', '')),
        'quantity': safe_int(row.get('Qty', 0)),
        'work_center': safe_str(row.get('Work center', ''))
    }
    return operation_data


def validate_operation_data(row_number, operation_data):
    """验证操作记录数据 - 增强版本"""
    errors = []

    # 验证操作类型
    valid_operation_types = ['Stock in', 'Stock out', 'Stock in - disassemble', 'Stock in - return']
    if not operation_data['operation_type']:
        errors.append(create_error(
            row_number, '操作类型不能为空', 'Operation type', '', 'error', '请填写操作类型'
        ))
    elif operation_data['operation_type'] not in valid_operation_types:
        errors.append(create_error(
            row_number, f'操作类型无效: {operation_data["operation_type"]}', 'Operation type',
            operation_data['operation_type'], 'error', f'有效操作类型: {", ".join(valid_operation_types)}'
        ))

    # 验证备件编号
    if not operation_data['part_no']:
        errors.append(create_error(
            row_number, '备件编号不能为空', 'Part No', '', 'error', '请填写备件编号'
        ))

    # 验证备件描述
    if not operation_data['description']:
        errors.append(create_error(
            row_number, '备件描述不能为空', 'Description', '', 'error', '请填写备件描述'
        ))

    # 验证数量
    if operation_data['quantity'] == 0:
        errors.append(create_error(
            row_number, '数量不能为0', 'Qty', operation_data['quantity'], 'error', '请填写非零的数量值'
        ))

    # 验证操作类型和数量的关系
    if operation_data['operation_type'] == 'Stock out' and operation_data['quantity'] > 0:
        errors.append(create_error(
            row_number, '出库操作数量应为负数', 'Qty', operation_data['quantity'], 'warning',
            '出库操作数量建议使用负数，系统会自动处理'
        ))
    elif operation_data['operation_type'].startswith('Stock in') and operation_data['quantity'] < 0:
        errors.append(create_error(
            row_number, '入库操作数量应为正数', 'Qty', operation_data['quantity'], 'warning',
            '入库操作数量建议使用正数，系统会自动处理'
        ))

    # 验证日期格式
    if operation_data['operation_date'] and not isinstance(operation_data['operation_date'], datetime):
        try:
            operation_data['operation_date'] = pd.to_datetime(operation_data['operation_date'])
        except:
            errors.append(create_error(
                row_number, '日期格式不正确', 'Date', operation_data['operation_date'],
                'error', '请使用 YYYY-MM-DD 格式'
            ))

    return errors


def check_duplicate_operation(conn, operation_data):
    """检查重复操作记录 - 增强版本"""
    try:
        # 检查完全重复的记录
        duplicate = conn.execute('''
            SELECT id, operation_date 
            FROM operation_records 
            WHERE operation_type = ? AND part_no = ? AND description = ? 
            AND quantity = ? AND operation_date = ?
        ''', (
            operation_data['operation_type'],
            operation_data['part_no'],
            operation_data['description'],
            operation_data['quantity'],
            operation_data['operation_date']
        )).fetchone()

        if duplicate:
            return True, f"与记录ID {duplicate['id']} 完全重复（操作时间: {duplicate['operation_date']}）"

        # 检查同一天同一备件的相似操作
        similar = conn.execute('''
            SELECT id, operation_type, quantity, operation_date
            FROM operation_records 
            WHERE part_no = ? AND operation_type = ? 
            AND date(operation_date) = date(?)
            AND ABS(quantity - ?) < 5  # 数量相差小于5
        ''', (
            operation_data['part_no'],
            operation_data['operation_type'],
            operation_data['operation_date'],
            operation_data['quantity']
        )).fetchone()

        if similar:
            return True, f"与记录ID {similar['id']} 高度相似（操作时间: {similar['operation_date']}, 数量: {similar['quantity']}）"

        return False, ""

    except Exception as e:
        current_app.logger.error(f"检查重复记录时出错: {str(e)}")
        return False, "检查失败"


def save_import_report(import_id, import_type, result):
    """保存导入报告到文件 - 增强版本"""
    try:
        report_data = {
            'import_id': import_id,
            'import_type': import_type,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'success': result.get('success', False),
            'message': result.get('message', ''),
            'created_count': result.get('created_count', 0),
            'updated_count': result.get('updated_count', 0),
            'imported_count': result.get('imported_count', 0),
            'error_count': result.get('error_count', 0),
            'not_found_count': result.get('not_found_count', 0),
            'skipped_duplicates': result.get('skipped_duplicates', 0),
            'errors': result.get('errors', []),
            'import_summary': result.get('import_summary', {}),
            'import_duration': result.get('import_summary', {}).get('import_duration', 0)
        }

        report_file = os.path.join('import_logs', f"{import_id}_report.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        current_app.logger.info(f"导入报告已保存: {report_file}")

        # 同时保存详细日志
        log_file = os.path.join('import_logs', f"{import_id}_detailed.log")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"导入ID: {import_id}\n")
            f.write(f"导入类型: {import_type}\n")
            f.write(f"导入时间: {report_data['timestamp']}\n")
            f.write(f"导入结果: {report_data['message']}\n")
            f.write(
                f"成功记录: {report_data.get('imported_count', 0) or report_data.get('created_count', 0) or report_data.get('updated_count', 0)}\n")
            f.write(f"错误数量: {report_data['error_count']}\n")
            f.write("=" * 50 + "\n")

            if report_data['errors']:
                f.write("错误详情:\n")
                for error in report_data['errors']:
                    f.write(
                        f"行 {error.get('row', 'N/A')}: [{error.get('field', 'General')}] {error.get('error', 'Unknown error')}\n")
                    f.write(f"   值: {error.get('value', 'N/A')}\n")
                    f.write(f"   建议: {error.get('suggestion', 'No suggestion')}\n")
                    f.write("-" * 30 + "\n")

    except Exception as e:
        current_app.logger.error(f"保存导入报告时出错: {str(e)}")


def create_error(row_number, error, field, value, severity, suggestion):
    """创建标准化的错误信息 - 增强版本"""
    return {
        'row': row_number,
        'error': error,
        'field': field,
        'value': str(value) if value is not None else '',
        'severity': severity,
        'suggestion': suggestion
    }


def clean_dataframe(df):
    """清理DataFrame数据 - 根据新的字段描述修正"""
    import time
    start_time = time.time()

    # 定义替换字典，用于将各种空值表示替换为空字符串
    replacement_dict = {
        'nan': '', 'None': '', 'null': '', 'NaN': '', 'NULL': '',
        'none': '', 'NONE': ''
    }

    # 删除全空行
    df = df.dropna(how='all')
    df = df.reset_index(drop=True)

    # 预处理关键字段：location（实际库位，不可为空）
    if 'location' in df.columns:
        df['location'] = df['location'].fillna('').astype(str).str.strip()
        df['location'] = df['location'].replace(replacement_dict)
        current_app.logger.info(f"处理 location 列，非空值数量: {df['location'].notna().sum()}")

    # 预处理其他可为空字段
    optional_fields = ['Rack', 'Level', 'Position', 'Side', 'State', 'Size Type', 'Description']
    for field in optional_fields:
        if field in df.columns:
            df[field] = df[field].fillna('').astype(str).str.strip()
            df[field] = df[field].replace(replacement_dict)

    # 预处理状态列
    if 'State' in df.columns:
        state_mapping = {
            '': 'free', 'nan': 'free', 'none': 'free', 'null': 'free',
            '空闲': 'free', '使用中': 'in_use', '低库存': 'low_stock',
            'free': 'free', 'in_use': 'in_use', 'low_stock': 'low_stock'
        }
        df['State'] = df['State'].map(state_mapping).fillna('free')

    # 预处理容量列
    if 'Capacity' in df.columns:
        df['Capacity'] = pd.to_numeric(df['Capacity'], errors='coerce').fillna(0)
        df['Capacity'] = df['Capacity'].clip(lower=0)

    end_time = time.time()
    current_app.logger.info(f"数据预处理完成，耗时: {end_time - start_time:.2f}秒")
    current_app.logger.info(f"预处理后 DataFrame 形状: {df.shape}")

    return df


def validate_excel_file(filename):
    """验证Excel文件类型"""
    allowed_extensions = {'xlsx', 'xls'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def safe_int(value, default=0):
    """安全转换为整数 - 增强版本"""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        # 处理浮点数
        if isinstance(value, float):
            return int(value)
        # 处理字符串
        if isinstance(value, str):
            # 移除可能存在的逗号（千位分隔符）
            value = value.replace(',', '')
            # 尝试直接转换
            return int(float(value))
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0):
    """安全转换为浮点数 - 增强版本"""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        if isinstance(value, str):
            value = value.replace(',', '')
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_str(value, default=''):
    """安全转换为字符串 - 增强版本"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        result = str(value).strip()
        return result if result else default
    except:
        return default


def safe_datetime(value, default=None):
    """安全转换为日期时间 - 增强版本"""
    if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # 尝试多种日期格式
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        # 使用pandas的日期解析作为后备
        return pd.to_datetime(value)
    except:
        return default