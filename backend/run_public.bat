@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo  Запуск сервера Bashkar (публичный доступ)
echo ========================================
echo.

cd /d ~dp0

if not exist .venv\Scripts\activate.bat (
    echo [!] Виртуальное окружение .venv не найдено. Создаю...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

if %errorlevel% neq 0 (
    echo [!] Не удалось активировать .venv
    pause
    exit /b 1
)

echo [+] Установка зависимостей...
pip install -q -r requirements.txt

echo [+] Сервер запускается на http://0.0.0.0:8000
echo    Открыть с другого компьютера: http://<ВАШ_IP_В_СЕТИ>:8000
echo    (узнать IP можно командой: ipconfig)
echo.
echo [+] Для доступа из интернета используйте ngrok (см. ИНСТРУКЦИЯ_ПУБЛИК.md)
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
