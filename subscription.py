"""Majburiy obuna moduli (aiogram 3).

Ishlatish:
    from subscription import SubscriptionMiddleware
    sub = SubscriptionMiddleware([ADMIN_ID])
    dp.message.outer_middleware(sub)
    dp.callback_query.outer_middleware(sub)

Railway Variables:
    CHANNELS = @kanal1,@kanal2
    (yopiq kanal: -1001234567890|https://t.me/+taklif_havolasi)
CHANNELS bo'sh bo'lsa, majburiy obuna o'chiq bo'ladi.
Bot kanallarda ADMIN bo'lishi shart.
"""
import os

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

SUB_TEXT = (
    "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, "
    "so'ng «✅ Tekshirish» ni bosing:"
)


def parse_channels():
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


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, admin_ids):
        self.admin_ids = set(admin_ids)
        self.channels = parse_channels()
        # /start havolasi (masalan, referal) obuna tugaguncha eslab qolinadi
        self.pending_start: dict[int, str] = {}

    async def missing(self, bot: Bot, user_id: int):
        out = []
        for chat, link in self.channels:
            chat_id = int(chat) if chat.lstrip("-").isdigit() else chat
            try:
                member = await bot.get_chat_member(chat_id, user_id)
                left = member.status in ("left", "kicked")
                restricted_out = member.status == "restricted" and not getattr(
                    member, "is_member", True
                )
                if left or restricted_out:
                    out.append((chat, link))
            except Exception:
                # Bot kanalda admin emas yoki kanal topilmadi: o'tkazib yuboramiz
                pass
        return out

    @staticmethod
    def keyboard(missing):
        kb = InlineKeyboardBuilder()
        for i, (_chat, link) in enumerate(missing, 1):
            if link:
                kb.button(text=f"📢 {i}-kanalga obuna bo'lish", url=link)
        kb.button(text="✅ Tekshirish", callback_data="check_sub")
        kb.adjust(1)
        return kb.as_markup()

    async def __call__(self, handler, event, data):
        if not self.channels:
            return await handler(event, data)

        user = data.get("event_from_user")
        if not user or user.id in self.admin_ids:
            return await handler(event, data)

        # Faqat shaxsiy chatda (guruhlarda tekshirmaymiz)
        chat = event.chat if isinstance(event, Message) else (
            event.message.chat if getattr(event, "message", None) else None
        )
        if chat is not None and chat.type != "private":
            return await handler(event, data)

        bot: Bot = data["bot"]

        # «✅ Tekshirish» tugmasi
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            missing = await self.missing(bot, user.id)
            if missing:
                await event.answer(
                    "Hali hamma kanalga obuna bo'lmagansiz ❌", show_alert=True
                )
                return
            await event.answer()
            arg = self.pending_start.pop(user.id, None)
            if arg:
                username = (await bot.me()).username
                kb = InlineKeyboardBuilder()
                kb.button(
                    text="▶️ Davom etish", url=f"https://t.me/{username}?start={arg}"
                )
                await event.message.answer(
                    "✅ Rahmat! Obuna tasdiqlandi.", reply_markup=kb.as_markup()
                )
            else:
                await event.message.answer(
                    "✅ Rahmat! Obuna tasdiqlandi. Endi /start ni bosing."
                )
            return

        missing = await self.missing(bot, user.id)
        if not missing:
            return await handler(event, data)

        # Obuna bo'lmagan: /start havolasini (referal) eslab qolamiz
        if isinstance(event, Message) and (event.text or "").startswith("/start "):
            self.pending_start[user.id] = event.text.split(maxsplit=1)[1]

        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(SUB_TEXT, reply_markup=self.keyboard(missing))
        elif isinstance(event, Message):
            await event.answer(SUB_TEXT, reply_markup=self.keyboard(missing))
        return
