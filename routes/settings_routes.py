from flask import render_template, request, redirect, url_for, flash
import json

def setup_settings_routes(app):
    """设置系统设置路由"""
    
    @app.route('/settings', methods=['GET', 'POST'])
    def system_settings():
        """系统设置页面"""
        if request.method == 'POST':
            # 获取表单数据
            settings_data = {
                'system_name': request.form.get('system_name', ''),
                'company_name': request.form.get('company_name', ''),
                'mail_server': request.form.get('mail_server', ''),
                'mail_port': request.form.get('mail_port', ''),
                'mail_username': request.form.get('mail_username', ''),
                'mail_password': request.form.get('mail_password', ''),
                'low_stock_threshold': request.form.get('low_stock_threshold', '10')
            }
            
            try:
                # 保存系统设置到数据库或配置文件
                # 这里应该调用实际的设置保存函数
                save_system_settings(settings_data)
                flash('系统设置保存成功', 'success')
                return redirect(url_for('system_settings'))
            except Exception as e:
                flash(f'系统设置保存失败: {str(e)}', 'error')
        
        # 获取当前系统设置
        current_settings = get_system_settings()
        
        return render_template('settings.html', settings=current_settings)
    
    @app.route('/update_email_settings', methods=['POST'])
    def update_email_settings():
        """更新邮件配置"""
        # 获取邮件配置数据
        email_settings = {
            'mail_server': request.form.get('mail_server', ''),
            'mail_port': request.form.get('mail_port', ''),
            'mail_username': request.form.get('mail_username', ''),
            'mail_password': request.form.get('mail_password', ''),
            'mail_use_tls': bool(request.form.get('mail_use_tls', False)),
            'mail_use_ssl': bool(request.form.get('mail_use_ssl', False))
        }
        
        try:
            # 保存邮件配置
            save_email_settings(email_settings)
            flash('邮件配置更新成功', 'success')
        except Exception as e:
            flash(f'邮件配置更新失败: {str(e)}', 'error')
        
        return redirect(url_for('system_settings'))
    
    @app.route('/update_inventory_settings', methods=['POST'])
    def update_inventory_settings():
        """更新库存设置"""
        # 获取库存设置数据
        inventory_settings = {
            'low_stock_threshold': request.form.get('low_stock_threshold', '10'),
            'auto_sync_enabled': bool(request.form.get('auto_sync_enabled', False))
        }
        
        try:
            # 保存库存设置
            save_inventory_settings(inventory_settings)
            flash('库存设置更新成功', 'success')
        except Exception as e:
            flash(f'库存设置更新失败: {str(e)}', 'error')
        
        return redirect(url_for('system_settings'))

def get_system_settings():
    """获取系统设置"""
    # 这里应该从数据库或配置文件中读取设置
    # 为简化示例，返回默认设置
    return {
        'system_name': '设备备件管理系统',
        'company_name': '示例公司',
        'mail_server': 'smtp.example.com',
        'mail_port': '587',
        'mail_username': '',
        'mail_password': '',
        'low_stock_threshold': '10'
    }

def save_system_settings(settings):
    """保存系统设置"""
    # 这里应该将设置保存到数据库或配置文件
    # 为简化示例，直接返回
    pass

def save_email_settings(email_settings):
    """保存邮件配置"""
    # 这里应该将邮件配置保存到数据库或配置文件
    pass

def save_inventory_settings(inventory_settings):
    """保存库存设置"""
    # 这里应该将库存设置保存到数据库或配置文件
    pass
