#!/bin/bash

# Скрипт остановки Project Monitor Bot
# Использование: ./stop_bot.sh [--force]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/bot.pid"
FORCE_STOP=false

# Обработка аргументов
if [ "$1" = "--force" ]; then
    FORCE_STOP=true
fi

echo "🛑 Остановка Project Monitor Bot"
echo "================================="

# Функция для graceful остановки
graceful_stop() {
    local pid=$1
    echo "📤 Отправка сигнала SIGTERM процессу $pid..."
    
    kill -TERM "$pid" 2>/dev/null || {
        echo "❌ Не удалось отправить SIGTERM"
        return 1
    }
    
    # Ждем до 30 секунд для graceful завершения
    local count=0
    while [ $count -lt 30 ]; do
        if ! ps -p "$pid" > /dev/null 2>&1; then
            echo "✅ Процесс завершен gracefully"
            return 0
        fi
        sleep 1
        count=$((count + 1))
        if [ $((count % 5)) -eq 0 ]; then
            echo "⏳ Ожидание завершения... ($count/30)"
        fi
    done
    
    echo "⚠️ Процесс не завершился за 30 секунд"
    return 1
}

# Функция для принудительной остановки
force_stop() {
    local pid=$1
    echo "💥 Принудительная остановка процесса $pid..."
    
    kill -KILL "$pid" 2>/dev/null || {
        echo "❌ Не удалось принудительно остановить процесс"
        return 1
    }
    
    sleep 2
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "❌ Процесс все еще работает"
        return 1
    else
        echo "✅ Процесс принудительно остановлен"
        return 0
    fi
}

# Функция для остановки по имени процесса
stop_by_name() {
    echo "🔍 Поиск процессов Project Monitor Bot..."
    
    # Ищем процессы Python с main.py
    local pids=$(pgrep -f "python.*main.py" 2>/dev/null || true)
    
    if [ -z "$pids" ]; then
        echo "ℹ️ Процессы бота не найдены"
        return 0
    fi
    
    echo "📋 Найдены процессы: $pids"
    
    for pid in $pids; do
        echo "🛑 Остановка процесса $pid..."
        if $FORCE_STOP; then
            force_stop "$pid"
        else
            graceful_stop "$pid" || force_stop "$pid"
        fi
    done
}

# Функция для очистки файлов
cleanup() {
    echo "🧹 Очистка временных файлов..."
    
    # Удаляем PID файл
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
        echo "✅ PID файл удален"
    fi
    
    # Удаляем lock файлы если есть
    find "$SCRIPT_DIR" -name "*.lock" -delete 2>/dev/null || true
    
    echo "✅ Очистка завершена"
}

# Основная логика
main() {
    # Проверяем PID файл
    if [ -f "$PID_FILE" ]; then
        BOT_PID=$(cat "$PID_FILE")
        echo "📋 Найден PID файл: $BOT_PID"
        
        # Проверяем, работает ли процесс
        if ps -p "$BOT_PID" > /dev/null 2>&1; then
            echo "🎯 Остановка процесса с PID: $BOT_PID"
            
            if $FORCE_STOP; then
                force_stop "$BOT_PID"
            else
                graceful_stop "$BOT_PID" || force_stop "$BOT_PID"
            fi
        else
            echo "ℹ️ Процесс с PID $BOT_PID уже не работает"
        fi
    else
        echo "ℹ️ PID файл не найден"
    fi
    
    # Дополнительная проверка по имени процесса
    stop_by_name
    
    # Очистка
    cleanup
    
    # Финальная проверка
    echo "🔍 Финальная проверка..."
    local remaining=$(pgrep -f "python.*main.py" 2>/dev/null | wc -l)
    
    if [ "$remaining" -eq 0 ]; then
        echo "🎉 Все процессы Project Monitor Bot остановлены"
    else
        echo "⚠️ Возможно остались работающие процессы ($remaining)"
        echo "   Используйте: ./stop_bot.sh --force"
        exit 1
    fi
}

# Функция показа статуса
show_status() {
    echo "📊 Статус Project Monitor Bot"
    echo "============================="
    
    # Проверяем PID файл
    if [ -f "$PID_FILE" ]; then
        BOT_PID=$(cat "$PID_FILE")
        if ps -p "$BOT_PID" > /dev/null 2>&1; then
            echo "🟢 Статус: Работает (PID: $BOT_PID)"
            
            # Показываем информацию о процессе
            echo "📋 Информация о процессе:"
            ps -p "$BOT_PID" -o pid,ppid,cmd,etime,pcpu,pmem --no-headers | while read line; do
                echo "   $line"
            done
            
            # Показываем последние строки лога
            if [ -f "$SCRIPT_DIR/bot.log" ]; then
                echo ""
                echo "📄 Последние 5 строк лога:"
                tail -5 "$SCRIPT_DIR/bot.log" | sed 's/^/   /'
            fi
        else
            echo "🔴 Статус: Не работает (устаревший PID файл)"
        fi
    else
        echo "🔴 Статус: Не работает (PID файл не найден)"
    fi
    
    # Проверяем другие процессы
    local other_pids=$(pgrep -f "python.*main.py" 2>/dev/null || true)
    if [ -n "$other_pids" ]; then
        echo ""
        echo "⚠️ Найдены другие процессы Python с main.py:"
        echo "$other_pids" | while read pid; do
            if [ "$pid" != "$BOT_PID" ]; then
                echo "   PID: $pid"
            fi
        done
    fi
}

# Обработка аргументов
case "${1:-stop}" in
    "status")
        show_status
        ;;
    "stop"|"--force")
        main
        ;;
    *)
        echo "Использование: $0 [stop|status|--force]"
        echo ""
        echo "Команды:"
        echo "  stop     - Graceful остановка бота (по умолчанию)"
        echo "  --force  - Принудительная остановка"
        echo "  status   - Показать статус бота"
        exit 1
        ;;
esac
