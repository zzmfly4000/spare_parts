import hashlib
import secrets
import re
from functools import wraps
from flask import session, abort

class SecurityManager:
    """安全管理服务，负责系统安全加固功能"""
    
    def __init__(self):
        self.min_password_length = 8
    
    def hash_password(self, password: str) -> str:
        """密码哈希处理"""
        # 使用SHA-256进行密码哈希
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.hash_password(password) == hashed_password
    
    def check_password_strength(self, password: str) -> Dict:
        """检查密码强度"""
        errors = []
        
        if len(password) < self.min_password_length:
            errors.append(f"密码长度至少{self.min_password_length}位")
        
        if not re.search(r"[A-Z]", password):
            errors.append("密码必须包含大写字母")
        
        if not re.search(r"[a-z]", password):
            errors.append("密码必须包含小写字母")
        
        if not re.search(r"\d", password):
            errors.append("密码必须包含数字")
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            errors.append("密码必须包含特殊字符")
        
        return {
            'is_strong': len(errors) == 0,
            'errors': errors
        }
    
    def generate_secure_token(self) -> str:
        """生成安全令牌"""
        return secrets.token_hex(32)
