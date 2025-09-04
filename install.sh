#!/bin/bash

# Скрипт установки бота для проверки планов в Jira

set -e

echo "🤖 Установка Standup Bot для проверки планов в Jira"
echo "=================================================="

# Проверяем права root
if [[ $EUID -eq 0 ]]; then
   echo "❌ Не запускайте этот скрипт от root! Используйте sudo только при необходимости."
   exit 1
fi

# Определяем директории
INSTALL_DIR="/opt/standup-bot"
SERVICE_FILE="/etc/systemd/system/standup-bot.service"

echo "📁 Директория установки: $INSTALL_DIR"

# Создаем пользователя для бота
echo "👤 Создание пользователя standup-bot..."
if ! id "standup-bot" &>/dev/null; then
    sudo useradd --system --shell /bin/bash --home-dir $INSTALL_DIR --create-home standup-bot
    echo "✅ Пользователь standup-bot создан"
else
    echo "ℹ️ Пользователь standup-bot уже существует"
fi

# Создаем директорию установки
echo "📁 Создание директории установки..."
sudo mkdir -p $INSTALL_DIR
sudo chown standup-bot:standup-bot $INSTALL_DIR

# Копируем файлы
echo "📄 Копирование файлов..."
sudo cp -r . $INSTALL_DIR/
sudo chown -R standup-bot:standup-bot $INSTALL_DIR

# Устанавливаем Python зависимости
echo "🐍 Установка Python зависимостей..."
cd $INSTALL_DIR

# Создаем виртуальное окружение
sudo -u standup-bot python3 -m venv venv
sudo -u standup-bot ./venv/bin/pip install --upgrade pip
sudo -u standup-bot ./venv/bin/pip install -r requirements.txt

# Создаем конфигурационный файл
echo "⚙️ Создание конфигурационного файла..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    sudo -u standup-bot cp env.example $INSTALL_DIR/.env
    echo "✅ Создан файл .env из шаблона"
    echo "⚠️ ВАЖНО: Отредактируйте файл $INSTALL_DIR/.env с вашими настройками!"
else
    echo "ℹ️ Файл .env уже существует, пропускаем"
fi

# Устанавливаем systemd сервис
echo "🔧 Установка systemd сервиса..."
sudo cp systemd/standup-bot.service $SERVICE_FILE
sudo systemctl daemon-reload

echo "✅ Установка завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Отредактируйте конфигурацию: sudo nano $INSTALL_DIR/.env"
echo "2. Запустите сервис: sudo systemctl start standup-bot"
echo "3. Включите автозапуск: sudo systemctl enable standup-bot"
echo "4. Проверьте статус: sudo systemctl status standup-bot"
echo "5. Просмотр логов: sudo journalctl -u standup-bot -f"
echo ""
echo "🔗 Полезные команды:"
echo "   Остановить: sudo systemctl stop standup-bot"
echo "   Перезапустить: sudo systemctl restart standup-bot"
echo "   Отключить автозапуск: sudo systemctl disable standup-bot"
