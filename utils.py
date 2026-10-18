# utils.py
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramNotFound

from config import INTERVALS, ADMIN_IDS

logger = logging.getLogger(__name__)


# Ошибки, при которых группа реально перестала быть доступна боту навсегда
# (её нет смысла хранить в базе — сообщения в неё никогда не уйдут).
# ВАЖНО: держим ключевые слова строго такими, какими Telegram Bot API
# реально их присылает (без пробелов/подчёркиваний "на глаз") —
# иначе строковое сравнение просто никогда не совпадёт.
_IRREVERSIBLE_SUBSTRINGS = (
    "chat not found",
    "group chat was deleted",
    "chat was deleted",
    "group is deactivated",
    "supergroup is deactivated",
    "chat_id_invalid",
    "peer_id_invalid",
    "bot was kicked",
    "bot is not a member",
    "user_id_invalid",
    "channel private",
    "channel_private",
    "have no rights to send a message",  # тех. дублирование ниже, см. _TEMPORARY
    "chat restricted",
    "chat_restricted",
)

# Ошибки, которые НЕ означают что группа умерла — их не нужно удалять,
# это либо временная проблема, либо недостающие права (группа жива).
_TEMPORARY_SUBSTRINGS = (
    "flood",
    "retry after",
    "timeout",
    "network",
    "telegram server error",
    "too many requests",
    "internal server error",
    "service unavailable",
    "not enough rights",
    "have no rights",  # боту просто не дали право писать — группа жива
    "message to be replied not found",
    "message can't be forwarded",
    "message can't be copied",
)


def is_group_unreachable(exc: Exception) -> bool:
    """
    Определяет, стоит ли считать группу окончательно недоступной
    (заблокирована/удалена/бот из неё удалён) и удалять её из базы.

    Приоритет отдаётся типу исключения aiogram, а не тексту ошибки —
    текст Telegram может меняться и раньше сравнивался с неточными
    шаблонами, из-за чего часть реально мёртвых групп не удалялась.
    """
    error_text = str(exc).lower()

    # Временные / "группа жива, просто не хватает прав" — никогда не удаляем
    for keyword in _TEMPORARY_SUBSTRINGS:
        if keyword in error_text:
            return False

    # TelegramForbiddenError — бота выгнали/заблокировали в чате.
    # Это самый надёжный сигнал, что группа больше недоступна.
    if isinstance(exc, TelegramForbiddenError):
        return True

    # TelegramNotFound / "чат не найден" — чат удалён или ID больше не существует
    if isinstance(exc, TelegramNotFound):
        return True

    if isinstance(exc, TelegramBadRequest):
        for keyword in _IRREVERSIBLE_SUBSTRINGS:
            if keyword in error_text:
                return True
        return False

    # Фолбэк на случай нестандартного исключения (например, при ретраях)
    for keyword in _IRREVERSIBLE_SUBSTRINGS:
        if keyword in error_text:
            return True

    return False


def format_post_title(post: Dict[str, Any]) -> str:
    """
    Форматирование названия поста для отображения в списке
    """
    title = post.get("title", "Без названия")
    if len(title) > 50:
        return title[:47] + "..."
    return title


def get_interval_name(minutes: int) -> str:
    """
    Получить название интервала по количеству минут
    """
    for name, value in INTERVALS.items():
        if value == minutes:
            return name
    return f"{minutes} минут"


def format_time(timestamp: int) -> str:
    """
    Форматирование Unix timestamp в читаемый вид
    """
    if not timestamp:
        return "Неизвестно"
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%d.%m.%Y %H:%M")


def chunks(lst: List, n: int):
    """
    Разбить список на части по n элементов
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def run_in_background(func, *args, **kwargs):
    """
    Запустить функцию в фоновом режиме
    """
    try:
        await func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Ошибка в фоновой задаче: {e}")

def is_admin(user_id: int) -> bool:
    """Админ — если он в ADMIN_IDS из .env или в таблице admins в базе."""
    if user_id in ADMIN_IDS:
        return True
    try:
        from database import get_database
        return user_id in get_database().get_admin_ids()
    except Exception as e:
        logger.error(f"Не удалось прочитать админов из базы: {e}")
        return False
