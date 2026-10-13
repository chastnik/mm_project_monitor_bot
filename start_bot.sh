#!/bin/bash

# Скрипт запуска Project Monitor Bot
# Использование: ./start_bot.sh [dev|prod]
# 
# Версия с улучшенной безопасностью:
# - Шифрование паролей пользователей
# - Безопасные права доступа к файлам
# - Отсутствие глобальных паролей Jira в конфигурации

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-dev}"

echo "🚀 Запуск Project Monitor Bot в режиме: $MODE"

# Функция для проверки зависимостей
check_dependencies() {
    echo "🔍 Проверка зависимостей..."
    
    # Проверка Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python3 не установлен"
        exit 1
    fi
    
    python_version=$(python3 --version | cut -d' ' -f2)
    echo "✅ Python: $python_version"
    
    # Проверка pip
    if ! command -v pip3 &> /dev/null; then
        echo "❌ pip3 не установлен"
        exit 1
    fi
    
    echo "✅ pip3 доступен"
}

# Функция для установки зависимостей
install_dependencies() {
    echo "📦 Установка зависимостей..."
    
    if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
        echo "❌ Файл requirements.txt не найден"
        exit 1
    fi
    
    # Создаем виртуальное окружение если его нет
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        echo "🔧 Создание виртуального окружения..."
        python3 -m venv "$SCRIPT_DIR/venv"
    fi
    
    # Активируем виртуальное окружение
    source "$SCRIPT_DIR/venv/bin/activate"
    
    # Обновляем pip
    pip install --upgrade pip
    
    # Устанавливаем зависимости
    pip install -r "$SCRIPT_DIR/requirements.txt"
    
    # Проверяем критически важные зависимости для безопасности
    echo "🔐 Проверка криптографических зависимостей..."
    python3 -c "
import sys
try:
    from cryptography.fernet import Fernet
    print('✅ Криптографическая библиотека доступна')
except ImportError as e:
    print(f'❌ Ошибка импорта cryptography: {e}')
    sys.exit(1)
" || {
        echo "❌ Критическая ошибка: библиотека шифрования недоступна"
        exit 1
    }
    
    echo "✅ Зависимости установлены"
}

# Функция для проверки конфигурации
check_config() {
    echo "⚙️ Проверка конфигурации..."
    
    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        if [ -f "$SCRIPT_DIR/env.example" ]; then
            echo "📝 Создание .env файла из примера..."
            cp "$SCRIPT_DIR/env.example" "$SCRIPT_DIR/.env"
            echo "⚠️ Отредактируйте файл .env с вашими настройками"
            echo "🔒 ВАЖНО: Глобальные настройки Jira больше не требуются!"
            echo "   Пользователи настраивают свои пароли через команды бота"
        else
            echo "❌ Файл .env не найден и нет примера"
            exit 1
        fi
    fi
    
    # Устанавливаем безопасные права доступа к .env
    chmod 600 "$SCRIPT_DIR/.env" 2>/dev/null || true
    echo "🔒 Установлены безопасные права доступа к .env"
    
    echo "✅ Конфигурация найдена"
}

# Функция для проверки подключений
test_connections() {
    echo "🧪 Проверка подключений..."
    
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    
    # Запускаем тест подключений если он существует
    if [ -f "$SCRIPT_DIR/test_connections.py" ]; then
        echo "🔗 Тестирование подключений к внешним сервисам..."
        python3 test_connections.py || {
            echo "⚠️ Есть проблемы с подключениями, но продолжаем запуск..."
        }
    fi
}

# Функция запуска в dev режиме
start_dev() {
    echo "🔧 Запуск в режиме разработки..."
    
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    
    # Запускаем с подробным логированием
    export LOG_LEVEL=DEBUG
    python3 main.py
}

# Функция запуска в prod режиме
start_prod() {
    echo "🏭 Запуск в продакшен режиме..."
    
    # Проверяем права доступа к критически важным файлам
    chmod 600 "$SCRIPT_DIR/.env" 2>/dev/null || true
    chmod 600 "$SCRIPT_DIR"/*.db 2>/dev/null || true
    chmod 600 "$SCRIPT_DIR/.crypto_salt" 2>/dev/null || true
    echo "🔒 Установлены безопасные права доступа к файлам"
    
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    
    # Создаем PID файл
    PID_FILE="$SCRIPT_DIR/bot.pid"
    
    # Проверяем, не запущен ли уже бот
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "⚠️ Бот уже запущен с PID: $OLD_PID"
            echo "   Используйте ./stop_bot.sh для остановки"
            exit 1
        else
            echo "🧹 Удаление устаревшего PID файла"
            rm -f "$PID_FILE"
        fi
    fi
    
    # Запускаем в фоне
    nohup python3 main.py > "$SCRIPT_DIR/bot.log" 2>&1 &
    BOT_PID=$!
    
    # Сохраняем PID
    echo $BOT_PID > "$PID_FILE"
    
    echo "✅ Бот запущен в фоне с PID: $BOT_PID"
    echo "📋 Логи: $SCRIPT_DIR/bot.log"
    echo "🛑 Остановка: ./stop_bot.sh"
    echo ""
    echo "🔒 БЕЗОПАСНОСТЬ:"
    echo "   • Пароли пользователей шифруются современными алгоритмами"
    echo "   • Файлы базы данных и соли защищены (права 600)"
    echo "   • Глобальные пароли Jira больше не требуются"
    echo ""
    echo "💡 НАСТРОЙКА ПОЛЬЗОВАТЕЛЕЙ:"
    echo "   Каждый пользователь должен настроить свой доступ к Jira:"
    echo "   • Отправьте боту личное сообщение: login <PAT> (Personal Access Token из профиля Jira)"
    echo "   • Проверьте подключение: test_jira"
    
    # Ждем несколько секунд и проверяем, что процесс все еще работает
    sleep 3
    if ps -p "$BOT_PID" > /dev/null 2>&1; then
        echo "🎉 Бот успешно запущен!"
    else
        echo "❌ Бот завершился с ошибкой. Проверьте логи:"
        tail -20 "$SCRIPT_DIR/bot.log"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# Основная логика
main() {
    echo "🤖 Project Monitor Bot - Скрипт запуска"
    echo "========================================"
    
    check_dependencies
    install_dependencies
    check_config
    
    if [ "$MODE" = "prod" ]; then
        test_connections
        start_prod
    else
        echo "ℹ️ Режим разработки - пропускаем тест подключений"
        start_dev
    fi
}

# Обработка сигналов
trap 'echo "❌ Прервано пользователем"; exit 1' INT TERM

# Запуск
main "$@"
