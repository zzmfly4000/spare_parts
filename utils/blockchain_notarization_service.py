import hashlib
import json
import time
from typing import Dict, Any

class BlockchainNotarizationService:
    """区块链存证服务，负责区块链数据存证功能"""
    
    def __init__(self):
        self.blockchain_nodes = []
        self.local_storage = {}
    
    def calculate_data_hash(self, data: Dict[str, Any]) -> str:
        """计算数据哈希值"""
        # 将数据转换为字符串并排序以确保一致性
        data_string = json.dumps(data, sort_keys=True, separators=(',', ':'))
        # 计算SHA256哈希值
        return hashlib.sha256(data_string.encode('utf-8')).hexdigest()
    
    def notarize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """对数据进行区块链存证"""
        # 计算数据哈希
        data_hash = self.calculate_data_hash(data)
        
        # 创建存证记录
        notarization_record = {
            'data_hash': data_hash,
            'timestamp': time.time(),
            'data_summary': self._generate_data_summary(data)
        }
        
        # 这里应该实现实际的上链逻辑
        # 为简化示例，存储在本地
        self.local_storage[data_hash] = notarization_record
        
        return {
            'success': True,
            'hash': data_hash,
            'notarization_id': f"ntf_{int(time.time())}",
            'timestamp': notarization_record['timestamp']
        }
    
    def _generate_data_summary(self, data: Dict[str, Any]) -> str:
        """生成数据摘要"""
        # 提取关键字段生成摘要
        summary_fields = ['part_no', 'name', 'operation_type', 'quantity']
        summary_parts = []
        for field in summary_fields:
            if field in data:
                summary_parts.append(f"{field}: {data[field]}")
        return "; ".join(summary_parts) if summary_parts else "No key fields"
