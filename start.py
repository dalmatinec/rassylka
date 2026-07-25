# start.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import time

from database import add_user, get_user_link, save_user_link, delete_user_link
from keyboards import main_menu, cancel_inline
from utils import get_link, get_chat_id

router = Router()

# Словарь с названиями ссылок
LINK_NAMES = {
    "chat": "💬 Чат",
    "news": "📢 Новости",
    "reserve": "🛟 Резерв",
    "bot": "🤖 Бот",
    "ceo": "👨‍💼 CEO",
    "operator": "🎧 Оператор"
}

def load_welcome_text():
    """Загружает приветственный текст из text.json"""
    try:
        with open("text.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("welcome", "")
    except:
        return "Добро пожаловать!"

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    # Игнорируем команду в группах
    if message.chat.type in ["group", "supergroup"]:
        return
    user = message.from_user
    # Регистрация пользователя
    add_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    # Загружаем текст приветствия и подставляем имя
    welcome_text = load_welcome_text().format(first_name=user.first_name)
    # Отправляем фото с подписью
    if os.path.exists("start.jpg"):
        photo = FSInputFile("start.jpg")
        await message.answer_photo(
            photo=photo,
            caption=welcome_text,
            reply_markup=main_menu()
        )
    else:
        await message.answer(
            welcome_text,
            reply_markup=main_menu()
        )

@router.callback_query(F.data.startswith("link_"))
async def callback_link(callback: types.CallbackQuery):
    """Обработчик кнопок со ссылками"""
    # НЕ вызываем await callback.answer() в начале!
    # Игнорируем нажатия в группах
    if callback.message.chat.type in ["group", "supergroup"]:
        await callback.answer("❌  Используйте бота в личных сообщениях", show_alert=True)
        return
    link_key = callback.data.replace("link_", "")
    link_name = LINK_NAMES.get(link_key, link_key)
    # Для чата, новостей, резерва - генерируем ссылку
    if link_key in ["chat", "news", "reserve"]:
        chat_id = get_chat_id(link_key)
        if not chat_id:
            await callback.answer("❌  Ссылка не настроена", show_alert=True)
            return
        user_id = callback.from_user.id
        # Проверяем наличие активной ссылки в БД для этого типа
        created_at = get_user_link(user_id, link_key)
        if created_at:
            elapsed = time.time() - created_at
            if elapsed < 1800:  # 30 минут
                remaining = int(1800 - elapsed)
                minutes = remaining // 60
                seconds = remaining % 60
                await callback.answer(
                    f"⏳  Новая ссылка будет доступна через {minutes} мин {seconds} сек",
                    show_alert=True
                )
                return
            else:
                # Время истекло, удаляем старую запись
                delete_user_link(user_id, link_key)
        try:
            from datetime import datetime, timedelta
            expire_date = datetime.now() + timedelta(minutes=30)
            link = await callback.bot.create_chat_invite_link(
                chat_id=chat_id,
                member_limit=1,
                expire_date=expire_date
            )
            save_user_link(user_id, link_key, int(time.time()))
            
            # Кнопка с ссылкой
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎟️ Вступить", url=link.invite_link)]
            ])
            
            await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=(
                    f"🎟️ Приглашение готово\n\n"
                    f"⏳ Действует: 30 минут\n"
                    f"🎯 Использование: 1 раз\n\n"
                    f"🔄 После истечения срока можно запросить новую ссылку."
                ),
                reply_markup=keyboard
            )
            await callback.answer()  # закрываем callback после успеха
        except Exception as e:
            await callback.answer(f"❌  Ошибка при генерации ссылки: {e}", show_alert=True)
    # Для бота, CEO, оператора - фиксированные ссылки
    else:
        url = get_link(link_key)
        if url:
            await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=f"{link_name}\n\n🔗 {url}"
            )
            await callback.answer()
        else:
            await callback.answer("❌  Ссылка не настроена", show_alert=True)

@router.callback_query(F.data == "support")
async def callback_support(callback: types.CallbackQuery):
    """Обработчик кнопки 'Связаться с оператором'"""
    await callback.answer()
    # Игнорируем нажатия в группах
    if callback.message.chat.type in ["group", "supergroup"]:
        await callback.answer("❌  Используйте бота в личных сообщениях", show_alert=True)
        return
    await callback.message.delete()
    await callback.message.answer(
        "Опишите проблему одним сообщением.\n"
        "Поддерживаются только текстовые сообщения.\n\n"
        "Ответ придет прямо в этот чат.",
        reply_markup=cancel_inline()
    )

@router.callback_query(F.data == "cancel_support")
async def callback_cancel(callback: types.CallbackQuery):
    """Отмена обращения"""
    await callback.answer()
    # Игнорируем нажатия в группах
    if callback.message.chat.type in ["group", "supergroup"]:
        await callback.answer("❌  Используйте бота в личных сообщениях", show_alert=True)
        return
    await callback.message.delete()
    await callback.message.answer(
        "❌  Обращение отменено"
    )