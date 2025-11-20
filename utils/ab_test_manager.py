import random
from typing import Dict, List

class ABTestManager:
    """A/B测试管理服务，负责A/B测试和灰度发布功能"""
    
    def __init__(self):
        self.experiments = {}
        self.user_assignments = {}
    
    def create_experiment(self, experiment_name: str, variants: List[str], traffic_ratio: Dict[str, float]) -> bool:
        """创建A/B测试实验"""
        self.experiments[experiment_name] = {
            'variants': variants,
            'traffic_ratio': traffic_ratio,
            'created_at': time.time()
        }
        return True
    
    def assign_user_to_variant(self, user_id: str, experiment_name: str) -> str:
        """将用户分配到实验变体"""
        # 检查用户是否已分配
        if user_id in self.user_assignments and experiment_name in self.user_assignments[user_id]:
            return self.user_assignments[user_id][experiment_name]
        
        # 获取实验配置
        experiment = self.experiments.get(experiment_name)
        if not experiment:
            return None
        
        # 根据流量比例分配用户到变体
        rand_value = random.random()
        cumulative_ratio = 0
        
        for variant, ratio in experiment['traffic_ratio'].items():
            cumulative_ratio += ratio
            if rand_value <= cumulative_ratio:
                # 记录用户分配
                if user_id not in self.user_assignments:
                    self.user_assignments[user_id] = {}
                self.user_assignments[user_id][experiment_name] = variant
                return variant
        
        # 默认返回第一个变体
        default_variant = experiment['variants'][0]
        if user_id not in self.user_assignments:
            self.user_assignments[user_id] = {}
        self.user_assignments[user_id][experiment_name] = default_variant
        return default_variant
