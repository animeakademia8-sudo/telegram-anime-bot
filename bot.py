import os
import random

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
# 1. НАЛАШТУВАН
# ===============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8421608017:AAGd5ikJ7bAU2OIpkCU8NI4Okbzi2Ed9upQ"

WELCOME_PHOTO = "images/welcome.jpg"

# тут зберігаємо id останнього повідомлення бота в кожному чаті
LAST_MESSAGE: dict[int, int] = {}  # {chat_id: message_id}

# простое состояние "режим поиска" для каждого чата
SEARCH_MODE: dict[int, bool] = {}  # {chat_id: True/False}

ANIME = {
    "neumeli": {
        "title": "Неумелый сэмпай",
        "genres": ["романтика", "комедия", "школа", "повседневность"],
        "episodes": {
            1: {
                "source": "BAACAgIAAxkBAAMVaRj24OIri4siBrWlRsZDIX0u_VgAAv57AAKaSjhI2zDVA1kRZnI2BA"
            },
            2: {
                "source": "BAACAgIAAxkBAAMfaRj4h-gAAYH9gLc9O6FG1xHfewqqAAIJfAACmko4SKEM3U0QuAvWNgQ"
            },
            3: {
                "source": "BAACAgIAAxkBAAMlaRj67-vSO4t9NKFnjP-6vOLnaFAAAhl8AAKaSjhINlo5cuQDLRI2BA"
            },
        },
    },
    "pridvorni_mag": {
        "title": "Придворный маг с навыком поддержки",
        "genres": ["приключения", "фэнтези", "экшен"],
        "episodes": {
            1: {
                "source": "BAACAgIAAxkBAAIC3GkkOM-7t-w06khdsdltYWevP4uGAALAigACC2whSaYsDQuBaW6oNgQ"
            },
            2: {
                "source": "BAACAgIAAxkBAAIC5mkkO1KvLt1dgCdWBIbCy0pzRCXyAALBigACC2whSUTWBHO3NgTZNgQ"
            },
            3: {
                "source": "BAACAgIAAxkBAAIC6GkkO1xpW64VhQi9QH7CFVYpwT5JAALDigACC2whSeRl-8aKAnmpNgQ"
            },
            4: {
                "source": "BAACAgIAAxkBAAIC6mkkO2cxrUllPgkSkWeoFZJo_liEAALFigACC2whSdoyTGtBVN4mNgQ"
            },
            5: {
                "source": "BAACAgIAAxkBAAIC7GkkO3RChv68Mm4frnbEj1SlxK-qAALHigACC2whSYpzVplj8OSdNgQ"
            },
            6: {
                "source": "BAACAgIAAxkBAAIC7mkkO4IGNJBEoBj7QCprmG1JM55aAALKigACC2whSYoiXyJgaPYnNgQ"
            },
            7: {
                "source": "BAACAgIAAxkBAAIC8GkkO4_XK3w-fG52q2Oy0ze8_6f5AALNigACC2whSUqvmz2y8VwdNgQ"
            },
            8: {
                "source": "BAACAgIAAxkBAAIC8mkkO5jQLbJVRXj0SPWO9CHLiwUeAALOigACC2whSfxA3xX4o_weNgQ"
            },
        },
    },
    "ga4iakyta": {
        "title": "Гачиакута",
        "genres": ["приключения", "фэнтези", "экшен", "суперспособности", "антиутопия"],
        "episodes": {
            1: {
                "source": "BAACAgIAAxkBAAICSWkZ-Kgi797xty9gUQiwHzQ6IhbwAAIqiAAC0E_RSDiNDuk9slE9NgQ"
            },
            2: {
                "source": "BAACAgIAAxkBAAICS2kZ-gp2odRw6qYgozEwuNRBQ46TAAIviAAC0E_RSPxJtnNeXZtINgQ"
            },
            3: {
                "source": "BAACAgIAAxkBAAICTWkZ-kcUrLcvkZhT39ttt7Rup3m6AAI6iAAC0E_RSHKHjGzKzKTMNgQ"
            },
            4: {
                "source": "BAACAgIAAxkBAAICT2kZ-vmEFLFV6rX-6Ep2ZWpjwE0lAAJWiAAC0E_RSOdsxn-Wg4sUNgQ"
            },
            5: {
                "source": "BAACAgIAAxkBAAICUWkZ-5roUcoWh_qa_qsy45dkxe__AAJfiAAC0E_RSPgmA_eRnuKfNgQ"
            },
            6: {
                "source": "BAACAgIAAxkBAAICU2kZ-7l8XzyBuT7jPFWK-FZjaEbEAAJniAAC0E_RSPiyqILZiXJtNgQ"
            },
            7: {
                "source": "BAACAgIAAxkBAAICVWkZ_C6qngsxNyoOrllSxERJonInAAJ0iAAC0E_RSMbgHGNLAb9ENgQ"
            },
            8: {
                "source": "BAACAgIAAxkBAAICV2kZ_FJI_oa57aSAtVfiUdq1ey_-AAJ-iAAC0E_RSLIke7Ve4EY0NgQ"
            },
            9: {
                "source": "BAACAgIAAxkBAAICWWkZ_H5UeUlRJC-QySc0GBfh57_4AAKBiAAC0E_RSF_ZYjUbNznxNgQ"
            },
            10: {
                "source": "BAACAgIAAxkBAAICW2kZ_LxjqEn7MDnu1kOIdd9uunnIAAKMiAAC0E_RSHk0LKSHRXWDNgQ"
            },
            11: {
                "source": "BAACAgIAAxkBAAICXWkZ_QL0bmkIvNBj49_t49EnDiDeAAKNiAAC0E_RSNpRpeqlP6aNNgQ"
            },
            12: {
                "source": "BAACAgIAAxkBAAICX2kZ_UjXMmzO1Qf2AuKV_SDf_dT4AAKQiAAC0E_RSD5LbrkS6nUvNgQ"
            },
            13: {
                "source": "BAACAgIAAxkBAAICYWkZ_YlepRDBQOOGc_kdUD34Cnf3AAKViAAC0E_RSMQQyY0orZ7CNgQ"
            },
            14: {
                "source": "BAACAgIAAxkBAAICY2kZ_celXJtd6nD5_jGxQDek4emEAAKkiAAC0E_RSAzuzSQ6ZRyYNgQ"
            },
            15: {
                "source": "BAACAgIAAxkBAAICZWkZ_gABwEuWT7mgqgehEtiAOEWp1wACrogAAtBP0UietkuvDP662DYE"
            },
            16: {
                "source": "BAACAgIAAxkBAAICZ2kZ_knyHpiyraYEURELR6ejO0zaAAK6iAAC0E_RSHxdpJIJCcMfNgQ"
            },
            17: {
                "source": "BAACAgIAAxkBAAICaWkZ_nkLwaofkObeDnC1CtRg8oDEAALBiAAC0E_RSJ7nifrQs1O2NgQ"
            },
            18: {
                "source": "BAACAgIAAxkBAAICa2kZ_u9372Z0SVNL2twsXli-Raj9AALEiAAC0E_RSJQB19aj5RlWNgQ"
            },
            19: {
                "source": "BAACAgIAAxkBAAICrWkazh87OUkjfSYK1UeHti1CeuYpAAIFkAAC0E_ZSII3zt7YJHrYNgQ"
            },
            20: {
                "source": "BAACAgIAAxkBAAICvWkkJXvdgQABfqZCK4ORx7nCVjODUwAClIkAAgtsIUmO-cMUGJ8nRzYE"
            },
        },
    },
}

# ===============================
# 2. КЛАВІАТУРИ
# ===============================


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    # Главное меню: Каталог + Случайное
    keyboard = [
        [
            InlineKeyboardButton("📚 Каталог", callback_data="catalog"),
            InlineKeyboardButton("🎲 Случайное аниме", callback_data="random"),
        ],
        [InlineKeyboardButton("🔍 Поиск по названию", callback_data="search")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_anime_menu() -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        keyboard.append(
            [InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")]
        )
    return InlineKeyboardMarkup(keyboard)


def build_genre_keyboard() -> InlineKeyboardMarkup:
    # собираем все жанры из ANIME
    genres_set = set()
    for anime in ANIME.values():
        for g in anime.get("genres", []):
            genres_set.add(g)

    genres = sorted(genres_set)

    rows = []
    row = []
    for g in genres:
        row.append(InlineKeyboardButton(g.capitalize(), callback_data=f"genre:{g}"))
        if len(row) == 2:  # по 2 жанра в ряд
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_anime_by_genre_keyboard(genre: str) -> InlineKeyboardMarkup:
    keyboard = []

    for slug, anime in ANIME.items():
        genres = anime.get("genres", [])
        if genre in genres:
            keyboard.append(
                [InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")]
            )

    if not keyboard:
        keyboard.append(
            [InlineKeyboardButton("Ничего не найдено", callback_data="catalog")]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Жанры", callback_data="catalog")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def build_episode_keyboard(slug: str, ep: int) -> InlineKeyboardMarkup:
    episodes = ANIME[slug]["episodes"]
    has_prev = (ep - 1) in episodes
    has_next = (ep + 1) in episodes

    nav_row = []
    if has_prev:
        nav_row.append(
            InlineKeyboardButton("◀️ Предыдущая", callback_data=f"prev:{slug}:{ep}")
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton("Следующая ▶️", callback_data=f"next:{slug}:{ep}")
        )

    rows = [
        [
            InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}"),
            InlineKeyboardButton("Жанры", callback_data="catalog"),
        ]
    ]

    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_episode_list_keyboard(slug: str) -> InlineKeyboardMarkup:
    eps = sorted(ANIME[slug]["episodes"].keys())
    rows = []
    row = []

    for e in eps:
        row.append(InlineKeyboardButton(f"Серия {e}", callback_data=f"ep:{slug}:{e}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ===============================
# 3. ХЕЛПЕРИ
# ===============================


async def set_last_message(chat_id: int, message_id: int):
    LAST_MESSAGE[chat_id] = message_id


async def set_search_mode(chat_id: int, value: bool):
    SEARCH_MODE[chat_id] = value


def is_search_mode(chat_id: int) -> bool:
    return SEARCH_MODE.get(chat_id, False)


async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Стартовый экран: картинка + кнопки
    """
    caption = "Приятного просмотра ✨"

    with open(WELCOME_PHOTO, "rb") as photo:
        sent = await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=build_main_menu_keyboard(),
        )

    await set_last_message(chat_id, sent.message_id)
    await set_search_mode(chat_id, False)


async def show_episode(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    slug: str,
    ep: int,
):
    """
    Показати конкретну серію.
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
    genres = ", ".join(anime.get("genres", []))
    caption = f"{anime['title']} [{genres}]\nСерия {ep}"

    sent = await context.bot.send_video(
        chat_id=chat_id,
        video=source,
        caption=caption,
        reply_markup=build_episode_keyboard(slug, ep),
    )

    await set_last_message(chat_id, sent.message_id)
    await set_search_mode(chat_id, False)


async def show_random_anime(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    slug = random.choice(list(ANIME.keys()))
    # всегда первая серия
    await show_episode(chat_id, context, slug, 1)


def search_anime_by_title(query: str):
    """
    Простой поиск по названию (поиск подстроки, регистронезависимый).
    Возвращает slug или None.
    """
    q = query.lower()
    for slug, anime in ANIME.items():
        if q in anime["title"].lower():
            return slug
    return None


# ===============================
# 4. ОБРОБКА /start (звичайний + з payload)
# ===============================


async def send_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    # 0. Видаляємо попереднє повідомлення бота (якщо було)
    msg_id = LAST_MESSAGE.get(chat_id)
    if msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    # 1. Парсимо payload
    payload = None
    parts = text.split(maxsplit=1)
    if len(parts) > 1:
        payload = parts[1].strip()

    if payload:
        try:
            slug, ep_str = payload.split("_", 1)
            ep = int(ep_str)
        except ValueError:
            await show_main_menu(chat_id, context)
        else:
            await show_episode(chat_id, context, slug, ep)
    else:
        await show_main_menu(chat_id, context)

    # 2. Видаляємо /start користувача
    try:
        await update.message.delete()
    except Exception:
        pass


# ===============================
# 5. КНОПКИ (callback_query)
# ===============================


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    # Главное меню
    if data == "menu":
        caption = "Приятного просмотра ✨"

        with open(WELCOME_PHOTO, "rb") as photo:
            media = InputMediaPhoto(
                media=photo,
                caption=caption,
            )

            await query.message.edit_media(
                media=media,
                reply_markup=build_main_menu_keyboard(),
            )

        await set_last_message(chat_id, query.message.message_id)
        await set_search_mode(chat_id, False)
        return

    # Каталог → показать жанры
    if data == "catalog":
        caption = "Выбери жанр:"

        await query.message.edit_caption(
            caption=caption,
            reply_markup=build_genre_keyboard(),
        )

        await set_last_message(chat_id, query.message.message_id)
        await set_search_mode(chat_id, False)
        return

    # Случайное аниме
    if data == "random":
        await show_random_anime(chat_id, context)
        return

    # Включить режим поиска
    if data == "search":
        await set_search_mode(chat_id, True)
        await query.message.edit_caption(
            caption="🔍 Введи название аниме сообщением (или его часть)",
            reply_markup=build_main_menu_keyboard(),
        )
        await set_last_message(chat_id, query.message.message_id)
        return

    # Выбор жанра → показать аниме по жанру
    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        caption = f"Жанр: {genre.capitalize()}\nВыбери аниме:"

        await query.message.edit_caption(
            caption=caption,
            reply_markup=build_anime_by_genre_keyboard(genre),
        )

        await set_last_message(chat_id, query.message.message_id)
        await set_search_mode(chat_id, False)
        return

    # Выбор аниме → первая серия
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
        genres = ", ".join(anime.get("genres", []))
        caption = f"{anime['title']} [{genres}]\nСерия {ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, ep),
        )

        await set_last_message(chat_id, query.message.message_id)
        await set_search_mode(chat_id, False)
        return

    # Выбор конкретной серии из списка
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
        genres = ", ".join(anime.get("genres", []))
        caption = f"{anime['title']} [{genres}]\nСерия {ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, ep),
        )

        await set_last_message(chat_id, query.message.message_id)
        await set_search_mode(chat_id, False)
        return

    # Список серий
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

        await set_last_message(chat_id, query.message.message_id)
        await set_search_mode(chat_id, False)
        return

    # Следующая серия
    if data.startswith("next:"):
        _, slug, ep_str = data.split(":")
        current_ep = int(ep_str)
        next_ep = current_ep + 1

        anime = ANIME.get(slug)
        if not anime:
            return

        episode = anime["episodes"].get(next_ep)
        if not episode:
            await query.answer("Дальше серий нет 😅", show_alert=False)
            return

        source = episode["source"]
        genres = ", ".join(anime.get("genres", []))
        caption = f"{anime['title']} [{genres}]\nСерия {next_ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, next_ep),
        )

        await set_last_message(chat_id, query.message.message_id)
        return

    # Предыдущая серия
    if data.startswith("prev:"):
        _, slug, ep_str = data.split(":")
        current_ep = int(ep_str)
        prev_ep = current_ep - 1

        anime = ANIME.get(slug)
        if not anime:
            return

        episode = anime["episodes"].get(prev_ep)
        if not episode:
            await query.answer("Предыдущих серий нет 😅", show_alert=False)
            return

        source = episode["source"]
        genres = ", ".join(anime.get("genres", []))
        caption = f"{anime['title']} [{genres}]\nСерия {prev_ep}"

        media = InputMediaVideo(
            media=source,
            caption=caption,
        )

        await query.message.edit_media(
            media=media,
            reply_markup=build_episode_keyboard(slug, prev_ep),
        )

        await set_last_message(chat_id, query.message.message_id)
        return


# ===============================
# 6. ОБРАБОТКА ТЕКСТА (поиск)
# ===============================


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # если не режим поиска — игнорим или можно что-то отвечать
    if not is_search_mode(chat_id):
        return

    slug = search_anime_by_title(text)
    if not slug:
        await update.message.reply_text(
            "😔 Ничего не нашёл по этому названию.\nПопробуй написать по-другому или короче."
        )
        return

    # нашли аниме → показываем первую серию
    await show_episode(chat_id, context, slug, 1)


# ===============================
# 7. DEBUG: отримаємо file_id
# ===============================


async def debug_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.video:
        return

    file_id = update.message.video.file_id
    print("VIDEO FILE_ID:", file_id)
    await update.message.reply_text(f"file_id для цього відео:\n{file_id}")


# ===============================
# 8. ЗАПУСК БОТА
# ===============================


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    # текст для поиска
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # debug видео
    app.add_handler(MessageHandler(filters.VIDEO, debug_video))

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
