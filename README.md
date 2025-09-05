# Project Monitor Bot для Mattermost + Jira

🤖 Бот для мониторинга проектов в Jira - отслеживание превышения трудозатрат и просроченных сроков выполнения задач с уведомлениями в Mattermost.

## Возможности

- 🚨 **Мониторинг превышения трудозатрат** - уведомления когда фактическое время превышает плановое
- ⏰ **Отслеживание просроченных сроков** - уведомления о задачах с истекшим сроком выполнения  
- 📢 **Уведомления в каналы** - отчеты для команды проекта
- 💬 **Персональные уведомления** - прямые сообщения ответственным за задачи
- 📋 **Подписки на проекты** - каждый канал может подписаться на мониторинг своего проекта
- 🔐 **Персональные настройки Jira** - каждый пользователь настраивает свое подключение к Jira
- 🗃️ **SQLite база данных** - хранение подписок, настроек и истории уведомлений
- ⚙️ **Команды администратора** - управление ботом и мониторингом
- 🔧 **Поддержка on-premise** Jira

## Поддерживаемые системы

- **Mattermost** (любая версия с поддержкой ботов)
- **Jira Server/Data Center** (on-premise) с аутентификацией по паролю или API токенам

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

### Настройка подключения к Jira:
- `setup_jira [username] [password]` - настроить персональное подключение к Jira
- `test_jira` - проверить подключение к Jira
- `change_password <new_password>` - изменить пароль для Jira

### Управление подписками (в каналах):
- `subscribe PROJECT_KEY` - подписать канал на мониторинг проекта
- `unsubscribe PROJECT_KEY` - отписать канал от мониторинга проекта
- `list_subscriptions` - показать активные подписки в канале

### Информационные команды:
- `help` - справка по командам
- `history [дни]` - история уведомлений
- `status` - статус бота и активные подписки

### Только для администраторов:
- `monitor_now` - запустить мониторинг всех проектов вручную
- `all_subscriptions` - просмотреть все подписки в системе
- `delete_subscription PROJECT_KEY CHANNEL_ID` - удалить конкретную подписку

## Архитектура

```
├── main.py                 # Основной файл запуска
├── config.py              # Управление конфигурацией
├── database.py            # Работа с SQLite БД (подписки, настройки, уведомления)
├── mattermost_client.py   # Интеграция с Mattermost
├── jira_client.py         # Базовый клиент Jira (глобальные настройки)
├── user_jira_client.py    # Персональные подключения к Jira с кешированием
├── project_monitor.py     # Мониторинг проектов и задач
├── scheduler.py           # Планировщик ежедневных проверок
├── bot_commands.py        # Обработка команд подписки и настроек
├── install.sh             # Скрипт установки
└── systemd/               # Конфигурация systemd сервиса
```

## Безопасность

🔐 **Персональные настройки Jira:**
- Каждый пользователь настраивает свое подключение к Jira
- Логины и пароли хранятся в локальной SQLite базе данных
- Нет общих учетных данных - каждый использует свои права доступа
- Подключения кешируются для оптимизации производительности

⚠️ **Важные моменты безопасности:**
- Пароли хранятся в открытом виде в БД (рекомендуется использовать API токены)
- База данных должна быть защищена на уровне файловой системы
- Рекомендуется запуск бота от отдельного пользователя с ограниченными правами

## Требования

- Python 3.8+
- Доступ к Mattermost API (бот токен)
- Персональный доступ к Jira API для каждого пользователя (логин/пароль)

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
