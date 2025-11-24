def sync_all_operations():
    """同步所有操作记录到库存 - 增强修复版本"""
    from models.database import DatabaseManager, calculate_stock_from_operations, update_stock_for_part

    db_manager = DatabaseManager()

    sync_result = {
        'inbound_synced': 0,
        'outbound_synced': 0,
        'stock_updated': 0,
        'errors': []
    }

    try:
        with db_manager.get_connection() as conn:
            # 获取所有备件
            cursor = conn.execute('SELECT id, part_no, current_stock FROM spare_parts')
            parts = cursor.fetchall()

            for part in parts:
                part_id = part[0]
                part_no = part[1]
                old_stock = part[2]

                try:
                    # 计算当前库存 - 使用修复后的函数
                    current_stock = calculate_stock_from_operations(part_no)

                    # 只有在库存发生变化时才更新
                    if current_stock != old_stock:
                        # 更新库存
                        update_result = update_stock_for_part(part_id, current_stock)

                        if update_result > 0:
                            sync_result['stock_updated'] += 1
                            current_app.logger.info(f"备件 {part_no} 库存同步: {old_stock} -> {current_stock}")
                        else:
                            current_app.logger.warning(f"备件 {part_no} 库存同步失败")
                    else:
                        current_app.logger.debug(f"备件 {part_no} 库存未变化: {current_stock}")

                except Exception as e:
                    error_msg = f"备件 {part_no} 同步失败: {str(e)}"
                    sync_result['errors'].append(error_msg)
                    current_app.logger.error(error_msg)

            # 统计操作类型
            new_in_count = conn.execute(
                "SELECT COUNT(*) FROM operation_records WHERE operation_type = 'Stock in'"
            ).fetchone()[0]

            disassemble_count = conn.execute(
                "SELECT COUNT(*) FROM operation_records WHERE operation_type = 'Stock in - disassemble'"
            ).fetchone()[0]

            return_count = conn.execute(
                "SELECT COUNT(*) FROM operation_records WHERE operation_type = 'Stock in - return'"
            ).fetchone()[0]

            outbound_count = conn.execute(
                "SELECT COUNT(*) FROM operation_records WHERE operation_type = 'Stock out'"
            ).fetchone()[0]

            sync_result['new_in_synced'] = new_in_count
            sync_result['disassemble_synced'] = disassemble_count
            sync_result['return_synced'] = return_count
            sync_result['outbound_synced'] = outbound_count

            current_app.logger.info(f"库存同步完成: 更新了 {sync_result['stock_updated']} 个备件库存")

    except Exception as e:
        error_msg = f"同步过程失败: {str(e)}"
        sync_result['errors'].append(error_msg)
        current_app.logger.error(error_msg)

    return sync_result


def force_recalculate_all_stock():
    """强制重新计算所有备件库存"""
    from models.database import recalculate_all_stock

    try:
        updated_count = recalculate_all_stock()
        current_app.logger.info(f"强制重新计算完成: 更新了 {updated_count} 个备件库存")
        return {
            'success': True,
            'updated_count': updated_count,
            'message': f'成功重新计算 {updated_count} 个备件的库存'
        }
    except Exception as e:
        current_app.logger.error(f"强制重新计算失败: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': f'重新计算库存失败: {str(e)}'
        }