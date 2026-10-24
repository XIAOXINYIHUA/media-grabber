@echo off
chcp 65001 >nul
title MediaGrabber 音频爬取工具
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py server.py
) else (
    python server.py
)

if %errorlevel% neq 0 (
    echo.
    echo 启动出错，请检查 Python 是否已安装。
    pause
)
