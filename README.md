# Project Monitor Bot для Mattermost + Jira

🤖 Бот для мониторинга проектов в Jira - отслеживание превышения трудозатрат и просроченных сроков выполнения задач с уведомлениями в Mattermost.

🔐 **Версия с улучшенной безопасностью** - пароли пользователей шифруются современными алгоритмами, отсутствуют глобальные пароли в конфигурации.

## Возможности

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
- 📊 **Просмотр проектов** - команда для просмотра всех доступных проектов в Jira
- 🔧 **Поддержка on-premise** Jira

## Поддерживаемые системы

- **Mattermost** (любая версия с поддержкой ботов)
- **Jira Server/Data Center** (on-premise) с аутентификацией по паролю или API токенам

## Быстрый старт

### 1. Установка

```bash
git clone https://github.com/chastnik/mm_project_monitor_bot.git
cd mm_project_monitor_bot
chmod +x install.sh
./install.sh
```

### 2. Настройка

Скопируйте и отредактируйте конфигурацию:

```bash
cp env.example .env
nano .env
```

⚠️ **Важно**: Глобальные пароли Jira больше не требуются в `.env`! Каждый пользователь настраивает доступ через команды бота.

### 3. Запуск

```bash
# Рекомендуемый способ
./start_bot.sh prod

# Альтернативно - управление через скрипт
./manage_bot.sh start

# Для разработки
./start_bot.sh dev
# или
python main.py
```

## Конфигурация

### Основные параметры

```env
# Mattermost
MATTERMOST_URL=https://your-mattermost-server.com
MATTERMOST_TOKEN=your_bot_token
MATTERMOST_CHANNEL_ID=channel_id_for_reports

# Jira (on-premise) - только URL, без глобальных паролей!
JIRA_URL=https://jira.your-company.com
JIRA_VERIFY_SSL=true

# Tempo API
TEMPO_API_URL=https://jira.your-company.com/rest/tempo-timesheets/4
TEMPO_API_TOKEN=your_tempo_token


# Администраторы и расписание
ADMIN_EMAILS=admin1@company.com,admin2@company.com
CHECK_TIME=12:00
```

## Настройка каналов

### Добавление бота в канал

**⚠️ Обязательно:** Перед использованием команд в каналах бот должен быть добавлен в канал!

**Пошаговая инструкция:**
1. Зайти в нужный канал в Mattermost
2. Нажать на название канала → "Управление каналом"
3. Выбрать "Участники" → "Добавить участников"
4. Найти бота по имени (например, `jora` или `standup-bot`)
5. Добавить бота в канал
6. Проверить: отправить команду `help` в канал

## Команды бота

### Вход в Jira (Personal Access Token):
- `login <PAT>` / `войти <PAT>` / `setup_jira <PAT>` - войти в Jira по персональному токену (только в личных сообщениях)
- `setup_jira` - показать текущее подключение
- `test_jira` - проверить подключение к Jira
- `logout` / `выйти` - удалить сохраненный токен

**Как получить Personal Access Token (Jira Server / Data Center 8.14+):**
1. Откройте Jira → аватар справа вверху → **Профиль** → **Personal Access Tokens**
   (`<JIRA_URL>/secure/ViewProfile.jspa?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens`)
2. Нажмите **Create token**, укажите название (например, `Project Monitor Bot`) и при желании срок действия
3. Скопируйте токен — Jira покажет его только один раз
4. Отправьте боту **в личные сообщения**: `login <токен>`

### Просмотр проектов:
- `list_projects` - показать все доступные проекты в Jira

### Управление подписками (в каналах):
- **⚠️ Важно:** Бот должен быть добавлен в канал перед выполнением команд!
- **⚠️ Важно:** Команды в каналах работают только с упоминанием бота: `@Жора команда`
- `subscribe PROJECT_KEY` - подписать канал на мониторинг проекта
- `unsubscribe PROJECT_KEY` - отписать канал от мониторинга проекта
- `list_subscriptions` - показать активные подписки в канале

### Управление мониторингом:
- `run_subscriptions` - запустить проверку подписок текущего канала вручную
- `history [дни]` - история уведомлений
- `status` - статус бота и активные подписки

### Аналитика и графики:
- `analytics PROJECT_KEY` / `аналитика PROJECT_KEY` / `графики PROJECT_KEY` - аналитика проекта с графиками

### Информационные команды:
- `help` - справка по командам

### Только для администраторов:
- `monitor_now` - запустить мониторинг всех проектов вручную
- `all_subscriptions` - просмотреть все подписки в системе
- `delete_subscription PROJECT_KEY CHANNEL_ID` - удалить конкретную подписку
- `list_users` - список пользователей с настройками Jira

### Алиасы команд:
Бот поддерживает естественные алиасы для всех команд:
- `help` / `справка` / `помощь` / `хелп` / `команды` / `что умеешь`
- `подписки` / `список подписок` / `мои подписки` / `что отслеживаешь`
- `проекты` / `список проектов` / `все проекты` / `доступные проекты` / `показать проекты` / `какие проекты`
- `подпиши` / `подпиши на проект` / `мониторить` / `отслеживать`
- `отпиши` / `отпиши от проекта` / `не мониторить` / `не отслеживать`
- `проверь` / `проверь подписки` / `запусти проверку` / `мониторинг`
- `login` / `войти` / `вход` / `токен` / `настрой jira` / `настрой подключение` / `настрой джиру`
- `проверь jira` / `тест jira` / `проверь подключение`
- `logout` / `выйти` / `выход`
- `история` / `история уведомлений` / `что было`
- `статус` / `как дела` / `что происходит`
- `аналитика` / `аналитика проекта` / `покажи аналитику` / `графики` / `покажи графики` / `charts`
- `запусти мониторинг` / `мониторинг сейчас` / `проверь все` / `проверь всё`
- `все подписки` / `все подписки системы`
- `удали подписку` / `удалить подписку`
- `пользователи` / `список пользователей` / `кто подключен`

## Архитектура системы

### Компоненты и связи

```mermaid
graph TB
    subgraph "Внешние системы"
        MM[Mattermost Server<br/>WebSocket + API]
        JIRA[Jira Server]
        TEMPO[Tempo API]
    end
    
    subgraph "Project Monitor Bot"
        MAIN[main.py<br/>Основной запуск]
        CONFIG[config.py<br/>Конфигурация]
        
        subgraph "Клиенты внешних API"
            MMC[mattermost_client.py<br/>WebSocket + API клиент]
            UJC[user_jira_client.py<br/>Персональные подключения]
        end
        
        subgraph "Безопасность и данные"
            CRYPTO[crypto_utils.py<br/>Шифрование паролей]
            DB[database.py<br/>SQLite БД]
        end
        
        subgraph "Бизнес-логика"
            MONITOR[project_monitor.py<br/>Мониторинг проектов]
            SCHED[scheduler.py<br/>Планировщик]
            COMMANDS[bot_commands.py<br/>Команды + алиасы]
        end
    end
    
    subgraph "Управление"
        START[start_bot.sh<br/>Запуск с проверками]
        MANAGE[manage_bot.sh<br/>Управление ботом]
        STOP[stop_bot.sh<br/>Остановка]
    end
    
    MAIN --> CONFIG
    MAIN --> MMC
    MAIN --> SCHED
    MAIN --> COMMANDS
    
    MMC -->|WebSocket| MM
    MMC -->|API| MM
    UJC --> JIRA
    UJC --> TEMPO
    
    COMMANDS --> UJC
    COMMANDS --> DB
    MONITOR --> UJC
    MONITOR --> MMC
    
    DB --> CRYPTO
    UJC --> DB
    
    SCHED --> MONITOR
    
    START -.-> MAIN
    MANAGE -.-> MAIN
    STOP -.-> MAIN
    
    classDef external fill:#e1f5fe
    classDef security fill:#f3e5f5
    classDef main fill:#e8f5e8
    classDef scripts fill:#fff3e0
    
    class MM,JIRA,TEMPO external
    class CRYPTO,DB security
    class MAIN main
    class START,MANAGE,STOP scripts
```

### Структура файлов

```
├── main.py                 # Основной файл запуска
├── config.py              # Управление конфигурацией  
├── crypto_utils.py         # 🔐 Шифрование паролей пользователей
├── database.py            # Работа с SQLite БД (подписки, настройки, уведомления)
├── mattermost_client.py   # WebSocket + API интеграция с Mattermost
├── user_jira_client.py    # Персональные подключения к Jira с кешированием
├── project_monitor.py     # Мониторинг проектов и задач
├── scheduler.py           # Планировщик ежедневных проверок
├── bot_commands.py        # Обработка команд + алиасы + подсказки
├── start_bot.sh           # 🔧 Скрипт запуска с проверками безопасности
├── manage_bot.sh          # 🔧 Универсальное управление ботом
├── stop_bot.sh            # 🔧 Безопасная остановка бота
├── requirements.txt       # Зависимости (включая websockets, cryptography)
├── README.md              # Документация проекта
├── SETUP.md               # Подробная инструкция по настройке
├── USER_GUIDE.md          # Руководство пользователя
└── env.example            # Пример конфигурации
```

## Процесс работы с ботом

```mermaid
flowchart TD
    START([Пользователь отправляет команду боту])
    
    CHANNEL{Команда в<br/>канале?}
    
    MENTION_CHECK{Есть упоминание<br/>@Жора/@Jora?}
    
    DIRECT_MSG[Личное сообщение<br/>Обработка команд]
    CHANNEL_MSG[Команда в канале<br/>Требует упоминания бота]
    
    ALIAS_CHECK[Проверка алиасов команд<br/>проекты → list_projects<br/>подписки → list_subscriptions]
    
    COMMAND_TYPE{Тип команды?}
    
    SETUP_JIRA[login PAT<br/>🔐 Шифрование токена]
    TEST_JIRA[test_jira<br/>Проверка подключения]
    LIST_PROJECTS[list_projects<br/>Показать все проекты]
    SUBSCRIBE[subscribe PROJECT_KEY<br/>Подписка на проект]
    LIST_SUBS[list_subscriptions<br/>Показать подписки]
    HELP[help<br/>Справка по командам]
    
    JIRA_REQUIRED{Требует настройки<br/>Jira?}
    
    JIRA_SETUP[Настройка Jira<br/>Проверка подключения]
    NO_JIRA[❌ Войдите в Jira<br/>login PAT]
    
    MONITOR_CYCLE[📊 Ежедневный мониторинг<br/>по расписанию]
    
    CHECK_ISSUES[Проверка задач:<br/>• Превышение трудозатрат<br/>• Просроченные сроки]
    
    ISSUES_FOUND{Найдены<br/>проблемы?}
    
    SEND_NOTIFICATIONS[📢 Уведомления:<br/>• В канал команды<br/>• Личные сообщения<br/>• Ссылки на задачи Jira]
    
    SAVE_HISTORY[💾 Сохранение истории<br/>уведомлений в БД]
    
    END([Ответ отправлен])
    
    START --> CHANNEL
    
    CHANNEL -->|Да| MENTION_CHECK
    CHANNEL -->|Нет| DIRECT_MSG
    
    MENTION_CHECK -->|Да| CHANNEL_MSG
    MENTION_CHECK -->|Нет| END
    
    DIRECT_MSG --> ALIAS_CHECK
    CHANNEL_MSG --> ALIAS_CHECK
    
    ALIAS_CHECK --> COMMAND_TYPE
    
    COMMAND_TYPE -->|Настройка| SETUP_JIRA
    COMMAND_TYPE -->|Проверка| TEST_JIRA
    COMMAND_TYPE -->|Проекты| LIST_PROJECTS
    COMMAND_TYPE -->|Подписка| SUBSCRIBE
    COMMAND_TYPE -->|Список| LIST_SUBS
    COMMAND_TYPE -->|Справка| HELP
    
    SETUP_JIRA --> JIRA_SETUP
    TEST_JIRA --> JIRA_REQUIRED
    LIST_PROJECTS --> JIRA_REQUIRED
    SUBSCRIBE --> JIRA_REQUIRED
    LIST_SUBS --> END
    HELP --> END
    
    JIRA_REQUIRED -->|Да| JIRA_SETUP
    JIRA_REQUIRED -->|Нет| NO_JIRA
    
    JIRA_SETUP --> END
    NO_JIRA --> END
    
    MONITOR_CYCLE --> CHECK_ISSUES
    CHECK_ISSUES --> ISSUES_FOUND
    
    ISSUES_FOUND -->|Да| SEND_NOTIFICATIONS
    SEND_NOTIFICATIONS --> SAVE_HISTORY
    SAVE_HISTORY --> END
    ISSUES_FOUND -->|Нет| END
    
    classDef startEnd fill:#e8f5e8,stroke:#4caf50,stroke-width:2px
    classDef process fill:#e3f2fd,stroke:#2196f3,stroke-width:2px
    classDef decision fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef security fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px
    classDef error fill:#ffebee,stroke:#f44336,stroke-width:2px
    
    class START,END startEnd
    class SETUP_JIRA,TEST_JIRA,LIST_PROJECTS,SUBSCRIBE,LIST_SUBS,HELP,JIRA_SETUP,MONITOR_CYCLE,CHECK_ISSUES,SEND_NOTIFICATIONS,SAVE_HISTORY process
    class CHANNEL,MENTION_CHECK,COMMAND_TYPE,JIRA_REQUIRED,ISSUES_FOUND decision
    class SETUP_JIRA security
    class NO_JIRA error
```

## Безопасность

🔐 **Современная система безопасности:**
- **Шифрование паролей**: все пароли пользователей шифруются AES-256 с PBKDF2HMAC
- **Отсутствие глобальных паролей**: нет централизованных учетных данных в конфигурации
- **Персональные подключения**: каждый пользователь использует свои права доступа к Jira
- **Безопасные файлы**: база данных и ключи шифрования защищены правами доступа 600
- **Обратная совместимость**: поддержка миграции старых незашифрованных данных

🛡️ **Меры защиты:**
- **Криптографическая соль**: уникальный ключ шифрования в файле `.crypto_salt`
- **Проверка зависимостей**: автоматическая проверка библиотеки `cryptography` при запуске
- **Изоляция процессов**: рекомендуется запуск от отдельного пользователя
- **Логирование безопасности**: все операции с паролями логируются без раскрытия данных

✅ **Гарантии безопасности:**
- Пароли **никогда** не хранятся в открытом виде
- Ключи шифрования **не попадают** в систему контроля версий
- Доступ к данным **только** у владельца файлов
- **Невозможность** расшифровки без доступа к серверу

## Требования

- **Python 3.12+** (рекомендуется 3.15 — на нем собирается Docker-образ)
- **Библиотека cryptography** ≥ 45.0.0 для шифрования токенов
- **Библиотека websockets** ≥ 11.0.0 для WebSocket соединения
- **Доступ к Mattermost API** (бот токен)
- **WebSocket поддержка** в Mattermost для реального времени
- **Jira Server / Data Center 8.14+** с включенными Personal Access Tokens; каждый пользователь входит по своему PAT
- **Права на создание файлов** для базы данных и ключей шифрования

## Примеры использования

### Настройка пользователя
```
# Личные сообщения с ботом
login <ваш_PAT>
test_jira
```

### Работа в канале
```
# Просмотр доступных проектов
@Жора проекты

# Подписка на проект
@Жора подпиши на проект IDB

# Просмотр подписок
@Жора подписки

# Ручная проверка
@Жора проверь подписки
```

### Алиасы команд
```
# Все эти команды работают одинаково:
@Жора проекты
@Жора список проектов
@Жора все проекты

@Жора подписки
@Жора список подписок
@Жора что отслеживаешь

@Жора подпиши на проект IDB
@Жора мониторить IDB
@Жора отслеживать IDB
```

### Уведомления
Бот отправляет уведомления с кликабельными ссылками:
```
🚨 Превышение трудозатрат

📋 Задача: [PROJ-123](https://jira.company.com/browse/PROJ-123) - Разработка функции
👤 Ответственный: Иван Петров
⏱️ Плановые часы: 8.0ч
📈 Фактические часы: 12.0ч
❗ Превышение: 4.0ч
```

## Развертывание

Подробная инструкция по настройке и развертыванию в файле [SETUP.md](SETUP.md).

## Управление ботом

### Запуск и остановка

```bash
# Рекомендуемый способ запуска
./start_bot.sh prod

# Альтернативно - через управляющий скрипт  
./manage_bot.sh start

# Остановка
./stop_bot.sh
# или
./manage_bot.sh stop

# Перезапуск
./manage_bot.sh restart
```

### Мониторинг и диагностика

```bash
# Статус бота
./manage_bot.sh status

# Просмотр логов
./manage_bot.sh logs

# Логи в реальном времени
./manage_bot.sh tail

# Проверка подключений
./manage_bot.sh test
```

### Настройка пользователей

После запуска бота каждый пользователь должен настроить свой доступ к Jira:

```
# В личных сообщениях с ботом
login <ваш_PAT>
test_jira

# В канале команды для подписки на проект
subscribe PROJECT_KEY
```

## Лицензия

MIT License - см. файл [LICENSE](LICENSE) для деталей.

## Поддержка

Если у вас есть вопросы или предложения:

1. Создайте [Issue](https://github.com/chastnik/mm_project_monitor_bot/issues) в GitHub
2. Проверьте [SETUP.md](SETUP.md) для решения типовых проблем
3. Изучите логи бота для диагностики
