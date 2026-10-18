# groups.py — управление группами через /groups (только в админской группе)
#
# /groups → меню:
#   📋 Мои группы      — список по 10 штук на страницу, ◀️ 1/3 ▶️
#                        нажал на группу → 🔍 Проверить / ✏️ Переименовать / 🗑 Удалить
#   🔍 Проверить все   — бот пробует написать в каждую группу, мёртвые помечает ❌
#   🗑 Удалить нерабочие — одним нажатием чистит все ❌ (и из рассылок тоже)
#   ➕ Добавить по ID  — если бот в группе, но сам её не подхватил
import logging
import asyncio
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from database import get_database
from config import ADMIN_GROUP_ID
from keyboards import (
    GROUPS_PER_PAGE,
    get_groups_main_keyboard,
    get_groups_page_keyboard,
    get_group_manage_keyboard,
    get_group_delete_confirm_keyboard,
    get_groups_back_keyboard,
)
from utils import is_group_unreachable, can_manage as is_admin

logger = logging.getLogger(__name__)
router = Router()
db = get_database()

# Таймаут для проверки одной группы (в секундах)
CHECK_GROUP_TIMEOUT = 8
# Чтобы две проверки не запустились одновременно
_check_running = False


class AddGroupStates(StatesGroup):
    waiting_for_chat_id = State()
    waiting_for_title = State()


class RenameGroupStates(StatesGroup):
    waiting_for_new_title = State()


MAIN_MENU_TEXT = (
    "📂 <b>Управление группами</b>\n\n"
    "📋 <b>Мои группы</b> — список, проверка, переименование, удаление\n"
    "🔍 <b>Проверить все</b> — найти группы, где бот больше не может писать\n"
    "➕ <b>Добавить по ID</b> — если бот в группе, но не подхватил её сам"
)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _allowed(chat_id: int, user_id: int) -> bool:
    return chat_id == ADMIN_GROUP_ID and is_admin(user_id)


async def _safe_edit(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


def _parse(data: str):
    """'gm_-100123_2' -> (-100123, 2)"""
    parts = data.split("_")
    return int(parts[1]), int(parts[2]) if len(parts) > 2 else 0


def _page_text(groups, page: int) -> str:
    total_pages = max(1, (len(groups) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    active = sum(1 for g in groups if g.get("is_active", 1))
    broken = len(groups) - active
    text = (
        f"📋 <b>Мои группы</b> — стр. {page + 1}/{total_pages}\n\n"
        f"Всего: <b>{len(groups)}</b>   ✅ {active}"
    )
    if broken:
        text += f"   ❌ {broken}"
    text += "\n\nНажмите на группу, чтобы открыть её."
    if broken:
        text += "\n❌ — бот не может туда писать, такие можно удалить кнопкой ниже."
    return text


async def _show_page(message: Message, page: int, edit: bool = True):
    groups = db.get_all_groups()
    if not groups:
        text = "📂 Групп пока нет.\n\nДобавьте бота в группу — она появится здесь сама."
        kb = get_groups_main_keyboard()
    else:
        total_pages = max(1, (len(groups) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        text = _page_text(groups, page)
        kb = get_groups_page_keyboard(groups, page)
    if edit:
        await _safe_edit(message, text, kb)
    else:
        await message.answer(text, reply_markup=kb)


def _group_text(group, posts_count: int) -> str:
    status = "✅ доступна" if group.get("is_active", 1) else "❌ недоступна (бот удалён / нет прав / чат удалён)"
    checked = group.get("last_checked")
    checked_text = datetime.fromtimestamp(checked).strftime("%d.%m.%Y %H:%M") if checked else "ещё не проверялась"
    return (
        f"👥 <b>{_esc(group['title'])}</b>\n\n"
        f"🆔 ID: <code>{group['chat_id']}</code>\n"
        f"📶 Статус: {status}\n"
        f"🕒 Проверка: {checked_text}\n"
        f"📨 В рассылках: {posts_count}"
    )


async def check_group_accessibility(bot: Bot, chat_id: int):
    """
    Проверяет, может ли бот писать в группу (отправляет и сразу удаляет тестовое сообщение).
    True — доступна, False — мёртвая, None — временная ошибка (статус не трогаем).
    """
    try:
        sent_message = await asyncio.wait_for(
            bot.send_message(chat_id, "Обновление...", parse_mode=None),
            timeout=CHECK_GROUP_TIMEOUT
        )
        try:
            await bot.delete_message(chat_id, sent_message.message_id)
        except Exception as e:
            logger.debug(f"Нет прав удалить тестовое сообщение в {chat_id}: {e}")
        return True

    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Таймаут при проверке группы {chat_id}")
        return None

    except Exception as e:
        logger.warning(f"Группа {chat_id} недоступна: {type(e).__name__}: {e}")
        if is_group_unreachable(e):
            return False
        logger.info(f"Временная ошибка для {chat_id}, статус не меняем")
        return None


# ===================== МЕНЮ =====================

@router.message(Command("groups"))
async def cmd_groups(message: Message, state: FSMContext):
    if not _allowed(message.chat.id, message.from_user.id):
        return
    await state.clear()
    await message.reply(MAIN_MENU_TEXT, reply_markup=get_groups_main_keyboard())


@router.callback_query(F.data == "groups_main_menu")
async def callback_groups_main_menu(callback: CallbackQuery, state: FSMContext):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await _safe_edit(callback.message, MAIN_MENU_TEXT, get_groups_main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "groups_close")
async def callback_groups_close(callback: CallbackQuery, state: FSMContext):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        await _safe_edit(callback.message, "📂 Меню закрыто.")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def callback_noop(callback: CallbackQuery):
    await callback.answer()


# ===================== СПИСОК ПО СТРАНИЦАМ =====================

@router.callback_query(F.data.startswith("groups_page_"))
async def callback_groups_page(callback: CallbackQuery, state: FSMContext):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    page = int(callback.data.rsplit("_", 1)[1])
    await _show_page(callback.message, page)
    await callback.answer()


# Старые кнопки из прошлой версии (если остались в чате)
@router.callback_query(F.data.in_({"groups_list", "groups_back_to_list"}))
async def callback_groups_list_legacy(callback: CallbackQuery):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    await _show_page(callback.message, 0)
    await callback.answer()


# ===================== ОДНА ГРУППА =====================

@router.callback_query(F.data.startswith("gm_"))
async def callback_group_manage(callback: CallbackQuery, state: FSMContext):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    chat_id, page = _parse(callback.data)
    group = db.get_group(chat_id)
    if not group:
        await callback.answer("❌ Группа уже удалена")
        await _show_page(callback.message, page)
        return
    posts_count = len(db.get_posts_for_group(chat_id))
    await _safe_edit(callback.message, _group_text(group, posts_count), get_group_manage_keyboard(chat_id, page))
    await callback.answer()


@router.callback_query(F.data.startswith("gchk_"))
async def callback_group_check_one(callback: CallbackQuery, bot: Bot):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    chat_id, page = _parse(callback.data)
    group = db.get_group(chat_id)
    if not group:
        await callback.answer("❌ Группа уже удалена")
        return

    await callback.answer("🔍 Проверяю...")
    result = await check_group_accessibility(bot, chat_id)
    if result is None:
        note = "⚠️ Не удалось проверить (временная ошибка), попробуйте позже"
    else:
        db.set_group_status(chat_id, result)
        note = "✅ Группа доступна" if result else "❌ Бот не может писать в эту группу"

    group = db.get_group(chat_id)
    posts_count = len(db.get_posts_for_group(chat_id))
    await _safe_edit(
        callback.message,
        _group_text(group, posts_count) + f"\n\n<b>{note}</b>",
        get_group_manage_keyboard(chat_id, page)
    )


@router.callback_query(F.data.startswith("gren_"))
async def callback_group_rename(callback: CallbackQuery, state: FSMContext):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    chat_id, page = _parse(callback.data)
    group = db.get_group(chat_id)
    if not group:
        await callback.answer("❌ Группа не найдена")
        return
    await state.set_state(RenameGroupStates.waiting_for_new_title)
    await state.update_data(chat_id_for_rename=chat_id, page=page)
    await _safe_edit(
        callback.message,
        f"✏️ Текущее название: <b>{_esc(group['title'])}</b>\n\nОтправьте новое название сообщением.",
        get_group_manage_keyboard(chat_id, page)
    )
    await callback.answer()


@router.message(RenameGroupStates.waiting_for_new_title, F.text)
async def process_rename_group(message: Message, state: FSMContext):
    if not _allowed(message.chat.id, message.from_user.id):
        return
    new_title = message.text.strip()[:100]
    if not new_title or new_title.startswith("/"):
        await message.reply("❌ Название не может быть пустым. Отправьте ещё раз:")
        return
    data = await state.get_data()
    chat_id = data.get("chat_id_for_rename")
    page = data.get("page", 0)
    await state.clear()

    db.update_group_title(chat_id, new_title)
    logger.info(f"✏️ Группа {chat_id} переименована в '{new_title}'")
    await message.reply(
        f"✅ Переименовано: <b>{_esc(new_title)}</b>",
        reply_markup=get_groups_back_keyboard(page)
    )


@router.callback_query(F.data.startswith("gdel_"))
async def callback_group_delete(callback: CallbackQuery):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    chat_id, page = _parse(callback.data)
    group = db.get_group(chat_id)
    if not group:
        await callback.answer("❌ Группа уже удалена")
        await _show_page(callback.message, page)
        return
    await _safe_edit(
        callback.message,
        f"🗑 Удалить группу <b>{_esc(group['title'])}</b>?\n\n"
        f"Она пропадёт из базы и из всех рассылок.\n"
        f"Если бот остаётся в группе — она вернётся, когда кто-то заново добавит бота.",
        get_group_delete_confirm_keyboard(chat_id, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gdely_"))
async def callback_group_delete_yes(callback: CallbackQuery):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    chat_id, page = _parse(callback.data)
    group = db.get_group(chat_id)
    db.delete_group(chat_id)
    logger.info(f"🗑 Группа {chat_id} ({group['title'] if group else '?'}) удалена из базы")
    await callback.answer("✅ Группа удалена")
    await _show_page(callback.message, page)


# ===================== ПРОВЕРКА ВСЕХ =====================

@router.callback_query(F.data == "groups_check_all")
async def callback_groups_check_all(callback: CallbackQuery, bot: Bot):
    """Пробует написать в каждую группу. Мёртвые помечает ❌ — удалить их можно одной кнопкой."""
    global _check_running
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    if _check_running:
        await callback.answer("⏳ Проверка уже идёт, дождитесь окончания", show_alert=True)
        return

    groups = db.get_all_groups()
    if not groups:
        await callback.answer("📂 Групп нет")
        return

    _check_running = True
    await callback.answer("🔍 Начинаю проверку...")
    total = len(groups)
    ok, dead, unknown = 0, [], 0

    try:
        await _safe_edit(callback.message, f"🔍 Проверяю группы: 0 / {total}\n⏳ Примерно {total * 2} сек.")
        logger.info(f"🔍 Начинаю проверку {total} групп...")

        for idx, group in enumerate(groups, 1):
            chat_id = group["chat_id"]
            try:
                result = await check_group_accessibility(bot, chat_id)
                if result is None:
                    unknown += 1
                elif result:
                    db.set_group_status(chat_id, True)
                    ok += 1
                else:
                    db.set_group_status(chat_id, False)
                    dead.append(group["title"])
            except Exception as e:
                # Сбой в коде/БД — группу НЕ трогаем
                unknown += 1
                logger.error(f"❌ Ошибка при проверке группы {chat_id}: {e}")

            if idx % 5 == 0 and idx != total:
                try:
                    await _safe_edit(
                        callback.message,
                        f"🔍 Проверяю группы: {idx} / {total}\n✅ {ok}   ❌ {len(dead)}"
                    )
                except Exception:
                    pass

            # Антифлуд-пауза между отправками
            await asyncio.sleep(1.5)
    finally:
        _check_running = False

    logger.info(f"✅ Проверка завершена: ok={ok} dead={len(dead)} unknown={unknown}")

    text = (
        f"✅ <b>Проверка завершена</b>\n\n"
        f"Проверено: {total}\n"
        f"✅ Рабочих: {ok}\n"
        f"❌ Нерабочих: {len(dead)}\n"
    )
    if unknown:
        text += f"⚠️ Не удалось проверить: {unknown} (статус не менялся)\n"
    if dead:
        text += "\n<b>Нерабочие:</b>\n" + "\n".join(f"• {_esc(t)}" for t in dead[:30])
        if len(dead) > 30:
            text += f"\n… и ещё {len(dead) - 30}"
        text += "\n\nНажмите «🗑 Удалить нерабочие», чтобы убрать их из базы и рассылок."

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    if dead:
        kb.button(text=f"🗑 Удалить нерабочие ({len(dead)})", callback_data="groups_delete_broken")
    kb.button(text="📋 Мои группы", callback_data="groups_page_0")
    kb.button(text="◀ Меню", callback_data="groups_main_menu")
    kb.adjust(1)

    try:
        await _safe_edit(callback.message, text, kb.as_markup())
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")
        await callback.message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data == "groups_delete_broken")
async def callback_groups_delete_broken(callback: CallbackQuery):
    """Удаляет все ❌ группы из базы (и из рассылок)"""
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    groups_deleted, relations_deleted = db.cleanup_database()
    logger.info(f"🗑️ Удалено нерабочих групп: {groups_deleted}, связей с рассылками: {relations_deleted}")
    await callback.answer(f"✅ Удалено нерабочих групп: {groups_deleted}", show_alert=True)
    await _show_page(callback.message, 0)


# ===================== ДОБАВИТЬ ВРУЧНУЮ =====================

@router.callback_query(F.data == "groups_add_manual")
async def callback_groups_add_manual(callback: CallbackQuery, state: FSMContext):
    if not _allowed(callback.message.chat.id, callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddGroupStates.waiting_for_chat_id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="groups_main_menu")
    await _safe_edit(
        callback.message,
        "📝 Отправьте ID группы, где уже есть бот\n"
        "(например: <code>-1003783496776</code>)\n\n"
        "Бот сам подтянет название группы.",
        kb.as_markup()
    )
    await callback.answer()


@router.message(AddGroupStates.waiting_for_chat_id, F.text)
async def process_add_group_id(message: Message, state: FSMContext, bot: Bot):
    if not _allowed(message.chat.id, message.from_user.id):
        return
    try:
        chat_id = int(message.text.strip())
    except ValueError:
        await message.reply("❌ ID должен быть числом. Отправьте ещё раз или /cancel:")
        return

    if db.get_group(chat_id):
        await state.clear()
        await message.reply(f"⚠️ Группа <code>{chat_id}</code> уже есть в базе.",
                            reply_markup=get_groups_back_keyboard(0))
        return

    # Пробуем узнать название автоматически
    try:
        chat = await bot.get_chat(chat_id)
        title = (chat.title or "Без названия")[:100]
    except Exception as e:
        logger.info(f"get_chat({chat_id}) не сработал: {e}")
        await state.update_data(chat_id=chat_id)
        await state.set_state(AddGroupStates.waiting_for_title)
        await message.reply(
            f"⚠️ Не удалось получить название группы автоматически "
            f"(возможно, бота там нет).\n\nОтправьте название вручную:"
        )
        return

    db.add_group(chat_id, title)
    await state.clear()
    logger.info(f"✅ Группа {chat_id} ({title}) добавлена вручную")
    await message.reply(
        f"✅ Группа добавлена: <b>{_esc(title)}</b>\nТеперь её можно выбирать в рассылках.",
        reply_markup=get_groups_back_keyboard(0)
    )


@router.message(AddGroupStates.waiting_for_title, F.text)
async def process_add_group_title(message: Message, state: FSMContext):
    if not _allowed(message.chat.id, message.from_user.id):
        return
    title = message.text.strip()[:100]
    if not title or title.startswith("/"):
        await message.reply("❌ Название не может быть пустым. Отправьте ещё раз:")
        return
    data = await state.get_data()
    chat_id = data.get("chat_id")
    db.add_group(chat_id, title)
    await state.clear()
    logger.info(f"✅ Группа {chat_id} ({title}) добавлена вручную")
    await message.reply(
        f"✅ Группа добавлена: <b>{_esc(title)}</b>\nТеперь её можно выбирать в рассылках.",
        reply_markup=get_groups_back_keyboard(0)
    )
