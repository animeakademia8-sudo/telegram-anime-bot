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

# slug -> {title, genres, episodes{ep: {"tracks": {track_name: {source, skip}}}}}
ANIME: dict[str, dict] = {}


# ===============================
# JSON SAVE/LOAD: ANIME
# ===============================
def load_anime() -> None:
    """
    Грузим старый или новый формат и конвертим в новый:
    episodes[ep] = {"tracks": {track_name: {"source": ..., "skip": ...}}}
    """
    global ANIME
    if not os.path.exists(ANIME_JSON_PATH):
        ANIME = {}
        return
    try:
        with open(ANIME_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        fixed_data = {}
        for slug, anime in data.items():
            title = anime.get("title", "")
            genres = anime.get("genres", [])
            episodes_raw = anime.get("episodes", {})

            episodes: dict[int, dict] = {}
            for ep_str, ep_data in episodes_raw.items():
                try:
                    ep_int = int(ep_str)
                except ValueError:
                    continue

                # Новый формат или старый?
                if isinstance(ep_data, dict) and "tracks" in ep_data:
                    # Уже новый формат
                    tracks = ep_data.get("tracks", {})
                    # Нормализуем треки: ensure dict with source/skip
                    norm_tracks = {}
                    for tname, tdata in tracks.items():
                        if isinstance(tdata, dict):
                            source = tdata.get("source")
                            skip = tdata.get("skip")
                        else:
                            # если вдруг хранили просто строку
                            source = tdata
                            skip = None
                        if source:
                            norm_tracks[tname] = {"source": source, "skip": skip}
                    if norm_tracks:
                        episodes[ep_int] = {"tracks": norm_tracks}
                else:
                    # Старый формат:
                    # может быть {"source": "...", "skip": "...", "ozv": "..."} или просто {"source": "..."}
                    if not isinstance(ep_data, dict):
                        continue
                    source = ep_data.get("source")
                    if not source:
                        continue
                    skip = ep_data.get("skip")
                    ozv = ep_data.get("ozv") or "default"
                    episodes[ep_int] = {
                        "tracks": {
                            ozv: {
                                "source": source,
                                "skip": skip,
                            }
                        }
                    }

            fixed_data[slug] = {
                "title": title,
                "genres": genres,
                "episodes": episodes,
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
                ep_obj = {}
                # сохраняем в новом формате
                tracks = ep_data.get("tracks", {})
                ep_obj["tracks"] = {}
                for tname, tinfo in tracks.items():
                    ep_obj["tracks"][tname] = {
                        "source": tinfo.get("source"),
                        "skip": tinfo.get("skip"),
                    }
                eps_json[str(ep_int)] = ep_obj

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
    global USER_PROGRESS, USER_FAVORITES, USER_WATCHED_TITLES
    if not os.path.exists(USERS_JSON_PATH):
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
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

        print("Loaded users from users.json")

    except Exception as e:
        print("Failed to load users.json:", e)
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}


def save_users() -> None:
    try:
        data_to_save = {
            "progress": {},
            "favorites": {},
            "watched_titles": {},
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
        if key in ("slug", "title", "ep", "genres", "skip", "ozv"):
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
        "skip": data.get("skip"),
        "ozv": data.get("ozv"),
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
            "[ozv: ...]\n"
            "[skip: ...]\n"
            "[genres: ...]"
        )

    slug = meta["slug"]
    title = meta["title"]
    ep = meta["ep"]
    genres = meta["genres"]
    skip = meta["skip"]
    ozv = meta["ozv"] or "default"
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
    ep_obj = ANIME[slug]["episodes"].setdefault(ep, {"tracks": {}})
    tracks = ep_obj.setdefault("tracks", {})

    tracks[ozv] = {
        "source": file_id,
        "skip": skip,
    }

    save_anime()

    return f"✅ Обновлено: {title} (slug: {slug}), серия {ep}, озвучка: {ozv}"


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


def build_tracks_keyboard(slug: str, ep: int, current_track: Optional[str]) -> list[list[InlineKeyboardButton]]:
    """
    Кнопки выбора озвучки (если больше одной).
    """
    anime = ANIME.get(slug)
    if not anime:
        return []
    ep_obj = anime["episodes"].get(ep)
    if not ep_obj:
        return []
    tracks = ep_obj.get("tracks", {})
    if len(tracks) <= 1:
        return []

    rows = []
    for tname in sorted(tracks.keys()):
        label = tname
        if label == "default":
            label = "Без названия"
        prefix = "✅" if tname == current_track else "🎧"
        btn_text = f"{prefix} {label}"
        # Экранируем ":" в имени озвучки, заменяя на специальную последовательность
        safe_tname = tname.replace(":", "__colon__")
        rows.append(
            [
                InlineKeyboardButton(
                    btn_text,
                    callback_data=f"track:{slug}:{ep}:{safe_tname}",
                )
            ]
        )
    return rows


def build_episode_keyboard(slug: str, ep: int, chat_id: int, current_track: Optional[str]) -> InlineKeyboardMarkup:
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

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}"),
        ],
        [fav_button],
        [watched_button],
    ]

    # Кнопки выбора озвучки (если есть несколько)
    track_rows = build_tracks_keyboard(slug, ep, current_track)
    rows.extend(track_rows)

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


def _pick_track_for_episode(slug: str, ep: int, track_name: Optional[str]) -> tuple[Optional[str], Optional[dict]]:
    """
    Возвращает (track_name, track_data) для серии.
    Если track_name не задан или не найден — берём первую доступную.
    """
    anime = ANIME.get(slug)
    if not anime:
        return None, None
    ep_obj = anime["episodes"].get(ep)
    if not ep_obj:
        return None, None
    tracks = ep_obj.get("tracks", {})
    if not tracks:
        return None, None

    if track_name and track_name in tracks:
        return track_name, tracks[track_name]

    # Берём первую дорожку
    first_name = next(iter(tracks.keys()))
    return first_name, tracks[first_name]


def episode_has_track(slug: str, ep: int, track_name: str) -> bool:
    """
    Проверяем, есть ли у указанной серии дорожка с таким названием.
    """
    anime = ANIME.get(slug)
    if not anime:
        return False
    ep_obj = anime["episodes"].get(ep)
    if not ep_obj:
        return False
    tracks = ep_obj.get("tracks", {})
    return track_name in tracks


async def show_episode(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    slug: str,
    ep: int,
    track_name: Optional[str] = None,
):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    if ep not in anime["episodes"]:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return

    chosen_track_name, track = _pick_track_for_episode(slug, ep, track_name)
    if not track:
        await edit_caption_only(chat_id, context, "Нет доступных дорожек для этой серии.", build_main_menu_keyboard(chat_id))
        return

    source = track.get("source")
    skip = track.get("skip")

    title = anime["title"]
    caption_lines = [f"{title}\nСерия {ep}"]
    if chosen_track_name:
        label = chosen_track_name if chosen_track_name != "default" else "Без названия"
        caption_lines.append(f"Озвучка: {label}")
    if skip:
        caption_lines.append(f"⏩ Пропустить опенинг: {skip}")
    caption = "\n".join(caption_lines)

    kb = build_episode_keyboard(slug, ep, chat_id, chosen_track_name)
    await send_or_edit_video(chat_id, context, source, caption, kb)

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
    # Выбираем первую серию
    eps = sorted(ANIME[slug]["episodes"].keys())
    if not eps:
        await edit_caption_only(chat_id, context, "Нет серий у этого тайтла 😔", build_main_menu_keyboard(chat_id))
        return
    await show_episode(chat_id, context, slug, eps[0])


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
        # первая серия
        anime = ANIME.get(slug)
        if not anime or not anime.get("episodes"):
            await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id))
            return
        first_ep = sorted(anime["episodes"].keys())[0]
        await show_episode(chat_id, context, slug, first_ep)
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
        # формат: next:slug:current_ep
        _, slug, ep_str = data.split(":")
        current = int(ep_str)
        next_ep = current + 1

        anime = ANIME.get(slug)
        if not anime or next_ep not in anime.get("episodes", {}):
            await query.answer("Следующая серия ещё не добавлена.", show_alert=True)
            return

        # вытаскиваем текущую озвучку из подписи
        msg = query.message
        current_track_name: Optional[str] = None
        if msg and msg.caption:
            for line in msg.caption.splitlines():
                line = line.strip()
                if line.lower().startswith("озвучка:"):
                    current_track_name = line.split(":", 1)[1].strip()
                    if current_track_name == "Без названия":
                        current_track_name = "default"
                    break

        if current_track_name and not episode_has_track(slug, next_ep, current_track_name):
            await query.answer("Для следующей серии нет дорожки в выбранной озвучке.", show_alert=True)
            return

        # если дорожка есть или озвучка не выбрана, просто показываем серию
        await show_episode(chat_id, context, slug, next_ep, track_name=current_track_name)
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
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("watch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).add(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("unwatch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).discard(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("track:"):
        # формат: track:slug:ep:track_name_escaped
        _, slug, ep_str, safe_tname = data.split(":", 3)
        ep = int(ep_str)
        track_name = safe_tname.replace("__colon__", ":")
        await show_episode(chat_id, context, slug, ep, track_name=track_name)
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

    # первая серия найденного тайтла
    anime = ANIME.get(found_slug)
    if not anime or not anime.get("episodes"):
        await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id))
        SEARCH_MODE[chat_id] = False
        return

    first_ep = sorted(anime["episodes"].keys())[0]
    await show_episode(chat_id, context, found_slug, first_ep)
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
