@echo off
chcp 65001 > nul
title 备件管理系统 - 启动器
color 0A

echo ========================================
echo        备件管理系统启动器
echo ========================================
echo.

:: 检查 Conda 环境是否存在
echo [1/4] 检查环境配置...
if not exist "C:\Miniconda3\envs\spare_parts\python.exe" (
    echo ❌ 错误: 未找到 spare_parts 环境
    echo 请先创建 Conda 环境
    pause
    exit /b 1
)

:: 激活环境
echo [2/4] 激活虚拟环境...
call C:\Miniconda3\Scripts\activate.bat spare_parts

:: 检查必要包
echo [3/4] 检查依赖包...
python -c "import flask, psycopg2" >nul 2>&1
if errorlevel 1 (
    echo ⚠ 安装缺失的依赖包...
    pip install -r requirements.txt
)

:: 启动应用
echo [4/4] 启动应用...
echo 系统将在 3 秒后启动...
timeout /t 3 /nobreak >nul

echo.
echo ✅ 启动成功！访问: http://localhost:5000
echo 按 Ctrl+C 停止服务
echo.

python run.py

pause