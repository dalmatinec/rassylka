# keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any
from config import INTERVALS


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для стартового сообщения"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="stats")
    return builder.as_markup()


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура админа в группе"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список рассылок", callback_data="list_posts")
    builder.button(text="➕ Создать рассылку", callback_data="create_post")
    builder.adjust(1)
    return builder.as_markup()


def get_posts_list_keyboard(posts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура со списком рассылок"""
    builder = InlineKeyboardBuilder()

    for post in posts:
        post_id = post["id"]
        title = post["title"]
        builder.button(text=f"{post_id}. {title}", callback_data=f"post_{post_id}")

    builder.adjust(1)
    return builder.as_markup()


def get_post_detail_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра рассылки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить название", callback_data=f"rename_post_{post_id}")
    builder.button(text="📢 Выбрать группы", callback_data=f"add_group_{post_id}")
    builder.button(text="➖ Убрать группы", callback_data=f"remove_group_{post_id}")
    builder.button(text="🕒 Изменить интервал", callback_data=f"change_interval_{post_id}")
    builder.button(text="🗑 Удалить рассылку", callback_data=f"delete_post_{post_id}")
    builder.button(text="◀ Назад", callback_data="back_to_list")
    builder.adjust(1)
    return builder.as_markup()


def get_groups_list_keyboard(groups: List[Dict[str, Any]], post_id: int, action: str) -> InlineKeyboardMarkup:
    """Клавиатура со списком групп для добавления/удаления/выбора.
    Сверху — кнопки «Выбрать все / Снять все» (или «Убрать все» при удалении)."""
    builder = InlineKeyboardBuilder()
    top_buttons = 0

    if groups:
        if action == "select":
            builder.button(text="✅ Выбрать все", callback_data=f"selall_{post_id}")
            builder.button(text="⬜ Снять все", callback_data=f"selnone_{post_id}")
            top_buttons = 2
        elif action == "add":
            builder.button(text="✅ Выбрать все", callback_data=f"addall_{post_id}")
            builder.button(text="⬜ Снять все", callback_data=f"addnone_{post_id}")
            top_buttons = 2
        elif action == "remove":
            builder.button(text="🗑 Убрать все группы", callback_data=f"remall_{post_id}")
            top_buttons = 1

    for group in groups:
        chat_id = group["chat_id"]
        title = group["title"]
        is_selected = group.get("is_selected", False)

        if is_selected:
            text = f"☑️ {title}"
        else:
            text = f"⬜ {title}"

        if action == "add":
            callback_data = f"add_chat_{post_id}_{chat_id}"
        elif action == "remove":
            callback_data = f"remove_chat_{post_id}_{chat_id}"
        else:
            callback_data = f"select_{post_id}_{chat_id}"

        builder.button(text=text, callback_data=callback_data)

    if action == "select":
        builder.button(text="➡️ Готово", callback_data=f"done_create_groups_{post_id}")
    else:
        builder.button(text="✅ Готово", callback_data=f"done_edit_groups_{post_id}")
    
    if post_id == 0:
        builder.button(text="◀ Назад", callback_data="cancel_create_0")
    else:
        builder.button(text="◀ Назад", callback_data=f"post_{post_id}")

    sizes = ([top_buttons] if top_buttons else []) + [1] * (len(groups) + 2)
    builder.adjust(*sizes)
    return builder.as_markup()


def get_interval_keyboard(post_id: int, action: str = "edit") -> InlineKeyboardMarkup:
    """Клавиатура для выбора интервала"""
    builder = InlineKeyboardBuilder()

    for interval_name, interval_minutes in INTERVALS.items():
        builder.button(
            text=interval_name,
            callback_data=f"{action}_interval_{post_id}_{interval_minutes}"
        )

    if post_id == 0:
        builder.button(text="◀ Назад", callback_data="cancel_create_0")
    else:
        builder.button(text="◀ Назад", callback_data=f"post_{post_id}")
    
    builder.adjust(1)
    return builder.as_markup()


def get_confirm_keyboard(action: str, post_id: int, data: str = "") -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения действия"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_{action}_{post_id}_{data}")
    builder.button(text="❌ Отмена", callback_data=f"cancel_{action}_{post_id}")
    builder.adjust(2)
    return builder.as_markup()


def get_title_input_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура на шаге ввода названия рассылки (создание)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Оставить автоназвание", callback_data="skip_title_0")
    builder.button(text="❌ Отмена", callback_data="cancel_create_0")
    builder.adjust(1)
    return builder.as_markup()


def get_cancel_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()


def get_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ Назад", callback_data=callback_data)
    return builder.as_markup()


def confirmation_keyboard(mailing_type: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки в ЛС"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_mailing_{mailing_type}")
    builder.button(text="❌ Отмена", callback_data="cancel_mailing")
    builder.adjust(2)
    return builder.as_markup()

# ========== КЛАВИАТУРЫ ДЛЯ УПРАВЛЕНИЯ ГРУППАМИ (/groups) ==========

GROUPS_PER_PAGE = 10


def get_groups_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню /groups"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Мои группы", callback_data="groups_page_0")
    builder.button(text="🔍 Проверить все группы", callback_data="groups_check_all")
    builder.button(text="➕ Добавить группу по ID", callback_data="groups_add_manual")
    builder.button(text="❌ Закрыть", callback_data="groups_close")
    builder.adjust(1)
    return builder.as_markup()


def get_groups_page_keyboard(groups: List[Dict[str, Any]], page: int) -> InlineKeyboardMarkup:
    """Список групп по страницам: кнопки групп + ◀ стр ▶ + действия"""
    builder = InlineKeyboardBuilder()
    total_pages = max(1, (len(groups) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = groups[page * GROUPS_PER_PAGE:(page + 1) * GROUPS_PER_PAGE]

    sizes = []
    for group in chunk:
        icon = "✅" if group.get("is_active", 1) else "❌"
        title = group["title"]
        if len(title) > 40:
            title = title[:38] + "…"
        builder.button(text=f"{icon} {title}", callback_data=f"gm_{group['chat_id']}_{page}")
        sizes.append(1)

    if total_pages > 1:
        builder.button(text="◀️", callback_data=f"groups_page_{(page - 1) % total_pages}")
        builder.button(text=f"{page + 1} / {total_pages}", callback_data="noop")
        builder.button(text="▶️", callback_data=f"groups_page_{(page + 1) % total_pages}")
        sizes.append(3)

    builder.button(text="🔍 Проверить все", callback_data="groups_check_all")
    sizes_tail = 1
    if any(not g.get("is_active", 1) for g in groups):
        builder.button(text="🗑 Удалить нерабочие", callback_data="groups_delete_broken")
        sizes_tail = 2
    sizes.append(sizes_tail)

    builder.button(text="◀ Меню", callback_data="groups_main_menu")
    sizes.append(1)

    builder.adjust(*sizes)
    return builder.as_markup()


def get_group_manage_keyboard(chat_id: int, page: int = 0) -> InlineKeyboardMarkup:
    """Меню одной группы"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Проверить", callback_data=f"gchk_{chat_id}_{page}")
    builder.button(text="✏️ Переименовать", callback_data=f"gren_{chat_id}_{page}")
    builder.button(text="🗑 Удалить", callback_data=f"gdel_{chat_id}_{page}")
    builder.button(text="◀ К списку", callback_data=f"groups_page_{page}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def get_group_delete_confirm_keyboard(chat_id: int, page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"gdely_{chat_id}_{page}")
    builder.button(text="❌ Нет", callback_data=f"gm_{chat_id}_{page}")
    builder.adjust(2)
    return builder.as_markup()


def get_groups_back_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ К списку", callback_data=f"groups_page_{page}")
    return builder.as_markup()
