import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta
from models.database import DatabaseManager

class DataVisualization:
    """数据可视化服务，负责数据可视化展示功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        # 设置matplotlib中文字体支持
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
    
    def generate_inventory_trend_chart(self, part_no, days=30):
        """生成备件库存趋势图表"""
        # 获取库存数据
        dates = []
        stock_levels = []
        
        # 模拟数据生成
        for i in range(days):
            date = datetime.now() - timedelta(days=days-i)
            dates.append(date.strftime('%m-%d'))
            # 模拟库存数据
            stock_levels.append(100 - i*2 if i < 20 else 60)
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        plt.plot(dates, stock_levels, marker='o', linewidth=2)
        plt.title(f'备件 {part_no} 库存趋势图')
        plt.xlabel('日期')
        plt.ylabel('库存数量')
        plt.xticks(rotation=45)
        plt.grid(True)
        
        # 将图表转换为base64编码
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        plt.close()
        
        return img_base64
    
    def generate_location_usage_chart(self):
        """生成库位使用率可视化图表"""
        # 获取库位数据
        locations = []
        usage_rates = []
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT location_code, 
                       CASE WHEN capacity > 0 THEN CAST(part_count AS FLOAT) / capacity * 100 ELSE 0 END as usage_rate
                FROM locations 
                WHERE capacity > 0
                ORDER BY usage_rate DESC
                LIMIT 10
            ''')
            results = cursor.fetchall()
            
            for row in results:
                locations.append(row[0])
                usage_rates.append(row[1])
        
        # 创建柱状图
        plt.figure(figsize=(12, 6))
        bars = plt.bar(locations, usage_rates, color='skyblue')
        plt.title('库位使用率 Top 10')
        plt.xlabel('库位编码')
        plt.ylabel('使用率 (%)')
        plt.xticks(rotation=45)
        
        # 在柱状图上添加数值标签
        for bar, rate in zip(bars, usage_rates):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{rate:.1f}%', ha='center', va='bottom')
        
        # 将图表转换为base64编码
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        plt.close()
        
        return img_base64
