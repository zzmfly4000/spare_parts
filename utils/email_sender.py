import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import logging


class EmailSender:
    """邮件发送服务"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.smtp_server = "smtp.example.com"
        self.smtp_port = 587
        self.sender_email = "noreply@example.com"
        self.sender_password = "password"

    def send_low_stock_alert(self, low_stock_parts):
        """发送低库存报警邮件"""
        try:
            # 构建邮件内容
            subject = "设备备件管理系统 - 低库存报警"

            # 构建HTML内容
            html_content = """
            <html>
            <head>
                <style>
                    body { font-family: Arial, sans-serif; }
                    .alert { color: #d9534f; font-weight: bold; }
                    table { border-collapse: collapse; width: 100%; }
                    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                    th { background-color: #f2f2f2; }
                    .critical { background-color: #f8d7da; }
                </style>
            </head>
            <body>
                <h2>低库存报警</h2>
                <p>以下备件库存已达到或低于最低库存阈值：</p>
                <table>
                    <tr>
                        <th>备件编号</th>
                        <th>备件名称</th>
                        <th>当前库存</th>
                        <th>最低库存</th>
                        <th>库位</th>
                        <th>状态</th>
                    </tr>
            """

            for part in low_stock_parts:
                status = "缺货" if part[4] == 0 else "低库存"
                row_class = "critical" if part[4] == 0 else ""

                html_content += f"""
                    <tr class="{row_class}">
                        <td>{part[1]}</td>
                        <td>{part[2]}</td>
                        <td>{part[4]}</td>
                        <td>{part[5]}</td>
                        <td>{part[11] if len(part) > 11 else 'N/A'}</td>
                        <td class="alert">{status}</td>
                    </tr>
                """

            html_content += """
                </table>
                <br>
                <p>请及时处理！</p>
                <p><em>设备备件管理系统</em></p>
            </body>
            </html>
            """

            # 这里应该实现实际的邮件发送逻辑
            # 为简化示例，仅记录日志
            self.logger.info(f"低库存报警邮件已准备，共{len(low_stock_parts)}个备件需要关注")

            return True
        except Exception as e:
            self.logger.error(f"发送低库存报警邮件失败: {str(e)}")
            return False

    def send_system_alert(self, subject, message):
        """发送系统告警邮件"""
        try:
            self.logger.info(f"系统告警邮件: {subject} - {message}")
            return True
        except Exception as e:
            self.logger.error(f"发送系统告警邮件失败: {str(e)}")
            return False