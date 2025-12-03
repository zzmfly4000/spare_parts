# [file name]: import_export_routes.py
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
import time
from models.database import (
    DatabaseManager,
    create_spare_part,
    create_operation_record,
    recalculate_all_stock,
    create_location_fast,
    update_location_fast,
    get_location_by_code,
    get_spare_part_by_part_no,
    calculate_stock_from_operations,
    calculate_stock_from_operations_with_connection,
    update_spare_part,
    get_spare_part_by_id,
    batch_update_parts,
    calculate_location_status,
    safe_int,
    safe_float,
    update_single_location_metrics
)
from utils.helpers import safe_str, validate_excel_file, safe_datetime
from utils.sync_utils import sync_all_operations


def setup_import_export_routes(app):
    """设置数据导入导出路由 - 性能优化版本"""

    # 创建导入日志目录
    log_dir = 'import_logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # =============================================================================
    # 库位导入辅助函数
    # =============================================================================

    def batch_upsert_locations(locations_data, conn):
        """使用UPSERT操作批量处理库位 - 最高性能版本"""
        if not locations_data:
            return 0, 0

        created_count = 0
        updated_count = 0
        batch_size = 200

        try:
            # 准备批量数据
            batch_data = []
            for location_data in locations_data:
                data_tuple = (
                    location_data.get('location_code', ''),
                    location_data.get('rack', ''),
                    location_data.get('level', ''),
                    location_data.get('position', ''),
                    location_data.get('side', ''),
                    location_data.get('status', 'free'),
                    location_data.get('capacity', 0),
                    location_data.get('size_type', ''),
                    location_data.get('description', ''),
                    0,  # variety_count
                    0,  # total_quantity
                    0.0,  # utilization_rate
                    0,  # low_stock_varieties
                    0,  # out_of_stock_varieties
                    0.0,  # total_value
                    'empty'  # status_category
                )
                batch_data.append(data_tuple)

            # 使用INSERT OR REPLACE实现UPSERT
            query = '''
                INSERT OR REPLACE INTO locations 
                (location_code, rack, level, position, side, status, capacity, size_type, description, 
                 variety_count, total_quantity, utilization_rate, low_stock_varieties, 
                 out_of_stock_varieties, total_value, status_category, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            '''

            # 执行批量操作
            for i in range(0, len(batch_data), batch_size):
                batch = batch_data[i:i + batch_size]
                try:
                    cursor = conn.executemany(query, batch)
                    # SQLite的executemany不返回具体的行数，我们估算
                    updated_count += len(batch)
                except Exception as e:
                    current_app.logger.error(f"批量UPSERT失败: {str(e)}")
                    # 回退到逐条处理
                    for data in batch:
                        try:
                            cursor = conn.execute(query, data)
                            updated_count += 1
                        except Exception:
                            continue

            # 由于使用了UPSERT，我们无法准确区分创建和更新
            # 可以粗略估计：如果库位原来不存在就是创建，存在就是更新
            # 这里简化处理，假设大部分是更新
            created_count = max(0, len(locations_data) - updated_count)

            return created_count, updated_count

        except Exception as e:
            current_app.logger.error(f"批量UPSERT过程失败: {str(e)}")
            return 0, 0

    # =============================================================================
    # 1. 库位导入功能 - 高性能版本
    # =============================================================================

    def process_locations_import_high_performance(df, import_id):
        """高性能库位导入处理 - 使用UPSERT操作"""
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

        current_app.logger.info(f"开始高性能库位导入，共 {len(df)} 行数据")

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 1. 快速预加载现有库位（可选，用于更准确的统计）
                existing_locations = {}
                try:
                    locations_result = conn.execute('SELECT location_code FROM locations').fetchall()
                    for location in locations_result:
                        existing_locations[location['location_code']] = True
                    current_app.logger.info(f"预加载完成: {len(existing_locations)} 个现有库位")
                except Exception as e:
                    current_app.logger.warning(f"预加载现有库位失败: {str(e)}")

                # 2. 准备数据 - 使用更高效的方式
                locations_to_upsert = []

                for index, row in df.iterrows():
                    row_number = index + 2
                    try:
                        location_data = extract_location_data_quick(row)
                        location_code = location_data.get('location_code', '').strip()

                        if not location_code:
                            errors.append(create_error(
                                row_number, '实际库位代码不能为空', 'location_code', '', 'error', '请填写实际库位代码'
                            ))
                            error_count += 1
                            continue

                        # 设置默认值
                        if 'status' not in location_data:
                            location_data['status'] = 'free'
                        if 'capacity' not in location_data:
                            location_data['capacity'] = 0

                        locations_to_upsert.append(location_data)

                    except Exception as e:
                        errors.append(create_error(
                            row_number, f'处理库位数据时出错: {str(e)}', '数据处理', '', 'error', '请检查数据格式'
                        ))
                        error_count += 1

                # 3. 使用批量UPSERT操作
                if locations_to_upsert:
                    created, updated = batch_upsert_locations(locations_to_upsert, conn)
                    created_count = created
                    updated_count = updated
                    current_app.logger.info(f"批量UPSERT完成: 创建 {created_count} 个，更新 {updated_count} 个")

                conn.commit()

        except Exception as e:
            error_msg = f'数据库操作失败: {str(e)}'
            current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
            errors.append(create_error(
                '系统', error_msg, '数据库', '', 'error', '请联系系统管理员'
            ))
            error_count += 1

        # 生成结果报告
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

        success = error_count == 0 or (created_count + updated_count) > 0

        if success:
            if error_count == 0:
                message = f'导入成功！创建 {created_count} 个库位，更新 {updated_count} 个库位，耗时 {import_duration:.1f}秒'
            else:
                message = f'部分导入成功！创建 {created_count} 个库位，更新 {updated_count} 个库位，错误 {error_count} 个，耗时 {import_duration:.1f}秒'
        else:
            message = f'导入失败！错误 {error_count} 个，耗时 {import_duration:.1f}秒'

        return {
            'success': success,
            'message': message,
            'created_count': created_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }

    @app.route('/import_locations', methods=['GET', 'POST'])
    def import_locations():
        """库位信息导入页面 - 高性能版本"""
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

                # 检查文件大小
                file.seek(0, 2)  # 移动到文件末尾
                file_size = file.tell()
                file.seek(0)  # 重置文件指针

                if file_size > 10 * 1024 * 1024:  # 10MB限制
                    flash('文件大小不能超过10MB', 'danger')
                    return redirect(request.url)

                import_start_time = datetime.now()
                import_id = f"locations_{import_start_time.strftime('%Y%m%d_%H%M%S')}"

                current_app.logger.info(
                    f"开始导入库位信息，文件: {file.filename}, 大小: {file_size}字节, 导入ID: {import_id}")

                try:
                    # 使用更快的读取方式，限制读取行数
                    df = pd.read_excel(
                        file,
                        dtype=str,
                        keep_default_na=False,
                        engine='openpyxl',
                        nrows=10000  # 限制最大行数，防止过大文件
                    )
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")

                    # 使用快速清理函数
                    df = clean_locations_dataframe_quick(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                    if len(df) == 0:
                        flash('Excel文件中没有有效的库位数据', 'danger')
                        return redirect(request.url)

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                # 检查必需列
                if 'location_code' not in df.columns:
                    flash('Excel文件中缺少必需的实际库位列，请使用系统提供的模板', 'danger')
                    return redirect(request.url)

                # 根据数据量选择处理方式
                if len(df) > 500:
                    # 大数据量使用批处理
                    result = process_locations_import_high_performance(df, import_id)
                else:
                    # 小数据量使用快速处理
                    result = process_locations_import_quick(df, import_id)

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

    def clean_locations_dataframe_quick(df):
        """清理库位DataFrame - 快速版本"""
        # 创建副本避免修改原数据
        df = df.copy()

        # 快速移除空行
        df = df.dropna(how='all').reset_index(drop=True)

        # 快速列名映射
        column_mapping = {
            'Rack': 'rack',
            'location': 'location_code',
            'Location': 'location_code',
            'Level': 'level',
            'Position': 'position',
            'Side': 'side',
            'State': 'status',
            'Capacity': 'capacity',
            'Size Type': 'size_type',
            'Size': 'size_type',
            'Description': 'description'
        }

        # 快速重命名
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df[new_col] = df[old_col]

        # 确保location_code列存在
        if 'location_code' not in df.columns:
            return pd.DataFrame()  # 如果没有关键列，返回空DataFrame

        # 快速清理location_code - 使用列表推导式，比apply快
        location_codes = []
        for val in df['location_code'].values:
            if pd.isna(val) or val == '':
                location_codes.append('')
            else:
                location_codes.append(str(val).strip())

        df['location_code'] = location_codes
        df = df[df['location_code'] != '']

        # 快速清理其他文本字段
        text_columns = ['rack', 'level', 'position', 'side', 'status', 'size_type', 'description']
        for col in text_columns:
            if col in df.columns:
                cleaned_values = []
                for val in df[col].values:
                    if pd.isna(val) or val == '':
                        cleaned_values.append('')
                    else:
                        cleaned_values.append(str(val).strip())
                df[col] = cleaned_values

        # 快速清理数字字段
        if 'capacity' in df.columns:
            capacities = []
            for val in df['capacity'].values:
                if pd.isna(val) or val == '':
                    capacities.append(0)
                else:
                    try:
                        capacities.append(int(float(str(val))))
                    except:
                        capacities.append(0)
            df['capacity'] = capacities

        current_app.logger.info(f"库位数据快速清理完成: 从 {len(df)} 行数据中清理出有效数据")
        return df.reset_index(drop=True)

    def process_locations_import_quick(df, import_id):
        """处理库位信息导入 - 快速版本"""
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

        current_app.logger.info(f"开始快速处理库位导入，共 {len(df)} 行数据")

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 快速预加载现有库位
                existing_locations = {}
                try:
                    locations_result = conn.execute('SELECT location_code FROM locations').fetchall()
                    for location in locations_result:
                        existing_locations[location['location_code']] = True
                    current_app.logger.info(f"预加载完成: {len(existing_locations)} 个现有库位")
                except Exception as e:
                    current_app.logger.error(f"预加载现有库位失败: {str(e)}")
                    # 继续处理，existing_locations为空

                # 设置进度报告间隔
                total_rows = len(df)
                progress_interval = max(1, total_rows // 10)  # 每10%报告一次进度
                last_progress_time = time.time()

                for index, row in df.iterrows():
                    row_number = index + 2

                    # 进度报告
                    if index % progress_interval == 0:
                        current_time = time.time()
                        if current_time - last_progress_time > 2:  # 至少2秒才报告一次
                            current_app.logger.info(
                                f"处理进度: {index + 1}/{total_rows} ({((index + 1) / total_rows * 100):.1f}%)")
                            last_progress_time = current_time

                    try:
                        # 快速数据提取
                        location_data = extract_location_data_quick(row)

                        # 验证必需字段
                        location_code = location_data.get('location_code', '').strip()
                        if not location_code:
                            errors.append(create_error(
                                row_number, '实际库位代码不能为空', 'location_code', '', 'error', '请填写实际库位代码'
                            ))
                            error_count += 1
                            continue

                        # 设置默认值
                        if 'status' not in location_data:
                            location_data['status'] = 'free'
                        if 'capacity' not in location_data:
                            location_data['capacity'] = 0

                        # 检查是否已存在
                        if location_code in existing_locations:
                            # 更新现有库位
                            try:
                                update_data = {k: v for k, v in location_data.items() if k != 'location_code'}

                                if update_data:
                                    update_success = update_location_simple(location_code, update_data, conn)
                                    if update_success:
                                        updated_count += 1
                                    else:
                                        errors.append(create_error(
                                            row_number, f'更新库位失败', '数据库', location_code, 'error', '库位可能不存在'
                                        ))
                                        error_count += 1
                            except Exception as e:
                                errors.append(create_error(
                                    row_number, f'更新库位失败: {str(e)}', '数据库', location_code, 'error', '请检查库位数据'
                                ))
                                error_count += 1
                        else:
                            # 创建新库位
                            try:
                                create_success = create_location_simple(location_data, conn)
                                if create_success:
                                    created_count += 1
                                    existing_locations[location_code] = True
                                else:
                                    errors.append(create_error(
                                        row_number, f'创建库位失败', '数据库', location_code, 'error', '请检查库位数据'
                                    ))
                                    error_count += 1
                            except Exception as e:
                                errors.append(create_error(
                                    row_number, f'创建库位失败: {str(e)}', '数据库', location_code, 'error', '请检查库位数据'
                                ))
                                error_count += 1

                    except Exception as e:
                        error_msg = f'处理库位数据时出错: {str(e)}'
                        errors.append(create_error(
                            row_number, error_msg, '数据处理', '', 'error', '请检查数据格式'
                        ))
                        error_count += 1

                conn.commit()
                current_app.logger.info(
                    f"库位导入完成: 创建 {created_count} 个，更新 {updated_count} 个，错误 {error_count} 个")

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
            'created_count': created_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'import_duration': import_duration
        })

        success = error_count == 0 or (created_count + updated_count) > 0

        if success:
            if error_count == 0:
                message = f'导入成功！创建 {created_count} 个库位，更新 {updated_count} 个库位，耗时 {import_duration:.1f}秒'
            else:
                message = f'部分导入成功！创建 {created_count} 个库位，更新 {updated_count} 个库位，错误 {error_count} 个，耗时 {import_duration:.1f}秒'
        else:
            message = f'导入失败！错误 {error_count} 个，耗时 {import_duration:.1f}秒'

        return {
            'success': success,
            'message': message,
            'created_count': created_count,
            'updated_count': updated_count,
            'error_count': error_count,
            'errors': errors,
            'import_summary': import_summary
        }

    def create_location_simple(location_data, conn):
        """创建库位 - 简化版本"""
        try:
            cursor = conn.execute('''
                INSERT INTO locations 
                (location_code, rack, level, position, side, status, capacity, size_type, description,
                 variety_count, total_quantity, utilization_rate, low_stock_varieties,
                 out_of_stock_varieties, total_value, status_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0.0, 0, 0, 0.0, 'empty')
            ''', (
                location_data['location_code'],
                location_data.get('rack', ''),
                location_data.get('level', ''),
                location_data.get('position', ''),
                location_data.get('side', ''),
                location_data.get('status', 'free'),
                location_data.get('capacity', 0),
                location_data.get('size_type', ''),
                location_data.get('description', '')
            ))
            return True
        except Exception as e:
            # 如果是重复键错误，忽略
            if "UNIQUE constraint failed" in str(e):
                return False
            raise e

    def update_location_simple(location_code, update_data, conn):
        """更新库位 - 简化版本"""
        try:
            fields = []
            values = []

            for key, value in update_data.items():
                fields.append(f"{key} = ?")
                values.append(value)

            values.append(location_code)

            query = f"UPDATE locations SET {', '.join(fields)} WHERE location_code = ?"
            cursor = conn.execute(query, values)

            return cursor.rowcount > 0
        except Exception as e:
            raise e

    def extract_location_data_quick(row):
        """提取库位数据 - 快速版本"""
        location_data = {}

        # 快速提取字段
        for col in ['location_code', 'rack', 'level', 'position', 'side', 'status', 'size_type', 'description']:
            if col in row and pd.notna(row[col]) and str(row[col]).strip():
                location_data[col] = str(row[col]).strip()

        # 处理容量字段
        if 'capacity' in row and pd.notna(row['capacity']) and str(row['capacity']).strip():
            try:
                location_data['capacity'] = int(float(str(row['capacity'])))
            except:
                location_data['capacity'] = 0

        return location_data

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
        """操作记录导入页面 - 修复重定向版本"""
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
                    df = clean_operations_dataframe_complete(df)
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

                # 处理导入
                result = process_operations_import_optimized(df, import_id)

                import_end_time = datetime.now()
                import_duration = (import_end_time - import_start_time).total_seconds()

                current_app.logger.info(f"操作记录导入完成，耗时: {import_duration:.2f}秒，结果: {result}")

                save_import_report(import_id, 'operations', result)

                # 关键修复：导入成功后直接重定向到操作记录页面
                if result['success']:
                    current_app.logger.info(f"导入成功，重定向到操作记录页面，导入记录数: {result['imported_count']}")
                    # 重定向到操作记录页面第一页
                    return redirect(url_for('operation_records', page=1))
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

        # GET请求保持不变
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
    # 3. 备件信息更新导入功能 - 优化字段映射
    # =============================================================================

    @app.route('/import_part_info_only', methods=['GET', 'POST'])
    def import_part_info_only():
        """备件信息更新导入页面 - 优化版本"""
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
                import_id = f"parts_{import_start_time.strftime('%Y%m%d_%H%M%S')}"

                current_app.logger.info(f"开始导入备件信息更新，文件: {file.filename}, 导入ID: {import_id}")

                try:
                    df = pd.read_excel(file, dtype=str, keep_default_na=False)
                    current_app.logger.info(f"成功读取Excel文件，共 {len(df)} 行数据")

                    # 使用优化的数据清理函数
                    df = clean_part_info_dataframe_complete(df)
                    current_app.logger.info(f"数据清理后，剩余 {len(df)} 行有效数据")

                except Exception as e:
                    error_msg = f'读取Excel文件失败: {str(e)}'
                    current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
                    flash(f'{error_msg}，请检查文件格式是否正确', 'danger')
                    return redirect(request.url)

                if not has_required_part_columns(df):
                    flash('Excel文件中缺少必需列"Part no"或"备件编号"', 'danger')
                    return redirect(request.url)

                # 根据数据量选择处理方式
                if len(df) > 1000:
                    result = process_part_info_update_advanced(df, import_id)
                else:
                    result = process_part_info_update_optimized(df, import_id)

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

    def has_required_part_columns(df):
        """检查是否包含必需的备件编号列"""
        part_no_columns = ['Part no', '备件编号', 'Part No', 'part_no']
        return any(col in df.columns for col in part_no_columns)

    def clean_part_info_dataframe_complete(df):
        """清理备件信息更新DataFrame - 彻底修复版本"""
        df = df.copy()

        # 移除全空行
        df = df.dropna(how='all').reset_index(drop=True)

        # 列名映射
        column_mapping = {
            'Part no': 'part_no',
            'Key part': 'key_part',
            'Low stock': 'min_stock',
            'High stock': 'max_stock',
            'LT (Week)': 'lt_weeks',
            'Unit price (RMB)': 'unit_price',
            '单位 Unit': 'unit'
        }

        # 重命名列
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df[new_col] = df[old_col]

        # 处理part_no
        if 'part_no' in df.columns:
            df['part_no'] = df['part_no'].apply(lambda x: safe_str(x).strip() if pd.notna(x) else '')
            df = df[df['part_no'] != '']

        # 处理数字字段
        numeric_columns = ['min_stock', 'max_stock', 'lt_weeks', 'unit_price']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_float(x) if pd.notna(x) else 0.0)

        # 处理文本字段
        text_columns = ['key_part', 'unit']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_str(x).strip() if pd.notna(x) else '')

        current_app.logger.info(f"备件信息数据清理完成: 从 {len(df)} 行数据中清理出有效数据")
        return df.reset_index(drop=True)

    def process_part_info_update_optimized(df, import_id):
        """处理备件信息更新导入 - 优化版本（包含库位状态更新）"""
        updated_count = 0
        not_found_count = 0
        error_count = 0
        errors = []
        affected_locations = set()

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
                parts_result = conn.execute('SELECT id, part_no, location FROM spare_parts').fetchall()
                for part in parts_result:
                    parts_cache[part['part_no']] = {
                        'id': part['id'],
                        'location': part['location']
                    }

                current_app.logger.info(f"预加载完成: {len(parts_cache)} 个备件")

                # 批量处理数据
                update_batch = []
                validation_errors = []

                for index, row in df.iterrows():
                    row_number = index + 2

                    try:
                        # 提取和验证数据
                        part_no = safe_str(row.get('part_no', '')).strip()
                        if not part_no:
                            validation_errors.append(create_error(
                                row_number, '备件编号不能为空', 'part_no', '', 'error', '请填写有效的备件编号'
                            ))
                            continue

                        # 检查备件是否存在
                        if part_no not in parts_cache:
                            validation_errors.append(create_error(
                                row_number, f'备件编号 "{part_no}" 不存在', 'part_no', part_no, 'error',
                                '请检查备件编号是否正确，或先创建该备件'
                            ))
                            not_found_count += 1
                            continue

                        part_id = parts_cache[part_no]['id']
                        part_location = parts_cache[part_no]['location']
                        update_data = extract_part_update_data_optimized(row, row_number)

                        if not update_data:
                            validation_errors.append(create_error(
                                row_number, '没有提供任何可更新的字段', '数据验证', '', 'warning',
                                '请至少填写一个需要更新的字段'
                            ))
                            continue

                        # 记录受影响的库位
                        if part_location:
                            affected_locations.add(part_location)

                        # 添加到批量更新列表
                        update_batch.append({
                            'part_id': part_id,
                            'part_no': part_no,
                            'location': part_location,
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

                # 更新相关库位状态
                if affected_locations:
                    current_app.logger.info(f"更新 {len(affected_locations)} 个相关库位的状态")
                    for location_code in affected_locations:
                        try:
                            # 重新计算库位状态
                            cursor = conn.execute('''
                                SELECT l.location_code, l.variety_count,
                                       COALESCE(SUM(p.current_stock), 0) as total_stock,
                                       COALESCE(MIN(p.min_stock), 0) as min_stock,
                                       COALESCE(MAX(p.max_stock), 0) as max_stock
                                FROM locations l
                                LEFT JOIN spare_parts p ON l.location_code = p.location
                                WHERE l.location_code = ?
                                GROUP BY l.location_code, l.variety_count
                            ''', (location_code,))

                            location_data = cursor.fetchone()

                            if location_data:
                                variety_count = safe_int(location_data['variety_count'])
                                total_stock = safe_int(location_data['total_stock'])
                                min_stock = safe_int(location_data['min_stock'])
                                max_stock = safe_int(location_data['max_stock'])

                                # 计算新的状态
                                if variety_count == 0:
                                    new_status = 'not_use'
                                else:
                                    new_status = calculate_location_status(variety_count, 0, total_stock, min_stock,
                                                                           max_stock)

                                # 更新库位状态
                                conn.execute('''
                                    UPDATE locations 
                                    SET status = ?, last_updated = CURRENT_TIMESTAMP 
                                    WHERE location_code = ?
                                ''', (new_status, location_code))

                        except Exception as e:
                            current_app.logger.error(f"更新库位 {location_code} 状态失败: {str(e)}")

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
            'locations_updated': len(affected_locations),
            'import_duration': import_duration
        })

        current_app.logger.info(f"备件信息更新导入完成，耗时: {import_duration:.2f}秒")

        success = error_count == 0 and updated_count > 0

        if success:
            if error_count == 0:
                message = f'导入成功！更新 {updated_count} 个备件，同步更新 {len(affected_locations)} 个库位状态'
            else:
                message = f'部分导入成功！更新 {updated_count} 个备件，同步更新 {len(affected_locations)} 个库位状态，错误 {error_count} 个'
        else:
            message = f'导入失败！未找到 {not_found_count} 个备件，错误 {error_count} 个'

        return {
            'success': success,
            'message': f'{message}，耗时 {import_duration:.2f}秒',
            'updated_count': updated_count,
            'not_found_count': not_found_count,
            'error_count': error_count,
            'locations_updated': len(affected_locations),
            'errors': errors,
            'import_summary': import_summary
        }

    def extract_part_update_data_optimized(row, row_number):
        """提取备件更新数据 - 优化版本"""
        update_data = {}

        # 处理关键备件字段
        key_part = safe_str(row.get('key_part', '')).strip().lower()
        if key_part:
            if key_part in ['yes', '是', 'true', '1', 'yes', 'true']:
                update_data['key_part'] = 1
            elif key_part in ['no', '否', 'false', '0', 'no', 'false']:
                update_data['key_part'] = 0

        # 处理数字字段
        numeric_fields = {
            'min_stock': 'min_stock',
            'max_stock': 'max_stock',
            'lt_weeks': 'lt_weeks',
            'unit_price': 'unit_price'
        }

        for field_name, col_name in numeric_fields.items():
            value = row.get(col_name)
            if pd.notna(value) and value is not None and str(value).strip():
                try:
                    if field_name == 'unit_price':
                        num_value = safe_float(value)
                    else:
                        num_value = safe_int(value)

                    if num_value is not None and num_value >= 0:
                        update_data[field_name] = num_value
                except (ValueError, TypeError) as e:
                    # 记录但不中断处理
                    current_app.logger.warning(f"行 {row_number} 字段 {col_name} 格式错误: {value}")

        # 验证库存阈值逻辑
        if 'min_stock' in update_data and 'max_stock' in update_data:
            if update_data['min_stock'] > update_data['max_stock']:
                # 移除有冲突的字段
                update_data.pop('min_stock', None)
                update_data.pop('max_stock', None)

        # 处理单位
        unit = safe_str(row.get('unit', '')).strip()
        if unit and unit != '':
            update_data['unit'] = unit

        return update_data

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
    # 4. 导出功能
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
    # 5. 导入报告下载功能
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
    # 6. 兼容性路由
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
        """处理操作记录导入 - 完整修复版本"""
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

        current_app.logger.info(f"开始处理操作记录导入，共 {len(df)} 行数据")

        # 在本地重新定义库存计算函数，避免导入问题
        def calculate_stock_from_operations_with_connection_local(part_no, conn):
            """本地重新定义库存计算函数"""
            try:
                # 计算所有入库操作的总和（正数）
                cursor = conn.execute('''
                    SELECT COALESCE(SUM(quantity), 0) 
                    FROM operation_records 
                    WHERE part_no = ? AND quantity > 0
                ''', (part_no,))
                total_in = cursor.fetchone()[0] or 0

                # 计算出库操作的总和（负数，但取绝对值）
                cursor = conn.execute('''
                    SELECT COALESCE(SUM(ABS(quantity)), 0) 
                    FROM operation_records 
                    WHERE part_no = ? AND quantity < 0
                ''', (part_no,))
                total_out = cursor.fetchone()[0] or 0

                # 计算总库存：所有入库 - 所有出库
                total_stock = total_in - total_out
                final_stock = max(0, total_stock)

                current_app.logger.debug(
                    f"库存计算(本地): {part_no} = {total_in}(入库) - {total_out}(出库) = {final_stock}")
                return final_stock
            except Exception as e:
                current_app.logger.error(f"库存计算失败 {part_no}: {str(e)}")
                return 0

        def batch_update_stock_optimized(affected_parts, conn):
            """批量更新库存 - 优化性能版本"""
            updated_count = 0
            batch_size = 50  # 减少批量大小避免锁定

            current_app.logger.info(f"开始批量更新 {len(affected_parts)} 个备件的库存")

            for i in range(0, len(affected_parts), batch_size):
                batch = list(affected_parts)[i:i + batch_size]
                current_app.logger.info(
                    f"处理库存更新批次 {i // batch_size + 1}/{(len(affected_parts) + batch_size - 1) // batch_size}")

                for part_no in batch:
                    try:
                        # 重新计算库存
                        new_stock = calculate_stock_from_operations_with_connection_local(part_no, conn)

                        # 更新备件库存
                        cursor = conn.execute('''
                            UPDATE spare_parts 
                            SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                            WHERE part_no = ?
                        ''', (new_stock, part_no))

                        if cursor.rowcount > 0:
                            updated_count += 1
                            if updated_count % 100 == 0:
                                current_app.logger.info(f"已更新 {updated_count} 个备件库存")

                    except Exception as e:
                        current_app.logger.error(f"批量更新备件 {part_no} 库存失败: {str(e)}")
                        # 继续处理其他备件

            return updated_count

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
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
                locations_result = conn.execute('SELECT location_code, status, variety_count FROM locations').fetchall()
                for location in locations_result:
                    locations_cache[location['location_code']] = {
                        'status': location['status'],
                        'variety_count': location['variety_count']
                    }

                current_app.logger.info(f"预加载完成: {len(parts_cache)} 备件, {len(locations_cache)} 库位")

                # 处理数据
                operations_to_insert = []
                parts_to_create = []
                locations_to_create = []
                affected_parts = set()  # 记录受影响的备件

                # 进度跟踪
                total_rows = len(df)
                progress_interval = max(1, total_rows // 20)  # 每5%报告一次进度
                last_progress_time = time.time()

                for index, row in df.iterrows():
                    row_number = index + 2

                    # 进度报告
                    if index % progress_interval == 0:
                        current_time = time.time()
                        if current_time - last_progress_time > 5:  # 至少5秒才报告一次
                            current_app.logger.info(
                                f"数据准备进度: {index + 1}/{total_rows} ({((index + 1) / total_rows * 100):.1f}%)")
                            last_progress_time = current_time

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

                        # 记录受影响的备件
                        affected_parts.add(part_no)

                        # 处理备件信息
                        if part_no not in parts_cache:
                            parts_to_create.append({
                                'part_no': part_no,
                                'name': operation_data['description'],
                                'type': operation_data.get('part_type', '通用'),
                                'location': location_code,
                                'supplier': operation_data.get('supplier_recipient', ''),
                                'description': operation_data['description'],
                                'current_stock': 0
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
                                'variety_count': 0
                            }

                        # 准备操作记录
                        operation_record = (
                            str(operation_data['operation_type']),
                            operation_data['operation_date'],
                            str(operation_data.get('supplier_recipient', '')),
                            str(operation_data.get('location', '')),
                            str(operation_data['part_no']),
                            str(operation_data['description']),
                            str(operation_data.get('part_type', '')),
                            str(operation_data.get('product_model', '')),
                            int(operation_data['quantity']),
                            str(operation_data.get('work_center', ''))
                        )

                        operations_to_insert.append(operation_record)
                        imported_count += 1

                    except Exception as e:
                        error_msg = f'处理操作记录时出错: {str(e)}'
                        errors.append(create_error(
                            row_number, error_msg, '数据处理', str(row.to_dict()),
                            'error', '请检查数据格式或联系管理员'
                        ))
                        error_count += 1

                current_app.logger.info(f"数据准备完成: 准备插入 {len(operations_to_insert)} 条操作记录")

                # 执行数据库操作
                current_app.logger.info("开始执行数据库操作...")

                # 创建新备件 - 分批处理
                if parts_to_create:
                    current_app.logger.info(f"创建 {len(parts_to_create)} 个新备件")
                    batch_size = 100
                    for i in range(0, len(parts_to_create), batch_size):
                        batch = parts_to_create[i:i + batch_size]
                        current_app.logger.info(
                            f"创建备件批次 {i // batch_size + 1}/{(len(parts_to_create) + batch_size - 1) // batch_size}")

                        for part_data in batch:
                            try:
                                cursor = conn.execute('''
                                    INSERT INTO spare_parts 
                                    (part_no, name, type, current_stock, min_stock, max_stock, key_part, 
                                     lt_weeks, unit_price, unit, location, supplier, description)
                                    VALUES (?, ?, ?, ?, 0, 0, FALSE, 0, 0.0, '个', ?, ?, ?)
                                ''', (
                                    str(part_data['part_no']),
                                    str(part_data['name']),
                                    str(part_data['type']),
                                    int(part_data['current_stock']),
                                    str(part_data.get('location', '')),
                                    str(part_data.get('supplier', '')),
                                    str(part_data['description'])
                                ))
                                parts_cache[part_data['part_no']]['id'] = cursor.lastrowid
                            except Exception as e:
                                current_app.logger.error(f"创建备件失败 {part_data['part_no']}: {str(e)}")

                # 创建新库位 - 分批处理
                if locations_to_create:
                    current_app.logger.info(f"创建 {len(locations_to_create)} 个新库位")
                    batch_size = 100
                    for i in range(0, len(locations_to_create), batch_size):
                        batch = locations_to_create[i:i + batch_size]
                        current_app.logger.info(
                            f"创建库位批次 {i // batch_size + 1}/{(len(locations_to_create) + batch_size - 1) // batch_size}")

                        for location_data in batch:
                            try:
                                conn.execute('''
                                    INSERT INTO locations 
                                    (location_code, rack, level, position, side, status, capacity, size_type, description, 
                                     variety_count, total_quantity, utilization_rate, low_stock_varieties,
                                     out_of_stock_varieties, total_value, status_category)
                                    VALUES (?, '', '', '', '', ?, 100, 'Medium', ?, 0, 0, 0.0, 0, 0, 0.0, 'empty')
                                ''', (
                                    str(location_data['location_code']),
                                    str(location_data['status']),
                                    str(location_data['description'])
                                ))
                            except Exception as e:
                                current_app.logger.error(f"创建库位失败: {str(e)}")

                # 插入操作记录 - 分批处理
                if operations_to_insert:
                    current_app.logger.info(f"开始插入 {len(operations_to_insert)} 条操作记录")
                    successful_inserts = 0
                    batch_size = 500

                    for i in range(0, len(operations_to_insert), batch_size):
                        batch = operations_to_insert[i:i + batch_size]
                        current_app.logger.info(
                            f"插入操作记录批次 {i // batch_size + 1}/{(len(operations_to_insert) + batch_size - 1) // batch_size}")

                        for operation in batch:
                            try:
                                conn.execute('''
                                    INSERT INTO operation_records 
                                    (operation_type, operation_date, supplier_recipient, location, part_no, 
                                     description, part_type, product_model, quantity, work_center)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', operation)
                                successful_inserts += 1

                            except Exception as e:
                                current_app.logger.error(f"插入操作记录失败: {str(e)}")
                                continue

                    current_app.logger.info(
                        f"成功插入 {successful_inserts} 条操作记录，失败 {len(operations_to_insert) - successful_inserts} 条")

                    # 更新实际导入数量
                    imported_count = successful_inserts

                # 关键修复：批量更新所有受影响备件的库存
                if affected_parts:
                    parts_updated = batch_update_stock_optimized(affected_parts, conn)
                else:
                    current_app.logger.info("没有受影响的备件需要更新库存")

                # 提交事务
                conn.commit()
                current_app.logger.info(
                    f"数据库事务提交成功，实际导入 {imported_count} 条操作记录，更新 {parts_updated} 个备件库存")

        except Exception as e:
            error_msg = f'数据库操作失败: {str(e)}'
            current_app.logger.error(f'{error_msg}\n{traceback.format_exc()}')
            errors.append(create_error('系统', error_msg, '数据库', '', 'error', '请联系系统管理员'))
            error_count += 1

        # 如果导入成功但库存更新失败，尝试强制重算所有库存
        if imported_count > 0 and parts_updated == 0:
            current_app.logger.warning("检测到库存更新失败，尝试强制重算所有库存")
            try:
                force_updated_count = force_recalculate_all_stock_local()
                if force_updated_count > 0:
                    parts_updated = force_updated_count
                    current_app.logger.info(f"强制重算成功，更新了 {force_updated_count} 个备件库存")
            except Exception as e:
                current_app.logger.error(f"强制重算库存失败: {str(e)}")

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
            'import_duration': import_duration
        })

        success = imported_count > 0

        if success:
            if error_count == 0:
                message = f'导入成功！导入 {imported_count} 条操作记录，更新 {parts_updated} 个备件库存'
            else:
                message = f'部分导入成功！导入 {imported_count} 条记录，更新 {parts_updated} 个备件库存，错误 {error_count} 个'
        else:
            message = f'导入失败！错误 {error_count} 个'

        current_app.logger.info(f"操作记录导入完成: {message}")

        # 保存导入报告
        save_import_report(import_id, 'operations', {
            'success': success,
            'message': message,
            'imported_count': imported_count,
            'error_count': error_count,
            'skipped_duplicates': skipped_duplicates,
            'new_parts_created': new_parts_created,
            'parts_updated': parts_updated,
            'locations_updated': locations_updated,
            'errors': errors,
            'import_summary': import_summary
        })

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
            'import_summary': import_summary
        }

    def force_recalculate_all_stock_local():
        """强制重新计算所有库存 - 本地版本"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取所有备件
                parts = conn.execute('SELECT id, part_no, current_stock FROM spare_parts').fetchall()
                updated_count = 0

                current_app.logger.info(f"开始强制重算 {len(parts)} 个备件的库存")

                for i, part in enumerate(parts):
                    part_id = part[0]
                    part_no = part[1]
                    old_stock = part[2]

                    try:
                        # 重新计算库存
                        # 计算所有入库操作的总和（正数）
                        cursor = conn.execute('''
                            SELECT COALESCE(SUM(quantity), 0) 
                            FROM operation_records 
                            WHERE part_no = ? AND quantity > 0
                        ''', (part_no,))
                        total_in = cursor.fetchone()[0] or 0

                        # 计算出库操作的总和（负数，但取绝对值）
                        cursor = conn.execute('''
                            SELECT COALESCE(SUM(ABS(quantity)), 0) 
                            FROM operation_records 
                            WHERE part_no = ? AND quantity < 0
                        ''', (part_no,))
                        total_out = cursor.fetchone()[0] or 0

                        # 计算总库存：所有入库 - 所有出库
                        new_stock = total_in - total_out
                        new_stock = max(0, new_stock)

                        # 只有在库存变化时才更新
                        if new_stock != old_stock:
                            conn.execute('''
                                UPDATE spare_parts 
                                SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                                WHERE id = ?
                            ''', (new_stock, part_id))
                            updated_count += 1

                            if updated_count % 100 == 0:
                                current_app.logger.info(f"强制重算进度: 已更新 {updated_count} 个备件")

                    except Exception as e:
                        current_app.logger.error(f"强制重算备件 {part_no} 失败: {str(e)}")
                        continue

                conn.commit()
                current_app.logger.info(f"强制重算完成: 更新了 {updated_count} 个备件库存")
                return updated_count

        except Exception as e:
            current_app.logger.error(f"强制重算过程失败: {str(e)}")
            return 0

    # =============================================================================
    # 其他处理函数
    # =============================================================================

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

    # =============================================================================
    # 辅助函数
    # =============================================================================

    def extract_operation_data(row):
        """提取操作记录数据 - 修复数据类型版本"""
        # 确保所有字段都有正确的数据类型
        operation_type = safe_str(row.get('Operation type', '')).strip()
        if not operation_type:
            operation_type = safe_str(row.get('operation_type', '')).strip()

        part_no = safe_str(row.get('Part No', '')).strip()
        if not part_no:
            part_no = safe_str(row.get('part_no', '')).strip()

        description = safe_str(row.get('Description', ''))
        if not description:
            description = safe_str(row.get('description', ''))

        # 处理日期 - 确保是 datetime 对象
        date_value = row.get('Date') or row.get('date')
        operation_date = safe_datetime(date_value) or datetime.now()

        # 处理数量 - 确保是整数
        quantity = safe_int(row.get('Qty', 0)) or safe_int(row.get('quantity', 0))

        # 自动调整数量符号
        if 'stock out' in operation_type.lower() and quantity > 0:
            quantity = -quantity
        elif 'stock in' in operation_type.lower() and quantity < 0:
            quantity = abs(quantity)

        operation_data = {
            'operation_type': operation_type,
            'operation_date': operation_date,
            'supplier_recipient': safe_str(row.get('Supplier or Recipients', '')) or safe_str(
                row.get('supplier_recipient', '')),
            'location': safe_str(row.get('Location', '')) or safe_str(row.get('location', '')),
            'part_no': part_no,
            'description': description,
            'part_type': safe_str(row.get('Type', '')) or safe_str(row.get('part_type', '')),
            'product_model': safe_str(row.get('Product Model', '')) or safe_str(row.get('product_model', '')),
            'quantity': quantity,
            'work_center': safe_str(row.get('Work center', '')) or safe_str(row.get('work_center', ''))
        }

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

    def clean_operations_dataframe_complete(df):
        """清理操作记录DataFrame - 彻底修复版本"""
        df = df.copy()

        # 移除全空行
        df = df.dropna(how='all').reset_index(drop=True)

        # 列名映射
        column_mapping = {
            'Operation type': 'operation_type',
            'Date': 'date',
            'Supplier or Recipients': 'supplier_recipient',
            'Location': 'location',
            'Part No': 'part_no',
            'Description': 'description',
            'Type': 'part_type',
            'Product Model': 'product_model',
            'Qty': 'quantity',
            'Work center': 'work_center'
        }

        # 重命名列
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df[new_col] = df[old_col]

        # 使用apply处理所有文本字段
        text_columns = ['operation_type', 'supplier_recipient', 'location', 'part_no', 'description', 'part_type',
                        'product_model', 'work_center']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: safe_str(x).strip() if pd.notna(x) else '')

        # 处理数字字段
        if 'quantity' in df.columns:
            df['quantity'] = df['quantity'].apply(lambda x: safe_int(x) if pd.notna(x) else 0)

        # 处理日期字段
        if 'date' in df.columns:
            df['date'] = df['date'].apply(lambda x: safe_datetime(x) if pd.notna(x) else datetime.now())

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
        """安全转换为日期时间 - 修复版本"""
        if value is None or value == '' or (isinstance(value, float) and np.isnan(value)):
            return default

        try:
            if isinstance(value, datetime):
                return value

            if isinstance(value, str):
                # 移除可能的空格和特殊字符
                value = value.strip()

                # 尝试常见的日期格式
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M',
                    '%Y-%m-%d',
                    '%Y/%m/%d %H:%M:%S',
                    '%Y/%m/%d %H:%M',
                    '%Y/%m/%d',
                    '%d/%m/%Y %H:%M:%S',
                    '%d/%m/%Y %H:%M',
                    '%d/%m/%Y',
                    '%m/%d/%Y %H:%M:%S',
                    '%m/%d/%Y %H:%M',
                    '%m/%d/%Y'
                ]

                for fmt in formats:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue

            # 如果以上都不行，使用 pandas 转换
            return pd.to_datetime(value)

        except Exception as e:
            current_app.logger.warning(f"日期转换失败: {value}, 错误: {str(e)}")
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
                'errors': result.get('errors', []),
                'import_summary': result.get('import_summary', {})
            }

            report_file = os.path.join('import_logs', f"{import_id}_report.json")
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            current_app.logger.error(f"保存导入报告时出错: {str(e)}")

    # =============================================================================
    # 调试函数
    # =============================================================================

    @app.route('/debug/import_fix')
    def debug_import_fix():
        """紧急导入修复 - 直接插入测试数据"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 先清空表（仅用于测试）
                conn.execute('DELETE FROM operation_records')

                # 插入一些测试数据
                import datetime as dt
                test_data = [
                    ('Stock in', dt.datetime.now(), '供应商A', 'A-01-01', 'PART-001', '测试轴承', '机械',
                     '6205ZZ', 100, '生产线A'),
                    ('Stock out', dt.datetime.now(), '部门B', 'B-02-01', 'PART-002', '测试螺丝', '电子', 'M6x20',
                     -50, '维修部'),
                    ('Stock in', dt.datetime.now(), '供应商C', 'C-03-01', 'PART-003', '测试密封圈', '机械',
                     '25x5x3', 200, '生产线B'),
                ]

                for data in test_data:
                    conn.execute('''
                        INSERT INTO operation_records 
                        (operation_type, operation_date, supplier_recipient, location, part_no, 
                         description, part_type, product_model, quantity, work_center)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', data)

                conn.commit()

                # 验证插入
                count = conn.execute('SELECT COUNT(*) FROM operation_records').fetchone()[0]
                records = conn.execute('SELECT * FROM operation_records ORDER BY id DESC LIMIT 5').fetchall()

                result_html = f"""
                <h1>紧急导入修复完成</h1>
                <p>成功插入 {count} 条测试记录</p>
                <h2>最近5条记录：</h2>
                <table border="1">
                    <tr>
                        <th>ID</th><th>操作类型</th><th>备件编号</th><th>描述</th><th>数量</th>
                    </tr>
                """

                for record in records:
                    result_html += f"""
                    <tr>
                        <td>{record[0]}</td>
                        <td>{record[1]}</td>
                        <td>{record[5]}</td>
                        <td>{record[6]}</td>
                        <td>{record[9]}</td>
                    </tr>
                    """

                result_html += "</table>"
                result_html += f'<p><a href="{url_for("operation_records")}">查看操作记录页面</a></p>'

                return result_html

        except Exception as e:
            return f"修复失败: {str(e)}", 500

    @app.route('/debug/simple_import')
    def debug_simple_import():
        """简化导入测试 - 处理少量数据"""
        try:
            # 创建一个简单的测试数据 DataFrame
            test_data = {
                'Operation type': ['Stock in', 'Stock out', 'Stock in'],
                'Date': ['2024-01-01', '2024-01-02', '2024-01-03'],
                'Supplier or Recipients': ['供应商A', '部门B', '供应商C'],
                'Location': ['A-01-01', 'B-02-01', 'C-03-01'],
                'Part No': ['TEST-001', 'TEST-002', 'TEST-003'],
                'Description': ['测试轴承', '测试螺丝', '测试密封圈'],
                'Type': ['机械', '电子', '机械'],
                'Product Model': ['6205ZZ', 'M6x20', '25x5x3'],
                'Qty': [100, -50, 200],
                'Work center': ['生产线A', '维修部', '生产线B']
            }

            df = pd.DataFrame(test_data)

            # 使用修复后的导入函数
            result = process_operations_import_simple(df, 'debug_test')

            return f"""
            <h1>简化导入测试结果</h1>
            <pre>{result}</pre>
            <p><a href="{url_for('operation_records')}">查看操作记录页面</a></p>
            <p><a href="{url_for('debug_database')}">查看数据库状态</a></p>
            """

        except Exception as e:
            return f"测试失败: {str(e)}", 500

    def process_operations_import_simple(df, import_id):
        """简化版操作记录导入 - 用于测试"""
        imported_count = 0
        errors = []

        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                for index, row in df.iterrows():
                    try:
                        # 直接构建操作记录数据
                        operation_data = (
                            str(row['Operation type']),
                            datetime.strptime(row['Date'], '%Y-%m-%d'),
                            str(row['Supplier or Recipients']),
                            str(row['Location']),
                            str(row['Part No']),
                            str(row['Description']),
                            str(row['Type']),
                            str(row['Product Model']),
                            int(row['Qty']),
                            str(row['Work center'])
                        )

                        # 插入记录
                        conn.execute('''
                            INSERT INTO operation_records 
                            (operation_type, operation_date, supplier_recipient, location, part_no, 
                             description, part_type, product_model, quantity, work_center)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', operation_data)

                        imported_count += 1

                    except Exception as e:
                        errors.append(f"第 {index + 1} 行失败: {str(e)}")

                conn.commit()

        except Exception as e:
            errors.append(f"数据库操作失败: {str(e)}")

        result = {
            'success': imported_count > 0,
            'imported_count': imported_count,
            'error_count': len(errors),
            'errors': errors
        }

        return result

    def batch_update_stock_after_import(affected_parts, conn):
        """批量更新库存 - 优化性能版本"""
        updated_count = 0
        batch_size = 50  # 减少批量大小避免锁定

        current_app.logger.info(f"开始批量更新 {len(affected_parts)} 个备件的库存")

        for i in range(0, len(affected_parts), batch_size):
            batch = list(affected_parts)[i:i + batch_size]
            current_app.logger.info(
                f"处理库存更新批次 {i // batch_size + 1}/{(len(affected_parts) + batch_size - 1) // batch_size}")

            for part_no in batch:
                try:
                    # 重新计算库存
                    new_stock = calculate_stock_from_operations_with_connection_local(part_no, conn)

                    # 更新备件库存
                    cursor = conn.execute('''
                        UPDATE spare_parts 
                        SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                        WHERE part_no = ?
                    ''', (new_stock, part_no))

                    if cursor.rowcount > 0:
                        updated_count += 1
                        if updated_count % 100 == 0:
                            current_app.logger.info(f"已更新 {updated_count} 个备件库存")

                except Exception as e:
                    current_app.logger.error(f"批量更新备件 {part_no} 库存失败: {str(e)}")
                    # 继续处理其他备件

        return updated_count

    def recalculate_all_stock_after_import():
        """导入后重新计算所有库存"""
        try:
            db_manager = DatabaseManager()
            with db_manager.get_connection() as conn:
                # 获取所有备件
                parts = conn.execute('SELECT id, part_no FROM spare_parts').fetchall()
                updated_count = 0

                for part in parts:
                    part_id = part[0]
                    part_no = part[1]

                    # 重新计算库存
                    new_stock = calculate_stock_from_operations_with_connection_local(part_no, conn)

                    # 更新库存
                    cursor = conn.execute('''
                        UPDATE spare_parts 
                        SET current_stock = ?, updated_date = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    ''', (new_stock, part_id))

                    if cursor.rowcount > 0:
                        updated_count += 1

                conn.commit()
                current_app.logger.info(f"导入后库存重算完成: 更新了 {updated_count} 个备件")
                return updated_count

        except Exception as e:
            current_app.logger.error(f"导入后库存重算失败: {str(e)}")
            return 0