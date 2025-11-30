# diagnose_system.py
import sqlite3
import requests
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

        # 检查数据
        cursor.execute("SELECT COUNT(*) FROM locations")
        count = cursor.fetchone()[0]
        print(f"✅ 库位数据: {count} 条记录")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ 数据库检查失败: {str(e)}")
        return False


def check_flask_server():
    """检查Flask服务器状态"""
    print("\n检查Flask服务器状态...")
    try:
        # 尝试连接测试端点
        response = requests.get('http://localhost:5000/api/locations/test', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Flask服务器运行正常: {data.get('message', '')}")
            return True
        else:
            print(f"❌ Flask服务器返回错误状态: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到Flask服务器，请确保服务器正在运行")
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
            response = requests.get(base_url + endpoint, timeout=10)
            print(f"{endpoint}: {'✅' if response.status_code == 200 else '❌'} {response.status_code}")

            if response.status_code != 200:
                try:
                    error_data = response.json()
                    print(f"   错误信息: {error_data.get('error', '未知错误')}")
                except:
                    print(f"   响应内容: {response.text[:100]}...")

        except Exception as e:
            print(f"{endpoint}: ❌ 连接失败 - {str(e)}")


def main():
    print("=" * 50)
    print("系统诊断工具")
    print("=" * 50)

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

    if db_ok and not server_ok:
        print("\n尝试启动服务器...")
        try:
            import subprocess
            subprocess.Popen([sys.executable, "app.py"])
            print("✅ 服务器启动命令已执行")
        except Exception as e:
            print(f"❌ 启动服务器失败: {str(e)}")


if __name__ == "__main__":
    main()