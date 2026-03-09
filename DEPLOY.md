# Деплой Project Monitor Bot (Docker)

## Требования

| Компонент | Минимальная версия |
|-----------|--------------------|
| Docker    | 20.10+             |
| Docker Compose | v2 (плагин `docker compose`) |
| Git       | 2.x                |
| RAM       | 256 МБ             |
| Диск      | 500 МБ             |

## Быстрая установка

```bash
# 1. Клонируем и устанавливаем (по умолчанию в /opt/project-monitor-bot)
git clone https://github.com/chastnik/mm_project_monitor_bot.git
cd mm_project_monitor_bot
sudo ./deploy/install.sh

# Или указать другую директорию:
sudo ./deploy/install.sh --dir /srv/monitor-bot
```

Скрипт выполнит:
- клонирование репозитория
- создание директории `data/` для персистентных данных
- создание `.env` из шаблона
- сборку Docker-образа

## Настройка

Отредактируйте `.env` в директории установки:

```bash
nano /opt/project-monitor-bot/.env
```

Обязательные параметры:

| Параметр | Описание |
|----------|----------|
| `MATTERMOST_URL` | URL вашего Mattermost-сервера |
| `MATTERMOST_TOKEN` | Токен бота (получите в Mattermost → Integrations → Bot Accounts) |
| `MATTERMOST_TEAM` | Название команды |
| `MATTERMOST_CHANNEL_ID` | ID канала для системных уведомлений |
| `JIRA_URL` | URL вашего Jira-сервера |
| `ADMIN_EMAILS` | Email-адреса администраторов через запятую |

> Пароли Jira **не нужны** в `.env` — пользователи настраивают доступ через
> личные сообщения боту: `setup_jira <username> <password>`.

## Запуск

```bash
cd /opt/project-monitor-bot
docker compose up -d
```

Проверка:

```bash
docker compose ps            # статус контейнера
docker compose logs -f       # логи в реальном времени
docker compose logs --tail 50 # последние 50 строк
```

## Обновление

```bash
cd /opt/project-monitor-bot
./deploy/update.sh
```

Скрипт автоматически:
1. Создаёт бэкап `data/` в `backups/`
2. Вытягивает изменения из git (`git pull`)
3. Пересобирает Docker-образ
4. Перезапускает контейнер
5. Удаляет старые Docker-образы

Дополнительные флаги:

```bash
./deploy/update.sh --dry-run     # показать изменения без применения
./deploy/update.sh --no-restart  # только собрать образ, не перезапускать
```

## Управление

```bash
# Остановить
docker compose stop

# Запустить
docker compose up -d

# Перезапустить
docker compose restart bot

# Посмотреть логи приложения (внутри контейнера)
docker compose logs -f

# Посмотреть логи из файла (на хосте)
tail -f data/standup_bot.log

# Зайти внутрь контейнера
docker compose exec bot sh
```

## Структура данных

```
/opt/project-monitor-bot/
├── .env                    # конфигурация (chmod 600)
├── data/
│   ├── standup_bot.db      # SQLite база данных
│   ├── standup_bot.log     # логи приложения
│   └── .crypto_salt        # соль шифрования паролей
├── backups/                # автобэкапы (создаются при обновлении)
│   └── data_backup_YYYYMMDD_HHMMSS/
├── docker-compose.yml
├── Dockerfile
└── ...                     # исходный код
```

> **Важно**: файл `.crypto_salt` содержит ключ шифрования паролей пользователей.
> При его потере все сохранённые пароли Jira станут нерасшифруемыми.
> Включайте `data/` в бэкапы.

## Резервное копирование

### Ручной бэкап

```bash
cd /opt/project-monitor-bot
cp -r data "backups/data_backup_$(date +%Y%m%d_%H%M%S)"
```

### Автоматический бэкап (cron)

```bash
# Ежедневный бэкап в 3:00
echo "0 3 * * * cd /opt/project-monitor-bot && cp -r data backups/data_backup_\$(date +\%Y\%m\%d_\%H\%M\%S) && find backups -maxdepth 1 -name 'data_backup_*' -mtime +30 -exec rm -rf {} +" | crontab -
```

## Мониторинг

Docker healthcheck проверяет, что процесс бота жив. Статус можно посмотреть:

```bash
docker inspect --format='{{.State.Health.Status}}' project-monitor-bot
```

Для интеграции с внешним мониторингом (Prometheus, Zabbix и т.д.) проверяйте:
- `docker compose ps` — контейнер в статусе `running (healthy)`
- наличие свежих записей в `data/standup_bot.log`

## Устранение проблем

### Контейнер не запускается

```bash
docker compose logs --tail 50
```

Частые причины:
- Неверный `MATTERMOST_TOKEN` → бот не может подключиться
- Недоступен `MATTERMOST_URL` → проверьте сеть и SSL
- `JIRA_VERIFY_SSL=true`, но сертификат самоподписанный → установите `false`

### Потеря .crypto_salt

Если файл потерян, пользователям нужно заново настроить Jira-доступ:

```
setup_jira <username> <password>
```

### Нехватка места на диске

```bash
# Очистить старые образы и кэши Docker
docker system prune -f

# Удалить старые бэкапы
find backups -maxdepth 1 -name "data_backup_*" -mtime +7 -exec rm -rf {} +
```
