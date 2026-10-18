import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, PROXY_URL
from handlers_user import router as user_router
from handlers_group import router as group_router
from groups import router as groups_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_scheduler(bot: Bot):
    from send_group import run_scheduled_mailing
    while True:
        try:
            await run_scheduled_mailing(bot)
        except Exception as e:
            logger.exception(f"Ошибка в планировщике: {e}")
            await asyncio.sleep(5)


async def main():
    logger.info("Запуск бота...")

    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else AiohttpSession()
    if PROXY_URL:
        logger.info(f"Работаю через прокси {PROXY_URL}")

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()

    dp.include_router(user_router)
    dp.include_router(group_router)
    dp.include_router(groups_router)

    # Сначала сетевой вызов, ПОТОМ фоновые задачи — чтобы планировщик
    # рассылок не конкурировал за event loop прямо в момент старта бота.
    await bot.delete_webhook(drop_pending_updates=True)

    scheduler_task = asyncio.create_task(run_scheduler(bot))

    logger.info("Бот запущен!")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
