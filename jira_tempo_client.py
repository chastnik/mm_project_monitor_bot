"""
Клиент для работы с Jira и Tempo API
"""
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from jira import JIRA
from config import config

logger = logging.getLogger(__name__)

class JiraTempoClient:
    def __init__(self):
        self.jira_client = None
        self.tempo_headers = {
            'Authorization': f'Bearer {config.TEMPO_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        self.connect()
    
    def connect(self):
        """Подключение к Jira"""
        try:
            # Для on-premise Jira может потребоваться отключить проверку SSL
            options = {
                'server': config.JIRA_URL,
                'verify': getattr(config, 'JIRA_VERIFY_SSL', True),  # По умолчанию проверяем SSL
            }
            
            # Аутентификация для on-premise Jira
            if hasattr(config, 'JIRA_AUTH_METHOD') and config.JIRA_AUTH_METHOD.lower() == 'token':
                # Для Jira Cloud или Server с API токенами
                self.jira_client = JIRA(
                    options=options,
                    basic_auth=(config.JIRA_USERNAME, config.JIRA_API_TOKEN)
                )
            else:
                # Для старых версий on-premise Jira с паролем
                self.jira_client = JIRA(
                    options=options,
                    basic_auth=(config.JIRA_USERNAME, config.JIRA_PASSWORD)
                )
            
            logger.info("Успешно подключились к on-premise Jira")
        except Exception as e:
            logger.error(f"Ошибка подключения к on-premise Jira: {e}")
            raise
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Получить пользователя Jira по email"""
        try:
            # Для on-premise Jira может быть другой API для поиска пользователей
            users = self.jira_client.search_users(query=email, maxResults=1)
            if users:
                user = users[0]
                # В on-premise Jira может не быть accountId, используем username или key
                user_id = getattr(user, 'accountId', None) or getattr(user, 'key', None) or getattr(user, 'name', None)
                
                return {
                    'accountId': user_id,  # Может быть username для on-premise
                    'displayName': getattr(user, 'displayName', email),
                    'emailAddress': getattr(user, 'emailAddress', email),
                    'username': getattr(user, 'name', email.split('@')[0])  # Добавляем username
                }
            return None
        except Exception as e:
            logger.warning(f"Пользователь с email {email} не найден в on-premise Jira: {e}")
            return None
    
    def get_worklog_for_date(self, account_id: str, date: str) -> Tuple[bool, float]:
        """
        Получить информацию о worklogs пользователя за определенную дату через Tempo API
        Возвращает (has_worklog, total_hours)
        """
        try:
            # Проверяем, используется ли Tempo Cloud API или встроенный в Jira
            if config.TEMPO_API_URL.startswith('https://api.tempo.io'):
                # Tempo Cloud API
                return self._get_worklog_tempo_cloud(account_id, date)
            else:
                # Встроенный Tempo в Jira - пробуем разные варианты API
                return self._get_worklog_tempo_onpremise(account_id, date)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к Tempo API для пользователя {account_id}: {e}")
            # Попробуем альтернативный способ через Jira API
            return self._get_worklog_via_jira(account_id, date)
        except Exception as e:
            logger.error(f"Ошибка получения worklog для пользователя {account_id}: {e}")
            return False, 0.0
    
    def _get_worklog_tempo_cloud(self, account_id: str, date: str) -> Tuple[bool, float]:
        """Получить worklog через Tempo Cloud API"""
        url = f"{config.TEMPO_API_URL}/worklogs"
        params = {
            'from': date,
            'to': date,
            'worker': account_id
        }
        
        response = requests.get(url, headers=self.tempo_headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        worklogs = data.get('results', [])
        
        if not worklogs:
            return False, 0.0
        
        total_seconds = sum(worklog.get('timeSpentSeconds', 0) for worklog in worklogs)
        total_hours = total_seconds / 3600.0
        
        return True, total_hours
    
    def _get_worklog_tempo_onpremise(self, account_id: str, date: str) -> Tuple[bool, float]:
        """Получить worklog через встроенный Tempo API в Jira"""
        # Список возможных URL паттернов для встроенного Tempo
        api_patterns = [
            f"{config.TEMPO_API_URL}/worklogs/user/{account_id}",
            f"{config.TEMPO_API_URL}/worklogs",
            f"{config.TEMPO_API_URL}/worklog/user/{account_id}",
            f"{config.TEMPO_API_URL}/worklog",
        ]
        
        params = {
            'from': date,
            'to': date,
            'dateFrom': date,
            'dateTo': date,
            'user': account_id,
            'worker': account_id
        }
        
        # Для встроенного Tempo может потребоваться аутентификация Jira
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Basic {self._get_jira_auth_header()}'
        }
        
        # Если есть Tempo токен, добавляем его
        if config.TEMPO_API_TOKEN:
            headers['Authorization'] = f'Bearer {config.TEMPO_API_TOKEN}'
        
        for url_pattern in api_patterns:
            try:
                logger.debug(f"Пробуем Tempo API URL: {url_pattern}")
                
                if hasattr(config, 'TEMPO_VERIFY_SSL') and not config.TEMPO_VERIFY_SSL:
                    response = requests.get(url_pattern, headers=headers, params=params, verify=False)
                else:
                    response = requests.get(url_pattern, headers=headers, params=params)
                
                response.raise_for_status()
                data = response.json()
                
                # Разные структуры ответа для разных версий
                worklogs = []
                if isinstance(data, list):
                    worklogs = data
                elif 'results' in data:
                    worklogs = data['results']
                elif 'worklogs' in data:
                    worklogs = data['worklogs']
                elif 'worklog' in data:
                    worklogs = data['worklog'] if isinstance(data['worklog'], list) else [data['worklog']]
                
                if worklogs:
                    total_seconds = sum(
                        worklog.get('timeSpentSeconds', 0) or 
                        worklog.get('timeSpent', 0) or 
                        (worklog.get('hours', 0) * 3600)
                        for worklog in worklogs
                    )
                    total_hours = total_seconds / 3600.0
                    
                    logger.info(f"Успешно получен worklog через {url_pattern}: {total_hours:.2f} часов")
                    return True, total_hours
                
            except requests.exceptions.RequestException as e:
                logger.debug(f"Ошибка для URL {url_pattern}: {e}")
                continue
            except Exception as e:
                logger.debug(f"Ошибка обработки ответа для {url_pattern}: {e}")
                continue
        
        logger.warning(f"Не удалось получить worklog через Tempo API, используем fallback")
        return self._get_worklog_via_jira(account_id, date)
    
    def _get_jira_auth_header(self) -> str:
        """Получить заголовок аутентификации для Jira"""
        import base64
        
        if config.JIRA_AUTH_METHOD.lower() == 'token':
            auth_string = f"{config.JIRA_USERNAME}:{config.JIRA_API_TOKEN}"
        else:
            auth_string = f"{config.JIRA_USERNAME}:{config.JIRA_PASSWORD}"
        
        return base64.b64encode(auth_string.encode()).decode()
    
    def _get_worklog_via_jira(self, user_id: str, date: str) -> Tuple[bool, float]:
        """
        Альтернативный метод получения worklog через стандартный Jira API
        Используется как fallback если Tempo API недоступен
        """
        try:
            from datetime import datetime, timedelta
            
            # Преобразуем дату в объект datetime
            check_date = datetime.strptime(date, '%Y-%m-%d')
            start_date = check_date.strftime('%Y-%m-%d')
            end_date = (check_date + timedelta(days=1)).strftime('%Y-%m-%d')
            
            # Ищем issues с worklog пользователя за указанную дату
            jql = f"worklogAuthor = '{user_id}' AND worklogDate >= '{start_date}' AND worklogDate < '{end_date}'"
            
            logger.debug(f"JQL запрос для поиска worklog: {jql}")
            
            # Выполняем поиск
            issues = self.jira_client.search_issues(jql, maxResults=100, expand='worklog')
            
            total_seconds = 0
            
            for issue in issues:
                if hasattr(issue.fields, 'worklog') and issue.fields.worklog:
                    for worklog in issue.fields.worklog.worklogs:
                        # Проверяем автора worklog
                        worklog_author = getattr(worklog.author, 'name', None) or getattr(worklog.author, 'accountId', None)
                        worklog_date = worklog.started[:10]  # Получаем только дату (YYYY-MM-DD)
                        
                        if worklog_author == user_id and worklog_date == date:
                            total_seconds += worklog.timeSpentSeconds
            
            total_hours = total_seconds / 3600.0
            has_worklog = total_seconds > 0
            
            logger.info(f"Через Jira API найдено {total_hours:.2f} часов worklog для пользователя {user_id}")
            
            return has_worklog, total_hours
            
        except Exception as e:
            logger.error(f"Ошибка получения worklog через Jira API для пользователя {user_id}: {e}")
            return False, 0.0
    
    def get_worklog_for_date_range(self, account_id: str, from_date: str, to_date: str) -> List[Dict]:
        """
        Получить worklogs пользователя за период
        """
        try:
            url = f"{config.TEMPO_API_URL}/worklogs"
            params = {
                'from': from_date,
                'to': to_date,
                'worker': account_id
            }
            
            response = requests.get(url, headers=self.tempo_headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            return data.get('results', [])
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к Tempo API для пользователя {account_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения worklog для пользователя {account_id}: {e}")
            return []
    
    def check_users_worklog_for_date(self, user_emails: List[str], check_date: str = None) -> Dict[str, Tuple[bool, float, str]]:
        """
        Проверить worklogs для списка пользователей за определенную дату
        Возвращает словарь: {email: (has_worklog, hours, display_name)}
        """
        if not check_date:
            check_date = datetime.now().strftime('%Y-%m-%d')
        
        results = {}
        
        for email in user_emails:
            try:
                # Получаем информацию о пользователе в Jira
                jira_user = self.get_user_by_email(email)
                if not jira_user:
                    logger.warning(f"Пользователь {email} не найден в Jira")
                    results[email] = (False, 0.0, email)
                    continue
                
                # Проверяем worklog
                has_worklog, hours = self.get_worklog_for_date(jira_user['accountId'], check_date)
                results[email] = (has_worklog, hours, jira_user['displayName'])
                
                logger.info(f"Пользователь {email} ({jira_user['displayName']}): "
                           f"{'есть' if has_worklog else 'нет'} worklog, {hours:.2f} часов")
                
            except Exception as e:
                logger.error(f"Ошибка проверки worklog для {email}: {e}")
                results[email] = (False, 0.0, email)
        
        return results
    
    def get_yesterday_date(self) -> str:
        """Получить вчерашнюю дату в формате YYYY-MM-DD"""
        yesterday = datetime.now() - timedelta(days=1)
        return yesterday.strftime('%Y-%m-%d')
    
    def get_current_date(self) -> str:
        """Получить текущую дату в формате YYYY-MM-DD"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def test_tempo_connection(self) -> bool:
        """Тестировать подключение к Tempo API"""
        try:
            url = f"{config.TEMPO_API_URL}/worklogs"
            params = {
                'from': self.get_current_date(),
                'to': self.get_current_date(),
                'limit': 1
            }
            
            response = requests.get(url, headers=self.tempo_headers, params=params)
            response.raise_for_status()
            
            logger.info("Подключение к Tempo API успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Tempo API: {e}")
            return False

# Глобальный экземпляр клиента
jira_tempo_client = JiraTempoClient()
