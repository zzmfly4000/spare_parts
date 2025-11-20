from flask import render_template, request, jsonify
from utils.api_documentation import APIDocumentation

def setup_api_test_routes(app, api_docs):
    """设置API测试路由"""
    
    @app.route('/api/docs')
    def api_documentation():
        """API文档页面"""
        docs = api_docs.generate_api_docs()
        return render_template('api_documentation.html', docs=docs)
    
    @app.route('/api/test', methods=['POST'])
    def test_api_endpoint():
        """测试API端点"""
        try:
            # 获取测试参数
            endpoint = request.form.get('endpoint')
            method = request.form.get('method', 'GET')
            params = request.form.get('params', '{}')
            
            # 这里应该实现实际的API调用逻辑
            # 为简化示例，返回模拟结果
            result = {
                'status': 'success',
                'data': {'message': 'API调用成功'},
                'execution_time': '0.125s'
            }
            
            return jsonify(result)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
