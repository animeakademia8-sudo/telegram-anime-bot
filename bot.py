import os
import random
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
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
# CONFIG
# ===============================
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8421608017:AAGd5ikJ7bAU2OIpkCU8NI4Okbzi2Ed9upQ"
WELCOME_PHOTO = "images/welcome.jpg"

# Чат, из которого бот берёт аниме
SOURCE_CHAT_ID = -1003362969236  # твой чат с аниме

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: dict[int, int] = {}              # chat_id -> message_id
LAST_MESSAGE_TYPE: dict[int, str] = {}         # chat_id -> "photo" or "video"
SEARCH_MODE: dict[int, bool] = {}              # chat_id -> bool

USER_PROGRESS: dict[int, dict] = {}            # chat_id -> {"slug": str, "ep": int}
USER_FAVORITES: dict[int, set] = {}            # chat_id -> set(slug)
USER_WATCHED: dict[int, set] = {}              # chat_id -> set((slug, ep))

# Главное: теперь ANIME наполняется автоматически из SOURCE_CHAT_ID
ANIME: dict[str, dict] = {}                    # slug -> {title, genres, episodes{ep: {source}}}

# Индекс по file_id (для возможности реагировать на исправленные подписи и хранить сырые видео)
# file_id -> {"slug": str | None, "ep": int | None}
VIDEO_INDEX: dict[str, dict] = {}


# ===============================
# UTILS: парсер подписи
# ===============================
def parse_caption_to_meta(caption: str) -> Optional[dict]:
    """
    Ожидаем формат:
    slug: ga4iakyta
    title: Гачиакута
    ep: 1
    genres: приключения, фэнтези, экшен
    Порядок строк может быть любым. genres — опционально.
    """
    if not caption:
        return None

    lines = [l.strip() for l in caption.splitlines() if l.strip()]
    data = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in ("slug", "title", "ep", "genres"):
            data[key] = value

    if "slug" not in data or "title" not in data or "ep" not in data:
        return None

    try:
        ep_num = int(data["ep"])
    except ValueError:
        return None

    genres_list = []
    if "genres" in data and data["genres"]:
        genres_list = [g.strip().lower() for g in data["genres"].split(",") if g.strip()]

    return {
        "slug": data["slug"],
        "title": data["title"],
        "ep": ep_num,
        "genres": genres_list,
    }


def add_or_update_anime_from_message(msg: Message) -> None:
    """
    Берём message из SOURCE_CHAT_ID с видео и подписью.
    - Если подпись корректная — добавляем/обновляем аниме в ANIME.
    - Если подпись некорректная — всё равно сохраняем file_id в VIDEO_INDEX
      (на будущее, вдруг пригодится).
    Важно: если потом придёт такая же серия уже с правильной подписью,
    бот корректно обновит ANIME.
    """
    if not msg.video:
        return

    file_id = msg.video.file_id
    meta = parse_caption_to_meta(msg.caption or "")

    # Если подпись нормальная — обновляем структуру ANIME
    if meta:
        slug = meta["slug"]
        title = meta["title"]
        ep = meta["ep"]
        genres = meta["genres"]

        if slug not in ANIME:
            ANIME[slug] = {
                "title": title,
                "genres": genres,
                "episodes": {},
            }
        else:
            # обновим title / genres (если есть новые)
            ANIME[slug]["title"] = title
            if genres:
                ANIME[slug]["genres"] = genres

        # Записываем/обновляем серию
        ANIME[slug]["episodes"][ep] = {"source": file_id}

        # Индекс по file_id -> знаем, какая это серия
        VIDEO_INDEX[file_id] = {"slug": slug, "ep": ep}
        return

    # Если подпись НЕ распарсилась — просто запоминаем file_id
    if file_id not in VIDEO_INDEX:
        VIDEO_INDEX[file_id] = {"slug": None, "ep": None}


# ===============================
# UI BUILDERS
# ===============================
def build_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📚 Каталог", callback_data="catalog"),
            InlineKeyboardButton("🎲 Случайное", callback_data="random"),
        ],
        [
            InlineKeyboardButton("⭐ Продолжить", callback_data="continue"),
            InlineKeyboardButton("🔍 Поиск", callback_data="search"),
        ],
        [
            InlineKeyboardButton("💖 Избранное", callback_data="favorites"),
            InlineKeyboardButton("👁 Просмотренное", callback_data="watched"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_genre_keyboard() -> InlineKeyboardMarkup:
    genres_set = set()
    for anime in ANIME.values():
        for g in anime.get("genres", []):
            genres_set.add(g)
    genres = sorted(genres_set)

    rows = []
    row = []
    for g in genres:
        row.append(InlineKeyboardButton(g.capitalize(), callback_data=f"genre:{g}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_anime_by_genre_keyboard(genre: str) -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        if genre in anime.get("genres", []):
            keyboard.append([InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")])
    if not keyboard:
        keyboard.append([InlineKeyboardButton("Ничего не найдено", callback_data="catalog")])
    keyboard.append([InlineKeyboardButton("⬅️ Жанры", callback_data="catalog")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def build_episode_keyboard(slug: str, ep: int, chat_id: int) -> InlineKeyboardMarkup:
    episodes = ANIME[slug]["episodes"]
    has_prev = (ep - 1) in episodes
    has_next = (ep + 1) in episodes

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"prev:{slug}:{ep}"))
    if has_next:
        nav.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"next:{slug}:{ep}"))

    fav_set = USER_FAVORITES.get(chat_id, set())
    if slug in fav_set:
        fav_button = InlineKeyboardButton("💔 Убрать из избранного", callback_data=f"fav_remove:{slug}")
    else:
        fav_button = InlineKeyboardButton("💖 В избранное", callback_data=f"fav_add:{slug}")

    watched_set = USER_WATCHED.get(chat_id, set())
    if (slug, ep) in watched_set:
        watched_button = InlineKeyboardButton("👁 Убрать из просмотренного", callback_data=f"unwatch:{slug}:{ep}")
    else:
        watched_button = InlineKeyboardButton("👁 В просмотренное", callback_data=f"watch:{slug}:{ep}")

    rows = [
        [
            InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back"),
        ],
        [fav_button],
        [watched_button],
    ]
    if nav:
        rows.append(nav)
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
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_anime_menu(chat_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        keyboard.append([InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")])
    if not keyboard:
        keyboard.append([InlineKeyboardButton("Пока нет аниме", callback_data="menu")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def build_favorites_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    favs = USER_FAVORITES.get(chat_id, set())
    rows = []
    for slug in favs:
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows = [[InlineKeyboardButton("Пусто", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_watched_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    watched = USER_WATCHED.get(chat_id, set())
    rows = []
    for slug, ep in sorted(watched):
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([InlineKeyboardButton(f"{title} — серия {ep}", callback_data=f"ep:{slug}:{ep}")])
    if not rows:
        rows = [[InlineKeyboardButton("Пусто", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ===============================
# HELPERS: single-message logic
# ===============================
async def send_or_edit_photo(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    photo_path: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
):
    msg_id = LAST_MESSAGE.get(chat_id)
    if msg_id:
        try:
            with open(photo_path, "rb") as ph:
                await context.bot.edit_message_media(
                    media=InputMediaPhoto(media=ph, caption=caption),
                    chat_id=chat_id,
                    message_id=msg_id,
                )
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=reply_markup,
            )
            LAST_MESSAGE_TYPE[chat_id] = "photo"
            return msg_id
        except Exception:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    with open(photo_path, "rb") as ph:
        sent = await context.bot.send_photo(
            chat_id=chat_id,
            photo=ph,
            caption=caption,
            reply_markup=reply_markup,
        )
    LAST_MESSAGE[chat_id] = sent.message_id
    LAST_MESSAGE_TYPE[chat_id] = "photo"
    return sent.message_id


async def send_or_edit_video(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    file_id_or_path: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
):
    msg_id = LAST_MESSAGE.get(chat_id)
    media = InputMediaVideo(media=file_id_or_path, caption=caption)
    if msg_id:
        try:
            await context.bot.edit_message_media(
                media=media,
                chat_id=chat_id,
                message_id=msg_id,
            )
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=reply_markup,
            )
            LAST_MESSAGE_TYPE[chat_id] = "video"
            return msg_id
        except Exception:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    sent = await context.bot.send_video(
        chat_id=chat_id,
        video=file_id_or_path,
        caption=caption,
        reply_markup=reply_markup,
    )
    LAST_MESSAGE[chat_id] = sent.message_id
    LAST_MESSAGE_TYPE[chat_id] = "video"
    return sent.message_id


async def edit_caption_only(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    caption: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    msg_id = LAST_MESSAGE.get(chat_id)
    if not msg_id:
        return await send_or_edit_photo(
            chat_id,
            context,
            WELCOME_PHOTO,
            caption,
            reply_markup or build_main_menu_keyboard(chat_id),
        )
    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=msg_id,
            caption=caption,
            reply_markup=reply_markup,
        )
        return msg_id
    except Exception:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        with open(WELCOME_PHOTO, "rb") as ph:
            sent = await context.bot.send_photo(
                chat_id=chat_id,
                photo=ph,
                caption=caption,
                reply_markup=reply_markup,
            )
        LAST_MESSAGE[chat_id] = sent.message_id
        LAST_MESSAGE_TYPE[chat_id] = "photo"
        return sent.message_id


# ===============================
# SCREENS
# ===============================
async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Приятного просмотра ✨\nВыбери опцию:"
    kb = build_main_menu_keyboard(chat_id)
    await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_genres(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Выбери жанр:"
    kb = build_genre_keyboard()
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_anime_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Список аниме:"
    kb = build_anime_menu(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_anime_by_genre(chat_id: int, context: ContextTypes.DEFAULT_TYPE, genre: str):
    caption = f"Жанр: {genre.capitalize()}\nВыбери аниме:"
    kb = build_anime_by_genre_keyboard(genre)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_episode(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    episode = anime["episodes"].get(ep)
    if not episode:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return

    caption = f"{anime['title']}\nСерия {ep}"
    kb = build_episode_keyboard(slug, ep, chat_id)
    await send_or_edit_video(chat_id, context, episode["source"], caption, kb)
    USER_PROGRESS[chat_id] = {"slug": slug, "ep": ep}
    SEARCH_MODE[chat_id] = False


async def show_episode_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    caption = f"{anime['title']}\nВыбери серию:"
    kb = build_episode_list_keyboard(slug)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_random(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not ANIME:
        await edit_caption_only(chat_id, context, "Пока нет доступных аниме 😔", build_main_menu_keyboard(chat_id))
        return
    slug = random.choice(list(ANIME.keys()))
    await show_episode(chat_id, context, slug, 1)


async def show_favorites(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Избранное:"
    kb = build_favorites_keyboard(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_watched(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Просмотренное:"
    kb = build_watched_keyboard(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


# ===============================
# CALLBACKS
# ===============================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "menu":
        await show_main_menu(chat_id, context)
        return

    if data == "catalog":
        await show_genres(chat_id, context)
        return

    if data == "random":
        await show_random(chat_id, context)
        return

    if data == "continue":
        prog = USER_PROGRESS.get(chat_id)
        if not prog:
            await query.answer("Ты ещё ничего не смотрел", show_alert=True)
            await show_main_menu(chat_id, context)
            return
        await show_episode(chat_id, context, prog["slug"], prog["ep"])
        return

    if data == "search":
        SEARCH_MODE[chat_id] = True
        caption = "🔍 Введи название аниме сообщением (или его часть)."
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id))
        return

    if data == "favorites":
        await show_favorites(chat_id, context)
        return

    if data == "watched":
        await show_watched(chat_id, context)
        return

    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        await show_anime_by_genre(chat_id, context, genre)
        return

    if data.startswith("anime:"):
        slug = data.split(":", 1)[1]
        await show_episode(chat_id, context, slug, 1)
        return

    if data == "back":
        prog = USER_PROGRESS.get(chat_id)
        if prog:
            slug = prog["slug"]
            ep = prog["ep"]
            await show_episode(chat_id, context, slug, ep)
        else:
            await show_main_menu(chat_id, context)
        return

    if data.startswith("list:"):
        slug = data.split(":", 1)[1]
        await show_episode_list(chat_id, context, slug)
        return

    if data.startswith("ep:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("next:"):
        _, slug, ep_str = data.split(":")
        current = int(ep_str)
        await show_episode(chat_id, context, slug, current + 1)
        return

    if data.startswith("prev:"):
        _, slug, ep_str = data.split(":")
        current = int(ep_str)
        await show_episode(chat_id, context, slug, current - 1)
        return

    if data.startswith("fav_add:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).add(slug)
        prog = USER_PROGRESS.get(chat_id)
        ep = 1
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        prog = USER_PROGRESS.get(chat_id)
        ep = 1
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("watch:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        USER_WATCHED.setdefault(chat_id, set()).add((slug, ep))
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("unwatch:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        USER_WATCHED.setdefault(chat_id, set()).discard((slug, ep))
        await show_episode(chat_id, context, slug, ep)
        return


# ===============================
# TEXT (SEARCH)
# ===============================
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not SEARCH_MODE.get(chat_id, False):
        return

    q = text.lower()
    found_slug = None
    for slug, anime in ANIME.items():
        if q in anime["title"].lower():
            found_slug = slug
            break

    # удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception:
        pass

    if not found_slug:
        await edit_caption_only(
            chat_id,
            context,
            "😔 Ничего не нашёл по этому названию.\nПопробуй другое слово.",
            build_main_menu_keyboard(chat_id),
        )
        SEARCH_MODE[chat_id] = False
        return

    await show_episode(chat_id, context, found_slug, 1)
    SEARCH_MODE[chat_id] = False


# ===============================
# SOURCE CHAT HANDLER
# ===============================
async def handle_source_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Сюда приходят сообщения из чата с аниме (SOURCE_CHAT_ID).
    Если это видео — пытаемся распарсить подпись и обновляем ANIME.
    Даже если подпись сейчас кривая, file_id всё равно попадёт в VIDEO_INDEX
    и при последующем корректном сообщении будет корректно привязан.
    """
    msg = update.message
    if not msg:
        return
    if msg.chat_id != SOURCE_CHAT_ID:
        return
    if not msg.video:
        return

    add_or_update_anime_from_message(msg)


# ===============================
# /start
# ===============================
async def send_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    last_id = LAST_MESSAGE.get(chat_id)
    if last_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_id)
        except Exception:
            pass
        LAST_MESSAGE.pop(chat_id, None)
        LAST_MESSAGE_TYPE.pop(chat_id, None)

    await show_main_menu(chat_id, context)

    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass


# ===============================
# DEBUG: get file_id
# ===============================
async def debug_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.video:
        return
    file_id = update.message.video.file_id
    await update.message.reply_text(f"VIDEO FILE_ID:\n{file_id}")


# ===============================
# BOOT
# ===============================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", send_start_message))

    # callbacks (кнопки)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # текст от пользователей (поиск)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Chat(SOURCE_CHAT_ID),
            handle_user_text,
        )
    )

    # сообщения из SOURCE_CHAT_ID (автодобавление аниме)
    app.add_handler(
        MessageHandler(
            filters.Chat(SOURCE_CHAT_ID) & filters.VIDEO,
            handle_source_chat_message,
        )
    )

    # debug — если тебе нужно где-то достать file_id вручную
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.Chat(SOURCE_CHAT_ID), debug_video))

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
