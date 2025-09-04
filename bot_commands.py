"""
Обработчик команд бота
"""
import logging
import re
from typing import Optional, Dict, List
from database import db_manager
from mattermost_client import mattermost_client
from jira_tempo_client import jira_tempo_client
from scheduler import scheduler

logger = logging.getLogger(__name__)

class BotCommandHandler:
    def __init__(self):
        self.commands = {
            'help': self.cmd_help,
            'add_user': self.cmd_add_user,
            'remove_user': self.cmd_remove_user,
            'list_users': self.cmd_list_users,
            'check_now': self.cmd_check_now,
            'history': self.cmd_history,
            'status': self.cmd_status,
        }
    
    def handle_message(self, message_text: str, user_email: str, channel_type: str = 'D') -> Optional[str]:
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
        admin_commands = ['add_user', 'remove_user', 'check_now']
        if command in admin_commands and not mattermost_client.is_user_admin(user_email):
            return "❌ У вас нет прав для выполнения этой команды"
        
        # Выполняем команду
        if command in self.commands:
            try:
                return self.commands[command](args, user_email)
            except Exception as e:
                logger.error(f"Ошибка выполнения команды {command}: {e}")
                return f"❌ Ошибка выполнения команды: {str(e)}"
        else:
            return self.cmd_help([], user_email)
    
    def cmd_help(self, args: List[str], user_email: str) -> str:
        """Показать справку по командам"""
        is_admin = mattermost_client.is_user_admin(user_email)
        
        help_text = """🤖 **Команды бота для проверки планов**

**Доступные команды:**
• `help` - показать эту справку
• `list_users` - показать список отслеживаемых пользователей
• `history` - показать историю проверок (по умолчанию за 7 дней)
• `status` - показать статус бота и подключений

"""
        
        if is_admin:
            help_text += """**Команды администратора:**
• `add_user <email> [имя]` - добавить пользователя в мониторинг
• `remove_user <email>` - удалить пользователя из мониторинга  
• `check_now` - запустить проверку вручную

"""
        
        help_text += """**Примеры:**
• `add_user john.doe@company.com Иван Иванов`
• `remove_user john.doe@company.com`
• `history 14` - история за 14 дней

Бот автоматически проверяет заполнение планов каждый день и отправляет отчеты."""
        
        return help_text
    
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
        jira_user = jira_tempo_client.get_user_by_email(email)
        jira_account_id = jira_user['accountId'] if jira_user else None
        
        if not mm_user and not jira_user:
            return f"⚠️ Пользователь {email} не найден ни в Mattermost, ни в Jira"
        
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
    
    def cmd_check_now(self, args: List[str], user_email: str) -> str:
        """Запустить проверку вручную"""
        return scheduler.run_manual_check()
    
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
            jira_status = "🟢 Подключен"
            if jira_tempo_client.jira_client:
                current_user = jira_tempo_client.jira_client.current_user()
                jira_status += f" ({current_user})"
        except:
            jira_status = "🔴 Ошибка подключения"
        
        message_parts.append(f"**Jira:** {jira_status}")
        
        # Тест Tempo API
        tempo_status = "🟢 Подключен" if jira_tempo_client.test_tempo_connection() else "🔴 Ошибка подключения"
        message_parts.append(f"**Tempo API:** {tempo_status}")
        
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
