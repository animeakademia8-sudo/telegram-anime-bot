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

BOT_TOKEN = os.environ.get("BOT_TOKEN")

WELCOME_PHOTO = "images/welcome.jpg"
SOURCE_CHAT_ID = -1003362969236

ANIME_JSON_PATH = "anime.json"
USERS_JSON_PATH = "users.json"

ADMIN_ID = 852405425

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: dict[int, int] = {}
LAST_MESSAGE_TYPE: dict[int, str] = {}
SEARCH_MODE: dict[int, bool] = {}

# user_id -> {slug: ep}
USER_PROGRESS: dict[int, dict[str, int]] = {}

# user_id -> set(slug)
USER_FAVORITES: dict[int, set[str]] = {}

# user_id -> set(slug)  # ТАЙТЛЫ, которые отмечены как "просмотренные"
USER_WATCHED_TITLES: dict[int, set[str]] = {}

# user_id -> {slug: audio_key}  # выбранная озвучка для тайтла
USER_AUDIO_CHOICE: dict[int, dict[str, str]] = {}

# slug -> {title, genres, episodes{ep: {source/variants}}}
ANIME: dict[str, dict] = {}


# ===============================
# JSON SAVE/LOAD: ANIME
# ===============================
def load_anime() -> None:
    global ANIME
    if not os.path.exists(ANIME_JSON_PATH):
        ANIME = {}
        return
    try:
        with open(ANIME_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        fixed_data = {}
        for slug, anime in data.items():
            episodes = anime.get("episodes", {})
            fixed_eps = {}
            for ep_str, ep_data in episodes.items():
                try:
                    ep_int = int(ep_str)
                except ValueError:
                    continue

                # поддержка двух форматов:
                # 1) старый: { "source": "file_id", ... }
                # 2) новый: { "audio_key": { "source": "file_id", "skip": "...", "ozv": "..." }, ... }
                fixed_eps[ep_int] = ep_data

            anime["episodes"] = fixed_eps
            fixed_data[slug] = {
                "title": anime.get("title", ""),
                "genres": anime.get("genres", []),
                "episodes": fixed_eps,
            }

        ANIME = fixed_data
        print(f"Loaded ANIME from {ANIME_JSON_PATH}, items:", len(ANIME))
    except Exception as e:
        print("Failed to load anime.json:", e)
        ANIME = {}


def save_anime() -> None:
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
    except Exception as e:
        print("Failed to save anime.json:", e)


# ===============================
# JSON SAVE/LOAD: USERS
# ===============================
def load_users() -> None:
    global USER_PROGRESS, USER_FAVORITES, USER_WATCHED_TITLES, USER_AUDIO_CHOICE
    if not os.path.exists(USERS_JSON_PATH):
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        USER_AUDIO_CHOICE = {}
        return

    try:
        with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # progress: user_id -> {slug: ep}
        USER_PROGRESS = {}
        for user_id_str, prog_map in data.get("progress", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(prog_map, dict):
                res = {}
                for slug, ep in prog_map.items():
                    if isinstance(slug, str) and isinstance(ep, int):
                        res[slug] = ep
                if res:
                    USER_PROGRESS[user_id] = res

        # favorites: user_id -> [slug, ...]
        USER_FAVORITES = {}
        for user_id_str, fav_list in data.get("favorites", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(fav_list, list):
                USER_FAVORITES[user_id] = set(
                    [slug for slug in fav_list if isinstance(slug, str)]
                )
            else:
                USER_FAVORITES[user_id] = set()

        # watched_titles: user_id -> [slug, ...]
        USER_WATCHED_TITLES = {}
        for user_id_str, wt_list in data.get("watched_titles", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(wt_list, list):
                USER_WATCHED_TITLES[user_id] = set(
                    [slug for slug in wt_list if isinstance(slug, str)]
                )
            else:
                USER_WATCHED_TITLES[user_id] = set()

        # audio_choice: user_id -> {slug: audio_key}
        USER_AUDIO_CHOICE = {}
        for user_id_str, audio_map in data.get("audio_choice", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(audio_map, dict):
                USER_AUDIO_CHOICE[user_id] = {
                    slug: ak for slug, ak in audio_map.items() if isinstance(slug, str) and isinstance(ak, str)
                }

        print("Loaded users from users.json")

    except Exception as e:
        print("Failed to load users.json:", e)
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        USER_AUDIO_CHOICE = {}


def save_users() -> None:
    try:
        data_to_save = {
            "progress": {},
            "favorites": {},
            "watched_titles": {},
            "audio_choice": {},
        }

        # progress: user_id -> {slug: ep}
        for user_id, prog_map in USER_PROGRESS.items():
            data_to_save["progress"][str(user_id)] = prog_map

        # favorites
        for user_id, fav_set in USER_FAVORITES.items():
            data_to_save["favorites"][str(user_id)] = list(fav_set)

        # watched titles
        for user_id, wt_set in USER_WATCHED_TITLES.items():
            data_to_save["watched_titles"][str(user_id)] = list(wt_set)

        # audio choice
        for user_id, audio_map in USER_AUDIO_CHOICE.items():
            data_to_save["audio_choice"][str(user_id)] = audio_map

        with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print("Failed to save users.json:", e)


# ===============================
# UTILS: парсер подписи
# ===============================
def parse_caption_to_meta(caption: str) -> Optional[dict]:
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
        if key in ("slug", "title", "ep", "genres", "skip", "ozv", "audio"):
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

    # ключ озвучки: либо явный audio: ..., либо ozv: ...
    audio_key = data.get("audio") or data.get("ozv") or "default"

    return {
        "slug": data["slug"],
        "title": data["title"],
        "ep": ep_num,
        "genres": genres_list,
        "skip": data.get("skip"),
        "ozv": data.get("ozv"),
        "audio_key": audio_key,
    }


def add_or_update_anime_from_message(msg: Message) -> Optional[str]:
    if not msg.video:
        return "❌ В сообщении нет видео."

    meta = parse_caption_to_meta(msg.caption or "")
    if not meta:
        return (
            "❌ Подпись не в нужном формате. Нужны строки:\n"
            "slug: ...\n"
            "title: ...\n"
            "ep: ...\n"
            "[skip: мм:cc]\n"
            "[ozv: название озвучки]\n"
            "[genres: ...]\n"
            "⚠ Дополнительно можно указать audio: ключ_озвучки (если не указать, берётся из ozv или 'default')"
        )

    slug = meta["slug"]
    title = meta["title"]
    ep = meta["ep"]
    genres = meta["genres"]
    skip = meta["skip"]
    ozv = meta["ozv"]
    audio_key = meta["audio_key"]
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
    episodes = ANIME[slug]["episodes"]

    # поддерживаем мульти-озвучки
    if ep not in episodes or not isinstance(episodes[ep], dict) or "source" in episodes[ep]:
        # если там старый формат или ничего — приведём к новому
        old = episodes.get(ep)
        variants = {}
        if isinstance(old, dict) and "source" in old:
            variants["default"] = {
                "source": old["source"],
                "skip": old.get("skip"),
                "ozv": old.get("ozv"),
            }
        episodes[ep] = variants

    if isinstance(episodes[ep], dict):
        episodes[ep][audio_key] = {
            "source": file_id,
            "skip": skip,
            "ozv": ozv or audio_key,
        }

    save_anime()

    return (
        f"✅ Обновлено: {title} (slug: {slug}), серия {ep}\n"
        f"🎙 Озвучка: {ozv or audio_key}"
    )


# ===============================
# UTILS: выбор варианта эпизода
# ===============================
def get_episode_variant(slug: str, ep: int, chat_id: int) -> Optional[dict]:
    """
    Возвращает словарь:
    {
        "source": ...,
        "skip": ...,
        "ozv": ...,
        "audio_key": ...
    }
    """
    anime = ANIME.get(slug)
    if not anime:
        return None

    episodes = anime.get("episodes", {})
    ep_data = episodes.get(ep)
    if not ep_data:
        return None

    # старый формат: один вариант
    if isinstance(ep_data, dict) and "source" in ep_data:
        return {
            "source": ep_data["source"],
            "skip": ep_data.get("skip"),
            "ozv": ep_data.get("ozv"),
            "audio_key": "default",
        }

    # новый формат: dict[audio_key] = {source, skip, ozv}
    if isinstance(ep_data, dict):
        user_choice = USER_AUDIO_CHOICE.get(chat_id, {}).get(slug)
        if user_choice and user_choice in ep_data:
            v = ep_data[user_choice]
            return {
                "source": v["source"],
                "skip": v.get("skip"),
                "ozv": v.get("ozv") or user_choice,
                "audio_key": user_choice,
            }

        # fallback — первый вариант
        for ak, v in ep_data.items():
            return {
                "source": v["source"],
                "skip": v.get("skip"),
                "ozv": v.get("ozv") or ak,
                "audio_key": ak,
            }

    return None


def get_audio_variants_for_episode(slug: str, ep: int) -> dict:
    """
    Возвращает словарь audio_key -> озвучка_человекочитаемо
    Для старого формата — один элемент {"default": "По умолчанию"}
    """
    anime = ANIME.get(slug)
    if not anime:
        return {}

    ep_data = anime.get("episodes", {}).get(ep)
    if not ep_data:
        return {}

    if isinstance(ep_data, dict) and "source" in ep_data:
        return {"default": "По умолчанию"}

    if isinstance(ep_data, dict):
        res = {}
        for ak, v in ep_data.items():
            name = v.get("ozv") or ak
            res[ak] = name
        return res

    return {}


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


def build_audio_keyboard(slug: str, ep: int, chat_id: int) -> list[list[InlineKeyboardButton]]:
    variants = get_audio_variants_for_episode(slug, ep)
    if not variants or len(variants) == 1:
        return []

    current = USER_AUDIO_CHOICE.get(chat_id, {}).get(slug)
    rows = []
    for ak, name in variants.items():
        prefix = "✅ " if ak == current else ""
        rows.append([
            InlineKeyboardButton(
                f"{prefix}{name}",
                callback_data=f"audio:{slug}:{ep}:{ak}",
            )
        ])
    return rows


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

    watched_titles = USER_WATCHED_TITLES.get(chat_id, set())
    if slug in watched_titles:
        watched_button = InlineKeyboardButton(
            "👁 Убрать тайтл из просмотренного",
            callback_data=f"unwatch_title:{slug}",
        )
    else:
        watched_button = InlineKeyboardButton(
            "👁 Тайтл просмотрен",
            callback_data=f"watch_title:{slug}",
        )

    rows = [
        [
            InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}"),
        ],
        [fav_button],
        [watched_button],
    ]

    # выбор озвучки (если вариантов > 1)
    audio_rows = build_audio_keyboard(slug, ep, chat_id)
    rows.extend(audio_rows)

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


def build_watched_titles_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    watched_titles = USER_WATCHED_TITLES.get(chat_id, set())
    rows = []
    for slug in sorted(watched_titles):
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows = [[InlineKeyboardButton("Пусто", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_continue_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    user_prog = USER_PROGRESS.get(chat_id, {})
    rows = []

    if not user_prog:
        rows.append([InlineKeyboardButton("Пока нечего продолжать", callback_data="menu")])
        rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
        return InlineKeyboardMarkup(rows)

    for slug, ep in user_prog.items():
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([
            InlineKeyboardButton(
                f"{title} — с {ep} серии",
                callback_data=f"cont:{slug}",
            )
        ])

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_continue_item_keyboard(chat_id: int, slug: str) -> InlineKeyboardMarkup:
    ep = USER_PROGRESS.get(chat_id, {}).get(slug)
    title = ANIME.get(slug, {}).get("title", slug)

    rows = []

    if ep:
        rows.append([
            InlineKeyboardButton(
                f"▶ Продолжить «{title}» c {ep} серии",
                callback_data=f"cont_play:{slug}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            f"✖ Убрать «{title}» из продолжения",
            callback_data=f"cont_remove:{slug}",
        )
    ])

    rows.append([
        InlineKeyboardButton("⬅️ Назад к списку", callback_data="continue_list")
    ])

    rows.append([
        InlineKeyboardButton("🍄 Меню", callback_data="menu")
    ])

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
    caption = "Приятного просмотра ✨\nВсе управление через кнопки ниже."
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

    variant = get_episode_variant(slug, ep, chat_id)
    if not variant:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return

    title = anime["title"]
    caption_lines = [
        f"{title}",
        f"Серия {ep}",
    ]
    if variant.get("skip"):
        caption_lines.append(f"⏭ Пропуск: {variant['skip']}")
    if variant.get("ozv"):
        caption_lines.append(f"🎙 Озвучка: {variant['ozv']}")

    caption = "\n".join(caption_lines)
    kb = build_episode_keyboard(slug, ep, chat_id)
    await send_or_edit_video(chat_id, context, variant["source"], caption, kb)

    USER_PROGRESS.setdefault(chat_id, {})
    USER_PROGRESS[chat_id][slug] = ep
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


async def show_watched_titles(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Просмотренные тайтлы:"
    kb = build_watched_titles_keyboard(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_continue_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Тайтлы, которые ты сейчас смотришь:"
    kb = build_continue_keyboard(chat_id)
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
        await show_continue_list(chat_id, context)
        return

    if data == "continue_list":
        await show_continue_list(chat_id, context)
        return

    if data.startswith("cont:"):
        slug = data.split(":", 1)[1]
        caption = "Что сделать с этим тайтлом?"
        kb = build_continue_item_keyboard(chat_id, slug)
        await edit_caption_only(chat_id, context, caption, kb)
        return

    if data.startswith("cont_play:"):
        slug = data.split(":", 1)[1]
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if not ep:
            await query.answer("Нет сохранённого прогресса для этого тайтла.", show_alert=True)
            await show_continue_list(chat_id, context)
            return
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("cont_remove:"):
        slug = data.split(":", 1)[1]
        if chat_id in USER_PROGRESS and slug in USER_PROGRESS[chat_id]:
            del USER_PROGRESS[chat_id][slug]
            if not USER_PROGRESS[chat_id]:
                del USER_PROGRESS[chat_id]
            save_users()
        await query.answer("Убрано из продолжения.")
        await show_continue_list(chat_id, context)
        return

    if data == "search":
        SEARCH_MODE[chat_id] = True
        caption = "🔍 Введи название аниме сообщением (или его часть).\n(Текст потом удалю, реагирую только на кнопки)"
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id))
        return

    if data == "favorites":
        await show_favorites(chat_id, context)
        return

    if data == "watched":
        await show_watched_titles(chat_id, context)
        return

    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        await show_anime_by_genre(chat_id, context, genre)
        return

    if data.startswith("anime:"):
        slug = data.split(":", 1)[1]
        await show_episode(chat_id, context, slug, 1)
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
        ep = USER_PROGRESS.get(chat_id, {}).get(slug, 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug, 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("watch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).add(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug, 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("unwatch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).discard(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug, 1)
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("audio:"):
        # audio:slug:ep:audio_key
        _, slug, ep_str, audio_key = data.split(":", 3)
        ep = int(ep_str)

        USER_AUDIO_CHOICE.setdefault(chat_id, {})
        USER_AUDIO_CHOICE[chat_id][slug] = audio_key
        save_users()

        await show_episode(chat_id, context, slug, ep)
        return


# ===============================
# TEXT (SEARCH) — с удалением
# ===============================
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # Если это текст от пользователя, а не команда и мы не в режиме поиска — сразу удаляем
    if not SEARCH_MODE.get(chat_id, False):
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    q = text.lower()
    found_slug = None
    for slug, anime in ANIME.items():
        if q in anime["title"].lower():
            found_slug = slug
            break

    # Удаляем сообщение с текстом поиска
    try:
        await update.message.delete()
    except Exception:
        pass

    if not found_slug:
        await edit_caption_only(
            chat_id,
            context,
            "😔 Ничего не нашёл по этому названию.\nПопробуй другое слово.\n(Я реагирую только на кнопки)",
            build_main_menu_keyboard(chat_id),
        )
        SEARCH_MODE[chat_id] = False
        return

    await show_episode(chat_id, context, found_slug, 1)
    SEARCH_MODE[chat_id] = False


# ===============================
# EXTRA CLEANUP ХЭНДЛЕР
# ===============================
async def cleanup_non_command_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    На всякий случай: удаляем любые некомандные сообщения,
    если они не из SOURCE_CHAT_ID. Чтобы чат не засирался.
    """
    msg = update.message
    if not msg:
        return
    chat_id = msg.chat_id

    # Сообщения из SOURCE_CHAT_ID не трогаем
    if chat_id == SOURCE_CHAT_ID:
        return

    # Команды не трогаем (их обрабатывают CommandHandler'ы)
    if msg.text and msg.text.startswith("/"):
        return

    # Всё остальное удаляем
    try:
        await msg.delete()
    except Exception:
        pass


# ===============================
# SOURCE CHAT HANDLER
# ===============================
async def handle_source_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if msg.chat_id != SOURCE_CHAT_ID:
        return
    if not msg.video:
        return

    add_or_update_anime_from_message(msg)


# ===============================
# /fix
# ===============================
async def cmd_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    target: Optional[Message] = None

    if msg.reply_to_message:
        target = msg.reply_to_message
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
# /dump_all
# ===============================
async def cmd_dump_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    chat_id = update.effective_chat.id

    if chat_id != ADMIN_ID:
        await msg.reply_text("⛔ Эта команда только для админа.")
        return

    if os.path.exists(ANIME_JSON_PATH):
        try:
            with open(ANIME_JSON_PATH, "rb") as f:
                await msg.reply_document(
                    document=f,
                    filename="anime.json",
                    caption="📁 Текущий anime.json",
                )
        except Exception as e:
            await msg.reply_text(f"❌ Не удалось отправить anime.json: {e}")
    else:
        await msg.reply_text("⚠️ Файл anime.json не найден на диске.")

    if os.path.exists(USERS_JSON_PATH):
        try:
            with open(USERS_JSON_PATH, "rb") as f:
                await msg.reply_document(
                    document=f,
                    filename="users.json",
                    caption="📁 Текущий users.json",
                )
        except Exception as e:
            await msg.reply_text(f"❌ Не удалось отправить users.json: {e}")
    else:
        await msg.reply_text("⚠️ Файл users.json ещё не создан.")


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
    load_anime()
    load_users()

    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CommandHandler("fix", cmd_fix))
    app.add_handler(CommandHandler("dump_all", cmd_dump_all))

    app.add_handler(CallbackQueryHandler(handle_callback))

    # Поиск — только текст, не команды, не из SOURCE_CHAT_ID
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Chat(SOURCE_CHAT_ID),
            handle_user_text,
        )
    )

    # Сообщения из SOURCE_CHAT_ID (автодобавление аниме)
    app.add_handler(
        MessageHandler(
            filters.Chat(SOURCE_CHAT_ID) & filters.VIDEO,
            handle_source_chat_message,
        )
    )

    # debug: видео не из SOURCE_CHAT_ID
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.Chat(SOURCE_CHAT_ID), debug_video))

    # Общий уборочный хэндлер — на САМОМ КОНЦЕ
    app.add_handler(
        MessageHandler(
            filters.ALL,
            cleanup_non_command_messages,
        )
    )

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
