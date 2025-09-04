# Настройка бота для проверки планов в Jira

## Описание

Бот для Mattermost, который ежедневно проверяет заполнение планов в Jira через плагин Tempo и отправляет уведомления.

## Функциональность

- ✅ Ежедневная проверка заполнения worklog в Jira через Tempo API
- 📊 Отправка отчетов в указанный канал Mattermost  
- 💬 Персональные напоминания пользователям, не заполнившим планы
- 🗃️ Управление списком отслеживаемых пользователей через SQLite БД
- 🔧 Команды администратора для управления ботом
- 📈 История проверок и статистика

## Требования

- Python 3.8+
- Доступ к Mattermost API (бот токен)
- Доступ к Jira API (API токен)
- Доступ к Tempo API (API токен)

## Быстрая установка

### 1. Скачайте и установите

```bash
git clone <repository-url> standup-bot
cd standup-bot
chmod +x install.sh
./install.sh
```

### 2. Настройте конфигурацию

Отредактируйте файл `/opt/standup-bot/.env`:

```bash
sudo nano /opt/standup-bot/.env
```

### 3. Запустите сервис

```bash
sudo systemctl start standup-bot
sudo systemctl enable standup-bot
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

### Настройка Tempo API

#### Для Tempo Cloud:
1. Войдите в Tempo
2. Перейдите в **Settings** → **API Integration**
3. Создайте новый API токен
4. Используйте стандартный URL: `https://api.tempo.io/core/3`

#### Для on-premise Tempo:
1. Узнайте у администратора URL вашего Tempo API
2. Обычно это: `https://your-jira-server.com/rest/tempo-timesheets/4`
3. Получите API токен или используйте аутентификацию Jira
4. В конфигурации установите:
   ```env
   TEMPO_API_URL=https://your-jira-server.com/rest/tempo-timesheets/4
   TEMPO_VERIFY_SSL=false  # если нужно
   ```

#### Fallback через Jira API:
Если Tempo API недоступен, бот автоматически попробует получить worklog через стандартный Jira API. Это может работать медленнее, но не требует отдельного Tempo токена.

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

# Tempo API
TEMPO_API_TOKEN=your_tempo_token
TEMPO_API_URL=https://jira.your-company.com/rest/tempo-timesheets/4
TEMPO_VERIFY_SSL=true

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
