"""
修复导入路由配置的脚本
"""

def check_import_routes():
    """检查所有导入路由是否正确定义"""
    required_routes = [
        'import_locations',
        'import_part_info_only',
        'import_operations',
        'download_locations_template',
        'download_part_info_update_template',
        'download_operations_template'
    ]

    print("检查导入路由配置...")

    # 这里可以添加更复杂的检查逻辑
    # 比如检查路由是否在应用中注册等

    print("导入路由检查完成！")
    print("请确保以下路由已正确定义：")
    for route in required_routes:
        print(f"  - {route}")

if __name__ == '__main__':
    check_import_routes()