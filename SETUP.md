# Настройка Project Monitor Bot для Mattermost + Jira

## Описание

Бот для мониторинга проектов в Jira - отслеживание превышения трудозатрат и просроченных сроков выполнения задач с уведомлениями в Mattermost.

## Функциональность

- 🚨 **Мониторинг превышения трудозатрат** - уведомления когда фактическое время превышает плановое
- ⏰ **Отслеживание просроченных сроков** - уведомления о задачах с истекшим сроком выполнения
- 📢 **Уведомления в каналы** - отчеты для команды проекта
- 💬 **Персональные уведомления** - прямые сообщения ответственным за задачи
- 🔗 **Кликабельные ссылки** - номера задач Jira в уведомлениях ведут на соответствующие страницы
- 📋 **Подписки на проекты** - каждый канал может подписаться на мониторинг своего проекта
- 🔐 **Персональные настройки Jira** - каждый пользователь настраивает свое подключение к Jira с шифрованием паролей
- 🗃️ **SQLite база данных** - хранение подписок, настроек и истории уведомлений
- ⚙️ **Команды администратора** - управление ботом и мониторингом
- 🎯 **Умные алиасы команд** - поддержка естественных команд на русском и английском языках
- 💡 **Контекстные подсказки** - бот предлагает правильные команды при ошибках
- 🌐 **WebSocket интеграция** - реальное время общения с Mattermost

## Требования

- Python 3.8+
- Доступ к Mattermost API (бот токен)
- Персональный доступ к Jira API для каждого пользователя (логин/пароль)

## Быстрая установка

### 1. Скачайте и установите

```bash
git clone https://github.com/chastnik/mm_project_monitor_bot.git project-monitor-bot
cd project-monitor-bot
chmod +x install.sh
./install.sh
```

### 2. Настройте конфигурацию

Отредактируйте файл `.env` в директории проекта:

```bash
nano .env
```

### 3. Запустите сервис

```bash
# Запуск через управляющий скрипт
./manage_bot.sh start

# Или через systemd (если настроен)
sudo systemctl start project-monitor-bot
sudo systemctl enable project-monitor-bot
```

### 4. Настройте персональные подключения к Jira

Каждый пользователь должен настроить свое подключение к Jira:

1. Напишите боту в личных сообщениях: `setup_jira <username> <password>`
2. Проверьте подключение: `test_jira`
3. Подпишитесь на проект в канале: `subscribe PROJECT_KEY`

## Управление ботом

### Скрипты управления

Проект включает удобные скрипты для управления ботом:

#### Универсальный скрипт `manage_bot.sh`
```bash
# Показать справку
./manage_bot.sh help

# Установить зависимости
./manage_bot.sh install

# Запустить в продакшене
./manage_bot.sh start

# Запустить в режиме разработки  
./manage_bot.sh dev

# Остановить бота
./manage_bot.sh stop

# Перезапустить
./manage_bot.sh restart

# Показать статус
./manage_bot.sh status

# Показать логи (последние 50 строк)
./manage_bot.sh logs

# Следить за логами в реальном времени
./manage_bot.sh tail

# Протестировать подключения
./manage_bot.sh test

# Создать резервную копию БД
./manage_bot.sh backup

# Очистить временные файлы
./manage_bot.sh cleanup
```

#### Отдельные скрипты
```bash
# Запуск (dev или prod режим)
./start_bot.sh [dev|prod]

# Остановка (graceful или принудительная)
./stop_bot.sh [--force]

# Показать статус
./stop_bot.sh status
```

### Примеры использования

#### Первый запуск
```bash
# 1. Установка зависимостей
./manage_bot.sh install

# 2. Тестирование подключений
./manage_bot.sh test

# 3. Запуск в режиме разработки для проверки
./manage_bot.sh dev
# Ctrl+C для остановки

# 4. Запуск в продакшене
./manage_bot.sh start
```

#### Ежедневное использование
```bash
# Проверить статус
./manage_bot.sh status

# Посмотреть логи
./manage_bot.sh logs 100

# Перезапустить при обновлении конфигурации
./manage_bot.sh restart
```

#### Обслуживание
```bash
# Создать резервную копию БД
./manage_bot.sh backup

# Очистить временные файлы и старые логи
./manage_bot.sh cleanup

# Принудительная остановка при зависании
./manage_bot.sh force-stop
```

### Устранение неполадок

#### Бот не запускается
```bash
# Проверить логи
./manage_bot.sh logs

# Протестировать подключения
./manage_bot.sh test

# Проверить конфигурацию
cat .env | grep -v PASSWORD
```

#### Бот зависает
```bash
# Проверить статус
./manage_bot.sh status

# Принудительная остановка
./manage_bot.sh force-stop

# Перезапуск
./manage_bot.sh start
```

#### Проблемы с подключением к Jira
```bash
# В боте проверить подключение пользователя
test_jira

# Обновить настройки пользователя
setup_jira username new_password
```

## Подробная настройка

### Создание бота в Mattermost

1. Войдите в Mattermost как администратор
2. Перейдите в **System Console** → **Integrations** → **Bot Accounts**
3. Нажмите **Create Bot Account**
4. Заполните поля:
   - **Username**: `project-monitor-bot`
   - **Display Name**: `Project Monitor Bot`
   - **Description**: `Бот для мониторинга проектов в Jira`
5. Скопируйте **Access Token** - это значение для `MATTERMOST_TOKEN`

### Получение ID канала

1. Откройте канал в Mattermost
2. В адресной строке найдите ID канала (после `/channels/`)
3. Или используйте API: `GET /api/v4/teams/{team_id}/channels/name/{channel_name}`

### Настройка подключения к Jira

Бот использует **персональные подключения к Jira** - каждый пользователь настраивает свои учетные данные:

1. **Безопасность**: Пароли пользователей шифруются и хранятся в базе данных
2. **Индивидуальные настройки**: Каждый пользователь подключается под своим аккаунтом
3. **Нет глобальных паролей**: В конфигурации бота не требуется указывать учетные данные Jira

#### Настройка SSL
Для самоподписанных сертификатов:
```env
JIRA_VERIFY_SSL=false
```

## Конфигурация

### Основные параметры (.env файл)

```env
# Настройки Mattermost
MATTERMOST_URL=https://your-mattermost-server.com
MATTERMOST_TOKEN=your_bot_token_here
MATTERMOST_USERNAME=project-monitor-bot
MATTERMOST_TEAM=your_team_name
MATTERMOST_SSL_VERIFY=true
# Канал для системных сообщений (ошибки, запуск, режим работы)
MATTERMOST_CHANNEL_ID=channel_id_for_reports

# Настройки Jira (on-premise)
JIRA_URL=https://jira.your-company.com
# Проверка SSL сертификатов (false для самоподписанных)
JIRA_VERIFY_SSL=true

# Tempo API (опционально, для расширенной работы с временными метками)
# TEMPO_API_URL=https://jira.your-company.com/rest/tempo-timesheets/4
# TEMPO_API_TOKEN=your_tempo_token

# База данных
DATABASE_PATH=standup_bot.db

# Администраторы (email адреса через запятую)
ADMIN_EMAILS=admin1@company.com,admin2@company.com

# Расписание проверки (время в формате HH:MM)
CHECK_TIME=12:00

# Часовой пояс
TIMEZONE=Europe/Moscow

# Логирование
LOG_LEVEL=INFO
LOG_FILE=standup_bot.log
```

## Команды бота

### Настройка подключения к Jira:
- `setup_jira <username> <password>` - настроить подключение к Jira
- `test_jira` - проверить подключение к Jira
- `change_password <new_password>` - изменить пароль для Jira

### Просмотр проектов:
- `list_projects` - показать все доступные проекты в Jira

### Управление подписками на проекты:
- `subscribe <PROJECT_KEY>` - подписать канал на мониторинг проекта
- `unsubscribe <PROJECT_KEY>` - отписать канал от мониторинга проекта  
- `list_subscriptions` - показать активные подписки в канале

### Управление мониторингом:
- `run_subscriptions` - запустить проверку подписок текущего канала
- `history` - история уведомлений за последние дни
- `status` - статус бота и активные подписки

### Информационные команды:
- `help` - показать справку по командам

### Команды администратора:
- `monitor_now` - запустить мониторинг всех проектов сейчас
- `all_subscriptions` - просмотреть все подписки в системе
- `delete_subscription <PROJECT_KEY> <CHANNEL_ID>` - удалить подписку

### Примеры использования команд:

```
# Настройка подключения к Jira
setup_jira myusername mypassword

# Просмотр доступных проектов  
list_projects

# Подписка канала на проект
subscribe MYPROJ

# Проверка подключения
test_jira

# Запуск проверки подписок канала
run_subscriptions

# Просмотр истории уведомлений
history

# Изменение пароля Jira
change_password new_password_here
```

## Управление сервисом

```bash
# Статус
sudo systemctl status project-monitor-bot

# Запуск/остановка
sudo systemctl start project-monitor-bot
sudo systemctl stop project-monitor-bot
sudo systemctl restart project-monitor-bot

# Автозапуск
sudo systemctl enable project-monitor-bot
sudo systemctl disable project-monitor-bot

# Логи
sudo journalctl -u project-monitor-bot -f
sudo journalctl -u project-monitor-bot --since "1 hour ago"
```

## Логи

Бот ведет логи в двух местах:
- **systemd journal**: `sudo journalctl -u project-monitor-bot -f`
- **файл**: `standup_bot.log` в директории проекта

## Устранение неисправностей

### Проблемы с подключением к on-premise Jira

1. **SSL ошибки**: Установите `JIRA_VERIFY_SSL=false` для самоподписанных сертификатов
2. **Аутентификация**: 
   - Для старых версий используйте `JIRA_AUTH_METHOD=password`
   - Для новых версий (8.14+) используйте `JIRA_AUTH_METHOD=token`
3. **URL**: Убедитесь, что URL корректный и доступен из сети
4. **Права доступа**: Пользователь должен иметь права на просмотр проектов и worklog

### Проблемы с Tempo API

1. **On-premise Tempo**: Уточните правильный URL API у администратора
2. **Fallback на Jira API**: Если Tempo недоступен, бот автоматически использует Jira API
3. **Версии Tempo**: Разные версии могут иметь разные URL структуры

### Пользователи не найдены

- Email в Mattermost должен совпадать с email в Jira
- В on-premise Jira может использоваться username вместо email
- Проверьте права доступа к пользователям в Jira

### Ошибки планировщика

- Проверьте формат времени в `CHECK_TIME` (HH:MM)
- Убедитесь, что системное время корректно

### Отладка

Для детальной отладки установите:
```env
LOG_LEVEL=DEBUG
```

Полезные команды для диагностики:
```bash
# Проверка статуса
sudo systemctl status project-monitor-bot

# Детальные логи
sudo journalctl -u project-monitor-bot -f --since "1 hour ago"

# Тест подключений (используйте скрипт управления)
./manage_bot.sh test
```

## Безопасность

- Бот работает под отдельным пользователем или в виртуальном окружении
- Ограниченные права доступа к файловой системе
- Токены хранятся в защищенном `.env` файле
- Логирование всех операций

## Мониторинг

Для мониторинга работы бота рекомендуется:

1. Настроить алерты на статус systemd сервиса
2. Мониторить размер лог файла
3. Проверять последние записи в БД
4. Настроить уведомления о сбоях через Mattermost webhooks
