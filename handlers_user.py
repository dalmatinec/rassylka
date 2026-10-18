# handlers_user.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from utils import is_admin
from database import get_database
from send import send_mailing, forward_mailing
from keyboards import confirmation_keyboard

logger = logging.getLogger(__name__)
router = Router()
db = get_database()


class MailingStates(StatesGroup):
    waiting_for_message = State()
    waiting_confirmation = State()


@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    db.add_user(user_id)

    user = db.get_user(user_id)
    if user and user["is_blocked"] == 1:
        db.update_user_blocked(user_id, 0)

    await message.answer("Привет")


@router.message(Command("send"))
async def cmd_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(MailingStates.waiting_for_message)
    await state.update_data(mailing_type="send")

    await message.answer(
        "📨 Отправьте сообщение для рассылки.\n"
        "Это может быть текст, фото, видео или документ.\n\n"
        "Для отмены используйте /cancel"
    )


@router.message(Command("forward"))
async def cmd_forward(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(MailingStates.waiting_for_message)
    await state.update_data(mailing_type="forward")

    await message.answer(
        "📨 Перешлите сообщение для рассылки.\n"
        "Это может быть текст, фото, видео или документ.\n\n"
        "Для отмены используйте /cancel"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нет активных действий для отмены.")
        return

    await state.clear()
    await message.answer("✅ Действие отменено.")


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        return

    help_text = (
        "📋 Доступные команды:\n\n"
        "🤖 Команды в личном чате:\n"
        "/start - показать приветствие\n"
        "/send - отправить рассылку в ЛС\n"
        "/forward - переслать рассылку в ЛС\n"
        "/cancel - отменить текущее действие\n\n"
        "➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
        "👥 Команды в админской группе:\n"
        "/list - список всех рассылок\n"
        "/new - создать новую рассылку (ответом на сообщение)\n"
        "/groups - управление группами (список, проверка, удаление)"
    )

    await message.answer(help_text)


@router.message(MailingStates.waiting_for_message, F.text | F.photo | F.video | F.document | F.audio | F.voice)
async def handle_mailing_message(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    mailing_type = data.get("mailing_type")

    await state.update_data(
        message_id=message.message_id,
        chat_id=message.chat.id
    )

    await state.set_state(MailingStates.waiting_confirmation)

    await message.answer(
        f"✅ Сообщение получено!\n"
        f"Тип рассылки: {'📤 send' if mailing_type == 'send' else '📨 forward'}\n\n"
        f"Нажмите ✅ Подтвердить для начала рассылки.\n"
        f"Или ❌ Отмена для отмены.",
        reply_markup=confirmation_keyboard(mailing_type)
    )


@router.callback_query(F.data.startswith("confirm_mailing_"))
async def confirm_mailing(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    data = await state.get_data()
    mailing_type = data.get("mailing_type")
    message_id = data.get("message_id")
    chat_id = data.get("chat_id")

    await callback.message.edit_text("⏳ Начинаю рассылку...")

    if mailing_type == "send":
        result = await send_mailing(callback.message, chat_id, message_id)
    else:
        result = await forward_mailing(callback.message, chat_id, message_id)

    await callback.message.edit_text(result)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cancel_mailing")
async def cancel_mailing(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()
