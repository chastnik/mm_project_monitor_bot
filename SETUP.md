# Настройка Project Monitor Bot для Mattermost + Jira

## Описание

Бот для мониторинга проектов в Jira - отслеживание превышения трудозатрат и просроченных сроков выполнения задач с уведомлениями в Mattermost.

## Функциональность

- 🚨 **Мониторинг превышения трудозатрат** - уведомления когда фактическое время превышает плановое
- ⏰ **Отслеживание просроченных сроков** - уведомления о задачах с истекшим сроком выполнения
- 📢 **Уведомления в каналы** - отчеты для команды проекта
- 💬 **Персональные уведомления** - прямые сообщения ответственным за задачи
- 📋 **Подписки на проекты** - каждый канал может подписаться на мониторинг своего проекта
- 🔐 **Персональные настройки Jira** - каждый пользователь настраивает свое подключение к Jira
- 🗃️ **SQLite база данных** - хранение подписок, настроек и истории уведомлений

## Требования

- Python 3.8+
- Доступ к Mattermost API (бот токен)
- Персональный доступ к Jira API для каждого пользователя (логин/пароль)

## Быстрая установка

### 1. Скачайте и установите

```bash
git clone https://github.com/chastnik/mm_standup_bot.git project-monitor-bot
cd project-monitor-bot
chmod +x install.sh
./install.sh
```

### 2. Настройте конфигурацию

Отредактируйте файл `/opt/project-monitor-bot/.env`:

```bash
sudo nano /opt/project-monitor-bot/.env
```

### 3. Запустите сервис

```bash
sudo systemctl start project-monitor-bot
sudo systemctl enable project-monitor-bot
```

### 4. Настройте персональные подключения к Jira

Каждый пользователь должен настроить свое подключение к Jira:

1. Напишите боту в личных сообщениях: `setup_jira <ваш_логин> <ваш_пароль>`
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
   - **Username**: `standup-bot`
   - **Display Name**: `Standup Bot`
   - **Description**: `Бот для проверки планов в Jira`
5. Скопируйте **Access Token** - это значение для `MATTERMOST_TOKEN`

### Получение ID канала

1. Откройте канал в Mattermost
2. В адресной строке найдите ID канала (после `/channels/`)
3. Или используйте API: `GET /api/v4/teams/{team_id}/channels/name/{channel_name}`

### Настройка Jira API (on-premise)

Для on-premise Jira есть два варианта аутентификации:

#### Вариант 1: API токены (Jira Server 8.14+)
1. Войдите в Jira как администратор
2. Перейдите в **Administration** → **User Management**
3. Найдите пользователя для бота
4. Создайте **Personal Access Token**
5. В конфигурации установите:
   ```env
   JIRA_AUTH_METHOD=token
   JIRA_API_TOKEN=your_personal_access_token
   ```

#### Вариант 2: Логин/пароль (старые версии)
1. Создайте служебного пользователя в Jira
2. Дайте ему права на просмотр проектов и worklog
3. В конфигурации установите:
   ```env
   JIRA_AUTH_METHOD=password
   JIRA_PASSWORD=service_user_password
   ```

#### Настройка SSL
Для самоподписанных сертификатов:
```env
JIRA_VERIFY_SSL=false
```

## Конфигурация

### Основные параметры (.env файл)

```env
# Mattermost
MATTERMOST_URL=https://your-mattermost-server.com
MATTERMOST_TOKEN=your_bot_token_here
MATTERMOST_CHANNEL_ID=channel_id_for_reports

# Jira (on-premise)
JIRA_URL=https://jira.your-company.com
JIRA_USERNAME=service_user
JIRA_AUTH_METHOD=password  # или token
JIRA_PASSWORD=service_password  # для старых версий
# JIRA_API_TOKEN=personal_access_token  # для новых версий
JIRA_VERIFY_SSL=true


# Администраторы
ADMIN_EMAILS=admin1@company.com,admin2@company.com

# Расписание
CHECK_TIME=09:00
```

### Управление пользователями

Администраторы могут управлять списком отслеживаемых пользователей через команды боту:

```
add_user john.doe@company.com Иван Иванов
remove_user john.doe@company.com
list_users
```

## Команды бота

### Доступные всем:
- `help` - справка по командам
- `list_users` - список отслеживаемых пользователей  
- `history [дни]` - история проверок
- `status` - статус бота

### Только для администраторов:
- `add_user <email> [имя]` - добавить пользователя
- `remove_user <email>` - удалить пользователя
- `check_now` - запустить проверку вручную

## Управление сервисом

```bash
# Статус
sudo systemctl status standup-bot

# Запуск/остановка
sudo systemctl start standup-bot
sudo systemctl stop standup-bot
sudo systemctl restart standup-bot

# Автозапуск
sudo systemctl enable standup-bot
sudo systemctl disable standup-bot

# Логи
sudo journalctl -u standup-bot -f
sudo journalctl -u standup-bot --since "1 hour ago"
```

## Логи

Бот ведет логи в двух местах:
- **systemd journal**: `sudo journalctl -u standup-bot -f`
- **файл**: `/opt/standup-bot/standup_bot.log`

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
sudo systemctl status standup-bot

# Детальные логи
sudo journalctl -u standup-bot -f --since "1 hour ago"

# Тест подключений
sudo -u standup-bot /opt/standup-bot/venv/bin/python -c "
from config import config
from jira_tempo_client import jira_tempo_client
print('Jira:', jira_tempo_client.jira_client.current_user())
print('Tempo:', jira_tempo_client.test_tempo_connection())
"
```

## Безопасность

- Бот работает под отдельным пользователем `standup-bot`
- Ограниченные права доступа к файловой системе
- Токены хранятся в защищенном `.env` файле
- Логирование всех операций

## Мониторинг

Для мониторинга работы бота рекомендуется:

1. Настроить алерты на статус systemd сервиса
2. Мониторить размер лог файла
3. Проверять последние записи в БД
4. Настроить уведомления о сбоях через Mattermost webhooks
