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

# 1) пробуємо взяти токен з ENV
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# 2) якщо ENV немає (як на Railway зараз) – використовуємо запасний
if not BOT_TOKEN:
    BOT_TOKEN = "8421608017:AAGd5ikJ7bAU2OIpkCU8NI4Okbzi2Ed9upQ"


# Локальна картинка-банер для старту
WELCOME_PHOTO = "images/welcome.jpg"

# Список аніме та серій
# Щоб додати нове аніме:
# 1) скопіюй блок "неумелый", встав нижче
# 2) зміни slug (ключ), title і FILE_ID_...
# Щоб додати серію:
# 1) скопіюй рядок "номер: { source: ... }"
# 2) встав нижче, зміни номер і FILE_ID
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
# 2. ДОПОМІЖНІ ФУНКЦІЇ КЛАВІАТУР
# ===============================


def build_anime_menu() -> InlineKeyboardMarkup:
    """Кнопки з переліком аніме."""
    keyboard = []
    for slug, anime in ANIME.items():
        keyboard.append(
            [InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")]
        )
    return InlineKeyboardMarkup(keyboard)


def build_episode_keyboard(slug: str, ep: int) -> InlineKeyboardMarkup:
    """Кнопки під серією: Аниме / Серии / Следующая / Меню."""
    episodes = ANIME[slug]["episodes"]
    has_next = (ep + 1) in episodes

    rows = [
        [
            InlineKeyboardButton("Аниме", callback_data="menu"),
            InlineKeyboardButton("Серии", callback_data=f"list:{slug}"),
        ],
    ]

    if has_next:
        rows.append(
            [
                InlineKeyboardButton(
                    "Следующая ▶️", callback_data=f"next:{slug}:{ep}"
                )
            ]
        )

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(rows)


def build_episode_list_keyboard(slug: str) -> InlineKeyboardMarkup:
    """Кнопки зі списком серій: Серия 1, Серия 2, ..."""
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
# 3. ПОКАЗ ВІТАЛЬНОГО ЕКРАНУ
# ===============================


async def send_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка /start – надсилаємо фото + текст + кнопки."""
    chat_id = update.effective_chat.id
    caption = "Приятного просмотра ✨\nВыбери аниме:"

    with open(WELCOME_PHOTO, "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=build_anime_menu(),
        )


async def show_menu_on_message(
    query, context: ContextTypes.DEFAULT_TYPE
):
    """Повернутись до меню – редагуємо існуюче повідомлення на фото+кнопки."""
    caption = "Приятного просмотра ✨\nВыбери аниме:"

    with open(WELCOME_PHOTO, "rb") as photo:
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo, caption=caption),
            reply_markup=build_anime_menu(),
        )


# ===============================
# 4. ПОКАЗ СЕРІЙ (ВІДЕО)
# ===============================


async def edit_to_episode(
    query, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int
):
    """Редагуємо поточне повідомлення: ставимо відео потрібної серії."""
    anime = ANIME.get(slug)
    if not anime:
        await query.message.reply_text("Аниме не найдено 🤔")
        return

    episode = anime["episodes"].get(ep)
    if not episode:
        await query.message.reply_text("Такой серии нет 😅")
        return

    source = episode["source"]  # file_id або пряме .mp4 посилання
    caption = f"{anime['title']}\nСерия {ep}"

    await query.message.edit_media(
        media=InputMediaVideo(media=source, caption=caption),
        reply_markup=build_episode_keyboard(slug, ep),
    )


async def show_episode_list(
    query, context: ContextTypes.DEFAULT_TYPE, slug: str
):
    """Редагуємо підпис + клавіатуру, показуємо список серій."""
    anime = ANIME.get(slug)
    if not anime:
        return

    caption = f"{anime['title']}\nВыбери серию:"

    await query.message.edit_caption(
        caption=caption,
        reply_markup=build_episode_list_keyboard(slug),
    )


# ===============================
# 5. ОБРОБКА CALLBACK-КНОПОК
# ===============================


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  

    data = query.data

    if data == "menu":
        # Повернутися до головного меню (фото + список аніме)
        await show_menu_on_message(query, context)
        return

    if data.startswith("anime:"):
        # Відкрити аніме → показати 1 серію
        slug = data.split(":", 1)[1]
        await edit_to_episode(query, context, slug, 1)
        return

    if data.startswith("ep:"):
        # Конкретна серія з меню серій
        _, slug, ep = data.split(":")
        await edit_to_episode(query, context, slug, int(ep))
        return

    if data.startswith("list:"):
        # Меню "Серии" – показати список серій
        slug = data.split(":", 1)[1]
        await show_episode_list(query, context, slug)
        return

    if data.startswith("next:"):
        # Наступна серія
        _, slug, ep = data.split(":")
        next_ep = int(ep) + 1
        await edit_to_episode(query, context, slug, next_ep)
        return


# ===============================
# 6. DEBUG: ОТРИМАТИ FILE_ID ВІДЕО
# ===============================


async def debug_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Якщо надіслати боту відео – він відповість file_id.
    Використовуй цей file_id у ANIME замість FILE_ID_...
    """
    if not update.message or not update.message.video:
        return

    file_id = update.message.video.file_id
    print("VIDEO FILE_ID:", file_id)

    # БЕЗ Markdown, просто текст
    await update.message.reply_text(
        f"file_id для цього відео:\n{file_id}"
    )

# ===============================
# 7. ЗАПУСК БОТА (LONG POLLING)
# ===============================


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", send_start_message))
    # кнопки
    app.add_handler(CallbackQueryHandler(handle_callback))
    # debug: ловимо file_id від відео
    app.add_handler(MessageHandler(filters.VIDEO, debug_video))

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
