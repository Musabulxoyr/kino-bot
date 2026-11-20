import os
import asyncio
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "movies.db")

db = sqlite3.connect(DB_PATH)
db.execute(
    "CREATE TABLE IF NOT EXISTS movies ("
    "code TEXT PRIMARY KEY, file_id TEXT, kind TEXT, title TEXT)"
)
db.commit()

dp = Dispatcher()
BOT_INFO = {}


def is_admin(m: Message) -> bool:
    return m.from_user and m.from_user.id == ADMIN_ID


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


@dp.message(Command("list"), F.from_user.id == ADMIN_ID)
async def list_movies(m: Message):
    rows = db.execute("SELECT code, title FROM movies ORDER BY rowid").fetchall()
    if not rows:
        await m.answer("Hozircha kino yo'q.")
        return
    await m.answer("\n".join(f"{c} — {t or 'nomsiz'}" for c, t in rows)[:4000])


@dp.message(Command("delete"), F.from_user.id == ADMIN_ID)
async def delete_movie(m: Message, command: CommandObject):
    code = (command.args or "").strip()
    if not code:
        await m.answer("Kodni yozing. Masalan: /delete 125")
        return
    cur = db.execute("DELETE FROM movies WHERE code = ?", (code,))
    db.commit()
    await m.answer("🗑 O'chirildi." if cur.rowcount else "Bunday kod topilmadi.")


def save_movie(src: Message, text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    code = parts[0]
    title = parts[1] if len(parts) > 1 else ""
    if src.video:
        file_id, kind = src.video.file_id, "video"
    else:
        file_id, kind = src.document.file_id, "document"
    db.execute(
        "INSERT OR REPLACE INTO movies (code, file_id, kind, title) VALUES (?,?,?,?)",
        (code, file_id, kind, title),
    )
    db.commit()
    return code


@dp.message(F.video | F.document, F.from_user.id == ADMIN_ID)
async def add_movie(m: Message):
    # Uzatilgan (forward) video: kodni reply orqali olamiz
    if m.forward_origin:
        await m.reply("Kodni shu videoga javob (reply) qilib yozing. Masalan: 125 Titanik")
        return
    caption = (m.caption or "").strip()
    if not caption:
        await m.answer("Videoning izohiga kod yozing. Masalan: 125 Titanik")
        return
    code = save_movie(m, caption)
    await m.answer(f"✅ Saqlandi. Kod: {code}")


@dp.message(
    F.text,
    F.from_user.id == ADMIN_ID,
    F.reply_to_message.video | F.reply_to_message.document,
)
async def add_movie_by_reply(m: Message):
    code = save_movie(m.reply_to_message, m.text)
    await m.answer(f"✅ Saqlandi. Kod: {code}")


@dp.message(F.text & ~F.text.startswith("/"))
async def get_movie(m: Message):
    code = m.text.strip()
    row = db.execute(
        "SELECT file_id, kind, title FROM movies WHERE code = ?", (code,)
    ).fetchone()
    if not row:
        await m.answer("❌ Bunday kodli kino topilmadi.")
        return
    file_id, kind, title = row
    link = f"🤖 https://t.me/{BOT_INFO.get('username', '')}"
    caption = f"🎬 {title}\n\n{link}" if title else link
    if kind == "video":
        await m.answer_video(file_id, caption=caption)
    else:
        await m.answer_document(file_id, caption=caption)


async def main():
    bot = Bot(TOKEN)
    me = await bot.get_me()
    BOT_INFO["username"] = me.username
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
