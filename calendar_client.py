"""
Модуль для работы с производственным календарем РФ
"""
import logging
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Set
from config import config

logger = logging.getLogger(__name__)

class CalendarClient:
    def __init__(self, api_url: str = None):
        self.api_url = api_url or getattr(config, 'CALENDAR_API_URL', 'https://calendar.kuzyak.in')
        self.session = requests.Session()
        self.session.timeout = 10
    
    def get_year_calendar(self, year: int) -> Optional[Dict]:
        """Получить календарь на год"""
        try:
            url = f"{self.api_url}/api/calendar/{year}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения календаря на {year} год: {e}")
            return None
    
    def get_day_info(self, year: int, month: int, day: int) -> Optional[Dict]:
        """Получить информацию о конкретном дне"""
        try:
            url = f"{self.api_url}/api/calendar/{year}/{month:02d}/{day:02d}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения информации о дне {day:02d}.{month:02d}.{year}: {e}")
            return None
    
    def get_holidays(self, year: int) -> Optional[List[Dict]]:
        """Получить список праздничных и сокращенных дней на год"""
        try:
            url = f"{self.api_url}/api/calendar/{year}/holiday"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения праздников на {year} год: {e}")
            return None
    
    def is_working_day(self, check_date: date = None) -> bool:
        """Проверить, является ли день рабочим"""
        if check_date is None:
            check_date = date.today()
        
        try:
            day_info = self.get_day_info(check_date.year, check_date.month, check_date.day)
            if not day_info:
                # Если не удалось получить информацию, считаем день рабочим (по умолчанию)
                logger.warning(f"Не удалось получить информацию о дне {check_date}, считаем рабочим")
                return True
            
            # Проверяем, является ли день выходным или праздничным
            # Структура ответа может быть разной, проверяем несколько возможных полей
            is_holiday = day_info.get('isHoliday', False) or day_info.get('is_holiday', False)
            is_weekend = day_info.get('isWeekend', False) or day_info.get('is_weekend', False)
            day_type = day_info.get('type', '').lower()
            
            # Если день праздничный или выходной, то не рабочий
            if is_holiday or is_weekend or day_type in ['holiday', 'weekend', 'выходной', 'праздничный']:
                return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки рабочего дня {check_date}: {e}")
            # В случае ошибки считаем день рабочим, чтобы не блокировать работу бота
            return True
    
    def extract_holidays_from_calendar(self, calendar_data: Dict, year: int = None) -> Set[date]:
        """Извлечь множество выходных и праздничных дней из календаря"""
        holidays = set()
        
        try:
            if year is None:
                year = calendar_data.get('year', datetime.now().year) if isinstance(calendar_data, dict) else datetime.now().year
            
            # Обрабатываем разные возможные структуры ответа
            if isinstance(calendar_data, dict):
                # Если календарь содержит массив месяцев
                months = calendar_data.get('months', [])
                if months:
                    for month_data in months:
                        if isinstance(month_data, dict):
                            month_num = month_data.get('month', 0)
                            days = month_data.get('days', [])
                            
                            for day_data in days:
                                if isinstance(day_data, dict):
                                    day_num = day_data.get('day', 0)
                                    is_holiday = day_data.get('isHoliday', False) or day_data.get('is_holiday', False)
                                    is_weekend = day_data.get('isWeekend', False) or day_data.get('is_weekend', False)
                                    day_type = day_data.get('type', '').lower()
                                    
                                    if is_holiday or is_weekend or day_type in ['holiday', 'weekend', 'выходной', 'праздничный']:
                                        try:
                                            holiday_date = date(year, month_num, day_num)
                                            holidays.add(holiday_date)
                                        except ValueError:
                                            continue
                
                # Альтернативная структура: массив дней
                days = calendar_data.get('days', [])
                if days and not months:
                    for day_data in days:
                        if isinstance(day_data, dict):
                            month_num = day_data.get('month', 0)
                            day_num = day_data.get('day', 0)
                            is_holiday = day_data.get('isHoliday', False) or day_data.get('is_holiday', False)
                            is_weekend = day_data.get('isWeekend', False) or day_data.get('is_weekend', False)
                            day_type = day_data.get('type', '').lower()
                            
                            if is_holiday or is_weekend or day_type in ['holiday', 'weekend', 'выходной', 'праздничный']:
                                try:
                                    holiday_date = date(year, month_num, day_num)
                                    holidays.add(holiday_date)
                                except ValueError:
                                    continue
            
            # Если не нашли праздники в основной структуре, пробуем получить через отдельный метод
            if not holidays:
                holidays_list = self.get_holidays(year)
                if holidays_list:
                    for holiday_data in holidays_list:
                        if isinstance(holiday_data, dict):
                            # Пробуем разные форматы даты
                            holiday_date_str = holiday_data.get('date') or holiday_data.get('holidayDate')
                            if holiday_date_str:
                                try:
                                    # Пробуем разные форматы
                                    if isinstance(holiday_date_str, str):
                                        # Формат YYYY-MM-DD
                                        if len(holiday_date_str) >= 10:
                                            holiday_date = datetime.strptime(holiday_date_str[:10], '%Y-%m-%d').date()
                                            holidays.add(holiday_date)
                                    elif isinstance(holiday_date_str, (int, float)):
                                        # Unix timestamp
                                        holiday_date = datetime.fromtimestamp(holiday_date_str).date()
                                        holidays.add(holiday_date)
                                except (ValueError, TypeError):
                                    # Пробуем извлечь из других полей
                                    month_num = holiday_data.get('month', 0)
                                    day_num = holiday_data.get('day', 0)
                                    if month_num and day_num:
                                        try:
                                            holiday_date = date(year, month_num, day_num)
                                            holidays.add(holiday_date)
                                        except ValueError:
                                            continue
            
            logger.info(f"Извлечено {len(holidays)} выходных и праздничных дней из календаря на {year} год")
            return holidays
            
        except Exception as e:
            logger.error(f"Ошибка извлечения праздников из календаря: {e}")
            return set()

# Глобальный экземпляр клиента календаря
calendar_client = CalendarClient()

