# send.py
import logging
import asyncio
from aiogram.types import Message

from database import get_database

logger = logging.getLogger(__name__)
db = get_database()


async def send_mailing(message: Message, chat_id: int, message_id: int) -> str:
    """
    Отправить сообщение всем пользователям (send)
    """
    users = db.get_all_users()
    total = len(users)
    success = 0
    blocked = 0
    errors = 0

    if total == 0:
        return "❌ Нет активных пользователей для рассылки."

    for user in users:
        user_id = user["user_id"]
        try:
            await message.bot.copy_message(
                chat_id=user_id,
                from_chat_id=chat_id,
                message_id=message_id
            )
            success += 1
            await asyncio.sleep(0.5)  # Задержка 0.5 сек между пользователями
        except Exception as e:
            error_text = str(e)
            if "bot was blocked by the user" in error_text or "user is deactivated" in error_text:
                db.update_user_blocked(user_id, 1)
                blocked += 1
            else:
                errors += 1
                logger.error(f"Ошибка при отправке пользователю {user_id}: {error_text}")

    report = (
        f"✅ Рассылка завершена\n\n"
        f"👥 Всего пользователей: {total}\n\n"
        f"✅ Успешно: {success}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"❌ Другие ошибки: {errors}"
    )

    return report


async def forward_mailing(message: Message, chat_id: int, message_id: int) -> str:
    """
    Переслать сообщение всем пользователям (forward)
    """
    users = db.get_all_users()
    total = len(users)
    success = 0
    blocked = 0
    errors = 0

    if total == 0:
        return "❌ Нет активных пользователей для рассылки."

    for user in users:
        user_id = user["user_id"]
        try:
            await message.bot.forward_message(
                chat_id=user_id,
                from_chat_id=chat_id,
                message_id=message_id
            )
            success += 1
            await asyncio.sleep(0.5)  # Задержка 0.5 сек между пользователями
        except Exception as e:
            error_text = str(e)
            if "bot was blocked by the user" in error_text or "user is deactivated" in error_text:
                db.update_user_blocked(user_id, 1)
                blocked += 1
            else:
                errors += 1
                logger.error(f"Ошибка при пересылке пользователю {user_id}: {error_text}")

    report = (
        f"✅ Рассылка завершена\n\n"
        f"👥 Всего пользователей: {total}\n\n"
        f"✅ Успешно: {success}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"❌ Другие ошибки: {errors}"
    )

    return report