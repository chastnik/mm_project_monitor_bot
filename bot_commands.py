"""
Обработчик команд бота
"""
import logging
import re
from typing import Optional, Dict, List
from database import db_manager
from mattermost_client import mattermost_client
from scheduler import scheduler

logger = logging.getLogger(__name__)

class BotCommandHandler:
    def __init__(self):
        self.commands = {
            'help': self.cmd_help,
            'subscribe': self.cmd_subscribe,
            'unsubscribe': self.cmd_unsubscribe,
            'list_subscriptions': self.cmd_list_subscriptions,
            'setup_jira': self.cmd_setup_jira,
            'test_jira': self.cmd_test_jira,
            'change_password': self.cmd_change_password,
            'monitor_now': self.cmd_monitor_now,
            'all_subscriptions': self.cmd_all_subscriptions,
            'delete_subscription': self.cmd_delete_subscription,
            'history': self.cmd_history,
            'status': self.cmd_status,
        }
    
    def handle_message(self, message_text: str, user_email: str, channel_type: str = 'D', 
                      channel_id: str = None, team_id: str = None, user_id: str = None) -> Optional[str]:
        """
        Обработать сообщение пользователя
        channel_type: 'D' для личных сообщений, 'O' для открытых каналов
        """
        if not message_text.strip():
            return None
        
        # Убираем упоминания бота если есть
        message_text = re.sub(r'@\w+\s*', '', message_text).strip()
        
        # Парсим команду
        parts = message_text.split()
        if not parts:
            return None
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Проверяем права доступа для админских команд
        admin_commands = ['monitor_now', 'all_subscriptions', 'delete_subscription']
        if command in admin_commands and not mattermost_client.is_user_admin(user_email):
            return "❌ У вас нет прав для выполнения этой команды"
        
        # Выполняем команду
        if command in self.commands:
            try:
                # Передаем дополнительные параметры для команд подписки
                if command in ['subscribe', 'unsubscribe', 'list_subscriptions']:
                    return self.commands[command](args, user_email, channel_id, team_id, user_id)
                elif command in ['setup_jira', 'test_jira', 'change_password']:
                    return self.commands[command](args, user_email, user_id)
                else:
                    return self.commands[command](args, user_email)
            except Exception as e:
                logger.error(f"Ошибка выполнения команды {command}: {e}")
                return f"❌ Ошибка выполнения команды: {str(e)}"
        else:
            return self.cmd_help([], user_email)
    
    def cmd_help(self, args: List[str], user_email: str) -> str:
        """Показать справку по командам"""
        is_admin = mattermost_client.is_user_admin(user_email)
        
        help_text = """📋 **Команды бота мониторинга проектов**

**Настройка подключения к Jira:**
• `setup_jira` - настроить подключение к Jira (логин/пароль)
• `test_jira` - проверить подключение к Jira
• `change_password` - изменить пароль для Jira

**Управление подписками на проекты:**
• `subscribe <PROJECT_KEY>` - подписать канал на мониторинг проекта
• `unsubscribe <PROJECT_KEY>` - отписать канал от мониторинга проекта  
• `list_subscriptions` - показать активные подписки в канале

**Информационные команды:**
• `help` - показать эту справку
• `history` - история уведомлений за последние дни
• `status` - статус бота и активные подписки

"""
        
        if is_admin:
            help_text += """**Команды администратора:**
• `monitor_now` - запустить мониторинг всех проектов сейчас
• `all_subscriptions` - просмотреть все подписки в системе
• `delete_subscription <PROJECT_KEY> <CHANNEL_ID>` - удалить подписку

"""
        else:
            help_text += """**Команды администратора:**
• _Доступны только администраторам_

"""
        
        help_text += """**Примеры использования:**
• `setup_jira` - настроить подключение к Jira
• `subscribe MYPROJ` - подписаться на мониторинг проекта MYPROJ
• `test_jira` - проверить подключение

**Что мониторит бот:**
🚨 **Превышение трудозатрат** - когда фактическое время превышает плановое
⏰ **Просроченные сроки** - когда срок выполнения задачи истек, а она не закрыта

ℹ️ **Важно:** Каждый пользователь должен настроить свое подключение к Jira перед созданием подписок."""
        
        return help_text
    
    def cmd_subscribe(self, args: List[str], user_email: str, channel_id: str = None, 
                     team_id: str = None, user_id: str = None) -> str:
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
                return f"✅ Канал подписан на мониторинг проекта **{project_key}** ({project_name})\n\n" \
                       f"Бот будет ежедневно проверять задачи проекта и отправлять уведомления о:\n" \
                       f"🚨 Превышении трудозатрат\n" \
                       f"⏰ Просроченных сроках"
            else:
                return "❌ Ошибка подписки на проект"
                
        except Exception as e:
            if "does not exist" in str(e) or "No project could be found" in str(e):
                return f"❌ Проект {project_key} не найден в Jira"
            else:
                logger.error(f"Ошибка подписки на проект {project_key}: {e}")
                return f"❌ Ошибка подписки на проект: {str(e)}"
    
    def cmd_unsubscribe(self, args: List[str], user_email: str, channel_id: str = None,
                        team_id: str = None, user_id: str = None) -> str:
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
    
    def cmd_list_subscriptions(self, args: List[str], user_email: str, channel_id: str = None,
                              team_id: str = None, user_id: str = None) -> str:
        """Показать активные подписки в канале"""
        if not channel_id:
            return "❌ Команда доступна только в каналах"
        
        subscriptions = db_manager.get_subscriptions_by_channel(channel_id)
        
        if not subscriptions:
            return "📋 В этом канале нет активных подписок на проекты\n\n" \
                   "Используйте `subscribe PROJECT_KEY` для подписки на мониторинг проекта"
        
        result = f"📋 **Активные подписки в канале ({len(subscriptions)}):**\n\n"
        
        for project_key, project_name, subscribed_by, created_at in subscriptions:
            result += f"• **{project_key}** - {project_name}\n"
            result += f"  _Подписал: {subscribed_by}, {created_at[:10]}_\n\n"
        
        result += "Для отписки используйте: `unsubscribe PROJECT_KEY`"
        
        return result
    
    def cmd_setup_jira(self, args: List[str], user_email: str, user_id: str = None) -> str:
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
    
    def cmd_test_jira(self, args: List[str], user_email: str, user_id: str = None) -> str:
        """Проверить подключение к Jira"""
        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            return """❌ **Настройки Jira не найдены**

Сначала настройте подключение командой: `setup_jira <username> <password>`"""
        
        from user_jira_client import user_jira_client
        success, message = user_jira_client.test_connection(user_email)
        
        return f"""🧪 **Тест подключения к Jira:**

{message}

{('Вы можете создавать подписки на проекты!' if success else 'Проверьте настройки командой `setup_jira`')}"""
    
    def cmd_change_password(self, args: List[str], user_email: str, user_id: str = None) -> str:
        """Изменить пароль для Jira"""
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
    
    def cmd_all_subscriptions(self, args: List[str], user_email: str) -> str:
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
    
    def cmd_delete_subscription(self, args: List[str], user_email: str) -> str:
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
    
    def cmd_add_user(self, args: List[str], user_email: str) -> str:
        """Добавить пользователя в мониторинг"""
        if not args:
            return "❌ Укажите email пользователя: `add_user user@company.com [Имя Фамилия]`"
        
        email = args[0].lower().strip()
        name = ' '.join(args[1:]) if len(args) > 1 else None
        
        # Валидация email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return "❌ Некорректный формат email адреса"
        
        # Проверяем существование пользователя в Mattermost
        mm_user = mattermost_client.get_user_by_email(email)
        mm_user_id = mm_user['id'] if mm_user else None
        
        # Проверяем существование пользователя в Jira
        # Функция удалена - используются персональные настройки
        jira_user = None  # Персональные настройки теперь
        jira_account_id = None
        
        if not mm_user:
            return f"⚠️ Пользователь {email} не найден в Mattermost"
        
        # Используем имя из систем если не указано
        if not name:
            if mm_user:
                name = f"{mm_user.get('first_name', '')} {mm_user.get('last_name', '')}".strip()
            elif jira_user:
                name = jira_user['displayName']
            
            if not name:
                name = email
        
        # Добавляем пользователя в БД
        success = db_manager.add_user(email, name, mm_user_id, jira_account_id)
        
        if success:
            warnings = []
            if not mm_user:
                warnings.append("не найден в Mattermost")
            if not jira_user:
                warnings.append("не найден в Jira")
            
            message = f"✅ Пользователь {name} ({email}) добавлен в мониторинг"
            if warnings:
                message += f"\n⚠️ Предупреждение: пользователь {', '.join(warnings)}"
            
            return message
        else:
            return f"❌ Пользователь {email} уже существует в базе данных"
    
    def cmd_remove_user(self, args: List[str], user_email: str) -> str:
        """Удалить пользователя из мониторинга"""
        if not args:
            return "❌ Укажите email пользователя: `remove_user user@company.com`"
        
        email = args[0].lower().strip()
        
        success = db_manager.remove_user(email)
        if success:
            return f"✅ Пользователь {email} удален из мониторинга"
        else:
            return f"❌ Пользователь {email} не найден в базе данных"
    
    def cmd_list_users(self, args: List[str], user_email: str) -> str:
        """Показать список отслеживаемых пользователей"""
        users = db_manager.get_active_users()
        
        if not users:
            return "📝 Список отслеживаемых пользователей пуст"
        
        message_parts = ["📝 **Отслеживаемые пользователи:**\n"]
        
        for i, (email, name, mm_id, jira_id) in enumerate(users, 1):
            status_icons = []
            if mm_id:
                status_icons.append("💬")  # Mattermost
            if jira_id:
                status_icons.append("📋")  # Jira
            
            status = " ".join(status_icons) if status_icons else "❓"
            display_name = name if name else email
            
            message_parts.append(f"{i}. {display_name} ({email}) {status}")
        
        message_parts.append(f"\n**Всего пользователей:** {len(users)}")
        message_parts.append("\n💬 - найден в Mattermost, 📋 - найден в Jira")
        
        return "\n".join(message_parts)
    
    def cmd_monitor_now(self, args: List[str], user_email: str) -> str:
        """Запустить мониторинг всех проектов вручную"""
        try:
            from project_monitor import project_monitor
            project_monitor.monitor_all_projects()
            return "✅ Мониторинг всех проектов запущен. Проверьте каналы с подписками на уведомления."
        except Exception as e:
            logger.error(f"Ошибка ручного мониторинга: {e}")
            return f"❌ Ошибка запуска мониторинга: {str(e)}"
    
    def cmd_history(self, args: List[str], user_email: str) -> str:
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
                by_date[check_date] = {'with': [], 'without': []}
            
            user_info = f"{name or email}"
            if has_worklog:
                user_info += f" ({hours:.1f}ч)"
                by_date[check_date]['with'].append(user_info)
            else:
                by_date[check_date]['without'].append(user_info)
        
        message_parts = [f"📊 **История проверок за {days} дней:**\n"]
        
        for date in sorted(by_date.keys(), reverse=True):
            data = by_date[date]
            message_parts.append(f"**{date}:**")
            
            if data['with']:
                message_parts.append(f"  ✅ Заполнили ({len(data['with'])}): {', '.join(data['with'])}")
            
            if data['without']:
                message_parts.append(f"  ❌ Не заполнили ({len(data['without'])}): {', '.join(data['without'])}")
            
            message_parts.append("")
        
        return "\n".join(message_parts)
    
    def cmd_status(self, args: List[str], user_email: str) -> str:
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
                me = mattermost_client.driver.users.get_user('me')
                mm_status += f" ({me['username']})"
        except:
            mm_status = "🔴 Ошибка подключения"
        
        message_parts.append(f"**Mattermost:** {mm_status}")
        
        # Тест Jira
        try:
            from jira_client import jira_client
            jira_status = "🟢 Подключен"
            if jira_client.jira_client:
                current_user = jira_client.jira_client.current_user()
                jira_status += f" ({current_user})"
        except:
            jira_status = "🔴 Ошибка подключения"
        
        message_parts.append(f"**Jira:** {jira_status}")
        
        # Статистика пользователей
        users = db_manager.get_active_users()
        message_parts.append(f"**Отслеживаемые пользователи:** {len(users)}")
        
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
