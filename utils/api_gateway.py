import jwt
import time
from functools import wraps
from flask import request, jsonify

class APIGateway:
    """API网关服务，负责API网关和统一认证功能"""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.routes = {}
    
    def register_route(self, path: str, service_url: str):
        """注册路由映射"""
        self.routes[path] = service_url
    
    def jwt_required(self, f):
        """JWT认证装饰器"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get('Authorization')
            if not token:
                return jsonify({'error': '缺少访问令牌'}), 401
            
            try:
                # 验证JWT令牌
                payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
                request.current_user = payload
            except jwt.ExpiredSignatureError:
                return jsonify({'error': '令牌已过期'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'error': '无效令牌'}), 401
            
            return f(*args, **kwargs)
        return decorated_function
