import sys
import os

# 将项目根目录添加到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from models.database import init_db
    if __name__ == '__main__':
        init_db()
        print("数据库初始化完成")
except ImportError as e:
    print(f"导入错误: {e}")
    print("请检查models目录和database.py文件是否存在")

