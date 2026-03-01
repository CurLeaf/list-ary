@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   构建 Listary 自动化工具集 EXE
echo ========================================
echo.

pyinstaller listary_tools.spec --clean --noconfirm

if %errorlevel%==0 (
    echo.
    echo ✓ 构建成功！
    echo   输出: dist\listary_tools.exe
    echo.
    echo 使用方式:
    echo   1. 将 listary_tools.exe 放到任意目录
    echo   2. Listary 配置 Path 指向 listary_tools.exe
    echo   3. Parameters 设为 {query}
    echo.
) else (
    echo.
    echo ✗ 构建失败，请检查错误信息。
)

pause
