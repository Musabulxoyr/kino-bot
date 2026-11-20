import os
import asyncio
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_ID", "0").replace(" ", "").split(",") if x.isdigit()
]
DB_PATH = os.getenv("DB_PATH", "movies.db")

db = sqlite3.connect(DB_PATH)
db.execute(
    "CREATE TABLE IF NOT EXISTS movies ("
    "code TEXT PRIMARY KEY, file_id TEXT, kind TEXT, title TEXT)"
)
db.commit()

dp = Dispatcher()
BOT_INFO = {}


def parse_channels():
    """CHANNELS=@kanal1,@kanal2 yoki -100123|https://t.me/+abc"""
    res = []
    for item in os.getenv("CHANNELS", "").split(","):
        item = item.strip()
        if not item:
            continue
        chat, _, link = item.partition("|")
        chat, link = chat.strip(), link.strip()
        if not link and chat.startswith("@"):
            link = f"https://t.me/{chat[1:]}"
        res.append((chat, link))
    return res


CHANNELS = parse_channels()


async def not_subscribed(bot: Bot, user_id: int):
    missing = []
    for chat, link in CHANNELS:
        chat_id = int(chat) if chat.lstrip("-").isdigit() else chat
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            left = member.status in ("left", "kicked")
            restricted_out = member.status == "restricted" and not getattr(
                member, "is_member", True
            )
            if left or restricted_out:
                missing.append((chat, link))
        except Exception:
            # Bot kanalda admin emas yoki kanal topilmadi: o'tkazib yuboramiz
            pass
    return missing


def sub_kb(missing):
    kb = InlineKeyboardBuilder()
    for i, (_chat, link) in enumerate(missing, 1):
        if link:
            kb.button(text=f"📢 {i}-kanalga obuna bo'lish", url=link)
    kb.button(text="✅ Tekshirish", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()


SUB_TEXT = "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, so'ng «✅ Tekshirish» ni bosing:"


def is_admin(m: Message) -> bool:
    return m.from_user and m.from_user.id in ADMIN_IDS


@dp.message(Command("start"))
async def start(m: Message):
    text = "🎬 Salom! Kino kodini yuboring, men kinoni topib beraman."
    if is_admin(m):
        text += (
            "\n\n👑 Admin buyruqlari:\n"
            "• Kino qo'shish: videoni yuboring, izohiga (caption) "
            "kod va nom yozing. Masalan: 125 Titanik\n"
            "• /list — barcha kinolar\n"
            "• /delete 125 — kinoni o'chirish"
        )
    await m.answer(text)


@dp.message(Command("list"), F.from_user.id.in_(ADMIN_IDS))
async def list_movies(m: Message):
    rows = db.execute("SELECT code, title FROM movies ORDER BY rowid").fetchall()
    if not rows:
        await m.answer("Hozircha kino yo'q.")
        return
    await m.answer("\n".join(f"{c} — {t or 'nomsiz'}" for c, t in rows)[:4000])


@dp.message(Command("delete"), F.from_user.id.in_(ADMIN_IDS))
async def delete_movie(m: Message, command: CommandObject):
    code = (command.args or "").strip()
    if not code:
        await m.answer("Kodni yozing. Masalan: /delete 125")
        return
    cur = db.execute("DELETE FROM movies WHERE code = ?", (code,))
    db.commit()
    await m.answer("🗑 O'chirildi." if cur.rowcount else "Bunday kod topilmadi.")


def next_code() -> str:
    """Raqamli kodlar ichida eng kattasidan keyingi bo'sh kod."""
    rows = db.execute("SELECT code FROM movies").fetchall()
    nums = [int(r[0]) for r in rows if r[0].isdigit()]
    return str(max(nums) + 1) if nums else "1"


def save_movie(src: Message, text: str):
    """(saqlandimi, kod) qaytaradi. Kod band bo'lsa, saqlamaydi."""
    parts = text.strip().split(maxsplit=1)
    code = parts[0]
    title = parts[1] if len(parts) > 1 else ""
    exists = db.execute("SELECT 1 FROM movies WHERE code = ?", (code,)).fetchone()
    if exists:
        return False, code
    if src.video:
        file_id, kind = src.video.file_id, "video"
    else:
        file_id, kind = src.document.file_id, "document"
    db.execute(
        "INSERT INTO movies (code, file_id, kind, title) VALUES (?,?,?,?)",
        (code, file_id, kind, title),
    )
    db.commit()
    return True, code


@dp.message(F.video | F.document, F.from_user.id.in_(ADMIN_IDS))
async def add_movie(m: Message):
    # Uzatilgan (forward) video: kodni reply orqali olamiz
    if m.forward_origin:
        await m.reply("Kodni shu videoga javob (reply) qilib yozing. Masalan: 125 Titanik")
        return
    caption = (m.caption or "").strip()
    if not caption:
        await m.answer("Videoning izohiga kod yozing. Masalan: 125 Titanik")
        return
    ok, code = save_movie(m, caption)
    if not ok:
        await m.answer(
            f"⚠️ Kechirasiz, siz {code} kodiga allaqachon kino joylagansiz.\n"
            f"➡️ Keyingi bo'sh kod: {next_code()}\n"
            f"Yoki avval /delete {code} bilan eskisini o'chiring."
        )
        return
    await m.answer(f"✅ Saqlandi. Kod: {code}\n➡️ Keyingi bo'sh kod: {next_code()}")


@dp.message(
    F.text,
    F.from_user.id.in_(ADMIN_IDS),
    F.reply_to_message.video | F.reply_to_message.document,
)
async def add_movie_by_reply(m: Message):
    ok, code = save_movie(m.reply_to_message, m.text)
    if not ok:
        await m.answer(
            f"⚠️ Kechirasiz, siz {code} kodiga allaqachon kino joylagansiz.\n"
            f"➡️ Keyingi bo'sh kod: {next_code()}\n"
            f"Yoki avval /delete {code} bilan eskisini o'chiring."
        )
        return
    await m.answer(f"✅ Saqlandi. Kod: {code}\n➡️ Keyingi bo'sh kod: {next_code()}")


@dp.callback_query(F.data == "check_sub")
async def check_sub(c: CallbackQuery, bot: Bot):
    missing = await not_subscribed(bot, c.from_user.id)
    if missing:
        await c.answer("Hali hamma kanalga obuna bo'lmagansiz ❌", show_alert=True)
        return
    await c.message.answer("✅ Rahmat! Endi kino kodini yoki nomini yozing 🎬")
    await c.answer()


async def send_movie(m: Message, file_id: str, kind: str, title: str):
    link = f"🤖 https://t.me/{BOT_INFO.get('username', '')}"
    caption = f"🎬 {title}\n\n{link}" if title else link
    if kind == "video":
        await m.answer_video(file_id, caption=caption)
    else:
        await m.answer_document(file_id, caption=caption)


@dp.message(F.text & ~F.text.startswith("/"))
async def get_movie(m: Message, bot: Bot):
    if CHANNELS and not is_admin(m):
        missing = await not_subscribed(bot, m.from_user.id)
        if missing:
            await m.answer(SUB_TEXT, reply_markup=sub_kb(missing))
            return

    query = m.text.strip()

    # 1) Kod bo'yicha aniq topish
    row = db.execute(
        "SELECT file_id, kind, title FROM movies WHERE code = ?", (query,)
    ).fetchone()
    if row:
        await send_movie(m, *row)
        return

    # 2) Nom bo'yicha qidirish (katta-kichik harfga qaramaydi)
    if len(query) < 2:
        await m.answer("❌ Bunday kodli kino topilmadi.")
        return
    q = query.casefold()
    rows = db.execute("SELECT code, file_id, kind, title FROM movies").fetchall()
    found = [r for r in rows if q in (r[3] or "").casefold()]

    if not found:
        await m.answer("❌ Bunday kino topilmadi. Kod yoki nomini tekshirib qayta yozing.")
    elif len(found) == 1:
        _code, file_id, kind, title = found[0]
        await send_movie(m, file_id, kind, title)
    else:
        lines = [f"{c} — {t}" for c, _f, _k, t in found[:30]]
        await m.answer(
            "🔎 Bir nechta kino topildi. Keraklisining kodini yozing:\n\n"
            + "\n".join(lines)
        )


async def main():
    bot = Bot(TOKEN)
    me = await bot.get_me()
    BOT_INFO["username"] = me.username
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
