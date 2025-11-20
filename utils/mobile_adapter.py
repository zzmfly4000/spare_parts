class MobileAdapter:
    """移动端适配服务，负责移动端适配功能"""
    
    def __init__(self):
        self.breakpoints = {
            'mobile': 768,
            'tablet': 1024,
            'desktop': 1200
        }
    
    def is_mobile_device(self, user_agent):
        """检测是否为移动设备"""
        mobile_keywords = ['Mobile', 'Android', 'iPhone', 'iPad', 'Windows Phone']
        return any(keyword in user_agent for keyword in mobile_keywords)
    
    def get_device_type(self, screen_width):
        """根据屏幕宽度判断设备类型"""
        if screen_width <= self.breakpoints['mobile']:
            return 'mobile'
        elif screen_width <= self.breakpoints['tablet']:
            return 'tablet'
        else:
            return 'desktop'
    
    def generate_responsive_css(self):
        """生成响应式CSS样式"""
        css = """
        /* 移动端适配样式 */
        @media (max-width: 768px) {
            .container {
                padding: 10px;
                width: 100%;
            }
            
            .sidebar {
                display: none;
            }
            
            .main-content {
                width: 100%;
                margin: 0;
            }
            
            .nav-menu {
                flex-direction: column;
            }
            
            .btn {
                width: 100%;
                margin-bottom: 10px;
            }
        }
        
        /* 平板适配样式 */
        @media (min-width: 769px) and (max-width: 1024px) {
            .container {
                padding: 15px;
            }
            
            .sidebar {
                width: 200px;
            }
        }
        """
        return css
