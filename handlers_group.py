# handlers_group.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_GROUP_ID
from utils import can_manage as is_admin, interval_text
from database import get_database
from keyboards import (
    get_posts_list_keyboard,
    get_post_detail_keyboard,
    get_groups_list_keyboard,
    get_interval_keyboard,
    get_confirm_keyboard,
    get_back_keyboard,
    get_title_input_keyboard,
    get_cancel_keyboard
)
from send_group import forward_to_group

logger = logging.getLogger(__name__)
router = Router()
db = get_database()


def is_admin_group(chat_id: int) -> bool:
    return chat_id == ADMIN_GROUP_ID


class CreatePostStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_groups = State()
    waiting_for_interval = State()
    waiting_confirmation = State()


class RenamePostStates(StatesGroup):
    waiting_for_new_title = State()


@router.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not is_admin_group(message.chat.id):
        return

    posts = db.get_all_posts()

    if not posts:
        await message.answer("📭 Нет созданных рассылок.")
        return

    text = "📋 Список рассылок:\n\n"
    for post in posts:
        groups_count = db.get_post_groups_count(post["id"])
        mark = "📤 " if post.get("is_once") or not post.get("interval") else ""
        text += f"{mark}{post['id']}. {post['title']} (групп: {groups_count})\n"

    await message.answer(text, reply_markup=get_posts_list_keyboard(posts))


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not is_admin_group(message.chat.id):
        return

    if not message.reply_to_message:
        await message.answer("❌ Используйте /new ответом на сообщение, которое хотите разослать.")
        return

    reply = message.reply_to_message

    if reply.text:
        auto_title = reply.text[:50] + "..." if len(reply.text) > 50 else reply.text
    elif reply.photo:
        auto_title = "[Фото]"
    elif reply.video:
        auto_title = "[Видео]"
    elif reply.document:
        auto_title = "[Документ]"
    elif reply.voice:
        auto_title = "[Голосовое]"
    else:
        auto_title = "Без названия"

    await state.update_data(
        source_chat_id=reply.chat.id,
        message_id=reply.message_id,
        title=auto_title,
        auto_title=auto_title,
        post_type="forward",
        reply_message=reply
    )

    await state.set_state(CreatePostStates.waiting_for_title)

    await message.answer(
        f"✏️ Введите название для этой рассылки (для себя, чтобы легко находить её в списке).\n\n"
        f"Автоназвание по умолчанию: «{auto_title}»",
        reply_markup=get_title_input_keyboard()
    )


async def _ask_for_groups(message: Message, state: FSMContext):
    """Показывает выбор групп после того, как название рассылки определено"""
    await state.set_state(CreatePostStates.waiting_for_groups)

    groups = db.get_all_groups(active_only=True)
    if not groups:
        await message.answer("❌ Нет доступных рабочих групп. Добавьте бота в группы.")
        await state.clear()
        return

    await state.update_data(selected_groups=[])
    await message.answer(
        _select_text(0, len(groups)),
        reply_markup=_select_keyboard(groups, [])
    )


def _select_text(selected: int, total: int) -> str:
    return (
        "📢 Выберите группы для рассылки\n"
        f"Выбрано: {selected} из {total}"
    )


def _select_keyboard(groups, selected_ids):
    for group in groups:
        group["is_selected"] = group["chat_id"] in selected_ids
    return get_groups_list_keyboard(groups, 0, "select")


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup=None):
    """edit_text, который не падает, если текст и кнопки не изменились"""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


@router.message(CreatePostStates.waiting_for_title, F.text)
async def process_post_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not is_admin_group(message.chat.id):
        return

    title = message.text.strip()[:100]
    if not title:
        await message.answer("❌ Название не может быть пустым. Введите ещё раз:")
        return

    await state.update_data(title=title)
    await _ask_for_groups(message, state)


@router.callback_query(CreatePostStates.waiting_for_title, F.data == "skip_title_0")
async def skip_post_title(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    state_data = await state.get_data()
    auto_title = state_data.get("auto_title", "Без названия")
    await state.update_data(title=auto_title)

    await callback.message.delete()
    await _ask_for_groups(callback.message, state)
    await callback.answer()


@router.callback_query(
    CreatePostStates.waiting_for_groups,
    F.data.startswith("select_")
)
async def toggle_group_for_post(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    data_parts = callback.data.split("_")
    chat_id = int(data_parts[2])

    state_data = await state.get_data()
    selected_groups = state_data.get("selected_groups", [])

    if chat_id in selected_groups:
        selected_groups.remove(chat_id)
    else:
        selected_groups.append(chat_id)

    await state.update_data(selected_groups=selected_groups)

    groups = db.get_all_groups(active_only=True)
    await _safe_edit(
        callback,
        _select_text(len(selected_groups), len(groups)),
        reply_markup=_select_keyboard(groups, selected_groups)
    )
    await callback.answer()


@router.callback_query(
    CreatePostStates.waiting_for_groups,
    F.data.in_({"selall_0", "selnone_0"})
)
async def select_all_groups_for_post(callback: CallbackQuery, state: FSMContext):
    """Кнопки «Выбрать все» / «Снять все» при создании рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    groups = db.get_all_groups(active_only=True)
    if callback.data == "selall_0":
        selected_groups = [g["chat_id"] for g in groups]
        note = f"✅ Выбраны все: {len(selected_groups)}"
    else:
        selected_groups = []
        note = "⬜ Выбор снят"

    await state.update_data(selected_groups=selected_groups)
    await _safe_edit(
        callback,
        _select_text(len(selected_groups), len(groups)),
        reply_markup=_select_keyboard(groups, selected_groups)
    )
    await callback.answer(note)


@router.callback_query(
    CreatePostStates.waiting_for_groups,
    F.data.startswith("done_create_groups_0")
)
async def done_groups_selection(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    state_data = await state.get_data()
    selected_groups = state_data.get("selected_groups", [])

    if not selected_groups:
        await callback.answer("❌ Выберите хотя бы одну группу.", show_alert=True)
        return

    await state.set_state(CreatePostStates.waiting_for_interval)

    await callback.message.edit_text(
        "🕒 Как отправлять?\n\n"
        "Интервал — бот будет сам повторять рассылку.\n"
        "«📤 Один раз» — отправит сейчас и больше не повторит.",
        reply_markup=get_interval_keyboard(0, "create")
    )
    await callback.answer()


@router.callback_query(
    CreatePostStates.waiting_for_interval,
    F.data.startswith("create_interval_0_")
)
async def process_interval_for_post(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    interval = int(callback.data.split("_")[3])
    await state.update_data(interval=interval)

    await state.set_state(CreatePostStates.waiting_confirmation)

    state_data = await state.get_data()
    selected_groups = state_data.get("selected_groups", [])
    title = state_data.get("title", "Без названия")

    groups_text = []
    for chat_id in selected_groups:
        group = db.get_group(chat_id)
        if group:
            groups_text.append(f"• {group['title']}")

    text = (
        f"📝 Проверьте данные рассылки:\n\n"
        f"📌 Название: {title}\n"
        f"📤 Тип: forward\n"
        f"🕒 Режим: {interval_text(interval)}\n"
        f"📢 Групп: {len(selected_groups)}\n\n"
        f"Список групп:\n" + "\n".join(groups_text) + "\n\n"
        f"Подтвердить создание?"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_confirm_keyboard("create", 0)
    )
    await callback.answer()


@router.callback_query(
    CreatePostStates.waiting_confirmation,
    F.data.startswith("confirm_create_0_")
)
async def confirm_create_post(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    state_data = await state.get_data()
    post_type = state_data.get("post_type", "forward")
    interval = state_data.get("interval")
    selected_groups = state_data.get("selected_groups", [])
    source_chat_id = state_data.get("source_chat_id")
    message_id = state_data.get("message_id")
    title = state_data.get("title", "Без названия")
    reply_message = state_data.get("reply_message")

    # Создаем пост
    post_id = db.create_post(title, post_type, source_chat_id, message_id, interval)

    db.add_groups_to_post(post_id, selected_groups)

    await state.clear()
    await callback.answer()
    await callback.message.edit_text(f"⏳ Отправляю в {len(selected_groups)} групп...")

    # Отправляем сразу после создания
    report = await forward_to_group(callback.bot, post_id)
    stats = report.split("\n", 1)[1] if "\n" in report else report

    if not interval:
        tail = "📤 Разовая рассылка — больше повторяться не будет.\nПовторить можно кнопкой «📤 Отправить сейчас»."
    else:
        tail = f"🔁 Дальше — автоматически, {interval_text(interval)[2:]}."

    await callback.message.edit_text(
        f"✅ Рассылка #{post_id} создана и отправлена!\n\n"
        f"📌 Название: {title}\n"
        f"🕒 Режим: {interval_text(interval)}\n"
        f"📢 Групп: {len(selected_groups)}\n\n"
        f"{stats}\n\n"
        f"{tail}",
        reply_markup=get_back_keyboard("back_to_list")
    )


@router.callback_query(
    CreatePostStates.waiting_for_title,
    F.data.startswith("cancel_create_0")
)
@router.callback_query(
    CreatePostStates.waiting_for_groups,
    F.data.startswith("cancel_create_0")
)
@router.callback_query(
    CreatePostStates.waiting_for_interval,
    F.data.startswith("cancel_create_0")
)
@router.callback_query(
    CreatePostStates.waiting_confirmation,
    F.data.startswith("cancel_create_0")
)
async def cancel_create_post(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text("❌ Создание рассылки отменено.")
    await callback.answer()


@router.callback_query(F.data.startswith("post_"))
async def show_post_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[1])

    post_info = db.get_post_info(post_id)
    if not post_info:
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    groups = db.get_post_groups(post_id)
    groups_text = "\n".join([f"• {g['title']}" for g in groups]) if groups else "Нет групп"

    text = (
        f"📨 Рассылка #{post_id}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📌 Название: {post_info['title']}\n"
        f"📤 Тип: {post_info['type']}\n"
        f"⏱ Режим: {interval_text(post_info)}\n"
        f"📊 Групп: {post_info['groups_count']}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📢 Список групп:\n{groups_text}"
    )

    await callback.message.edit_text(text, reply_markup=get_post_detail_keyboard(post_id))
    await callback.answer()


@router.callback_query(F.data == "back_to_list")
async def back_to_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    posts = db.get_all_posts()

    if not posts:
        await callback.message.edit_text("📭 Нет созданных рассылок.")
        return

    text = "📋 Список рассылок:\n\n"
    for post in posts:
        groups_count = db.get_post_groups_count(post["id"])
        mark = "📤 " if post.get("is_once") or not post.get("interval") else ""
        text += f"{mark}{post['id']}. {post['title']} (групп: {groups_count})\n"

    await callback.message.edit_text(text, reply_markup=get_posts_list_keyboard(posts))
    await callback.answer()


def _edit_groups_text(post_id: int, groups) -> str:
    selected = sum(1 for g in groups if g.get("is_selected"))
    return (
        f"📢 Группы рассылки #{post_id}\n"
        f"Выбрано: {selected} из {len(groups)}\n\n"
        f"Нажмите на группу, чтобы включить/выключить её."
    )


async def _show_edit_groups(callback: CallbackQuery, post_id: int, note: str = None):
    groups = db.get_groups_with_status(post_id)
    if not groups:
        await callback.message.edit_text(
            "❌ Нет рабочих групп. Добавьте бота в группы.",
            reply_markup=get_back_keyboard(f"post_{post_id}")
        )
        await callback.answer()
        return
    await _safe_edit(
        callback,
        _edit_groups_text(post_id, groups),
        reply_markup=get_groups_list_keyboard(groups, post_id, "add")
    )
    await callback.answer(note)


@router.callback_query(F.data.startswith("add_group_"))
async def add_group_to_post(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])

    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    await _show_edit_groups(callback, post_id)


@router.callback_query(F.data.startswith("addall_") | F.data.startswith("addnone_"))
async def add_all_groups_to_post(callback: CallbackQuery):
    """«Выбрать все» / «Снять все» для существующей рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    action, post_id = callback.data.split("_")
    post_id = int(post_id)
    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    if action == "addall":
        ids = [g["chat_id"] for g in db.get_all_groups(active_only=True)]
        db.add_groups_to_post(post_id, ids)
        note = f"✅ Добавлены все группы: {len(ids)}"
    else:
        db.clear_post_groups(post_id)
        note = "⬜ Все группы сняты"
    logger.info(f"Рассылка #{post_id}: {note}")
    await _show_edit_groups(callback, post_id, note)


@router.callback_query(F.data.startswith("remove_group_"))
async def remove_group_from_post(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])

    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    groups = db.get_post_groups(post_id)

    if not groups:
        await callback.message.edit_text("❌ У этой рассылки нет групп.")
        await callback.answer()
        return

    for group in groups:
        group["is_selected"] = True

    await callback.message.edit_text(
        f"➖ Группы рассылки #{post_id} (сейчас: {len(groups)})\n"
        f"Нажмите на группу, чтобы убрать её из рассылки.",
        reply_markup=get_groups_list_keyboard(groups, post_id, "remove")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_chat_"))
async def toggle_add_group(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    data_parts = callback.data.split("_")
    post_id = int(data_parts[2])
    chat_id = int(data_parts[3])

    if chat_id in db.get_post_group_ids(post_id):
        db.remove_group_from_post(post_id, chat_id)
        note = "⬜ Группа убрана"
    else:
        db.add_group_to_post(post_id, chat_id)
        note = "☑️ Группа добавлена"

    await _show_edit_groups(callback, post_id, note)


@router.callback_query(F.data.startswith("remove_chat_"))
async def toggle_remove_group(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    data_parts = callback.data.split("_")
    post_id = int(data_parts[2])
    chat_id = int(data_parts[3])

    db.remove_group_from_post(post_id, chat_id)

    groups = db.get_post_groups(post_id)
    for group in groups:
        group["is_selected"] = True

    await _safe_edit(
        callback,
        f"➖ Группы рассылки #{post_id} (осталось: {len(groups)})\n"
        f"Нажмите на группу, чтобы убрать её из рассылки.",
        reply_markup=get_groups_list_keyboard(groups, post_id, "remove")
    )
    await callback.answer("✅ Группа убрана")


@router.callback_query(F.data.startswith("remall_"))
async def remove_all_groups_from_post(callback: CallbackQuery):
    """«Убрать все группы» из рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[1])
    db.clear_post_groups(post_id)
    await callback.message.edit_text(
        f"🗑 Все группы убраны из рассылки #{post_id}.\n"
        f"Рассылка не будет никуда отправляться, пока не добавите группы.",
        reply_markup=get_back_keyboard(f"post_{post_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("done_edit_groups_"))
async def done_groups(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[3])

    await callback.message.edit_text(
        "✅ Список групп обновлен!",
        reply_markup=get_back_keyboard(f"post_{post_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rename_post_"))
async def rename_post_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])

    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    await state.update_data(post_id=post_id)
    await state.set_state(RenamePostStates.waiting_for_new_title)

    await callback.message.edit_text(
        f"✏️ Введите новое название для рассылки #{post_id}:",
        reply_markup=get_cancel_keyboard(f"post_{post_id}")
    )
    await callback.answer()


@router.message(RenamePostStates.waiting_for_new_title, F.text)
async def rename_post_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not is_admin_group(message.chat.id):
        return

    title = message.text.strip()[:100]
    if not title:
        await message.answer("❌ Название не может быть пустым. Введите ещё раз:")
        return

    state_data = await state.get_data()
    post_id = state_data.get("post_id")

    if not post_id or not db.post_exists(post_id):
        await message.answer("❌ Рассылка не найдена.")
        await state.clear()
        return

    db.update_post_title(post_id, title)
    await state.clear()

    await message.answer(
        f"✅ Название рассылки #{post_id} изменено на «{title}»",
        reply_markup=get_back_keyboard(f"post_{post_id}")
    )


@router.callback_query(F.data.startswith("send_now_"))
async def send_post_now(callback: CallbackQuery):
    """Разово отправить рассылку прямо сейчас (интервал не сбивается)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])
    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return
    count = db.get_post_groups_count(post_id)
    if not count:
        await callback.answer("❌ У рассылки нет групп", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(f"⏳ Отправляю рассылку #{post_id} в {count} групп...")
    report = await forward_to_group(callback.bot, post_id)
    await callback.message.edit_text(report, reply_markup=get_back_keyboard(f"post_{post_id}"))


@router.callback_query(F.data.startswith("change_interval_"))
async def change_interval(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])

    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"🕒 Как отправлять рассылку #{post_id}?\n\n"
        f"Интервал — бот будет сам повторять.\n"
        f"«Один раз» — без повтора.",
        reply_markup=get_interval_keyboard(post_id, "edit")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_interval_"))
async def set_interval(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    data_parts = callback.data.split("_")
    post_id = int(data_parts[2])
    interval = int(data_parts[3])

    db.update_post_interval(post_id, interval)

    await callback.message.edit_text(
        f"✅ Режим рассылки #{post_id}: {interval_text(interval)}",
        reply_markup=get_back_keyboard(f"post_{post_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_post_"))
async def delete_post(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])

    if not db.post_exists(post_id):
        await callback.message.edit_text("❌ Рассылка не найдена.")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить рассылку #{post_id}?\n"
        f"Это действие невозможно отменить.",
        reply_markup=get_confirm_keyboard("delete", post_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_post(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])

    db.delete_post(post_id)

    await callback.message.edit_text(
        f"✅ Рассылка #{post_id} удалена!",
        reply_markup=get_back_keyboard("back_to_list")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_delete_"))
async def cancel_delete_post(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        "❌ Удаление отменено.",
        reply_markup=get_back_keyboard(f"post_{post_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_edit_"))
async def cancel_edit_interval(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    if not is_admin_group(callback.message.chat.id):
        await callback.answer("⛔ Не админская группа", show_alert=True)
        return

    post_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        "❌ Изменение интервала отменено.",
        reply_markup=get_back_keyboard(f"post_{post_id}")
    )
    await callback.answer()


@router.message(F.new_chat_members)
async def bot_added_to_group(message: Message):
    for member in message.new_chat_members:
        if member.id == (await message.bot.me()).id:
            chat_id = message.chat.id
            title = message.chat.title or "Без названия"

            db.add_group(chat_id, title)
            logger.info(f"✅ Бот добавлен в группу {chat_id} ({title})")
            
            try:
                await message.answer(f"✅ Бот добавлен в группу: {title}")
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке подтверждения добавления бота: {e}")


@router.message(F.left_chat_member)
async def bot_removed_from_group(message: Message):
    if message.left_chat_member.id == (await message.bot.me()).id:
        chat_id = message.chat.id

        group = db.get_group(chat_id)
        if group:
            title = group["title"]
            db.delete_group(chat_id)
            logger.info(f"Бот удален из группы: {title}")

@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    """Бота добавили/удалили/выгнали — срабатывает и в супергруппах и в каналах,
    даже когда сервисного сообщения «бот добавлен» нет."""
    if event.chat.type not in ("group", "supergroup", "channel"):
        return
    status = event.new_chat_member.status
    chat_id = event.chat.id
    title = event.chat.title or "Без названия"

    if status in ("member", "administrator", "creator"):
        db.add_group(chat_id, title)
        logger.info(f"✅ Бот в чате {chat_id} ({title}) — статус {status}, группа подключена")
    elif status in ("left", "kicked"):
        if db.get_group(chat_id):
            db.delete_group(chat_id)
            logger.info(f"🚪 Бот удалён из {chat_id} ({title}) — группа убрана из базы")
