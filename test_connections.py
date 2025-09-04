#!/usr/bin/env python3
"""
Скрипт для тестирования подключений к Mattermost, Jira и Tempo
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Настройка логирования для тестирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_with_custom_config():
    """Тестирование с переданными настройками"""
    
    # Устанавливаем переменные окружения из переданной конфигурации
    config_vars = {
        'MATTERMOST_URL': 'https://mm.1bit.support',
        'MATTERMOST_TOKEN': 'aqzsmr4e7ibupf1moinkqcke3e',
        'MATTERMOST_USERNAME': 'jora',
        'MATTERMOST_TEAM': 'BI&RPA',
        'MATTERMOST_CHANNEL_ID': 'bnewb36nbbyzigfgb9sxxoagqc',
        'MATTERMOST_SSL_VERIFY': 'false',
        
        'JIRA_URL': 'https://jira.1solution.ru',
        'JIRA_USERNAME': 'SVChashin',
        'JIRA_PASSWORD': 'wevbAf-2zejjo-cicpig',
        'JIRA_AUTH_METHOD': 'password',
        'JIRA_VERIFY_SSL': 'false',
        
        'TEMPO_API_URL': 'https://jira.1solution.ru/rest/tempo-timesheets/4',
        'TEMPO_API_TOKEN': '',
        'TEMPO_VERIFY_SSL': 'false',
        
        'ADMIN_EMAILS': 'svchashin@1cbit.ru',
        'CHECK_TIME': '12:00',
        'TIMEZONE': 'Europe/Moscow',
        'LOG_LEVEL': 'INFO'
    }
    
    # Устанавливаем переменные окружения
    for key, value in config_vars.items():
        os.environ[key] = value
    
    print("🧪 Тестирование подключений с предоставленными настройками")
    print("=" * 60)
    
    # Импортируем модули после установки переменных окружения
    try:
        from config import config
        print(f"✅ Конфигурация загружена")
        print(f"   Mattermost: {config.MATTERMOST_URL}")
        print(f"   Jira: {config.JIRA_URL}")
        print(f"   Tempo: {config.TEMPO_API_URL}")
        print()
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False
    
    # Тестируем Mattermost
    print("🔵 Тестирование подключения к Mattermost...")
    try:
        from mattermost_client import MattermostClient
        mm_client = MattermostClient()
        
        # Получаем информацию о боте
        me = mm_client.driver.users.get_user('me')
        print(f"✅ Mattermost: Подключен как {me['username']} ({me.get('email', 'без email')})")
        
        # Проверяем канал
        channel_info = mm_client.get_channel_info(config.MATTERMOST_CHANNEL_ID)
        if channel_info:
            print(f"✅ Канал найден: {channel_info['display_name']}")
        else:
            print(f"⚠️ Канал {config.MATTERMOST_CHANNEL_ID} не найден или нет доступа")
        
    except Exception as e:
        print(f"❌ Mattermost: {e}")
        return False
    
    print()
    
    # Тестируем Jira
    print("🟠 Тестирование подключения к Jira...")
    try:
        from jira_tempo_client import JiraTempoClient
        jira_client = JiraTempoClient()
        
        # Получаем информацию о текущем пользователе
        current_user = jira_client.jira_client.current_user()
        print(f"✅ Jira: Подключен как {current_user}")
        
        # Тестируем поиск пользователя по email администратора
        admin_email = config.ADMIN_EMAILS[0] if config.ADMIN_EMAILS else 'test@example.com'
        jira_user = jira_client.get_user_by_email(admin_email)
        if jira_user:
            print(f"✅ Найден пользователь в Jira: {jira_user['displayName']} ({admin_email})")
        else:
            print(f"⚠️ Пользователь {admin_email} не найден в Jira")
        
    except Exception as e:
        print(f"❌ Jira: {e}")
        return False
    
    print()
    
    # Тестируем Tempo API
    print("🟡 Тестирование Tempo API...")
    try:
        # Тестируем подключение к Tempo
        tempo_result = jira_client.test_tempo_connection()
        if tempo_result:
            print(f"✅ Tempo API: Подключение успешно")
        else:
            print(f"⚠️ Tempo API: Прямое подключение не удалось, будет использован fallback через Jira API")
        
        # Тестируем получение worklog (если есть пользователь)
        if jira_user:
            from datetime import datetime, timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            has_worklog, hours = jira_client.get_worklog_for_date(jira_user['accountId'], yesterday)
            print(f"✅ Тест worklog за {yesterday}: {'найден' if has_worklog else 'не найден'} ({hours:.2f} часов)")
        
    except Exception as e:
        print(f"❌ Tempo: {e}")
        # Это не критическая ошибка, так как есть fallback
    
    print()
    print("🎉 Тестирование завершено!")
    
    # Итоговая сводка
    print("\n📋 Итоговая сводка:")
    print("✅ Mattermost - подключение работает")
    print("✅ Jira - подключение работает") 
    print("⚠️ Tempo - проверьте логи выше для деталей")
    print("\n🚀 Бот готов к запуску!")
    
    return True

if __name__ == '__main__':
    try:
        success = test_with_custom_config()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️ Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        sys.exit(1)
