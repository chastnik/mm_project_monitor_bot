#!/bin/bash

# Универсальный скрипт управления Project Monitor Bot
# Использование: ./manage_bot.sh [start|stop|restart|status|logs|install]
# 
# Версия с улучшенной безопасностью:
# - Шифрование паролей пользователей
# - Персональные настройки Jira для каждого пользователя

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND="${1:-help}"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции вывода
print_info() {
    echo -e "${BLUE}ℹ️ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_header() {
    echo -e "${BLUE}🤖 Project Monitor Bot - $1${NC}"
    echo "========================================"
}

# Функция показа помощи
show_help() {
    print_header "Управление"
    echo ""
    echo "Использование: $0 [команда]"
    echo ""
    echo "Доступные команды:"
    echo "  start     - Запустить бота в продакшен режиме"
    echo "  dev       - Запустить бота в режиме разработки"
    echo "  stop      - Остановить бота"
    echo "  restart   - Перезапустить бота"
    echo "  status    - Показать статус бота"
    echo "  logs      - Показать логи бота"
    echo "  tail      - Следить за логами в реальном времени"
    echo "  install   - Установить зависимости"
    echo "  test      - Протестировать подключения"
    echo "  backup    - Создать резервную копию базы данных"
    echo "  cleanup   - Очистить временные файлы"
    echo "  help      - Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 start          # Запуск в продакшене"
    echo "  $0 dev            # Запуск в разработке"
    echo "  $0 logs -20       # Последние 20 строк логов"
    echo "  $0 restart        # Перезапуск"
    echo ""
    print_warning "ВАЖНО: Настройка безопасности"
    echo "• Глобальные пароли Jira больше не требуются в .env"
    echo "• Каждый пользователь настраивает доступ через бота:"
    echo "  - Отправьте боту: login <PAT> (Personal Access Token из профиля Jira)"
    echo "  - Проверьте: test_jira"
    echo "• Пароли шифруются и хранятся безопасно"
}

# Функция запуска
start_bot() {
    local mode="${1:-prod}"
    print_header "Запуск ($mode)"
    
    if [ -x "$SCRIPT_DIR/start_bot.sh" ]; then
        "$SCRIPT_DIR/start_bot.sh" "$mode"
    else
        print_error "Файл start_bot.sh не найден или не исполняемый"
        exit 1
    fi
}

# Функция остановки
stop_bot() {
    local force_flag="$1"
    print_header "Остановка"
    
    if [ -x "$SCRIPT_DIR/stop_bot.sh" ]; then
        "$SCRIPT_DIR/stop_bot.sh" $force_flag
    else
        print_error "Файл stop_bot.sh не найден или не исполняемый"
        exit 1
    fi
}

# Функция перезапуска
restart_bot() {
    print_header "Перезапуск"
    
    print_info "Остановка бота..."
    stop_bot
    
    sleep 2
    
    print_info "Запуск бота..."
    start_bot "prod"
}

# Функция показа статуса
show_status() {
    if [ -x "$SCRIPT_DIR/stop_bot.sh" ]; then
        "$SCRIPT_DIR/stop_bot.sh" status
    else
        print_error "Файл stop_bot.sh не найден"
        exit 1
    fi
}

# Функция показа логов
show_logs() {
    local lines="${1:-50}"
    print_header "Логи (последние $lines строк)"
    
    local log_file="$SCRIPT_DIR/standup_bot.log"
    
    if [ -f "$log_file" ]; then
        tail -n "$lines" "$log_file"
    else
        print_warning "Файл логов не найден: $log_file"
        
        # Попробуем найти другие лог файлы
        local other_logs=$(find "$SCRIPT_DIR" -name "*.log" -type f 2>/dev/null)
        if [ -n "$other_logs" ]; then
            print_info "Найдены другие лог файлы:"
            echo "$other_logs"
        fi
    fi
}

# Функция слежения за логами
tail_logs() {
    print_header "Слежение за логами"
    
    local log_file="$SCRIPT_DIR/standup_bot.log"
    
    if [ -f "$log_file" ]; then
        print_info "Нажмите Ctrl+C для выхода"
        echo ""
        tail -f "$log_file"
    else
        print_error "Файл логов не найден: $log_file"
        exit 1
    fi
}

# Функция установки зависимостей
install_deps() {
    print_header "Установка зависимостей"
    
    # Проверяем наличие requirements.txt
    if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
        print_error "Файл requirements.txt не найден"
        exit 1
    fi
    
    # Создаем виртуальное окружение
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        print_info "Создание виртуального окружения..."
        python3 -m venv "$SCRIPT_DIR/venv"
        print_success "Виртуальное окружение создано"
    fi
    
    # Активируем и устанавливаем зависимости
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    
    print_info "Обновление pip..."
    pip install --upgrade pip
    
    print_info "Установка зависимостей..."
    pip install -r requirements.txt
    
    print_success "Зависимости установлены"
}

# Функция тестирования
test_connections() {
    print_header "Тестирование подключений"
    
    cd "$SCRIPT_DIR"
    
    if [ ! -d "venv" ]; then
        print_error "Виртуальное окружение не найдено. Запустите: $0 install"
        exit 1
    fi
    
    source venv/bin/activate
    
    if [ -f "test_connections.py" ]; then
        python3 test_connections.py
    else
        print_warning "Файл test_connections.py не найден"
        
        # Простая проверка импортов
        print_info "Проверка импортов основных модулей..."
        python3 -c "
import sys
modules = ['database', 'mattermost_client', 'jira_client', 'user_jira_client', 'project_monitor']
for module in modules:
    try:
        __import__(module)
        print(f'✅ {module}')
    except Exception as e:
        print(f'❌ {module}: {e}')
"
    fi
}

# Функция создания резервной копии
backup_database() {
    print_header "Резервное копирование"
    
    local db_files=$(find "$SCRIPT_DIR" -name "*.db" -type f)
    
    if [ -z "$db_files" ]; then
        print_warning "Файлы базы данных не найдены"
        return
    fi
    
    local backup_dir="$SCRIPT_DIR/backups"
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    
    mkdir -p "$backup_dir"
    
    echo "$db_files" | while read db_file; do
        if [ -f "$db_file" ]; then
            local basename=$(basename "$db_file")
            local backup_file="$backup_dir/${basename%.db}_${timestamp}.db"
            
            cp "$db_file" "$backup_file"
            print_success "Создана копия: $backup_file"
        fi
    done
    
    # Удаляем старые бэкапы (старше 30 дней)
    find "$backup_dir" -name "*.db" -mtime +30 -delete 2>/dev/null || true
    
    print_info "Старые бэкапы (>30 дней) удалены"
}

# Функция очистки
cleanup() {
    print_header "Очистка"
    
    local cleaned=0
    
    # Удаляем временные файлы
    local temp_files="*.tmp *.lock __pycache__ *.pyc .pytest_cache"
    for pattern in $temp_files; do
        if find "$SCRIPT_DIR" -name "$pattern" -exec rm -rf {} + 2>/dev/null; then
            cleaned=$((cleaned + 1))
        fi
    done
    
    # Очищаем старые логи
    if [ -f "$SCRIPT_DIR/standup_bot.log" ]; then
        local log_size=$(stat -f%z "$SCRIPT_DIR/standup_bot.log" 2>/dev/null || stat -c%s "$SCRIPT_DIR/standup_bot.log" 2>/dev/null || echo 0)
        if [ "$log_size" -gt 10485760 ]; then  # 10MB
            tail -1000 "$SCRIPT_DIR/standup_bot.log" > "$SCRIPT_DIR/standup_bot.log.tmp"
            mv "$SCRIPT_DIR/standup_bot.log.tmp" "$SCRIPT_DIR/standup_bot.log"
            print_info "Лог файл обрезан (оставлены последние 1000 строк)"
            cleaned=$((cleaned + 1))
        fi
    fi
    
    if [ $cleaned -gt 0 ]; then
        print_success "Очистка завершена"
    else
        print_info "Нечего очищать"
    fi
}

# Основная логика
main() {
    case "$COMMAND" in
        "start")
            start_bot "prod"
            ;;
        "dev")
            start_bot "dev"
            ;;
        "stop")
            stop_bot
            ;;
        "force-stop")
            stop_bot "--force"
            ;;
        "restart")
            restart_bot
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "${2:-50}"
            ;;
        "tail")
            tail_logs
            ;;
        "install")
            install_deps
            ;;
        "test")
            test_connections
            ;;
        "backup")
            backup_database
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            print_error "Неизвестная команда: $COMMAND"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Обработка сигналов
trap 'print_error "Прервано пользователем"; exit 1' INT TERM

# Запуск
main "$@"
