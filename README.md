# Mattermost Standup Bot для Jira/Tempo

🤖 Бот для автоматической проверки заполнения планов работы в Jira через плагин Tempo с уведомлениями в Mattermost.

## Возможности

- ✅ **Ежедневная проверка** заполнения worklog в Jira через Tempo API
- 📊 **Канальные отчеты** со списком кто заполнил/не заполнил планы  
- 💬 **Персональные напоминания** пользователям, не заполнившим планы
- 🗃️ **SQLite база данных** для управления списком отслеживаемых пользователей
- ⚙️ **Команды администратора** для управления ботом
- 📈 **История проверок** и статистика
- 🔧 **Поддержка on-premise** Jira и Tempo

## Поддерживаемые системы

- **Mattermost** (любая версия с поддержкой ботов)
- **Jira Server/Data Center** (on-premise) с аутентификацией по паролю или API токенам
- **Tempo** (Cloud или on-premise) с автоматическим fallback на Jira API

## Быстрый старт

### 1. Установка

```bash
git clone https://github.com/chastnik/mm_standup_bot.git
cd mm_standup_bot
chmod +x install.sh
./install.sh
```

### 2. Настройка

Скопируйте и отредактируйте конфигурацию:

```bash
cp env.example .env
nano .env
```

### 3. Запуск

```bash
# Для разработки
python main.py

# Для продакшена (через systemd)
sudo systemctl start standup-bot
sudo systemctl enable standup-bot
```

## Конфигурация

### Основные параметры

```env
# Mattermost
MATTERMOST_URL=https://your-mattermost-server.com
MATTERMOST_TOKEN=your_bot_token
MATTERMOST_CHANNEL_ID=channel_id_for_reports

# Jira (on-premise)
JIRA_URL=https://jira.your-company.com
JIRA_USERNAME=service_user
JIRA_AUTH_METHOD=password
JIRA_PASSWORD=service_password

# Tempo API
TEMPO_API_URL=https://jira.your-company.com/rest/tempo-timesheets/4
TEMPO_API_TOKEN=your_tempo_token

# Администраторы и расписание
ADMIN_EMAILS=admin1@company.com,admin2@company.com
CHECK_TIME=12:00
```

## Команды бота

### Доступные всем:
- `help` - справка по командам
- `list_users` - список отслеживаемых пользователей
- `history [дни]` - история проверок
- `status` - статус бота и подключений

### Только для администраторов:
- `add_user <email> [имя]` - добавить пользователя в мониторинг
- `remove_user <email>` - удалить пользователя
- `check_now` - запустить проверку вручную

## Архитектура

```
├── main.py                 # Основной файл запуска
├── config.py              # Управление конфигурацией
├── database.py            # Работа с SQLite БД
├── mattermost_client.py   # Интеграция с Mattermost
├── jira_tempo_client.py   # Интеграция с Jira/Tempo
├── scheduler.py           # Планировщик проверок
├── bot_commands.py        # Обработка команд
├── install.sh             # Скрипт установки
└── systemd/               # Конфигурация systemd сервиса
```

## Требования

- Python 3.8+
- Доступ к Mattermost API (бот токен)
- Доступ к Jira API (пароль или API токен)
- Доступ к Tempo API (опционально, есть fallback)

## Развертывание

Подробная инструкция по настройке и развертыванию в файле [SETUP.md](SETUP.md).

## Безопасность

- Отдельный системный пользователь для работы бота
- Защищенное хранение конфигурации в `.env` файле
- Ограниченные права доступа к файловой системе
- Логирование всех операций

## Мониторинг

```bash
# Статус сервиса
sudo systemctl status standup-bot

# Логи в реальном времени
sudo journalctl -u standup-bot -f

# Проверка подключений
sudo -u standup-bot /opt/standup-bot/venv/bin/python -c "
from jira_tempo_client import jira_tempo_client
print('Jira:', jira_tempo_client.test_tempo_connection())
"
```

## Лицензия

MIT License - см. файл [LICENSE](LICENSE) для деталей.

## Поддержка

Если у вас есть вопросы или предложения:

1. Создайте [Issue](https://github.com/chastnik/mm_standup_bot/issues) в GitHub
2. Проверьте [SETUP.md](SETUP.md) для решения типовых проблем
3. Изучите логи бота для диагностики
