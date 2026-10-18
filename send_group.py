# send_group.py
import logging
import asyncio
from aiogram import Bot
from datetime import datetime

from database import get_database
from utils import is_group_unreachable

logger = logging.getLogger(__name__)
db = get_database()


async def send_to_group(bot: Bot, post_id: int) -> str:
    """
    Отправить сообщение в группы (send) для циклической рассылки
    """
    post = db.get_post(post_id)
    if not post:
        return "❌ Рассылка не найдена."

    groups = db.get_post_groups(post_id)
    if not groups:
        return "❌ Нет групп для рассылки."

    success = 0
    errors = 0

    for group in groups:
        chat_id = group["chat_id"]
        try:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=post["source_chat_id"],
                message_id=post["message_id"]
            )
            success += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            errors += 1
            logger.error(f"Ошибка при отправке в группу {chat_id}: {e}")

            # Проверяем, является ли ошибка необратимой
            if is_group_unreachable(e):
                db.delete_group(chat_id)
                logger.info(f"🗑️ Удалена неактуальная группа {chat_id} из базы")

    report = (
        f"📨 Рассылка #{post_id} выполнена\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {errors}"
    )

    return report


async def forward_to_group(bot: Bot, post_id: int) -> str:
    """
    Переслать сообщение в группы (forward) для циклической рассылки
    """
    post = db.get_post(post_id)
    if not post:
        return "❌ Рассылка не найдена."

    groups = db.get_post_groups(post_id)
    if not groups:
        return "❌ Нет групп для рассылки."

    success = 0
    errors = 0

    for group in groups:
        chat_id = group["chat_id"]
        try:
            await bot.forward_message(
                chat_id=chat_id,
                from_chat_id=post["source_chat_id"],
                message_id=post["message_id"]
            )
            success += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            errors += 1
            logger.error(f"Ошибка при пересылке в группу {chat_id}: {e}")

            # Проверяем, является ли ошибка необратимой
            if is_group_unreachable(e):
                db.delete_group(chat_id)
                logger.info(f"🗑️ Удалена неактуальная группа {chat_id} из базы")

    report = (
        f"📨 Рассылка #{post_id} выполнена\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {errors}"
    )

    return report


async def run_scheduled_mailing(bot: Bot):
    """
    Запуск циклических рассылок по расписанию
    """
    while True:
        try:
            posts = db.get_all_posts()

            for post in posts:
                post_id = post["id"]
                post_type = post["type"]
                interval = post["interval"]
                created_at = post["created_at"]

                now = datetime.now().timestamp()
                time_diff = now - created_at

                if time_diff >= interval * 60:
                    db.update_post_created_at(post_id, int(now))

                    if post_type == "send":
                        await send_to_group(bot, post_id)
                    else:
                        await forward_to_group(bot, post_id)

            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Ошибка в планировщике: {e}")
            await asyncio.sleep(60)
