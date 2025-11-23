def sync_all_operations():
    """同步所有操作记录到库存"""
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
            cursor = conn.execute('SELECT id, part_no FROM spare_parts')
            parts = cursor.fetchall()
            
            for part in parts:
                part_id = part[0]
                part_no = part[1]
                
                try:
                    # 计算当前库存
                    current_stock = calculate_stock_from_operations(part_no)
                    
                    # 更新库存
                    update_result = update_stock_for_part(part_id, current_stock)
                    
                    if update_result > 0:
                        sync_result['stock_updated'] += 1
                        
                except Exception as e:
                    sync_result['errors'].append(f"备件 {part_no} 同步失败: {str(e)}")
            
            # 统计操作类型
            inbound_count = conn.execute(
                "SELECT COUNT(*) FROM operation_records WHERE operation_type LIKE '%Stock in%'"
            ).fetchone()[0]
            
            outbound_count = conn.execute(
                "SELECT COUNT(*) FROM operation_records WHERE operation_type = 'Stock out'"
            ).fetchone()[0]
            
            sync_result['inbound_synced'] = inbound_count
            sync_result['outbound_synced'] = outbound_count
            
    except Exception as e:
        sync_result['errors'].append(f"同步过程失败: {str(e)}")
    
    return sync_result