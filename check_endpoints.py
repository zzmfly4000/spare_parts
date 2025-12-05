import os
import re

# 检查的目录
directories = ['templates', '.']

# 需要检查的文件模式
patterns = ['.html', '.py']

# 需要替换的旧端点
old_endpoints = ['login_page', 'logout']

for directory in directories:
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.endswith(pattern) for pattern in patterns):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    for endpoint in old_endpoints:
                        if f'url_for(\'{endpoint}\')' in content:
                            print(f"Found old endpoint '{endpoint}' in {filepath}")
                except Exception as e:
                    pass