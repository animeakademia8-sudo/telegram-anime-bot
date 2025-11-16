import os

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===============================
# 1. НАЛАШТУВАННЯ
# ===============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8421608017:AAGd5ikJ7bAU2OIpkCU8NI4Okbzi2Ed9upQ"

WELCOME_PHOTO = "images/welcome.jpg"

ANIME = {
    "neumelyi": {
        "title": "Неумелый семпай",
        "episodes": {
            1: {"source": "BAACAgIAAxkBAAMVaRj24OIri4siBrWlRsZDIX0u_VgAAv57AAKaSjhI2zDVA1kRZnI2BA"},
            2: {"source": "BAACAgIAAxkBAAMfaRj4h-gAAYH9gLc9O6FG1xHfewqqAAIJfAACmko4SKEM3U0QuAvWNgQ"},
            3: {"source": "BAACAgIAAxkBAAMlaRj67-vSO4t9NKFnjP-6vOLnaFAAAhl8AAKaSjhINlo5cuQDLRI2BA"},
        },
    },
    "temnoe_proshloe": {
        "title": "Темное прошлое злодейки",
        "episodes": {
            1: {"source": "FILE_ID_TEMNOE_1"},
            2: {"source": "FILE_ID_TEMNOE_2"},
        },
    },
    "sluga": {
        "title": "Слуга",
        "episodes": {
            1: {"source": "FILE_ID_SLUGA_1"},
        },
    },
    "voina_12": {
        "title": "Война двенадцати",
        "episodes": {
            1: {"source": "FILE_ID_VOINA_1"},
        },
    },
    "nenasyt_berserk": {
        "title": "Ненаситний берсерк",
        "episodes": {
            1: {"source": "FILE_ID_BERSERK_1"},
        },
    },
    "neumelyi23": {
        "title": "Неумелы444й семпай",
        "episodes": {
            1: {"source": "BAACAgIAAxkBAAMVaRj24OIri4siBrWlRsZDIX0u_VgAAv57AAKaSjhI2zDVA1kRZnI2BA"},
            2: {"source": "BAACAgIAAxkBAAMfaRj4h-gAAYH9gLc9O6FG1xHfewqqAAIJfAACmko4SKEM3U0QuAvWNgQ"},
            3: {"source": "BAACAgIAAxkBAAMlaRj67-vSO4t9NKFnjP-6vOLnaFAAAhl8AAKaSjhINlo5cuQDLRI2BA"},
            4: {"source": "BAACAgIAAxkBAAMlaRj67-vSO4t9NKFnjP-6vOLnaFAAAhl8AAKaSjhINlo5cuQDLRI2BA"},
        },
    },
}

# ===============================
# 2. КЛАВІАТУРИ
# ===============================


def build_anime_menu() -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        keyboard.append(
            [InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")]
        )
    return InlineKeyboardMarkup(keyboard)


def build_episode_keyboard(slug: str, ep: int) -> InlineKeyboardMarkup:
    episodes = ANIME[slug]["episodes"]
    has_next = (ep + 1) in episodes

    rows = [
        [
            InlineKeyboardButton("Аниме", callback_data="menu"),
            InlineKeyboardButton("Серии", callback_data=f"list:{slug}"),
        ]
    ]

    if has_next:
        rows.append(
            [InlineKeyboardButton("Следующая ▶️", callback_data=f"next:{slug}:{ep}")]
        )

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_episode_list_keyboard(slug: str) -> InlineKeyboardMarkup:
    eps = sorted(ANIME[slug]["episodes"].keys())
    rows = []
    row = []

    for e in eps:
        row.append(
            InlineKeyboardButton(f"Серия {e}", callback_data=f"ep:{slug}:{e}")
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ===============================
# 3. ХЕЛПЕРИ ДЛЯ /start
# ===============================


async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Показати стартовий екран.
    Для /start просто надсилаємо фото з меню.
    """
    caption = "Приятного просмотра ✨\nВыбери аниме:"

    with open(WELCOME_PHOTO, "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=build_anime_menu(),
        )


async def show_episode(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    slug: str,
    ep: int,
):
    """
    Показати конкретну серію при старті (deep-link).
    Далі все управління йде через callback-и з редагуванням того самого повідомлення.
    """
    anime = ANIME.get(slug)
    if not anime:
        await context.bot.send_message(chat_id, "Аниме не найдено 🤔")
        return

    episode = anime["episodes"].get(ep)
    if not episode:
        await context.bot.send_message(chat_id, "Такой серии нет 😅")
        return

    source = episode["source"]
    caption = f"{anime['title']}\nСерия {ep}"

    await context.bot.send_video(
        chat_id=chat_id,
        video=source,
        caption=caption,
        reply_markup=build_episode_keyboard(slug, ep),
    )


# ===============================
# 4. ОБРОБКА /start (звичайний + з payload)
# ===============================


async def send_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    # Видаляємо /start, щоб не захламляло чат
    try:
        await update.message.delete()
    except Exception:
        pass

    # Перевіряємо, чи є аргумент після /start (deep-link)
    payload = None
    parts = text.split(maxsplit=1)
    if len(parts) > 1:
        payload = parts[1].strip()

    if payload:
        # Очікуємо формат slug_ep, напр. neumelyi_1
        try:
            slug, ep_str = payload.split("_", 1)
            ep = int(ep_str)
        except ValueError:
            # Якщо щось не так – просто меню
            await show_main_menu(chat_id, context)
            return

        # Відкриваємо конкретну серію
        await show_episode(chat_id, context, slug, ep)
    else:
        # Звичайний /start → меню
        await show_main_menu(chat_id, context)


# ===============================
# 5. КНОПКИ (callback_query)
# ===============================


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id  # можна залишити як є

    # Меню: повертаємось до стартового фото + список аніме
    if data == "menu":
        caption = "Приятного просмотра ✨\nВыбери аниме:"

        with open(WELCOME_PHOTO, "rb") as photo:
            media = InputMediaPhoto(
                media=photo,
                caption=caption,
            )

            await query.message.edit_media(
                media=media,
                reply_markup=build_anime_menu(),
            )
        return

    # Вибір аніме → показати 1 серію, редагуючи існуюче повідомлення
    if data.startswith("anime:"):
        slug = data.split(":", 1)[1]
        ep = 1

        anime = ANIME.get(slug)
        if not anime:
            return

        episode = anime["episodes"].get(ep)
        if not episode:
            return

        source = episode["source"]
        caption = f"{anime['title']}\nСерия {ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, ep),
        )
        return

    # Конкретна серія
    if data.startswith("ep:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)

        anime = ANIME.get(slug)
        if not anime:
            return

        episode = anime["episodes"].get(ep)
        if not episode:
            return

        source = episode["source"]
        caption = f"{anime['title']}\nСерия {ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, ep),
        )
        return

    # Список серій (міняємо тільки підпис і клавіатуру)
    if data.startswith("list:"):
        slug = data.split(":", 1)[1]
        anime = ANIME.get(slug)
        if not anime:
            return

        caption = f"{anime['title']}\nВыбери серию:"

        await query.message.edit_caption(
            caption=caption,
            reply_markup=build_episode_list_keyboard(slug),
        )
        return

    # Следующая серия
    if data.startswith("next:"):
        _, slug, ep_str = data.split(":")
        next_ep = int(ep_str) + 1

        anime = ANIME.get(slug)
        if not anime:
            return

        episode = anime["episodes"].get(next_ep)
        if not episode:
            await query.answer("Дальше серий нет 😅", show_alert=False)
            return

        source = episode["source"]
        caption = f"{anime['title']}\nСерия {next_ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, next_ep),
        )
        return


# ===============================
# 6. DEBUG: отримаємо file_id
# ===============================


async def debug_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.video:
        return

    file_id = update.message.video.file_id
    print("VIDEO FILE_ID:", file_id)
    await update.message.reply_text(f"file_id для цього відео:\n{file_id}")


# ===============================
# 7. ЗАПУСК БОТА
# ===============================


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.VIDEO, debug_video))

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
