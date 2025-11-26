import os
import json
import random
import time
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

# user_id -> set(slug)
USER_WATCHED_TITLES: dict[int, set[str]] = {}

# user stats (first_seen/last_seen)
USER_STATS: dict[int, dict] = {}

# user_id -> {slug: audio_key}
USER_AUDIO_CHOICE: dict[int, dict[str, str]] = {}

# slug -> {title, genres, episodes{ep: variants...}}
ANIME: dict[str, dict] = {}

# ===============================
# HELPERS: user stats persistence
# ===============================
def touch_user(user_id: int):
    now = int(time.time())
    stat = USER_STATS.get(user_id)
    if not stat:
        USER_STATS[user_id] = {"first_seen": now, "last_seen": now}
    else:
        stat["last_seen"] = now
    # save_users will persist this (we call save_users from places where needed)
    # but to keep it simple we save immediately
    save_users()

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

        # Normalize episodes: keys -> int; keep variant formats as-is
        fixed = {}
        for slug, anime in data.items():
            episodes = anime.get("episodes", {})
            fixed_eps = {}
            for ep_str, ep_data in episodes.items():
                try:
                    ep_int = int(ep_str)
                except Exception:
                    continue
                fixed_eps[ep_int] = ep_data
            fixed[slug] = {
                "title": anime.get("title", ""),
                "genres": anime.get("genres", []),
                "episodes": fixed_eps,
            }
        ANIME = fixed
        print(f"Loaded ANIME from {ANIME_JSON_PATH}, items: {len(ANIME)}")
    except Exception as e:
        print("Failed to load anime.json:", e)
        ANIME = {}

def save_anime() -> None:
    try:
        data_to_save = {}
        for slug, anime in ANIME.items():
            eps_json = {}
            for ep_int, ep_data in anime.get("episodes", {}).items():
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
    global USER_PROGRESS, USER_FAVORITES, USER_WATCHED_TITLES, USER_STATS, USER_AUDIO_CHOICE
    if not os.path.exists(USERS_JSON_PATH):
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        USER_STATS = {}
        USER_AUDIO_CHOICE = {}
        return
    try:
        with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        USER_PROGRESS = {}
        for user_id_str, prog in data.get("progress", {}).items():
            try:
                uid = int(user_id_str)
            except Exception:
                continue
            if isinstance(prog, dict):
                USER_PROGRESS[uid] = {k: v for k, v in prog.items() if isinstance(k, str) and isinstance(v, int)}
        USER_FAVORITES = {}
        for user_id_str, fav in data.get("favorites", {}).items():
            try:
                uid = int(user_id_str)
            except Exception:
                continue
            if isinstance(fav, list):
                USER_FAVORITES[uid] = set([s for s in fav if isinstance(s, str)])
            else:
                USER_FAVORITES[uid] = set()
        USER_WATCHED_TITLES = {}
        for user_id_str, wt in data.get("watched_titles", {}).items():
            try:
                uid = int(user_id_str)
            except Exception:
                continue
            if isinstance(wt, list):
                USER_WATCHED_TITLES[uid] = set([s for s in wt if isinstance(s, str)])
            else:
                USER_WATCHED_TITLES[uid] = set()
        USER_STATS = {}
        for user_id_str, st in data.get("stats", {}).items():
            try:
                uid = int(user_id_str)
            except Exception:
                continue
            if isinstance(st, dict):
                USER_STATS[uid] = {"first_seen": st.get("first_seen"), "last_seen": st.get("last_seen")}
        USER_AUDIO_CHOICE = {}
        for user_id_str, ac in data.get("audio_choice", {}).items():
            try:
                uid = int(user_id_str)
            except Exception:
                continue
            if isinstance(ac, dict):
                USER_AUDIO_CHOICE[uid] = {k: v for k, v in ac.items() if isinstance(k, str) and isinstance(v, str)}
        print("Loaded users from users.json")
    except Exception as e:
        print("Failed to load users.json:", e)
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        USER_STATS = {}
        USER_AUDIO_CHOICE = {}

def save_users() -> None:
    try:
        data = {"progress": {}, "favorites": {}, "watched_titles": {}, "stats": {}, "audio_choice": {}}
        for uid, prog in USER_PROGRESS.items():
            data["progress"][str(uid)] = prog
        for uid, fav in USER_FAVORITES.items():
            data["favorites"][str(uid)] = list(fav)
        for uid, wt in USER_WATCHED_TITLES.items():
            data["watched_titles"][str(uid)] = list(wt)
        for uid, st in USER_STATS.items():
            data["stats"][str(uid)] = {"first_seen": st.get("first_seen"), "last_seen": st.get("last_seen")}
        for uid, ac in USER_AUDIO_CHOICE.items():
            data["audio_choice"][str(uid)] = ac
        with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save users.json:", e)

# ===============================
# UTILS: parse caption
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
    except Exception:
        return None
    genres = []
    if "genres" in data and data["genres"]:
        genres = [g.strip().lower() for g in data["genres"].split(",") if g.strip()]
    audio_key = data.get("audio") or data.get("ozv") or "default"
    return {"slug": data["slug"], "title": data["title"], "ep": ep_num, "genres": genres, "skip": data.get("skip"), "ozv": data.get("ozv"), "audio_key": audio_key}

# ===============================
# UTILS: add/update anime from message
# ===============================
def add_or_update_anime_from_message(msg: Message) -> Optional[str]:
    if not msg.video:
        return "❌ В сообщении нет видео."
    meta = parse_caption_to_meta(msg.caption or "")
    if not meta:
        return ("❌ Подпись не в нужном формате. Нужны строки:\n"
                "slug: ...\ntitle: ...\nep: ...\n[skip: мм:сс]\n[ozv: название]\n[genres: ...]\n[audio: ключ]\n")
    slug = meta["slug"]
    title = meta["title"]
    ep = meta["ep"]
    genres = meta["genres"]
    skip = meta.get("skip")
    ozv = meta.get("ozv")
    audio_key = meta.get("audio_key")
    file_id = msg.video.file_id

    if slug not in ANIME:
        ANIME[slug] = {"title": title, "genres": genres, "episodes": {}}
    else:
        ANIME[slug]["title"] = title
        if genres:
            ANIME[slug]["genres"] = genres

    eps = ANIME[slug].setdefault("episodes", {})
    # Convert old-style or ensure dict
    old = eps.get(ep)
    # If old is None or old has 'source' -> convert to variants dict
    if old is None:
        eps[ep] = {}
    elif isinstance(old, dict) and "source" in old:
        eps[ep] = {"default": {"source": old["source"], "skip": old.get("skip"), "ozv": old.get("ozv")}}
    elif not isinstance(old, dict):
        eps[ep] = {}

    # store under audio_key
    ep_obj = eps.setdefault(ep, {})
    ep_obj[audio_key] = {"source": file_id, "skip": skip, "ozv": ozv or audio_key}

    save_anime()
    extra = []
    if skip:
        extra.append(f"skip={skip}")
    if ozv:
        extra.append(f"ozv={ozv}")
    return f"✅ Обновлено: {title} (slug:{slug}) ep:{ep} audio:{audio_key} {' '.join(extra)}"

# ===============================
# UTILS: episode variant selection & audio listing
# ===============================
def get_episode_variant(slug: str, ep: int, chat_id: Optional[int]) -> Optional[dict]:
    """
    Возвращает dict: {source, skip, ozv, audio_key}
    """
    anime = ANIME.get(slug)
    if not anime:
        return None
    eps = anime.get("episodes", {})
    ep_data = eps.get(ep)
    if not ep_data:
        return None
    # old style: single dict with source
    if isinstance(ep_data, dict) and "source" in ep_data:
        return {"source": ep_data["source"], "skip": ep_data.get("skip"), "ozv": ep_data.get("ozv"), "audio_key": "default"}
    if isinstance(ep_data, dict):
        chosen = None
        if chat_id is not None:
            user_map = USER_AUDIO_CHOICE.get(chat_id, {})
            ak = user_map.get(slug)
            if ak and ak in ep_data:
                chosen = (ak, ep_data[ak])
        if not chosen:
            # take first available
            for ak, v in ep_data.items():
                chosen = (ak, v)
                break
        if not chosen:
            return None
        ak, v = chosen
        return {"source": v.get("source"), "skip": v.get("skip"), "ozv": v.get("ozv") or ak, "audio_key": ak}
    return None

def get_audio_variants_for_episode(slug: str, ep: int) -> dict:
    """
    returns {audio_key: human_name}
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
            res[ak] = v.get("ozv") or ak
        return res
    return {}

# ===============================
# UI BUILDERS
# ===============================
def build_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📚 Каталог", callback_data="catalog"),
         InlineKeyboardButton("🎲 Случайное", callback_data="random")],
        [InlineKeyboardButton("⭐ Продолжить", callback_data="continue"),
         InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("💖 Избранное", callback_data="favorites"),
         InlineKeyboardButton("👁 Просмотренное", callback_data="watched")],
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
            rows.append(row); row = []
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

def build_episode_list_keyboard(slug: str) -> InlineKeyboardMarkup:
    eps = sorted(ANIME[slug]["episodes"].keys())
    rows = []; row = []
    for e in eps:
        row.append(InlineKeyboardButton(f"Серия {e}", callback_data=f"ep:{slug}:{e}"))
        if len(row) == 3:
            rows.append(row); row = []
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
    watched = USER_WATCHED_TITLES.get(chat_id, set())
    rows = []
    for slug in sorted(watched):
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows = [[InlineKeyboardButton("Пусто", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_continue_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    prog = USER_PROGRESS.get(chat_id, {})
    rows = []
    if not prog:
        rows.append([InlineKeyboardButton("Пока нечего продолжать", callback_data="menu")])
        rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
        return InlineKeyboardMarkup(rows)
    for slug, ep in prog.items():
        title = ANIME.get(slug, {}).get("title", slug)
        rows.append([InlineKeyboardButton(f"{title} — с {ep} серии", callback_data=f"cont:{slug}")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_continue_item_keyboard(chat_id: int, slug: str) -> InlineKeyboardMarkup:
    ep = USER_PROGRESS.get(chat_id, {}).get(slug)
    title = ANIME.get(slug, {}).get("title", slug)
    rows = []
    if ep:
        rows.append([InlineKeyboardButton(f"▶ Продолжить «{title}» c {ep} серии", callback_data=f"cont_play:{slug}")])
    rows.append([InlineKeyboardButton(f"✖ Убрать «{title}» из продолжения", callback_data=f"cont_remove:{slug}")])
    rows.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data="continue_list")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_search_results_keyboard(matches: list[tuple[str,str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(title, callback_data=f"anime:{slug}")] for slug, title in matches]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_audio_keyboard(slug: str, ep: int, chat_id: int) -> list[list[InlineKeyboardButton]]:
    variants = get_audio_variants_for_episode(slug, ep)
    if not variants or len(variants) <= 1:
        return []
    current = USER_AUDIO_CHOICE.get(chat_id, {}).get(slug)
    rows = []
    for ak, name in variants.items():
        prefix = "✅ " if ak == current else "🎧 "
        rows.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"audio:{slug}:{ep}:{ak}")])
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
    fav_button = InlineKeyboardButton("💔 Убрать из избранного", callback_data=f"fav_remove:{slug}") if slug in fav_set else InlineKeyboardButton("💖 В избранное", callback_data=f"fav_add:{slug}")
    watched_set = USER_WATCHED_TITLES.get(chat_id, set())
    watched_button = InlineKeyboardButton("👁 Убрать тайтл из просмотренного", callback_data=f"unwatch_title:{slug}") if slug in watched_set else InlineKeyboardButton("👁 Тайтл просмотрен", callback_data=f"watch_title:{slug}")
    rows = [[InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}")],[fav_button],[watched_button]]
    # audio rows
    rows.extend(build_audio_keyboard(slug, ep, chat_id))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

# ===============================
# HELPERS: single-message logic
# ===============================
async def send_or_edit_photo(chat_id: int, context: ContextTypes.DEFAULT_TYPE, photo_path: str, caption: str, reply_markup: InlineKeyboardMarkup):
    msg_id = LAST_MESSAGE.get(chat_id)
    if msg_id:
        try:
            with open(photo_path, "rb") as ph:
                await context.bot.edit_message_media(media=InputMediaPhoto(media=ph, caption=caption), chat_id=chat_id, message_id=msg_id)
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
            LAST_MESSAGE_TYPE[chat_id] = "photo"
            return msg_id
        except Exception:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    with open(photo_path, "rb") as ph:
        sent = await context.bot.send_photo(chat_id=chat_id, photo=ph, caption=caption, reply_markup=reply_markup)
    LAST_MESSAGE[chat_id] = sent.message_id
    LAST_MESSAGE_TYPE[chat_id] = "photo"
    return sent.message_id

async def send_or_edit_video(chat_id: int, context: ContextTypes.DEFAULT_TYPE, file_id_or_path: str, caption: str, reply_markup: InlineKeyboardMarkup):
    msg_id = LAST_MESSAGE.get(chat_id)
    media = InputMediaVideo(media=file_id_or_path, caption=caption)
    if msg_id:
        try:
            await context.bot.edit_message_media(media=media, chat_id=chat_id, message_id=msg_id)
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
            LAST_MESSAGE_TYPE[chat_id] = "video"
            return msg_id
        except Exception:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    sent = await context.bot.send_video(chat_id=chat_id, video=file_id_or_path, caption=caption, reply_markup=reply_markup)
    LAST_MESSAGE[chat_id] = sent.message_id
    LAST_MESSAGE_TYPE[chat_id] = "video"
    return sent.message_id

async def edit_caption_only(chat_id: int, context: ContextTypes.DEFAULT_TYPE, caption: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    msg_id = LAST_MESSAGE.get(chat_id)
    if not msg_id:
        return await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, reply_markup or build_main_menu_keyboard(chat_id))
    try:
        await context.bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=caption, reply_markup=reply_markup)
        return msg_id
    except Exception:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        with open(WELCOME_PHOTO, "rb") as ph:
            sent = await context.bot.send_photo(chat_id=chat_id, photo=ph, caption=caption, reply_markup=reply_markup)
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

async def show_episode(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int, track_name: Optional[str] = None):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    # if user specified track_name (from button), set it in user choice
    if track_name:
        USER_AUDIO_CHOICE.setdefault(chat_id, {})[slug] = track_name
        save_users()
    variant = get_episode_variant(slug, ep, chat_id)
    if not variant:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return
    title = anime.get("title", "")
    lines = [f"{title}", f"Серия {ep}"]
    if variant.get("ozv"):
        lines.append(f"🎙 Озвучка: {variant['ozv']}")
    if variant.get("skip"):
        lines.append(f"⏭ Пропустить: {variant['skip']}")
    caption = "\n".join(lines)
    kb = build_episode_keyboard(slug, ep, chat_id)
    await send_or_edit_video(chat_id, context, variant["source"], caption, kb)
    USER_PROGRESS.setdefault(chat_id, {})[slug] = ep
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
    eps = sorted(ANIME[slug].get("episodes", {}).keys())
    if not eps:
        await edit_caption_only(chat_id, context, "Нет серий у этого тайтла.", build_main_menu_keyboard(chat_id))
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
    if not query:
        return
    await query.answer()
    data = query.data or ""
    chat_id = query.message.chat_id
    touch_user(chat_id)

    # MENU
    if data == "menu":
        await show_main_menu(chat_id, context); return
    if data == "catalog":
        await show_genres(chat_id, context); return
    if data == "random":
        await show_random(chat_id, context); return
    if data == "continue":
        await show_continue_list(chat_id, context); return
    if data == "continue_list":
        await show_continue_list(chat_id, context); return

    # CONTINUE ITEMS
    if data.startswith("cont:"):
        slug = data.split(":",1)[1]; kb = build_continue_item_keyboard(chat_id, slug)
        await edit_caption_only(chat_id, context, "Что сделать с этим тайтлом?", kb); return
    if data.startswith("cont_play:"):
        slug = data.split(":",1)[1]
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if not ep:
            await query.answer("Нет сохранённого прогресса для этого тайтла.", show_alert=True)
            await show_continue_list(chat_id, context); return
        # try to use user's audio choice (get_episode_variant will handle)
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("cont_remove:"):
        slug = data.split(":",1)[1]
        if chat_id in USER_PROGRESS and slug in USER_PROGRESS[chat_id]:
            del USER_PROGRESS[chat_id][slug]
            if not USER_PROGRESS[chat_id]:
                del USER_PROGRESS[chat_id]
            save_users()
        await query.answer("Убрано из продолжения.")
        await show_continue_list(chat_id, context); return

    # SEARCH MODE
    if data == "search":
        SEARCH_MODE[chat_id] = True
        caption = "🔍 Введи название аниме сообщением (или его часть).\n(Текст потом удалю, реагирую только на кнопки)"
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id)); return

    # FAVORITES / WATCHED
    if data == "favorites":
        await show_favorites(chat_id, context); return
    if data == "watched":
        await show_watched_titles(chat_id, context); return

    # GENRE -> ANIME or ANIME list
    if data.startswith("genre:"):
        genre = data.split(":",1)[1]; await show_anime_by_genre(chat_id, context, genre); return

    # ANIME selected -> open first series (respect user's audio choice if exists)
    if data.startswith("anime:"):
        slug = data.split(":",1)[1]
        anime = ANIME.get(slug)
        if not anime or not anime.get("episodes"):
            await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id)); return
        first_ep = sorted(anime["episodes"].keys())[0]
        await show_episode(chat_id, context, slug, first_ep); return

    if data.startswith("list:"):
        slug = data.split(":",1)[1]; await show_episode_list(chat_id, context, slug); return

    if data.startswith("ep:"):
        _, slug, ep_str = data.split(":"); ep = int(ep_str)
        await show_episode(chat_id, context, slug, ep); return

    # NEXT/PREV should preserve chosen audio_key if possible
    if data.startswith("next:") or data.startswith("prev:"):
        typ, slug, ep_str = data.split(":")
        current = int(ep_str)
        new_ep = current + 1 if typ == "next" else current - 1
        # keep user's chosen audio_key for slug
        await show_episode(chat_id, context, slug, new_ep); return

    # FAVORITE toggle
    if data.startswith("fav_add:"):
        slug = data.split(":",1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).add(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug); ep = sorted(anime["episodes"].keys())[0] if anime and anime.get("episodes") else 1
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("fav_remove:"):
        slug = data.split(":",1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug); ep = sorted(anime["episodes"].keys())[0] if anime and anime.get("episodes") else 1
        await show_episode(chat_id, context, slug, ep); return

    # WATCH toggle
    if data.startswith("watch_title:"):
        slug = data.split(":",1)[1]; USER_WATCHED_TITLES.setdefault(chat_id, set()).add(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug) or 1; await show_episode(chat_id, context, slug, ep); return
    if data.startswith("unwatch_title:"):
        slug = data.split(":",1)[1]; USER_WATCHED_TITLES.setdefault(chat_id, set()).discard(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug) or 1; await show_episode(chat_id, context, slug, ep); return

    # audio selection: audio:slug:ep:audio_key
    if data.startswith("audio:"):
        _, slug, ep_str, audio_key = data.split(":",3)
        ep = int(ep_str)
        USER_AUDIO_CHOICE.setdefault(chat_id, {})[slug] = audio_key
        save_users()
        # show same ep but with chosen audio (show_episode will read user's choice)
        await show_episode(chat_id, context, slug, ep, track_name=audio_key)
        return

# ===============================
# TEXT SEARCH handler (with multi-results)
# ===============================
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    touch_user(chat_id)
    # if not in search mode - delete message
    if not SEARCH_MODE.get(chat_id, False):
        try:
            await update.message.delete()
        except Exception:
            pass
        return
    q = text.lower()
    matches = []
    for slug, anime in ANIME.items():
        title = anime.get("title","")
        if q in title.lower():
            matches.append((slug, title))
    try:
        await update.message.delete()
    except Exception:
        pass
    if not matches:
        await edit_caption_only(chat_id, context, "😔 Ничего не нашёл по этому названию.\nПопробуй другое слово.\n(Я реагирую только на кнопки)", build_main_menu_keyboard(chat_id))
        SEARCH_MODE[chat_id] = False
        return
    if len(matches) == 1:
        slug = matches[0][0]
        anime = ANIME.get(slug)
        if not anime or not anime.get("episodes"):
            await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id))
            SEARCH_MODE[chat_id] = False
            return
        first_ep = sorted(anime["episodes"].keys())[0]
        await show_episode(chat_id, context, slug, first_ep)
        SEARCH_MODE[chat_id] = False
        return
    kb = build_search_results_keyboard(matches)
    await edit_caption_only(chat_id, context, "Нашёл несколько тайтлв, выбери нужный:", kb)
    SEARCH_MODE[chat_id] = False

# ===============================
# CLEANUP (final fallback)
# ===============================
async def cleanup_non_command_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat_id = msg.chat_id
    if chat_id == SOURCE_CHAT_ID:
        return
    if msg.text and msg.text.startswith("/"):
        return
    try:
        await msg.delete()
    except Exception:
        pass

# ===============================
# SOURCE CHAT: auto add series
# ===============================
async def handle_source_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if msg.chat_id != SOURCE_CHAT_ID:
        return
    if not msg.video:
        return
    res = add_or_update_anime_from_message(msg)
    # do not notify in source chat to avoid noise

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
        await msg.reply_text("❗ Отправь /fix в ответ на сообщение с видео (или пересылай сообщение с серией боту)."); return
    from_chat_id = None
    if target.forward_from_chat:
        from_chat_id = target.forward_from_chat.id
    elif target.chat:
        from_chat_id = target.chat.id
    if from_chat_id != SOURCE_CHAT_ID and msg.from_user.id != ADMIN_ID:
        await msg.reply_text("❌ Это сообщение не из SOURCE_CHAT_ID. Перешли боту серию из нужного чата."); return
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
        await msg.reply_text("⛔ Эта команда только для админа."); return
    if os.path.exists(ANIME_JSON_PATH):
        try:
            with open(ANIME_JSON_PATH, "rb") as f:
                await msg.reply_document(document=f, filename="anime.json", caption="📁 Текущий anime.json")
        except Exception as e:
            await msg.reply_text(f"❌ Не удалось отправить anime.json: {e}")
    else:
        await msg.reply_text("⚠️ Файл anime.json не найден на диске.")
    if os.path.exists(USERS_JSON_PATH):
        try:
            with open(USERS_JSON_PATH, "rb") as f:
                await msg.reply_document(document=f, filename="users.json", caption="📁 Текущий users.json")
        except Exception as e:
            await msg.reply_text(f"❌ Не удалось отправить users.json: {e}")
    else:
        await msg.reply_text("⚠️ Файл users.json ещё не создан.")

# ===============================
# /stats (admin)
# ===============================
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await msg.reply_text("⛔ Эта команда только для админа."); return
    total = len(USER_STATS)
    now = int(time.time())
    day_ago = now - 24*3600
    week_ago = now - 7*24*3600
    active_day = sum(1 for s in USER_STATS.values() if (s.get("last_seen") or 0) >= day_ago)
    active_week = sum(1 for s in USER_STATS.values() if (s.get("last_seen") or 0) >= week_ago)
    text = (f"👥 Всего пользователей: <b>{total}</b>\n"
            f"🔥 Активны за 24 часа: <b>{active_day}</b>\n"
            f"📅 Активны за 7 дней: <b>{active_week}</b>\n")
    await msg.reply_text(text, parse_mode="HTML")

# ===============================
# /start
# ===============================
async def send_start_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    touch_user(chat_id)
    last_id = LAST_MESSAGE.get(chat_id)
    if last_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_id)
        except Exception:
            pass
        LAST_MESSAGE.pop(chat_id, None); LAST_MESSAGE_TYPE.pop(chat_id, None)
    await show_main_menu(chat_id, context)
    try:
        await update.message.delete()
    except Exception:
        pass

# ===============================
# debug: get file_id
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
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Chat(SOURCE_CHAT_ID), handle_user_text))
    app.add_handler(MessageHandler(filters.Chat(SOURCE_CHAT_ID) & filters.VIDEO, handle_source_chat_message))
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.Chat(SOURCE_CHAT_ID), debug_video))
    app.add_handler(MessageHandler(filters.ALL, cleanup_non_command_messages))
    print("BOT STARTED...")
    app.run_polling()

if __name__ == "__main__":
    main()
