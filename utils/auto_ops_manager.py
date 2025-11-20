from apscheduler.schedulers.background import BackgroundScheduler
from utils.backup_manager import BackupManager
from utils.system_monitor import SystemMonitor
from utils.alert_manager import AlertManager
import logging

class AutoOpsManager:
    """自动化运维管理服务，负责系统自动化运维功能"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.backup_manager = BackupManager()
        self.system_monitor = SystemMonitor()
        self.alert_manager = AlertManager()
        self.logger = logging.getLogger(__name__)
    
    def start_scheduler(self):
        """启动定时任务调度器"""
        # 添加自动备份任务（每天凌晨2点执行）
        self.scheduler.add_job(
            self._perform_auto_backup,
            'cron',
            hour=2,
            minute=0
        )
        
        # 添加系统监控任务（每30分钟执行一次）
        self.scheduler.add_job(
            self._perform_system_monitoring,
            'interval',
            minutes=30
        )
        
        self.scheduler.start()
        self.logger.info("自动化运维调度器已启动")
    
    def _perform_auto_backup(self):
        """执行自动备份任务"""
        try:
            result = self.backup_manager.backup_database()
            if result['success']:
                self.logger.info(f"自动备份成功: {result['backup_path']}")
            else:
                self.logger.error(f"自动备份失败: {result.get('error', '未知错误')}")
        except Exception as e:
            self.logger.error(f"自动备份异常: {str(e)}")
    
    def _perform_system_monitoring(self):
        """执行系统监控任务"""
        try:
            alerts = self.alert_manager.check_system_alerts()
            if alerts:
                self.logger.warning(f"系统监控发现 {len(alerts)} 个告警")
            else:
                self.logger.info("系统监控检查完成，未发现异常")
        except Exception as e:
            self.logger.error(f"系统监控异常: {str(e)}")
