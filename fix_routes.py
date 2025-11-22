"""
修复模板中路由引用的脚本
运行此脚本来修复所有模板中的路由引用问题
"""

import os
import re


def fix_template_routes():
    """修复模板中的路由引用"""
    template_dir = 'templates'

    # 要修复的文件列表
    template_files = ['base.html', 'index.html']

    # 路由映射 - 将旧路由映射到新路由
    route_mapping = {
        # 导入路由
        r"url_for\('import_parts'\)": "url_for('import_part_info_only')",
        r"url_for\('import_operations_advanced'\)": "url_for('import_operations')",
        r'href="/import_parts"': 'href="/import_part_info_only"',
        r'href="/import_operations_advanced"': 'href="/import_operations"',

        # 导出路由
        r"url_for\('export_data'\)": "url_for('export_parts_advanced')",
        r'href="/export_data"': 'href="/export_parts_advanced"',

        # 其他可能的路由
        r"url_for\('parts_import'\)": "url_for('import_part_info_only')",
        r"url_for\('operations_import'\)": "url_for('import_operations')"
    }

    for template_file in template_files:
        file_path = os.path.join(template_dir, template_file)
        if os.path.exists(file_path):
            print(f"修复文件: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 替换路由引用
            for old_route, new_route in route_mapping.items():
                content = re.sub(old_route, new_route, content)

            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"完成修复: {file_path}")
        else:
            print(f"文件不存在: {file_path}")


if __name__ == '__main__':
    fix_template_routes()
    print("路由修复完成！")