"""
Тексты сообщений бота, связанные с авторизацией в Jira по Personal Access Token (PAT)
"""

import re

from config import config

# Команды, после которых в сообщении может идти токен
_LOGIN_COMMAND_RE = re.compile(
    r"(?i)\b(setup_jira|login|войти|вход|токен|token|настрой\s+(?:jira|джира|джиру|подключение)|jira\s+настройка)\b\s+\S.*",
    re.DOTALL,
)
# Длинные строки, похожие на токен (PAT в Jira Data Center - 44 символа base64)
_TOKEN_LIKE_RE = re.compile(r"[A-Za-z0-9+/=_-]{24,}")


def mask_secrets(text) -> str:
    """Скрыть токены в тексте сообщения перед записью в лог"""
    text = str(text)
    text = _LOGIN_COMMAND_RE.sub(lambda m: f"{m.group(1)} ***", text)
    return _TOKEN_LIKE_RE.sub("***", text)


def pat_profile_url() -> str:
    """Ссылка на страницу создания Personal Access Token в Jira Server / Data Center"""
    base_url = config.JIRA_URL.rstrip("/")
    return f"{base_url}/secure/ViewProfile.jspa?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"


def pat_instructions() -> str:
    """Пошаговая инструкция по созданию PAT и входу в бота"""
    return f"""**Как войти по Personal Access Token (PAT):**
1. Откройте Jira: {config.JIRA_URL}
2. Нажмите на свой аватар (справа вверху) → **Профиль** → **Personal Access Tokens**
   (прямая ссылка: {pat_profile_url()})
3. Нажмите **Create token**, укажите название (например, `Project Monitor Bot`) и при желании срок действия
4. Скопируйте токен — Jira покажет его **только один раз**
5. Отправьте боту **в личные сообщения**: `login <ваш_токен>`

После входа проверьте подключение командой `test_jira`.

🔒 Токен хранится в зашифрованном виде. Логин и пароль от Jira боту больше не нужны.
Если токен истечет или будет отозван — создайте новый и снова выполните `login <новый_токен>`."""


def setup_required_message() -> str:
    """Сообщение для пользователя, который еще не вошел по PAT"""
    return f"""❌ **Вы не вошли в Jira**

{pat_instructions()}"""


def legacy_user_disabled_message() -> str:
    """Уведомление пользователям, которые были подключены по логину/паролю до перехода на PAT"""
    return f"""⚠️ **Вход в Jira по логину и паролю отключен**

Бот перешел на авторизацию через **Personal Access Token (PAT)**. Ваше прежнее подключение (логин/пароль) отключено, сохраненный пароль удален.

Пока вы не войдете заново, бот не сможет проверять проекты по подпискам, которые вы создавали.

{pat_instructions()}"""


def token_invalid_block_message() -> str:
    """Уведомление о приостановке проверок из-за недействительного токена"""
    return f"""🔒 **Проверки приостановлены — токен Jira недействителен**

Бот не смог подключиться к Jira с вашим Personal Access Token: возможно, токен истек или был отозван.

**Все автоматические проверки ваших проектов приостановлены** до обновления токена.

{pat_instructions()}

Если проблема сохраняется, обратитесь к администратору."""
