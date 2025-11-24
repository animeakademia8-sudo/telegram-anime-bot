import os
import random
from typing import Optional, Dict, Any

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
    Video,
    Animation,
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

# ===============================
# IN-MEM STORAGE
# ===============================

# Каталог аниме = динамически наполняется из постов
# структура:
# ANIME = {
#   slug: {
#       "title": str,
#       "genres": [str, ...],
#       "episodes": {
#           ep_number (int): {"source": file_id}
#       }
#   },
#   ...
# }
ANIME: Dict[str, Dict[str, Any]] = {}

# одно сообщение бота на чат
LAST_MESSAGE: dict[int, int] = {}           # chat_id -> message_id
LAST_MESSAGE_TYPE: dict[int, str] = {}      # chat_id -> "photo" или "video"

# режим поиска (по названию) по чатам
SEARCH_MODE: dict[int, bool] = {}           # chat_id -> bool

# прогресс пользователя (последняя серия)
USER_PROGRESS: dict[int, dict] = {}         # chat_id -> {"slug": str, "ep": int}

# избранные тайтлы
USER_FAVORITES: dict[int, set] = {}         # chat_id -> set(slug)

# просмотренные тайтлы
USER_WATCHED: dict[int, set] = {}           # chat_id -> set(slug)


# ===============================
# PARSER: постов с канала
# ===============================

def parse_anime_caption(text: str) -> Optional[dict]:
    """
    Ждём формат (порядок строк – любой, регистр ключей – не важен):

    slug: neumeli
    title: Неумелый сэмпай
    ep: 1
    genres: романтика, комедия, школа, повседневность
    """
    if not text:
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    data = {}

    for line in lines:
        lower = line.lower()
        if lower.startswith("slug:"):
            data["slug"] = line.split(":", 1)[1].strip()
        elif lower.startswith("title:"):
            data["title"] = line.split(":", 1)[1].strip()
        elif lower.startswith("ep:"):
            ep_str = line.split(":", 1)[1].strip()
            try:
                data["ep"] = int(ep_str)
            except ValueError:
                return None
        elif lower.startswith("genres:"):
            genres_str = line.split(":", 1)[1].strip()
            # разделение по запятой
            genres = [g.strip().lower() for g in genres_str.split(",") if g.strip()]
            data["genres"] = genres

    # обязательные поля
    if "slug" not in data or "title" not in data or "ep" not in data:
        return None

    # genres опционально
    if "genres" not in data:
        data["genres"] = []

    return data


def add_or_update_anime_from_message(video_file_id: str, caption: str) -> Optional[dict]:
    """
    Парсим подпись сообщения, если формат корректный – добавляем/обновляем ANIME
    и возвращаем словарь {slug, title, ep, genres}.
    """
    parsed = parse_anime_caption(caption)
    if not parsed:
        return None

    slug = parsed["slug"]
    title = parsed["title"]
    ep = parsed["ep"]
    genres = parsed.get("genres", [])

    anime = ANIME.setdefault(slug, {
        "title": title,
        "genres": genres,
        "episodes": {}
    })

    # если вдруг поменяли title/genres – обновим
    anime["title"] = title
    # объединим старые и новые жанры
    old_genres = set(anime.get("genres", []))
    new_genres = set(genres)
    merged = sorted(old_genres.union(new_genres))
    anime["genres"] = merged

    # добавляем / обновляем эпизод
    anime["episodes"][ep] = {"source": video_file_id}

    return {
        "slug": slug,
        "title": title,
        "ep": ep,
        "genres": anime["genres"],
    }


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

    # избранное
    fav_set = USER_FAVORITES.get(chat_id, set())
    if slug in fav_set:
        fav_button = InlineKeyboardButton("💔 Убрать из избранного", callback_data=f"fav_remove:{slug}")
    else:
        fav_button = InlineKeyboardButton("💖 В избранное", callback_data=f"fav_add:{slug}")

    # просмотренное
    watched_set = USER_WATCHED.get(chat_id, set())
    if slug in watched_set:
        watched_button = InlineKeyboardButton("👁 Убрать из просмотренного", callback_data=f"unwatch:{slug}")
    else:
        watched_button = InlineKeyboardButton("👁 Добавить в просмотренное", callback_data=f"watch:{slug}")

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


def build_anime_menu() -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        keyboard.append([InlineKeyboardButton(anime["title"], callback_data=f"anime:{slug}")])
    if not keyboard:
        keyboard.append([InlineKeyboardButton("Пока пусто", callback_data="menu")])
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
    for slug in watched:
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
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
        return await send_or_edit_photo(
            chat_id,
            context,
            WELCOME_PHOTO,
            caption,
            reply_markup or build_main_menu_keyboard(chat_id),
        )


# ===============================
# SCREENS
# ===============================

async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not ANIME:
        caption = (
            "Приятного просмотра ✨\n\n"
            "Пока каталог пуст.\n"
            "Добавь серии в канал/группу, где я админ, в формате:\n\n"
            "slug: kod_anime\n"
            "title: Название аниме\n"
            "ep: 1\n"
            "genres: жанр1, жанр2\n"
        )
    else:
        caption = "Приятного просмотра ✨\nВыбери опцию:"
    kb = build_main_menu_keyboard(chat_id)
    await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_genres(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not ANIME:
        await edit_caption_only(
            chat_id,
            context,
            "Каталог пока пуст. Добавь аниме через канал.",
            build_main_menu_keyboard(chat_id),
        )
        return
    caption = "Выбери жанр:"
    kb = build_genre_keyboard()
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_anime_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not ANIME:
        await edit_caption_only(
            chat_id,
            context,
            "Каталог пока пуст. Добавь аниме через канал.",
            build_main_menu_keyboard(chat_id),
        )
        return
    caption = "Список аниме:"
    kb = build_anime_menu()
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_anime_by_genre(chat_id: int, context: ContextTypes.DEFAULT_TYPE, genre: str):
    caption = f"Жанр: {genre.capitalize()}\nВыбери аниме:"
    kb = build_anime_by_genre_keyboard(genre)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_episode(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    slug: str,
    ep: int,
):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(
            chat_id,
            context,
            "Аниме не найдено.",
            build_main_menu_keyboard(chat_id),
        )
        return

    episode = anime["episodes"].get(ep)
    if not episode:
        await edit_caption_only(
            chat_id,
            context,
            "Такой серии нет.",
            build_main_menu_keyboard(chat_id),
        )
        return

    caption = f"{anime['title']}\nСерия {ep}"
    kb = build_episode_keyboard(slug, ep, chat_id)
    await send_or_edit_video(chat_id, context, episode["source"], caption, kb)

    USER_PROGRESS[chat_id] = {"slug": slug, "ep": ep}
    SEARCH_MODE[chat_id] = False


async def show_episode_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(
            chat_id,
            context,
            "Аниме не найдено.",
            build_main_menu_keyboard(chat_id),
        )
        return
    caption = f"{anime['title']}\nВыбери серию:"
    kb = build_episode_list_keyboard(slug)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_random(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not ANIME:
        await edit_caption_only(
            chat_id,
            context,
            "Каталог пока пуст, нечего выбирать случайно.",
            build_main_menu_keyboard(chat_id),
        )
        return
    slug = random.choice(list(ANIME.keys()))
    # берем первую доступную серию
    eps = sorted(ANIME[slug]["episodes"].keys())
    first_ep = eps[0]
    await show_episode(chat_id, context, slug, first_ep)


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
        await edit_caption_only(
            chat_id,
            context,
            caption,
            build_main_menu_keyboard(chat_id),
        )
        return

    if data == "favorites":
        await show_favorites(chat_id, context)
        return

    if data == "watched":
        await show_watched(chat_id, context)
        return

    if data == "back":
        # просто вернём главное меню (минимум логики, но стабильно)
        await show_main_menu(chat_id, context)
        return

    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        await show_anime_by_genre(chat_id, context, genre)
        return

    if data.startswith("anime:"):
        slug = data.split(":", 1)[1]
        # если есть прогресс по этому тайтлу – продолжаем оттуда
        prog = USER_PROGRESS.get(chat_id)
        ep = 1
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        else:
            eps = sorted(ANIME[slug]["episodes"].keys())
            ep = eps[0]
        await show_episode(chat_id, context, slug, ep)
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
        slug = data.split(":", 1)[1]
        USER_WATCHED.setdefault(chat_id, set()).add(slug)
        prog = USER_PROGRESS.get(chat_id)
        ep = 1
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("unwatch:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED.setdefault(chat_id, set()).discard(slug)
        prog = USER_PROGRESS.get(chat_id)
        ep = 1
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        await show_episode(chat_id, context, slug, ep)
        return


# ===============================
# TEXT (SEARCH)
# ===============================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # это именно текст от пользователя в ЛС
    if not SEARCH_MODE.get(chat_id, False):
        return

    q = text.lower()
    found_slug = None
    for slug, anime in ANIME.items():
        if q in anime["title"].lower():
            found_slug = slug
            break

    # удаляем сообщение пользователя, чтобы не было "ленты"
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

    # показываем первую серию найденного тайтла
    eps = sorted(ANIME[found_slug]["episodes"].keys())
    first_ep = eps[0]
    await show_episode(chat_id, context, found_slug, first_ep)
    SEARCH_MODE[chat_id] = False


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
        await update.message.delete()
    except Exception:
        pass


# ===============================
# CHANNEL/GROUP HANDLER: ловим новые серии
# ===============================

async def handle_new_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ловим видео/анимацию из каналов/групп, где бот есть.
    Парсим подпись и обновляем ANIME.
    """
    msg = update.effective_message
    if not msg:
        return

    # берём video либо animation (gif/webm)
    video: Optional[Video] = msg.video
    anim: Optional[Animation] = msg.animation

    file_id = None
    if video:
        file_id = video.file_id
    elif anim:
        file_id = anim.file_id

    if not file_id:
        return

    caption = msg.caption or ""
    parsed = add_or_update_anime_from_message(file_id, caption)
    if not parsed:
        # формат не подошёл — просто игнор
        return

    # для дебага можно написать в лог-чате или консоль
    print(f"Updated ANIME from channel: {parsed['slug']} ep {parsed['ep']}")


# ===============================
# DEBUG: get file_id (в ЛС)
# ===============================

async def debug_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    vid = update.message.video or update.message.animation
    if not vid:
        return
    file_id = vid.file_id
    await update.message.reply_text(f"VIDEO/ANIMATION FILE_ID:\n{file_id}")


# ===============================
# BOOT
# ===============================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ЛС + команды
    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # поиск по тексту
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # приём медиа из каналов/групп (серии)
    app.add_handler(
        MessageHandler(
            (filters.VIDEO | filters.ANIMATION) & ~filters.ChatType.PRIVATE,
            handle_new_media,
        )
    )

    # debug в ЛС
    app.add_handler(
        MessageHandler(
            (filters.VIDEO | filters.ANIMATION) & filters.ChatType.PRIVATE,
            debug_video,
        )
    )

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
