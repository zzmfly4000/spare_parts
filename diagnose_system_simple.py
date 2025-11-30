# diagnose_system_simple.py
import sqlite3
import urllib.request
import urllib.error
import json
import sys
from datetime import datetime


def check_database():
    """检查数据库状态"""
    print("检查数据库状态...")
    try:
        conn = sqlite3.connect('spare_parts.db')
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='locations'")
        if not cursor.fetchone():
            print("❌ locations 表不存在")
            return False

        # 检查表结构
        cursor.execute("PRAGMA table_info(locations)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"✅ locations 表存在，包含字段: {columns}")

        # 检查是否有新字段
        required_columns = ['variety_count', 'total_quantity', 'status_category']
        missing_columns = [col for col in required_columns if col not in columns]
        if missing_columns:
            print(f"❌ 缺少字段: {missing_columns}")
        else:
            print("✅ 数据库字段完整")

        # 检查数据
        cursor.execute("SELECT COUNT(*) FROM locations")
        count = cursor.fetchone()[0]
        print(f"✅ 库位数据: {count} 条记录")

        # 检查样本数据
        cursor.execute("SELECT location_code, variety_count, total_quantity, status_category FROM locations LIMIT 3")
        sample_data = cursor.fetchall()
        print("样本数据:")
        for row in sample_data:
            print(f"  - {row}")

        conn.close()
        return len(missing_columns) == 0

    except Exception as e:
        print(f"❌ 数据库检查失败: {str(e)}")
        return False


def check_flask_server():
    """检查Flask服务器状态"""
    print("\n检查Flask服务器状态...")
    try:
        # 尝试连接测试端点
        req = urllib.request.Request('http://localhost:5000/api/locations/test')
        response = urllib.request.urlopen(req, timeout=5)

        if response.status == 200:
            data = json.loads(response.read().decode())
            print(f"✅ Flask服务器运行正常: {data.get('message', '')}")
            return True
        else:
            print(f"❌ Flask服务器返回错误状态: {response.status}")
            return False

    except urllib.error.URLError as e:
        print(f"❌ 无法连接到Flask服务器: {e.reason}")
        return False
    except Exception as e:
        print(f"❌ 服务器检查失败: {str(e)}")
        return False


def check_api_endpoints():
    """检查API端点"""
    print("\n检查API端点...")
    endpoints = [
        '/api/locations/test',
        '/api/locations/rack_layout'
    ]

    base_url = 'http://localhost:5000'

    for endpoint in endpoints:
        try:
            req = urllib.request.Request(base_url + endpoint)
            response = urllib.request.urlopen(req, timeout=10)
            print(f"{endpoint}: ✅ {response.status}")

            if response.status == 200:
                data = json.loads(response.read().decode())
                if not data.get('success'):
                    print(f"   API返回错误: {data.get('error', '未知错误')}")

        except urllib.error.HTTPError as e:
            print(f"{endpoint}: ❌ HTTP错误 {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            print(f"{endpoint}: ❌ 连接失败 - {e.reason}")
        except Exception as e:
            print(f"{endpoint}: ❌ 检查失败 - {str(e)}")


def check_python_environment():
    """检查Python环境"""
    print("检查Python环境...")
    try:
        import flask
        print(f"✅ Flask版本: {flask.__version__}")
    except ImportError:
        print("❌ Flask未安装")

    try:
        import sqlite3
        print("✅ sqlite3可用")
    except ImportError:
        print("❌ sqlite3不可用")


def main():
    print("=" * 50)
    print("系统诊断工具 (简化版)")
    print("=" * 50)

    # 检查Python环境
    check_python_environment()

    # 检查数据库
    db_ok = check_database()

    # 检查服务器
    server_ok = check_flask_server()

    # 如果服务器运行，检查API端点
    if server_ok:
        check_api_endpoints()

    print("\n" + "=" * 50)
    print("诊断总结:")
    print(f"数据库: {'✅ 正常' if db_ok else '❌ 异常'}")
    print(f"服务器: {'✅ 正常' if server_ok else '❌ 异常'}")

    if not server_ok:
        print("\n建议:")
        print("1. 确保Flask服务器正在运行")
        print("2. 检查端口5000是否被占用")
        print("3. 运行: python app.py")
        print("4. 如果端口被占用，可以尝试: python app.py --port 5001")

    if db_ok and not server_ok:
        print("\n尝试启动服务器...")
        try:
            import subprocess
            subprocess.Popen([sys.executable, "app.py"])
            print("✅ 服务器启动命令已执行，请等待几秒后刷新页面")
        except Exception as e:
            print(f"❌ 启动服务器失败: {str(e)}")


if __name__ == "__main__":
    main()