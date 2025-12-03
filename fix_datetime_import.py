# fix_datetime_import.py
import re

with open('enhanced_settings_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

print("正在修复 enhanced_settings_routes.py 中的 datetime 导入问题...")

# 1. 替换所有 datetime.datetime 为 dt.datetime
content = re.sub(r'datetime\.datetime\.', 'dt.', content)

# 2. 替换所有 datetime.timedelta 为 dt.timedelta
content = re.sub(r'datetime\.timedelta', 'dt.timedelta', content)

# 3. 替换所有 datetime.now() 为 dt.datetime.now()
content = re.sub(r'datetime\.now\(\)', 'dt.datetime.now()', content)

# 4. 替换所有 datetime.fromtimestamp 为 dt.datetime.fromtimestamp
content = re.sub(r'datetime\.fromtimestamp', 'dt.datetime.fromtimestamp', content)

# 5. 替换所有 datetime.strftime 为 dt.datetime.strftime（针对模块调用）
content = re.sub(r'datetime\.strftime\(', 'dt.datetime.strftime(', content)

# 6. 替换所有 datetime.strptime 为 dt.datetime.strptime
content = re.sub(r'datetime\.strptime', 'dt.datetime.strptime', content)

# 7. 修改导入部分
# 找到 import datetime 行
if 'import datetime' in content:
    # 替换为 import datetime as dt
    content = content.replace('import datetime', 'import datetime as dt')

# 删除 from datetime import datetime
if 'from datetime import datetime' in content:
    content = content.replace('from datetime import datetime\n', '')

# 8. 修复可能遗漏的 datetime 前缀
content = re.sub(r'\bdatetime\.(?!dt)', 'dt.', content)

# 保存文件
with open('enhanced_settings_routes_fixed.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("修复完成！已保存为 enhanced_settings_routes_fixed.py")