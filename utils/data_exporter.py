import pandas as pd
import io
from datetime import datetime
from models.database import DatabaseManager

class DataExporter:
    """数据导出服务，负责数据导出和报表生成功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def export_parts_to_excel(self):
        """导出备件信息到Excel"""
        try:
            with self.db_manager.get_connection() as conn:
                # 查询备件数据
                cursor = conn.execute('''
                    SELECT part_no, name, type, current_stock, min_stock, max_stock,
                           key_part, lt_weeks, unit_price, unit, location, supplier, description
                    FROM spare_parts
                ''')
                rows = cursor.fetchall()
                
                # 创建DataFrame
                df = pd.DataFrame(rows, columns=[
                    '备件编号', '备件名称', '类型', '当前库存', '最低库存', '最高库存',
                    '关键备件', '交货期(周)', '单价', '单位', '库位', '供应商', '描述'
                ])
                
                # 将DataFrame保存到内存中的Excel文件
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='备件信息', index=False)
                
                output.seek(0)
                return output
        except Exception as e:
            raise Exception(f"导出备件信息失败: {str(e)}")
    
    def export_operations_to_csv(self, start_date=None, end_date=None):
        """导出操作记录到CSV"""
        try:
            with self.db_manager.get_connection() as conn:
                # 构建查询条件
                query = "SELECT * FROM operation_records"
                params = []
                
                if start_date and end_date:
                    query += " WHERE operation_date BETWEEN ? AND ?"
                    params.extend([start_date, end_date])
                
                query += " ORDER BY operation_date DESC"
                
                # 查询数据
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                # 创建DataFrame
                df = pd.DataFrame(rows, columns=[
                    'ID', '操作类型', '操作时间', '供应商/接收方', '库位', '备件编号',
                    '描述', '备件类型', '数量', '工作中心', '创建时间'
                ])
                
                # 将DataFrame保存到内存中的CSV文件
                output = io.StringIO()
                df.to_csv(output, index=False)
                return output.getvalue()
        except Exception as e:
            raise Exception(f"导出操作记录失败: {str(e)}")
