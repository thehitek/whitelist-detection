@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo Запуск Whitelist Checker
echo ========================================
echo.

:: Проверяем наличие git и обновляем проект
git --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Проверка обновлений проекта...
    git pull origin main
    if errorlevel 1 (
        echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось обновить проект
    ) else (
        echo [OK] Проект обновлен
    )
    echo.
) else (
    echo [ПРЕДУПРЕЖДЕНИЕ] Git не установлен или не добавлен в PATH
    echo Автоматическое обновление недоступно
    echo.
)

:: Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не установлен или не добавлен в PATH
    echo Пожалуйста, установите Python 3.8 или выше
    pause
    exit /b 1
)

:: Создаем виртуальное окружение, если его нет
if not exist ".venv" (
    echo [INFO] Создание виртуального окружения...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение
        pause
        exit /b 1
    )
    echo [OK] Виртуальное окружение создано
)

:: Активируем виртуальное окружение
call .venv\Scripts\activate.bat

:: Обновляем pip
echo [INFO] Обновление pip...
python -m pip install --upgrade pip

:: Устанавливаем/обновляем зависимости
echo [INFO] Установка зависимостей...
pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости
    pause
    exit /b 1
)
echo [OK] Зависимости установлены

:: Проверяем наличие репозитория whitelist
if not exist "russia-mobile-internet-whitelist" (
    echo [INFO] Клонирование репозитория whitelist...
    git clone https://github.com/hxehex/russia-mobile-internet-whitelist.git
    if errorlevel 1 (
        echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось клонировать репозиторий
        echo Приложение попытается загрузить данные при первом запуске
    )
) else (
    echo [INFO] Обновление репозитория whitelist...
    cd russia-mobile-internet-whitelist
    git pull origin main
    if errorlevel 1 (
        echo [ПРЕДУПРЕЖДЕНИЕ] Не удалось обновить репозиторий
    )
    cd ..
)

:: Запускаем приложение
echo.
echo ========================================
echo Запуск приложения...
echo ========================================
python main.py

:: Если приложение завершилось с ошибкой
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Приложение завершилось с ошибкой
    pause
    exit /b 1
)

endlocal
