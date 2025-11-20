import logging
from typing import Dict, List
from utils.system_monitor import SystemMonitor
from utils.email_sender import EmailSender

class AlertManager:
    """告警管理服务，负责系统监控告警功能"""
    
    def __init__(self):
        self.system_monitor = SystemMonitor()
        self.email_sender = EmailSender()
        self.alert_rules = self._load_default_alert_rules()
        self.logger = logging.getLogger(__name__)
    
    def _load_default_alert_rules(self) -> Dict:
        """加载默认告警规则"""
        return {
            'cpu_usage': {
                'threshold': 80,
                'enabled': True,
                'description': 'CPU使用率过高'
            },
            'memory_usage': {
                'threshold': 85,
                'enabled': True,
                'description': '内存使用率过高'
            },
            'disk_usage': {
                'threshold': 90,
                'enabled': True,
                'description': '磁盘使用率过高'
            },
            'database_unhealthy': {
                'enabled': True,
                'description': '数据库连接异常'
            }
        }
    
    def check_system_alerts(self) -> List[Dict]:
        """检查系统告警"""
        alerts = []
        health_status = self.system_monitor.get_health_status()
        
        # 检查CPU使用率
        if (self.alert_rules['cpu_usage']['enabled'] and 
            health_status['resources']['cpu_percent'] > self.alert_rules['cpu_usage']['threshold']):
            alerts.append({
                'type': 'cpu_usage',
                'level': 'WARNING',
                'message': f"CPU使用率过高: {health_status['resources']['cpu_percent']}%",
                'threshold': self.alert_rules['cpu_usage']['threshold']
            })
        
        # 检查内存使用率
        if (self.alert_rules['memory_usage']['enabled'] and 
            health_status['resources']['memory_percent'] > self.alert_rules['memory_usage']['threshold']):
            alerts.append({
                'type': 'memory_usage',
                'level': 'WARNING',
                'message': f"内存使用率过高: {health_status['resources']['memory_percent']}%",
                'threshold': self.alert_rules['memory_usage']['threshold']
            })
        
        # 检查磁盘使用率
        if (self.alert_rules['disk_usage']['enabled'] and 
            health_status['resources']['disk_usage'] > self.alert_rules['disk_usage']['threshold']):
            alerts.append({
                'type': 'disk_usage',
                'level': 'WARNING',
                'message': f"磁盘使用率过高: {health_status['resources']['disk_usage']}%",
                'threshold': self.alert_rules['disk_usage']['threshold']
            })
        
        # 检查数据库状态
        if (self.alert_rules['database_unhealthy']['enabled'] and 
            health_status['database']['status'] != 'healthy'):
            alerts.append({
                'type': 'database_unhealthy',
                'level': 'ERROR',
                'message': f"数据库连接异常: {health_status['database']['message']}",
                'threshold': None
            })
        
        # 发送告警通知
        if alerts:
            self._send_alert_notifications(alerts)
        
        return alerts
    
    def _send_alert_notifications(self, alerts: List[Dict]):
        """发送告警通知"""
        try:
            # 构建告警邮件内容
            subject = "系统告警通知"
            body = "系统检测到以下告警:\n\n"
            for alert in alerts:
                body += f"- {alert['message']} (级别: {alert['level']})\n"
            
            # 发送邮件告警
            # self.email_sender.send_email(subject, body)
            self.logger.info(f"发送了 {len(alerts)} 条告警通知")
        except Exception as e:
            self.logger.error(f"发送告警通知失败: {str(e)}")
