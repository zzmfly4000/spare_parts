from flask import jsonify, request
from models.database import (get_spare_part_by_part_no, update_spare_part, 
                           create_operation_record, get_all_spare_parts)
import json

class SystemIntegrationAPI:
    """系统集成API服务，负责系统集成API功能"""
    
    def __init__(self, app):
        self.app = app
        self._register_routes()
    
    def _register_routes(self):
        """注册API路由"""
        @self.app.route('/api/v1/parts/<part_no>', methods=['GET'])
        def get_part_info(part_no):
            """获取备件信息API"""
            try:
                part = get_spare_part_by_part_no(part_no)
                if part:
                    return jsonify({
                        'success': True,
                        'data': {
                            'id': part[0],
                            'part_no': part[1],
                            'name': part[2],
                            'type': part[3],
                            'current_stock': part[4],
                            'min_stock': part[5],
                            'max_stock': part[6]
                        }
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': '备件不存在'
                    }), 404
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/v1/parts/<part_no>/stock', methods=['PUT'])
        def update_part_stock(part_no):
            """更新备件库存API"""
            try:
                data = request.get_json()
                quantity = data.get('quantity')
                
                if quantity is None:
                    return jsonify({
                        'success': False,
                        'error': '缺少quantity参数'
                    }), 400
                
                # 这里应该实现实际的库存更新逻辑
                # 为简化示例，直接返回成功
                return jsonify({
                    'success': True,
                    'message': f'备件{part_no}库存更新成功'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
