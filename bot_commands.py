"""
Обработчик команд бота
"""

import logging
import re

from database import db_manager
from mattermost_client import mattermost_client
from scheduler import scheduler

logger = logging.getLogger(__name__)


class BotCommandHandler:
    def __init__(self):
        self.commands = {
            "help": self.cmd_help,
            "subscribe": self.cmd_subscribe,
            "unsubscribe": self.cmd_unsubscribe,
            "list_subscriptions": self.cmd_list_subscriptions,
            "list_projects": self.cmd_list_projects,
            "setup_jira": self.cmd_setup_jira,
            "test_jira": self.cmd_test_jira,
            "change_password": self.cmd_change_password,
            "run_subscriptions": self.cmd_run_subscriptions,
            "monitor_now": self.cmd_monitor_now,
            "all_subscriptions": self.cmd_all_subscriptions,
            "delete_subscription": self.cmd_delete_subscription,
            "history": self.cmd_history,
            "status": self.cmd_status,
            "analytics": self.cmd_analytics,
            "list_users": self.cmd_list_users,
        }

    def handle_message(
        self,
        message_text: str,
        user_email: str,
        channel_type: str = "D",
        channel_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
    ) -> str | None:
        """
        Обработать сообщение пользователя
        channel_type: 'D' для личных сообщений, 'O' для открытых каналов
        """
        if not message_text.strip():
            return None

        # Отладочная информация
        logger.info(f"🔍 bot_commands: message_text={message_text}, type={type(message_text)}")

        # Проверяем тип message_text
        if isinstance(message_text, list):
            logger.info(f"🔍 Преобразуем список в строку: {message_text}")
            message_text = " ".join(message_text)
            logger.info(f"🔍 Результат: {message_text}, type={type(message_text)}")

        # Убираем упоминание бота только в каналах и ТОЛЬКО в начале сообщения,
        # чтобы не ломать пароли/аргументы, начинающиеся с символа '@'
        if channel_type != "D":
            bot_names = []
            try:
                if getattr(mattermost_client, "bot_username", None):
                    bot_names.append(mattermost_client.bot_username)
            except Exception:
                pass
            # Добавляем общеизвестные варианты имен бота
            bot_names.extend(["jora", "Жора", "project-monitor-bot", "project_monitor_bot"])
            # Формируем паттерн: начальное упоминание любого из имен
            escaped = [re.escape(name) for name in bot_names if name]
            if escaped:
                pattern = r"^\s*@(" + "|".join(escaped) + r")\b\s*"
                message_text = re.sub(pattern, "", message_text, flags=re.IGNORECASE).strip()

        # Парсим команду
        parts = message_text.split()
        if not parts:
            return None

        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Маппинг алиасов команд
        command_aliases = {
            "help": "help",
            "справка": "help",
            "помощь": "help",
            "хелп": "help",
            "команды": "help",
            "что умеешь": "help",
            "subscribe": "subscribe",
            "подписка": "subscribe",
            "подпиши": "subscribe",
            "подпиши на проект": "subscribe",
            "проект": "subscribe",
            "мониторить": "subscribe",
            "отслеживать": "subscribe",
            "unsubscribe": "unsubscribe",
            "отписка": "unsubscribe",
            "отпиши": "unsubscribe",
            "отпиши от проекта": "unsubscribe",
            "не мониторить": "unsubscribe",
            "не отслеживать": "unsubscribe",
            "list_subscriptions": "list_subscriptions",
            "подписки": "list_subscriptions",
            "список подписок": "list_subscriptions",
            "мои подписки": "list_subscriptions",
            "что отслеживаешь": "list_subscriptions",
            "list_projects": "list_projects",
            "проекты": "list_projects",
            "список проектов": "list_projects",
            "все проекты": "list_projects",
            "доступные проекты": "list_projects",
            "показать проекты": "list_projects",
            "какие проекты": "list_projects",
            "setup_jira": "setup_jira",
            "настрой jira": "setup_jira",
            "настрой подключение": "setup_jira",
            "jira настройка": "setup_jira",
            "настрой джира": "setup_jira",
            "настрой джиру": "setup_jira",
            "test_jira": "test_jira",
            "проверь jira": "test_jira",
            "тест jira": "test_jira",
            "проверь подключение": "test_jira",
            "change_password": "change_password",
            "смени пароль": "change_password",
            "измени пароль": "change_password",
            "новый пароль": "change_password",
            "run_subscriptions": "run_subscriptions",
            "проверь": "run_subscriptions",
            "проверь подписки": "run_subscriptions",
            "запусти проверку": "run_subscriptions",
            "мониторинг": "run_subscriptions",
            "history": "history",
            "история": "history",
            "история уведомлений": "history",
            "что было": "history",
            "status": "status",
            "статус": "status",
            "как дела": "status",
            "что происходит": "status",
            "analytics": "analytics",
            "аналитика": "analytics",
            "аналитика проекта": "analytics",
            "покажи аналитику": "analytics",
            "monitor_now": "monitor_now",
            "запусти мониторинг": "monitor_now",
            "мониторинг сейчас": "monitor_now",
            "проверь все": "monitor_now",
            "проверь всё": "monitor_now",
            "all_subscriptions": "all_subscriptions",
            "все подписки": "all_subscriptions",
            "все подписки системы": "all_subscriptions",
            "delete_subscription": "delete_subscription",
            "удали подписку": "delete_subscription",
            "удалить подписку": "delete_subscription",
            "list_users": "list_users",
            "пользователи": "list_users",
            "список пользователей": "list_users",
            "кто подключен": "list_users",
        }

        # Преобразуем алиас в основную команду
        # 1) Пробуем 3-словный, 2-словный алиасы, затем одно слово
        multi_keys = []
        if len(parts) >= 3:
            multi_keys.append((parts[0] + " " + parts[1] + " " + parts[2]).lower())
        if len(parts) >= 2:
            multi_keys.append((parts[0] + " " + parts[1]).lower())
        multi_keys.append(command)
        for key in multi_keys:
            if key in command_aliases:
                command = command_aliases[key]
                # Пересчитаем args, убрав количество слов, занятых алиасом
                consumed = len(key.split())
                args = parts[consumed:]
                break

        # Проверяем права доступа для админских команд
        admin_commands = ["monitor_now", "all_subscriptions", "delete_subscription", "list_users"]
        if command in admin_commands and not mattermost_client.is_user_admin(user_email):
            return "❌ У вас нет прав для выполнения этой команды"

        # Выполняем команду
        if command in self.commands:
            try:
                # Передаем дополнительные параметры для команд подписки
                if command in ["subscribe", "unsubscribe", "list_subscriptions", "run_subscriptions"]:
                    return self.commands[command](args, user_email, channel_id, team_id, user_id)
                elif command in ["setup_jira", "test_jira", "change_password"]:
                    return self.commands[command](args, user_email, user_id)
                elif command == "analytics":
                    return self.commands[command](args, user_email, channel_id, user_id)
                else:
                    return self.commands[command](args, user_email)
            except Exception as e:
                logger.error(f"Ошибка выполнения команды {command}: {e}")
                return f"❌ Ошибка выполнения команды: {e!s}"
        else:
            return self.cmd_help([], user_email)

    def cmd_analytics(
        self, args: list[str], user_email: str, channel_id: str | None = None, user_id: str | None = None
    ) -> str:
        """Показать расширенную аналитику проекта в Jira"""
        if not args:
            return "❌ Укажите ключ проекта: `аналитика PROJECT_KEY` или `analytics PROJECT_KEY`"
        # Нормализуем: пропустим служебные слова и возьмём последний валидный токен
        import re

        tokens = [t for t in args if t and t.strip()]
        if tokens and tokens[0].lower() in ["проекта", "project", "проекта:", "project:"]:
            tokens = tokens[1:]
        # Ищем последний токен похожий на ключ (буквы/цифры/_/-)
        project_key = None
        for t in reversed(tokens):
            if re.match(r"^[A-Za-zА-Яа-я0-9_-]+$", t):
                project_key = t.upper()
                break
        if not project_key:
            return "❌ Не удалось распознать ключ проекта. Пример: `аналитика IDB`"

        # Проверяем настройки Jira пользователя
        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            return """❌ **Настройки Jira не найдены**

Сначала настройте подключение командой: `setup_jira <username> <password>`"""

        if not channel_id:
            return "❌ Команда доступна только в каналах или личных сообщениях с ботом"

        try:
            from mattermost_client import mattermost_client
            from project_analytics import ProjectAnalytics

            # Получаем аналитику и путь к изображению
            analytics = ProjectAnalytics()
            report_text, image_path = analytics.build_project_analytics(user_email, project_key)

            if report_text:
                # Отправляем текстовый отчет
                mattermost_client.send_channel_message(channel_id, report_text)

                # Отправляем изображение, если оно было создано
                if image_path:
                    mattermost_client.upload_image(
                        channel_id, image_path, f"📊 Аналитика проекта {project_key}", root_id=None
                    )
                return None  # Сообщение уже отправлено через send_channel_message и upload_image
            else:
                return f"❌ Не удалось получить аналитику для проекта {project_key}. Проверьте ключ проекта и ваше подключение к Jira."

        except Exception as e:
            logger.error(f"Ошибка выполнения команды аналитики для проекта {project_key}: {e}")
            return f"❌ Ошибка при получении аналитики проекта: {e!s}"

    def cmd_help(self, args: list[str], user_email: str) -> str:
        """Показать справку по командам"""
        is_admin = mattermost_client.is_user_admin(user_email)

        help_text = """📋 **Команды бота мониторинга проектов**

**Настройка подключения к Jira:**
• `setup_jira <username> <password>` - настроить подключение к Jira
• `test_jira` - проверить подключение к Jira
• `change_password <new_password>` - изменить пароль для Jira

**Просмотр проектов:**
• `list_projects` - показать все доступные проекты в Jira

**Управление подписками на проекты:**
• `subscribe <PROJECT_KEY>` - подписать канал на мониторинг проекта
• `unsubscribe <PROJECT_KEY>` - отписать канал от мониторинга проекта
• `list_subscriptions` - показать активные подписки в канале

**Управление мониторингом:**
• `run_subscriptions` - запустить проверку подписок текущего канала
• `history` - история уведомлений за последние дни
• `status` - статус бота и активные подписки

**Информационные команды:**
• `help` - показать эту справку
• `analytics PROJECT_KEY` / `аналитика PROJECT_KEY` - расширенная аналитика проекта (с графиками)

"""

        if is_admin:
            help_text += """**Команды администратора:**
• `monitor_now` - запустить мониторинг всех проектов сейчас
• `all_subscriptions` - просмотреть все подписки в системе
• `delete_subscription <PROJECT_KEY> <CHANNEL_ID>` - удалить подписку
• `list_users` - список пользователей с настройками Jira

"""
        else:
            help_text += """**Команды администратора:**
• _Доступны только администраторам_

"""

        help_text += """**Примеры использования:**
• `setup_jira myuser mypassword` - настроить подключение к Jira
• `list_projects` - посмотреть все доступные проекты
• `subscribe MYPROJ` - подписаться на мониторинг проекта MYPROJ
• `test_jira` - проверить подключение

**Что мониторит бот:**
🚨 **Превышение трудозатрат** - когда фактическое время превышает плановое
⏰ **Просроченные сроки** - когда срок выполнения задачи истек, а она не закрыта

ℹ️ **Важно:** Каждый пользователь должен настроить свое подключение к Jira перед созданием подписок."""

        return help_text

    def cmd_subscribe(
        self,
        args: list[str],
        user_email: str,
        channel_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Подписать канал на мониторинг проекта"""
        if not args:
            return "❌ Укажите ключ проекта: `subscribe PROJECT_KEY`"

        if not channel_id:
            return "❌ Команда доступна только в каналах"

        project_key = args[0].upper()

        # Проверяем настройки Jira пользователя
        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            return """❌ **Настройки Jira не найдены**

Перед подпиской на проекты необходимо настроить подключение к Jira.
Используйте команду: `setup_jira`"""

        try:
            from user_jira_client import user_jira_client

            # Проверяем существование проекта в Jira через персональное подключение
            project_info = user_jira_client.get_project_info(user_email, project_key)
            if not project_info:
                return f"❌ Проект {project_key} не найден в Jira или нет доступа"

            project_key, project_name = project_info

            # Подписываем канал
            success = db_manager.subscribe_to_project(
                project_key, project_name, channel_id, team_id, user_id, user_email
            )

            if success:
                return (
                    f"✅ Канал подписан на мониторинг проекта **{project_key}** ({project_name})\n\n"
                    f"Бот будет ежедневно проверять задачи проекта и отправлять уведомления о:\n"
                    f"🚨 Превышении трудозатрат\n"
                    f"⏰ Просроченных сроках"
                )
            else:
                return "❌ Ошибка подписки на проект"

        except Exception as e:
            if "does not exist" in str(e) or "No project could be found" in str(e):
                return f"❌ Проект {project_key} не найден в Jira"
            else:
                logger.error(f"Ошибка подписки на проект {project_key}: {e}")
                return f"❌ Ошибка подписки на проект: {e!s}"

    def cmd_unsubscribe(
        self,
        args: list[str],
        user_email: str,
        channel_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Отписать канал от мониторинга проекта"""
        if not args:
            return "❌ Укажите ключ проекта: `unsubscribe PROJECT_KEY`"

        if not channel_id:
            return "❌ Команда доступна только в каналах"

        project_key = args[0].upper()

        success = db_manager.unsubscribe_from_project(project_key, channel_id)

        if success:
            return f"✅ Канал отписан от мониторинга проекта **{project_key}**"
        else:
            return f"❌ Подписка на проект {project_key} не найдена в этом канале"

    def cmd_list_subscriptions(
        self,
        args: list[str],
        user_email: str,
        channel_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Показать активные подписки в канале"""
        if not channel_id:
            return "❌ Команда доступна только в каналах"

        subscriptions = db_manager.get_subscriptions_by_channel(channel_id)

        if not subscriptions:
            return (
                "📋 В этом канале нет активных подписок на проекты\n\n"
                "Используйте `subscribe PROJECT_KEY` для подписки на мониторинг проекта"
            )

        result = f"📋 **Активные подписки в канале ({len(subscriptions)}):**\n\n"

        for project_key, project_name, subscribed_by, created_at, _active in subscriptions:
            result += f"• **{project_key}** - {project_name}\n"
            result += f"  _Подписал: {subscribed_by}, {created_at[:10]}_\n\n"

        result += "Для отписки используйте: `unsubscribe PROJECT_KEY`"

        return result

    def cmd_list_projects(self, args: list[str], user_email: str, user_id: str | None = None) -> str:
        """Показать все доступные проекты в Jira"""
        try:
            from user_jira_client import user_jira_client

            # Получаем клиент Jira для пользователя
            jira_client = user_jira_client.get_jira_client(user_email)
            if not jira_client:
                return """❌ **Не удалось подключиться к Jira**

Сначала настройте подключение командой: `setup_jira username password`"""

            # Получаем все проекты без ограничений через прямой вызов API
            # Jira API возвращает максимум 50 проектов за раз по умолчанию, поэтому используем пагинацию
            all_projects = []
            start_at = 0
            max_results = 50

            # Простой класс для представления проекта
            class Project:
                def __init__(self, data):
                    self.key = data.get("key", "")
                    self.name = data.get("name", "")
                    self.id = data.get("id", "")

            try:
                while True:
                    # Используем прямой вызов к REST API для получения всех проектов
                    url = jira_client._options["server"] + "/rest/api/2/project"
                    params = {
                        "startAt": start_at,
                        "maxResults": max_results,
                        "expand": "description,lead,url,projectKeys",
                    }

                    response = jira_client._session.get(url, params=params)
                    response.raise_for_status()
                    projects_data = response.json()

                    if not projects_data:
                        break

                    # Преобразуем данные в объекты Project
                    for project_data in projects_data:
                        all_projects.append(Project(project_data))

                    # Если получили меньше max_results, значит это последняя страница
                    if len(projects_data) < max_results:
                        break

                    start_at += max_results

                projects = all_projects
                logger.info(f"Получено {len(projects)} проектов через API с пагинацией")

            except Exception as api_error:
                # Если прямой вызов API не сработал, используем стандартный метод
                logger.warning(f"Не удалось получить все проекты через API, используем стандартный метод: {api_error}")
                try:
                    projects = list(jira_client.projects())
                    logger.info(f"Получено {len(projects)} проектов через стандартный метод")
                except Exception as e:
                    logger.error(f"Ошибка получения проектов: {e}")
                    return f"❌ **Ошибка получения списка проектов:** {e!s}"

            if not projects:
                return "ℹ️ **Доступные проекты не найдены**"

            # Формируем список проектов
            result = f"📋 **Доступные проекты в Jira ({len(projects)}):**\n\n"

            # Группируем проекты по первым буквам для удобства
            projects_by_letter = {}
            for project in projects:
                first_letter = project.key[0].upper()
                if first_letter not in projects_by_letter:
                    projects_by_letter[first_letter] = []
                projects_by_letter[first_letter].append(project)

            # Сортируем по ключам
            for letter in sorted(projects_by_letter.keys()):
                result += f"**{letter}:**\n"
                for project in sorted(projects_by_letter[letter], key=lambda x: x.key):
                    result += f"• `{project.key}` - {project.name}\n"
                result += "\n"

            result += "💡 **Для подписки на проект используйте:** `subscribe PROJECT_KEY`\n"
            if projects:
                result += f"**Пример:** `subscribe {projects[0].key}`"

            return result

        except Exception as e:
            logger.error(f"Ошибка получения списка проектов: {e}")
            return f"❌ **Ошибка получения проектов:** {e!s}"

    def cmd_setup_jira(self, args: list[str], user_email: str, user_id: str | None = None) -> str:
        """Настроить подключение к Jira"""
        if not user_id:
            return "❌ Ошибка получения ID пользователя"

        # Проверяем, есть ли уже настройки
        existing_settings = db_manager.get_user_jira_settings(user_email)

        if not args:
            if existing_settings:
                _, jira_username, _, last_test_success = existing_settings
                status = "✅ работает" if last_test_success else "❌ ошибка"
                return f"""🔧 **Текущие настройки Jira:**

👤 **Пользователь:** {jira_username}
🔗 **Статус:** {status}

Для изменения настроек используйте:
`setup_jira <username> <password>`

Для проверки подключения: `test_jira`"""
            else:
                return """🔧 **Настройка подключения к Jira**

Для настройки подключения используйте:
`setup_jira <username> <password>`

**Пример:**
`setup_jira myusername mypassword`

⚠️ **Безопасность:** Настройки сохраняются в зашифрованном виде."""

        if len(args) < 2:
            return "❌ Укажите логин и пароль: `setup_jira <username> <password>`"

        jira_username = args[0]
        jira_password = " ".join(args[1:])  # Пароль может содержать пробелы

        # Сохраняем настройки
        success = db_manager.save_user_jira_settings(user_email, user_id, jira_username, jira_password)

        if success:
            # Тестируем подключение
            from user_jira_client import user_jira_client

            test_success, test_message = user_jira_client.test_connection(user_email)

            if test_success:
                return f"""✅ **Настройки Jira сохранены и проверены!**

👤 **Пользователь:** {jira_username}
🔗 **Статус:** {test_message}

Теперь вы можете подписываться на проекты командой `subscribe PROJECT_KEY`"""
            else:
                return f"""⚠️ **Настройки сохранены, но есть проблема с подключением:**

❌ {test_message}

Проверьте логин/пароль и попробуйте снова."""
        else:
            return "❌ Ошибка сохранения настроек Jira"

    def cmd_test_jira(self, args: list[str], user_email: str, user_id: str | None = None) -> str:
        """Проверить подключение к Jira"""
        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            return """❌ **Настройки Jira не найдены**

Сначала настройте подключение командой: `setup_jira <username> <password>`"""

        from user_jira_client import user_jira_client

        success, message = user_jira_client.test_connection(user_email)

        return f"""🧪 **Тест подключения к Jira:**

{message}

{("Вы можете создавать подписки на проекты!" if success else "Проверьте настройки командой `setup_jira`")}"""

    def cmd_change_password(self, args: list[str], user_email: str, user_id: str | None = None) -> str:
        """Изменить пароль для Jira"""
        if not user_id:
            return "❌ Ошибка получения ID пользователя"

        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            return """❌ **Настройки Jira не найдены**

Сначала настройте подключение командой: `setup_jira <username> <password>`"""

        if not args:
            return "❌ Укажите новый пароль: `change_password <new_password>`"

        new_password = " ".join(args)  # Пароль может содержать пробелы
        _, jira_username, _, _ = settings

        # Обновляем пароль
        success = db_manager.save_user_jira_settings(user_email, user_id, jira_username, new_password)

        if success:
            # Очищаем кеш подключения
            from user_jira_client import user_jira_client

            user_jira_client.clear_user_cache(user_email)

            # Тестируем новое подключение
            test_success, test_message = user_jira_client.test_connection(user_email)

            if test_success:
                return f"✅ **Пароль обновлен и проверен!**\n\n{test_message}"
            else:
                return f"⚠️ **Пароль обновлен, но есть проблема:**\n\n❌ {test_message}"
        else:
            return "❌ Ошибка обновления пароля"

    def cmd_all_subscriptions(self, args: list[str], user_email: str) -> str:
        """Показать все подписки в системе (только для администраторов)"""
        subscriptions = db_manager.get_all_subscriptions()

        if not subscriptions:
            return "📋 **В системе нет активных подписок**"

        result = f"📋 **Все подписки в системе ({len(subscriptions)}):**\n\n"

        active_count = 0
        inactive_count = 0

        for project_key, project_name, channel_id, subscribed_by, created_at, active in subscriptions:
            status = "🟢" if active else "🔴"
            if active:
                active_count += 1
            else:
                inactive_count += 1

            result += f"{status} **{project_key}** - {project_name or 'Без названия'}\n"
            result += f"   📢 Канал: `{channel_id}`\n"
            result += f"   👤 Подписал: {subscribed_by}\n"
            result += f"   📅 Создано: {created_at[:10]}\n\n"

        result += f"**Статистика:** Активных: {active_count}, Неактивных: {inactive_count}\n\n"
        result += "Для удаления подписки: `delete_subscription PROJECT_KEY CHANNEL_ID`"

        return result

    def cmd_delete_subscription(self, args: list[str], user_email: str) -> str:
        """Удалить подписку (только для администраторов)"""
        if len(args) < 2:
            return """❌ Укажите проект и канал: `delete_subscription PROJECT_KEY CHANNEL_ID`

Для просмотра всех подписок: `all_subscriptions`"""

        project_key = args[0].upper()
        channel_id = args[1]

        success = db_manager.delete_subscription_by_id(project_key, channel_id)

        if success:
            return f"✅ **Подписка удалена**\n\n📋 Проект: {project_key}\n📢 Канал: `{channel_id}`"
        else:
            return f"❌ Подписка не найдена: {project_key} в канале `{channel_id}`"

    def cmd_list_users(self, args: list[str], user_email: str) -> str:
        """Показать список пользователей с настройками Jira"""
        # Получаем всех пользователей с настройками Jira из БД
        try:
            import sqlite3

            with sqlite3.connect(db_manager.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_email, jira_username FROM user_jira_settings")
                users = cursor.fetchall()
        except Exception as e:
            return f"❌ Ошибка получения списка пользователей: {e}"

        if not users:
            return "📝 Нет пользователей с настройками Jira"

        message_parts = ["📝 **Пользователи с настройками Jira:**\n"]

        for i, (email, jira_username) in enumerate(users, 1):
            message_parts.append(f"{i}. {email} (Jira: {jira_username})")

        message_parts.append(f"\n**Всего пользователей:** {len(users)}")

        return "\n".join(message_parts)

    def cmd_run_subscriptions(
        self,
        args: list[str],
        user_email: str,
        channel_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Запустить проверку подписок для текущего канала"""
        if not channel_id:
            return "❌ Команда доступна только в каналах"

        # Проверяем, есть ли подписки для данного канала
        subscriptions = db_manager.get_subscriptions_by_channel(channel_id)
        if not subscriptions:
            return "ℹ️ В этом канале нет активных подписок на проекты. Используйте `subscribe PROJECT_KEY` для добавления подписок."

        # Все подписки уже активные (фильтр в SQL)
        active_subscriptions = subscriptions
        if not active_subscriptions:
            return "ℹ️ В этом канале нет активных подписок. Активируйте подписки или добавьте новые."

        try:
            from project_monitor import project_monitor

            # Запускаем мониторинг только для подписок этого канала
            # subscription: (project_key, project_name, subscribed_by_email, created_at, active)
            project_keys = [sub[0] for sub in active_subscriptions]  # sub[0] - project_key

            logger.info(f"Запуск ручной проверки подписок канала {channel_id}: {project_keys}")

            results = []
            for project_key in project_keys:
                try:
                    # Мониторим конкретный проект для конкретного канала
                    result = project_monitor.monitor_project_for_channel(project_key, channel_id)
                    if result:
                        results.append(f"✅ {project_key}: {result}")
                    else:
                        results.append(f"ℹ️ {project_key}: нет проблем")
                except Exception as e:
                    logger.error(f"Ошибка мониторинга проекта {project_key}: {e}")
                    results.append(f"❌ {project_key}: ошибка проверки")

            if results:
                response = "🔍 **Результаты проверки подписок канала:**\n\n" + "\n".join(results)
                response += f"\n\n💡 Проверено проектов: {len(project_keys)}"
            else:
                response = "ℹ️ Проверка завершена, проблем не обнаружено"

            return response

        except Exception as e:
            logger.error(f"Ошибка ручного мониторинга подписок: {e}")
            return f"❌ Ошибка запуска проверки: {e!s}"

    def cmd_monitor_now(self, args: list[str], user_email: str) -> str:
        """Запустить мониторинг всех проектов вручную"""
        try:
            from project_monitor import project_monitor

            project_monitor.monitor_all_projects()
            return "✅ Мониторинг всех проектов запущен. Проверьте каналы с подписками на уведомления."
        except Exception as e:
            logger.error(f"Ошибка ручного мониторинга: {e}")
            return f"❌ Ошибка запуска мониторинга: {e!s}"

    def cmd_history(self, args: list[str], user_email: str) -> str:
        """Показать историю проверок"""
        days = 7  # По умолчанию за неделю

        if args:
            try:
                days = int(args[0])
                if days < 1 or days > 30:
                    return "❌ Количество дней должно быть от 1 до 30"
            except ValueError:
                return "❌ Некорректное количество дней"

        history = db_manager.get_check_history(days)

        if not history:
            return f"📊 Нет данных за последние {days} дней"

        # Группируем по датам
        by_date = {}
        for check_date, email, name, has_worklog, hours in history:
            if check_date not in by_date:
                by_date[check_date] = {"with": [], "without": []}

            user_info = f"{name or email}"
            if has_worklog:
                user_info += f" ({hours:.1f}ч)"
                by_date[check_date]["with"].append(user_info)
            else:
                by_date[check_date]["without"].append(user_info)

        message_parts = [f"📊 **История проверок за {days} дней:**\n"]

        for date in sorted(by_date.keys(), reverse=True):
            data = by_date[date]
            message_parts.append(f"**{date}:**")

            if data["with"]:
                message_parts.append(f"  ✅ Заполнили ({len(data['with'])}): {', '.join(data['with'])}")

            if data["without"]:
                message_parts.append(f"  ❌ Не заполнили ({len(data['without'])}): {', '.join(data['without'])}")

            message_parts.append("")

        return "\n".join(message_parts)

    def cmd_status(self, args: list[str], user_email: str) -> str:
        """Показать статус бота"""
        message_parts = ["🤖 **Статус бота:**\n"]

        # Статус планировщика
        scheduler_status = "🟢 Запущен" if scheduler.running else "🔴 Остановлен"
        message_parts.append(f"**Планировщик:** {scheduler_status}")

        # Проверка подключений
        try:
            # Тест Mattermost
            mm_status = "🟢 Подключен"
            if mattermost_client.driver:
                me = mattermost_client.driver.users.get_user("me")
                mm_status += f" ({me['username']})"
        except Exception:
            mm_status = "🔴 Ошибка подключения"

        message_parts.append(f"**Mattermost:** {mm_status}")

        # Тест Jira
        try:
            from jira_client import jira_client

            jira_status = "🟢 Подключен"
            if jira_client.jira_client:
                current_user = jira_client.jira_client.current_user()
                jira_status += f" ({current_user})"
        except Exception:
            jira_status = "🔴 Ошибка подключения"

        message_parts.append(f"**Jira:** {jira_status}")

        # Статистика подписок
        subscriptions = db_manager.get_all_subscriptions()
        active_subscriptions = [s for s in subscriptions if s[5]]  # активные подписки
        message_parts.append(f"**Активные подписки:** {len(active_subscriptions)}")

        # Последняя проверка
        history = db_manager.get_check_history(1)
        if history:
            last_check = history[0][0]  # Дата последней проверки
            message_parts.append(f"**Последняя проверка:** {last_check}")
        else:
            message_parts.append("**Последняя проверка:** не выполнялась")

        return "\n".join(message_parts)


# Глобальный экземпляр обработчика команд
command_handler = BotCommandHandler()
