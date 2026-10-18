# admins.py — выдача и снятие админки (в админской группе)
#
# /admins                — список админов (с кнопками «снять»)
# /addadmin              — ответом на сообщение человека: выдать админку
# /addadmin 123456789    — то же по ID
# /deladmin              — ответом на сообщение или /deladmin ID: забрать админку
#
# Выдавать/забирать может только админ. Админы из .env (ADMIN_IDS) — главные,
# их через бота снять нельзя.
import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_GROUP_ID, ADMIN_IDS, ALL_ADMINS
from database import get_database
from utils import is_admin

logger = logging.getLogger(__name__)
router = Router()
db = get_database()


def _esc(text) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _target(message: Message, command: CommandObject):
    """Кому выдаём/забираем: ответ на сообщение или ID в команде. -> (user_id, name) | (None, None)"""
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        if u.is_bot:
            return None, None
        name = f"@{u.username}" if u.username else u.full_name
        return u.id, name
    if command.args:
        arg = command.args.strip().split()[0]
        if arg.lstrip("-").isdigit():
            return int(arg), None
    return None, None


def _admins_view():
    lines = ["👮 <b>Админы бота</b>\n"]
    kb = InlineKeyboardBuilder()
    for uid in ADMIN_IDS:
        lines.append(f"⭐ <code>{uid}</code> — главный (из .env)")
    for a in db.get_admins():
        if a["user_id"] in ADMIN_IDS:
            continue
        name = a.get("username") or ""
        lines.append(f"👤 <code>{a['user_id']}</code> {_esc(name)}")
        kb.button(text=f"❌ Снять {name or a['user_id']}", callback_data=f"deladm_{a['user_id']}")
    if ALL_ADMINS:
        lines.append("\n🔓 Включено <b>ALL_ADMINS=1</b>: рассылками может управлять любой участник этой группы.")
    lines.append(
        "\nВыдать: ответьте на сообщение человека командой /addadmin\n"
        "или напишите <code>/addadmin ID</code>"
    )
    kb.adjust(1)
    return "\n".join(lines), kb.as_markup()


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if message.chat.id != ADMIN_GROUP_ID or not is_admin(message.from_user.id):
        return
    text, kb = _admins_view()
    await message.reply(text, reply_markup=kb)


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, command: CommandObject):
    if message.chat.id != ADMIN_GROUP_ID or not is_admin(message.from_user.id):
        return
    user_id, name = _target(message, command)
    if not user_id:
        await message.reply(
            "Ответьте командой /addadmin на сообщение человека,\n"
            "или напишите <code>/addadmin 123456789</code>"
        )
        return
    db.add_admin(user_id, name)
    logger.info(f"👮 {message.from_user.id} выдал админку {user_id} ({name})")
    await message.reply(f"✅ Админка выдана: {_esc(name) if name else ''} <code>{user_id}</code>")


@router.message(Command("deladmin"))
async def cmd_deladmin(message: Message, command: CommandObject):
    if message.chat.id != ADMIN_GROUP_ID or not is_admin(message.from_user.id):
        return
    user_id, name = _target(message, command)
    if not user_id:
        await message.reply(
            "Ответьте командой /deladmin на сообщение человека,\n"
            "или напишите <code>/deladmin 123456789</code>"
        )
        return
    if user_id in ADMIN_IDS:
        await message.reply("⭐ Это главный админ из .env — его можно убрать только в файле .env")
        return
    if db.remove_admin(user_id):
        logger.info(f"👮 {message.from_user.id} забрал админку у {user_id}")
        await message.reply(f"✅ Админка снята: <code>{user_id}</code>")
    else:
        await message.reply(f"ℹ️ <code>{user_id}</code> не был админом")


@router.callback_query(F.data.startswith("deladm_"))
async def cb_deladmin(callback: CallbackQuery):
    if callback.message.chat.id != ADMIN_GROUP_ID or not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    user_id = int(callback.data.split("_")[1])
    db.remove_admin(user_id)
    logger.info(f"👮 {callback.from_user.id} забрал админку у {user_id}")
    text, kb = _admins_view()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer("✅ Админка снята")
