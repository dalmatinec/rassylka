from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import get_link

def main_menu():
    """Главное меню - инлайн кнопки"""
    buttons = [
        [
            InlineKeyboardButton(text="⚜️ 𝐂𝐇𝐀𝐓", callback_data="link_chat"),
            InlineKeyboardButton(text="⚜️ 𝐍𝐄𝐖𝐒", callback_data="link_news")
        ],
        [
            InlineKeyboardButton(text="⚜️𝙍𝙀𝙎𝙀𝙍𝙑", callback_data="link_reserve")
        ],
        [
            InlineKeyboardButton(text="⚜️ 𝘽𝙊𝙏", url=get_link("bot")),
            InlineKeyboardButton(text="⚜️ 𝙒𝙚𝙗𝙨𝙖𝙮𝙩", url=get_link("website"))
        ],
        [
            InlineKeyboardButton(text="⚜️ 𝙈𝙊𝙍𝙀𝙉𝘼", url=get_link("ceo")),
            InlineKeyboardButton(text="⚜️ 𝙊𝙋𝙀𝙍𝘼𝙏𝙊𝙍", url=get_link("operator"))
        ],
        [
            InlineKeyboardButton(text="📤 Пиши если спам", callback_data="support")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_inline():
    """Кнопка отмены - инлайн"""
    buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_support")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_panel():
    """Админ-панель (инлайн)"""
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔗 Изменить ссылки", callback_data="admin_edit_links")],
        [InlineKeyboardButton(text="👨‍💻 Изменить операторов", callback_data="admin_edit_operators")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="admin_back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)