from models.database import get_low_stock_parts
from utils.email_sender import EmailSender
import logging

class StockAlertService:
    """库存报警服务，负责低库存检查和报警功能"""
    
    def __init__(self):
        self.email_sender = EmailSender()
        self.logger = logging.getLogger(__name__)
    
    def check_low_stock_and_alert(self):
        """检查低库存并发送报警邮件"""
        try:
            # 获取低库存备件列表
            low_stock_parts = get_low_stock_parts()
            
            if low_stock_parts:
                # 发送报警邮件
                self.email_sender.send_low_stock_alert(low_stock_parts)
                self.logger.info(f"发送了低库存报警，共{len(low_stock_parts)}个备件")
                return True
            else:
                self.logger.info("没有发现低库存备件")
                return False
        except Exception as e:
            self.logger.error(f"低库存检查失败: {str(e)}")
            return False
    
    def get_low_stock_statistics(self):
        """获取低库存统计信息"""
        try:
            low_stock_parts = get_low_stock_parts()
            total_low_stock = len(low_stock_parts)
            
            # 统计缺货备件数量
            out_of_stock_count = sum(1 for part in low_stock_parts if part[4] == 0)  # current_stock为0
            
            return {
                'total_low_stock': total_low_stock,
                'out_of_stock_count': out_of_stock_count
            }
        except Exception as e:
            self.logger.error(f"获取低库存统计信息失败: {str(e)}")
            return {}
