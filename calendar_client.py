"""
Модуль для работы с производственным календарем РФ

API: https://calendar.kuzyak.in
Структура ответов:
  GET /api/calendar/{year}
    → { year, months: [{ id (0-based), name, workingDays, notWorkingDays, shortDays, workingHours }], status }
  GET /api/calendar/{year}/{MM}/{DD}
    → { year, month: { name, id (0-based) }, date, isWorkingDay: bool, isShortDay: bool, status, holiday?: str }
"""
import logging
import calendar as cal
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from config import config

logger = logging.getLogger(__name__)


class CalendarClient:
    def __init__(self, api_url: str = None):
        self.api_url = api_url or getattr(config, 'CALENDAR_API_URL', 'https://calendar.kuzyak.in')
        self.session = requests.Session()
        self.session.timeout = 10

    # ── Базовые запросы к API ────────────────────────────────────────────

    def get_year_calendar(self, year: int) -> Optional[Dict]:
        """Получить агрегированную информацию по месяцам на год"""
        try:
            url = f"{self.api_url}/api/calendar/{year}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения календаря на {year} год: {e}")
            return None

    def get_day_info(self, year: int, month: int, day: int) -> Optional[Dict]:
        """
        Получить информацию о конкретном дне.
        month — 1-based (1=Январь, 12=Декабрь).
        """
        try:
            url = f"{self.api_url}/api/calendar/{year}/{month:02d}/{day:02d}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения информации о дне {day:02d}.{month:02d}.{year}: {e}")
            return None

    # ── Проверка рабочего дня (используется ежедневно) ───────────────────

    def is_working_day(self, check_date: date = None) -> bool:
        """
        Проверить, является ли день рабочим.
        1) weekday >= 5 → выходной (быстрая проверка без API)
        2) Запрос к API → поле isWorkingDay
        3) При ошибке API будний день считается рабочим
        """
        if check_date is None:
            check_date = date.today()

        # Быстрая проверка: суббота (5) или воскресенье (6) — однозначно выходной
        if check_date.weekday() >= 5:
            return False

        try:
            day_info = self.get_day_info(check_date.year, check_date.month, check_date.day)
            if not day_info:
                logger.warning(f"Не удалось получить информацию о дне {check_date}, считаем рабочим (будний день)")
                return True

            # API возвращает поле isWorkingDay (bool)
            is_working = day_info.get('isWorkingDay', True)

            if not is_working:
                holiday_name = day_info.get('holiday', '')
                if holiday_name:
                    logger.info(f"{check_date} — нерабочий день: {holiday_name}")
                else:
                    logger.info(f"{check_date} — нерабочий день")

            return is_working

        except Exception as e:
            logger.error(f"Ошибка проверки рабочего дня {check_date}: {e}")
            # В случае ошибки будний день считаем рабочим
            return True

    # ── Загрузка календаря на год (выходные + праздники) ─────────────────

    def fetch_year_holidays(self, year: int) -> Tuple[Set[date], Dict[date, str]]:
        """
        Загрузить все нерабочие дни года через поденные запросы к API.
        Возвращает (множество нерабочих дат, словарь {дата: описание}).

        Оптимизация: запрашиваем только дни, у которых weekday < 5 (будни),
        плюс все субботы/воскресенья добавляем без запроса к API.
        Исключение: в РФ бывают рабочие субботы (перенос), но в текущей версии
        мы их не учитываем — бот и так не работает в выходные (weekday >= 5).
        """
        holidays: Set[date] = set()
        descriptions: Dict[date, str] = {}

        # Определяем все дни года
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        total_days = (end - start).days + 1

        # Сначала добавляем все субботы и воскресенья без запросов к API
        current = start
        weekdays_to_check: List[date] = []
        for _ in range(total_days):
            if current.weekday() >= 5:
                holidays.add(current)
            else:
                weekdays_to_check.append(current)
            current += timedelta(days=1)

        logger.info(f"Календарь {year}: {len(holidays)} выходных (Сб/Вс), "
                     f"проверяем {len(weekdays_to_check)} будних дней через API")

        # Запрашиваем будние дни параллельно (до 10 потоков)
        def _check_day(d: date) -> Tuple[date, bool, str]:
            """Запросить один день. Возвращает (дата, is_working, описание)."""
            try:
                info = self.get_day_info(d.year, d.month, d.day)
                if info:
                    is_working = info.get('isWorkingDay', True)
                    holiday_name = info.get('holiday', '')
                    return d, is_working, holiday_name
                return d, True, ''  # При ошибке считаем рабочим
            except Exception:
                return d, True, ''

        non_working_weekdays = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_check_day, d): d for d in weekdays_to_check}
            for future in as_completed(futures):
                try:
                    d, is_working, holiday_name = future.result()
                    if not is_working:
                        holidays.add(d)
                        non_working_weekdays += 1
                        if holiday_name:
                            descriptions[d] = holiday_name
                except Exception as e:
                    logger.error(f"Ошибка при проверке дня: {e}")

        logger.info(f"Календарь {year}: найдено {non_working_weekdays} нерабочих будних дней (праздники/переносы), "
                     f"всего нерабочих дней: {len(holidays)}")

        return holidays, descriptions

    def extract_holidays_from_calendar(self, calendar_data: Dict, year: int = None) -> Set[date]:
        """
        Извлечь нерабочие дни из данных календаря.
        Так как API /api/calendar/{year} не содержит поденной информации,
        используем fetch_year_holidays() для загрузки через поденные запросы.
        """
        if year is None:
            year = calendar_data.get('year', datetime.now().year) if isinstance(calendar_data, dict) else datetime.now().year

        holidays, _ = self.fetch_year_holidays(year)
        return holidays


# Глобальный экземпляр клиента календаря
calendar_client = CalendarClient()
