import numpy as np
from typing import Dict, List
from datetime import datetime, timedelta
from models.database import DatabaseManager

class IntelligentRecommendationEngine:
    """智能推荐引擎，负责智能推荐和预测分析功能"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def predict_part_demand(self, part_id: int, days: int = 30) -> Dict:
        """预测备件需求"""
        # 获取历史消耗数据
        consumption_history = self._get_consumption_history(part_id, days)
        
        # 简单的线性回归预测
        if len(consumption_history) > 1:
            predicted_demand = self._linear_regression_predict(consumption_history)
        else:
            predicted_demand = sum(consumption_history) / len(consumption_history) if consumption_history else 0
        
        return {
            'part_id': part_id,
            'predicted_demand': predicted_demand,
            'confidence': 0.8 if len(consumption_history) > 5 else 0.5
        }
    
    def _get_consumption_history(self, part_id: int, days: int) -> List[int]:
        """获取备件消耗历史"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.execute('''
                SELECT ABS(quantity) as consumption
                FROM operation_records 
                WHERE part_id = ? AND operation_type = 'Stock out'
                AND operation_date >= date('now', '-{} days')
                ORDER BY operation_date
            '''.format(days), (part_id,))
            return [row[0] for row in cursor.fetchall()]
    
    def _linear_regression_predict(self, data: List[int]) -> float:
        """线性回归预测"""
        x = np.arange(len(data))
        y = np.array(data)
        
        # 简单线性回归
        slope, intercept = np.polyfit(x, y, 1)
        next_value = slope * len(data) + intercept
        return max(0, next_value)  # 确保预测值非负
