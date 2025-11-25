import os
import json
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

ANIME_JSON_PATH = "anime.json"
USERS_JSON_PATH = "users.json"

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: dict[int, int] = {}              # chat_id -> message_id
LAST_MESSAGE_TYPE: dict[int, str] = {}         # chat_id -> "photo" or "video"
SEARCH_MODE: dict[int, bool] = {}              # chat_id -> bool

# user_id -> {"slug": str, "ep": int}
USER_PROGRESS: dict[int, dict] = {}

# user_id -> set(slug)
USER_FAVORITES: dict[int, set] = {}

# user_id -> set((slug, ep))
USER_WATCHED: dict[int, set] = {}

# slug -> {title, genres, episodes{ep: {source}}}
ANIME: dict[str, dict] = {}


# ===============================
# JSON SAVE/LOAD: ANIME
# ===============================
def load_anime() -> None:
    """Загружаем ANIME из anime.json, если файл существует."""
    global ANIME
    if not os.path.exists(ANIME_JSON_PATH):
        ANIME = {}
        return
    try:
        with open(ANIME_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # ключи ep в JSON — строки, приведём к int
        for slug, anime in data.items():
            episodes = anime.get("episodes", {})
            fixed_eps = {}
            for ep_str, ep_data in episodes.items():
                try:
                    ep_int = int(ep_str)
                except ValueError:
                    continue
                fixed_eps[ep_int] = ep_data
            anime["episodes"] = fixed_eps
        ANIME = data
        print(f"Loaded ANIME from {ANIME_JSON_PATH}, items:", len(ANIME))
    except Exception as e:
        print("Failed to load anime.json:", e)
        ANIME = {}


def save_anime() -> None:
    """Сохраняем ANIME в anime.json."""
    try:
        data_to_save = {}
        for slug, anime in ANIME.items():
            episodes = anime.get("episodes", {})
            eps_json = {}
            for ep_int, ep_data in episodes.items():
                eps_json[str(ep_int)] = ep_data
            data_to_save[slug] = {
                "title": anime.get("title", ""),
                "genres": anime.get("genres", []),
                "episodes": eps_json,
            }

        with open(ANIME_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        print(f"Saved ANIME to {ANIME_JSON_PATH}, items:", len(data_to_save))
    except Exception as e:
        print("Failed to save anime.json:", e)


# ===============================
# JSON SAVE/LOAD: USERS
# ===============================
def load_users() -> None:
    """Загружаем USER_PROGRESS, USER_FAVORITES, USER_WATCHED из users.json."""
    global USER_PROGRESS, USER_FAVORITES, USER_WATCHED
    if not os.path.exists(USERS_JSON_PATH):
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED = {}
        return

    try:
        with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # progress: user_id -> {"slug": str, "ep": int}
        USER_PROGRESS = {}
        for user_id_str, prog in data.get("progress", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            slug = prog.get("slug")
            ep = prog.get("ep")
            if slug and isinstance(ep, int):
                USER_PROGRESS[user_id] = {"slug": slug, "ep": ep}

        # favorites: user_id -> [slug, ...]
        USER_FAVORITES = {}
        for user_id_str, fav_list in data.get("favorites", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(fav_list, list):
                USER_FAVORITES[user_id] = set(fav_list)
            else:
                USER_FAVORITES[user_id] = set()

        # watched: user_id -> [[slug, ep], ...]
        USER_WATCHED = {}
        for user_id_str, watched_list in data.get("watched", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            watched_set = set()
            if isinstance(watched_list, list):
                for item in watched_list:
                    if isinstance(item, list) and len(item) == 2:
                        slug, ep = item
                        if isinstance(slug, str) and isinstance(ep, int):
                            watched_set.add((slug, ep))
            USER_WATCHED[user_id] = watched_set

        print("Loaded users from users.json")

    except Exception as e:
        print("Failed to load users.json:", e)
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED = {}


def save_users() -> None:
    """Сохраняем USER_PROGRESS, USER_FAVORITES, USER_WATCHED в users.json."""
    try:
        data_to_save = {
            "progress": {},
            "favorites": {},
            "watched": {},
        }

        # progress: user_id -> {"slug":..., "ep":...}
        for user_id, prog in USER_PROGRESS.items():
            data_to_save["progress"][str(user_id)] = {
                "slug": prog.get("slug"),
                "ep": prog.get("ep"),
            }

        # favorites: user_id -> [slug, ...]
        for user_id, fav_set in USER_FAVORITES.items():
            data_to_save["favorites"][str(user_id)] = list(fav_set)

        # watched: user_id -> [[slug, ep], ...]
        for user_id, watched_set in USER_WATCHED.items():
            pairs = []
            for slug, ep in watched_set:
                pairs.append([slug, ep])
            data_to_save["watched"][str(user_id)] = pairs

        with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)

        print("Saved users to users.json")

    except Exception as e:
        print("Failed to save users.json:", e)


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


def add_or_update_anime_from_message(msg: Message) -> Optional[str]:
    """
    Берём message с видео и подписью, парсим подпись и обновляем ANIME.
    Сразу сохраняем ANIME в anime.json.
    Возвращаем строку с результатом (для /fix).
    """
    if not msg.video:
        return "❌ В сообщении нет видео."

    meta = parse_caption_to_meta(msg.caption or "")
    if not meta:
        return "❌ Подпись не в нужном формате. Нужны строки:\nslug: ...\ntitle: ...\nep: ...\n[genres: ...]"

    slug = meta["slug"]
    title = meta["title"]
    ep = meta["ep"]
    genres = meta["genres"]
    file_id = msg.video.file_id

    if slug not in ANIME:
        ANIME[slug] = {
            "title": title,
            "genres": genres,
            "episodes": {},
        }
    else:
        ANIME[slug]["title"] = title
        if genres:
            ANIME[slug]["genres"] = genres

    ANIME[slug].setdefault("episodes", {})
    ANIME[slug]["episodes"][ep] = {"source": file_id}

    save_anime()

    return f"✅ Обновлено: {title} (slug: {slug}), серия {ep}"


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
    save_users()
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
        save_users()
        prog = USER_PROGRESS.get(chat_id)
        ep = 1
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        save_users()
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
        save_users()
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("unwatch:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        USER_WATCHED.setdefault(chat_id, set()).discard((slug, ep))
        save_users()
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
    Автодобавление новых серий: сюда приходят сообщения из чата с аниме (SOURCE_CHAT_ID).
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
# /fix — обновить серию по исправленной подписи
# ===============================
async def cmd_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Использование:
    1) Исправляешь подпись у сообщения с серией в SOURCE_CHAT_ID.
    2) Пересылаешь ЭТО сообщение боту (или пишешь /fix в ответ на нужное сообщение, если бот в чате).
    3) Бот берёт актуальную подпись и обновляет ANIME.
    """
    msg = update.message
    if not msg:
        return

    target: Optional[Message] = None

    # Если команда в ответ на сообщение
    if msg.reply_to_message:
        target = msg.reply_to_message
    # Если переслано из канала/чата
    elif msg.forward_from_chat or msg.forward_from_message_id:
        target = msg

    if not target:
        await msg.reply_text("❗ Отправь /fix в ответ на сообщение с видео (или пересылай сообщение с серией боту).")
        return

    from_chat_id = None
    if target.forward_from_chat:
        from_chat_id = target.forward_from_chat.id
    elif target.chat:
        from_chat_id = target.chat.id

    if from_chat_id != SOURCE_CHAT_ID:
        await msg.reply_text("❌ Это сообщение не из SOURCE_CHAT_ID. Перешли боту серию из нужного чата.")
        return

    result = add_or_update_anime_from_message(target)
    await msg.reply_text(result or "✅ Обновлено.")


# ===============================
# /export_anime — отправить текущий anime.json
# ===============================
async def cmd_export_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет актуальный anime.json в чат.
    Полезно для Railway: кидаешь серии боту на хостинге, потом /export_anime и забираешь файл.
    """
    # на всякий случай сохраним текущее состояние ANIME в файл
    save_anime()

    if not os.path.exists(ANIME_JSON_PATH):
        await update.message.reply_text("❌ Файл anime.json не найден.")
        return

    try:
        await update.message.reply_document(
            document=open(ANIME_JSON_PATH, "rb"),
            filename="anime.json",
            caption="Вот твой актуальный anime.json 📦",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить файл: {e}")


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
    # Загружаем существующие данные при старте
    load_anime()
    load_users()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", send_start_message))

    # /fix
    app.add_handler(CommandHandler("fix", cmd_fix))

    # /export_anime
    app.add_handler(CommandHandler("export_anime", cmd_export_anime))

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
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
