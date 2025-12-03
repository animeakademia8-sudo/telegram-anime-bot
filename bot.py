# bot.py
import os
import json
import random
from collections import deque
from typing import Optional, Dict, List

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
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # или вставь строкой
WELCOME_PHOTO = "images/welcome.jpg"
SOURCE_CHAT_ID = -1003362969236

ANIME_JSON_PATH = "anime.json"
USERS_JSON_PATH = "users.json"

ADMIN_ID = 852405425
ADMIN2_ID = 8505295670

# ===============================
# ACHIEVEMENTS (тут как у тебя, не трогаю)
# ===============================
ACHIEVEMENTS = {
    1: (
        "images/ach_1.jpg",
        "💀 Ты сделал первый шаг в море аниме.\n"
        "💰 Награда за голову: 1 000 белли.\n"
        "Морская стража пока вас игнорирует."
    ),

    5: (
        "images/ach_5.jpg",
        "🏴‍☠️ О тебе начинают ходить слухи.\n"
        "💰 Награда за голову: 5 000 000 белли.\n"
        "В тавернах спорят — новичок ты или будущая угроза."
    ),

    10: (
        "images/ach_10.jpg",
        "💣 Ты выходишь из тени обычных пиратов.\n"
        "💰 Награда за голову: 16 000 000 белли.\n"
        "Дозорные начинают узнавать твоё имя."
    ),

    25: (
        "images/ach_25.jpg",
        "🔥 Ты всё чаще попадаешь в сводки новостей.\n"
        "💰 Награда за голову: 77 000 000 белли.\n"
        "Мировое Правительство впервые заинтересовалось тобой."
    ),

    50: (
        "images/ach_50.jpg",
        "💥 Ты становишься серьёзной угрозой.\n"
        "💰 Награда за голову: 470 000 000 белли.\n"
        "Твоё имя обсуждают капитаны известных команд."
    ),

    100: (
        "images/ach_100.jpg",
        "👑 Ты ступил на уровень легенд.\n"
        "💰 Награда за голову: 1 000 000 000 белли.\n"
        "Тебя уже сравнивают с будущими Йонко."
    ),

    200: (
        "images/ach_200.jpg",
        "⚔️ Ты стал кошмаром для флота.\n"
        "💰 Награда за голову: 1 965 000 000 белли.\n"
        "Даже в столице Мирового Правительства знают твоё имя."
    ),

    300: (
        "images/ach_300.jpg",
        "🏴‍☠️ Твой флаг узнают в каждом порту.\n"
        "💰 Награда за голову: 3 000 000 000 белли.\n"
        "Ты официально признан одним из Йонко."
    ),

    500: (
        "images/ach_500.jpg",
        "🐉 Ты стоишь в шаге от вершины мира.\n"
        "💰 Награда за голову: 4 048 900 000 белли.\n"
        "Тебя считают главным претендентом на звание Короля Пиратов."
    ),

    1000: (
        "images/ach_1000.jpg",
        "👑 Ты — Король Пиратов.\n"
        "💰 Награда за голову: 5 564 800 000 белли.\n"
        "О тебе слагают легенды даже в Мари Джоа."
    ),

    2000: (
        "images/ach_2000.jpg",
        "🌌 Ты вышел за пределы легенд.\n"
        "💰 Награда за голову: скрыта Мировым Правительством.\n"
        "Твоё имя запрещено произносить даже в столице власти."
    ),
}
ACHIEVEMENT_THRESHOLDS = sorted(ACHIEVEMENTS.keys())

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: Dict[int, int] = {}
LAST_MESSAGE_TYPE: Dict[int, str] = {}
SEARCH_MODE: Dict[int, bool] = {}

# user_id -> {slug: ep}
USER_PROGRESS: Dict[int, Dict[str, int]] = {}

# user_id -> deque(slug) maxlen=20
USER_CONTINUE: Dict[int, deque] = {}

# user_id -> set(slug)
USER_FAVORITES: Dict[int, set] = {}

# user_id -> set(slug)
USER_WATCHED_TITLES: Dict[int, set] = {}

# user_id -> {slug: track_name}
CURRENT_TRACK: Dict[int, Dict[str, str]] = {}

# slug -> anime data
ANIME: Dict[str, dict] = {}

# remember if current show_episode was triggered by random (so we show random button)
RANDOM_MODE_FLAG: Dict[int, bool] = {}

# ===============================
# HELPERS: load/save
# ===============================
def load_anime() -> None:
    global ANIME
    if not os.path.exists(ANIME_JSON_PATH):
        ANIME = {}
        return
    try:
        with open(ANIME_JSON_PATH, "r", encoding="utf-8") as f:
            ANIME = json.load(f)
        print("Loaded anime.json, items:", len(ANIME))
    except Exception as e:
        print("Failed to load anime.json:", e)
        ANIME = {}

def save_anime() -> None:
    try:
        with open(ANIME_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(ANIME, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save anime.json:", e)

def load_users() -> None:
    global USER_PROGRESS, USER_CONTINUE, USER_FAVORITES, USER_WATCHED_TITLES, CURRENT_TRACK
    if not os.path.exists(USERS_JSON_PATH):
        USER_PROGRESS = {}
        USER_CONTINUE = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        CURRENT_TRACK = {}
        return
    try:
        with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        USER_PROGRESS = {int(k): v for k, v in data.get("progress", {}).items()}
        USER_CONTINUE = {}
        for k, lst in data.get("continue", {}).items():
            try:
                uid = int(k)
                USER_CONTINUE[uid] = deque(lst, maxlen=20)
            except Exception:
                pass
        USER_FAVORITES = {int(k): set(v) for k, v in data.get("favorites", {}).items()}
        USER_WATCHED_TITLES = {int(k): set(v) for k, v in data.get("watched_titles", {}).items()}
        CURRENT_TRACK = {int(k): v for k, v in data.get("current_track", {}).items()}
        print("Loaded users.json")
    except Exception as e:
        print("Failed to load users.json:", e)
        USER_PROGRESS = {}
        USER_CONTINUE = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        CURRENT_TRACK = {}

def save_users() -> None:
    try:
        data = {
            "progress": {str(k): v for k, v in USER_PROGRESS.items()},
            "continue": {str(k): list(v) for k, v in USER_CONTINUE.items()},
            "favorites": {str(k): list(v) for k, v in USER_FAVORITES.items()},
            "watched_titles": {str(k): list(v) for k, v in USER_WATCHED_TITLES.items()},
            "current_track": {str(k): v for k, v in CURRENT_TRACK.items()},
        }
        with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save users.json:", e)

# ===============================
# UTILS: achievements
# ===============================
def get_achievement_for_count(count: int) -> Optional[tuple[str, str]]:
    if count < 1:
        return None
    chosen_threshold = None
    for th in ACHIEVEMENT_THRESHOLDS:
        if count >= th:
            chosen_threshold = th
        else:
            break
    if chosen_threshold is None:
        return None
    return ACHIEVEMENTS[chosen_threshold]

# ===============================
# PARSER подписи (как у тебя)
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
        if key in ("slug", "title", "ep", "genres", "skip", "ozv", "status"):
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
    status = data.get("status", "ongoing").lower()
    if status not in ("ongoing", "finish", "finished", "completed"):
        status = "ongoing"
    if status in ("finished", "completed"):
        status = "finish"
    return {
        "slug": data["slug"],
        "title": data["title"],
        "ep": ep_num,
        "genres": genres_list,
        "skip": data.get("skip"),
        "ozv": data.get("ozv"),
        "status": status,
    }

# ===============================
# ADD/UPDATE anime from source chat
# ===============================
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
            "[status: ongoing/finish]\n"
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
    status = meta["status"]
    file_id = msg.video.file_id

    if slug not in ANIME:
        ANIME[slug] = {"title": title, "genres": genres, "status": status, "episodes": {}}
    else:
        ANIME[slug]["title"] = title
        if genres:
            ANIME[slug]["genres"] = genres
        ANIME[slug]["status"] = status

    ANIME[slug].setdefault("episodes", {})
    ep_obj = ANIME[slug]["episodes"].setdefault(str(ep), {"tracks": {}})
    tracks = ep_obj.setdefault("tracks", {})
    tracks[ozv] = {"source": file_id, "skip": skip}

    save_anime()
    return f"✅ Обновлено: {title} (slug: {slug}), серия {ep}, статус: {status}, озвучка: {ozv}"

# ===============================
# UI BUILDERS (в духе твоего кода)
# ===============================
def build_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📚 Каталог", callback_data="catalog"),
         InlineKeyboardButton("🎲 Случайное", callback_data="random")],
        [InlineKeyboardButton("▶ Продолжить", callback_data="continue:0")],
        [InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("💖 Избранное", callback_data="favorites"),
         InlineKeyboardButton("👁 Просмотренное", callback_data="watched:0")],
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

def build_anime_by_genre_keyboard(genre: str, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    items = []
    for slug, anime in ANIME.items():
        if genre in anime.get("genres", []):
            items.append((slug, anime))
    items.sort(key=lambda x: x[1].get("title", "").lower())
    keyboard = []
    if not items:
        keyboard.append([InlineKeyboardButton("Ничего не найдено", callback_data="catalog")])
    else:
        total = len(items)
        total_pages = (total + per_page - 1) // per_page
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1
        start = page * per_page
        end = start + per_page
        page_items = items[start:end]
        for slug, anime in page_items:
            title = anime.get("title", slug)
            status = anime.get("status", "ongoing")
            if status == "ongoing":
                title = f"{title} [Онг.]"
            keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"genre_page:{genre}:{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"genre_page:{genre}:{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("⬅️ Жанры", callback_data="catalog")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)

def build_ongoings_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for slug, anime in ANIME.items():
        if anime.get("status", "ongoing") == "ongoing":
            title = anime["title"] + " [Онг.]"
            rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows.append([InlineKeyboardButton("Нет онгоингов", callback_data="menu")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_tracks_keyboard(slug: str, ep: int, current_track: Optional[str]) -> List[List[InlineKeyboardButton]]:
    anime = ANIME.get(slug)
    if not anime:
        return []
    ep_obj = anime["episodes"].get(str(ep))
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
        safe_tname = tname.replace(":", "__colon__")
        rows.append([InlineKeyboardButton(btn_text, callback_data=f"track:{slug}:{ep}:{safe_tname}")])
    return rows

def build_episode_keyboard(slug: str, ep: int, chat_id: int, show_random: bool, current_track: Optional[str]) -> InlineKeyboardMarkup:
    episodes = ANIME[slug]["episodes"]
    user_tracks = CURRENT_TRACK.get(chat_id, {})
    stored_track = user_tracks.get(slug)
    if stored_track:
        current_track = stored_track
    has_prev = str(ep - 1) in episodes
    has_next_same_track = False
    has_next_other_track = False

    # определяем наличие следующей серии в той же или другой озвучке
    if str(ep + 1) in episodes:
        next_tracks = episodes[str(ep + 1)].get("tracks", {})
        if current_track and current_track in next_tracks:
            has_next_same_track = True
        elif next_tracks:
            has_next_other_track = True

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"prev:{slug}:{ep}"))
    if has_next_same_track:
        nav.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"next:{slug}:{ep}"))
    elif has_next_other_track:
        nav.append(InlineKeyboardButton("Следующая (другая озвучка) ▶️", callback_data=f"next_other:{slug}:{ep}"))

    fav_set = USER_FAVORITES.get(chat_id, set())
    if slug in fav_set:
        fav_button = InlineKeyboardButton("💔 Убрать из избранного", callback_data=f"fav_remove:{slug}")
    else:
        fav_button = InlineKeyboardButton("💖 В избранное", callback_data=f"fav_add:{slug}")

    watched_titles = USER_WATCHED_TITLES.get(chat_id, set())
    if slug in watched_titles:
        watched_button = InlineKeyboardButton("👁 Убрать тайтл из просмотренного", callback_data=f"unwatch_title:{slug}")
    else:
        watched_button = InlineKeyboardButton("👁 Тайтл просмотрен", callback_data=f"watch_title:{slug}")

    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}")],
        [fav_button],
        [watched_button],
    ]

    track_rows = build_tracks_keyboard(slug, ep, current_track)
    rows.extend(track_rows)

    if nav:
        rows.append(nav)

    # Если текущ показ вызван рандомом — покажем кнопку рандома чтобы можно было нажать ещё раз
    if show_random:
        rows.append([InlineKeyboardButton("🎲 Случайное", callback_data="random")])

    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_episode_list_keyboard(slug: str) -> InlineKeyboardMarkup:
    eps = sorted([int(k) for k in ANIME[slug]["episodes"].keys()])
    rows = []
    row = []
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
        title = anime["title"]
        status = anime.get("status", "ongoing")
        if status == "ongoing":
            title = f"{title} [Онг.]"
        keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not keyboard:
        keyboard.append([InlineKeyboardButton("Пока нет аниме", callback_data="menu")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)

def build_favorites_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    favs = USER_FAVORITES.get(chat_id, set())
    sorted_slugs = sorted(list(favs), key=lambda s: ANIME.get(s, {}).get("title", s).lower())
    rows = []
    for slug in sorted_slugs:
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing":
            title = f"{title} [Онг.]"
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows = [[InlineKeyboardButton("Пусто", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_watched_titles_keyboard(chat_id: int, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    watched_titles = USER_WATCHED_TITLES.get(chat_id, set())
    watched_list = sorted(list(watched_titles), key=lambda s: ANIME.get(s, {}).get("title", s).lower())
    keyboard = []
    if not watched_list:
        keyboard.append([InlineKeyboardButton("Пусто", callback_data="menu")])
        keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
        return InlineKeyboardMarkup(keyboard)
    total = len(watched_list)
    total_pages = (total + per_page - 1) // per_page
    if page < 0: page = 0
    if page >= total_pages: page = total_pages - 1
    start = page * per_page; end = start + per_page
    page_slugs = watched_list[start:end]
    for slug in page_slugs:
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing": title = f"{title} [Онг.]"
        keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"watched:{page-1}"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"watched:{page+1}"))
    if nav_row: keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)

def build_continue_keyboard(chat_id: int, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    user_prog = list(USER_CONTINUE.get(chat_id, deque()))
    rows = []
    if not user_prog:
        rows.append([InlineKeyboardButton("Пока нечего продолжать", callback_data="menu")])
        rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
        return InlineKeyboardMarkup(rows)
    total = len(user_prog)
    total_pages = (total + per_page - 1) // per_page
    if page < 0: page = 0
    if page >= total_pages: page = total_pages - 1
    start = page * per_page; end = start + per_page
    page_items = user_prog[start:end]
    for slug in page_items:
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing": title = f"{title} [Онг.]"
        rows.append([InlineKeyboardButton(f"{title} — с {USER_PROGRESS.get(chat_id, {}).get(slug, 1)} серии", callback_data=f"cont:{slug}")])
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"continue:{page-1}"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"continue:{page+1}"))
    if nav_row: rows.append(nav_row)
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_continue_item_keyboard(chat_id: int, slug: str) -> InlineKeyboardMarkup:
    ep = USER_PROGRESS.get(chat_id, {}).get(slug)
    anime = ANIME.get(slug, {})
    title = anime.get("title", slug)
    status = anime.get("status", "ongoing")
    if status == "ongoing": title = f"{title} [Онг.]"
    rows = []
    if ep:
        rows.append([InlineKeyboardButton(f"▶ Продолжить «{title}» с {ep} серии", callback_data=f"cont_play:{slug}")])
    rows.append([InlineKeyboardButton(f"✖ Убрать «{title}» из продолжения", callback_data=f"cont_remove:{slug}")])
    rows.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data="continue_list")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_search_results_keyboard(matches: list) -> InlineKeyboardMarkup:
    matches_sorted = sorted(matches, key=lambda s: ANIME.get(s, {}).get("title", s).lower())
    rows = []
    for slug in matches_sorted:
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing": title = f"{title} [Онг.]"
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows: rows = [[InlineKeyboardButton("Ничего не найдено", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

# ===============================
# HELPERS: single-message logic
# ===============================
async def send_or_edit_photo(chat_id: int, context: ContextTypes.DEFAULT_TYPE, photo_path: Optional[str], caption: str, reply_markup: InlineKeyboardMarkup):
    use_path = None
    if photo_path and os.path.exists(photo_path):
        use_path = photo_path
    elif WELCOME_PHOTO and os.path.exists(WELCOME_PHOTO):
        use_path = WELCOME_PHOTO
    msg_id = LAST_MESSAGE.get(chat_id)
    if not use_path:
        if msg_id:
            try:
                await context.bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=caption, reply_markup=reply_markup)
                LAST_MESSAGE_TYPE[chat_id] = "text"
                return msg_id
            except Exception:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
        sent = await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup)
        LAST_MESSAGE[chat_id] = sent.message_id
        LAST_MESSAGE_TYPE[chat_id] = "text"
        return sent.message_id
    if msg_id:
        try:
            with open(use_path, "rb") as ph:
                await context.bot.edit_message_media(media=InputMediaPhoto(media=ph, caption=caption), chat_id=chat_id, message_id=msg_id)
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
            LAST_MESSAGE_TYPE[chat_id] = "photo"
            return msg_id
        except Exception:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    with open(use_path, "rb") as ph:
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
        return await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, reply_markup or build_main_menu_keyboard(chat_id))

# ===============================
# SHOW SCREENS
# ===============================
async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Приятного просмотра ✨\nВсе управление через кнопки ниже."
    kb = build_main_menu_keyboard(chat_id)
    await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, kb)
    SEARCH_MODE[chat_id] = False
    RANDOM_MODE_FLAG[chat_id] = False

async def show_genres(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Выбери жанр:"
    kb = build_genre_keyboard()
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False
    RANDOM_MODE_FLAG[chat_id] = False

async def show_anime_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Список аниме:"
    kb = build_anime_menu(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False
    RANDOM_MODE_FLAG[chat_id] = False

async def show_anime_by_genre(chat_id: int, context: ContextTypes.DEFAULT_TYPE, genre: str, page: int = 0):
    caption = f"Жанр: {genre.capitalize()}\nВыбери аниме:"
    kb = build_anime_by_genre_keyboard(genre, page=page)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False
    RANDOM_MODE_FLAG[chat_id] = False

async def show_ongoings(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Онгоинги (ещё выходят):"
    kb = build_ongoings_keyboard()
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False
    RANDOM_MODE_FLAG[chat_id] = False

def _pick_track_for_episode(slug: str, ep: int, chat_id: int, track_name: Optional[str]):
    anime = ANIME.get(slug)
    if not anime:
        return None, None
    ep_obj = anime["episodes"].get(str(ep))
    if not ep_obj:
        return None, None
    tracks = ep_obj.get("tracks", {})
    if not tracks:
        return None, None
    if track_name and track_name in tracks:
        return track_name, tracks[track_name]
    user_tracks = CURRENT_TRACK.get(chat_id, {})
    stored_track = user_tracks.get(slug)
    if stored_track and stored_track in tracks:
        return stored_track, tracks[stored_track]
    first_name = next(iter(tracks.keys()))
    return first_name, tracks[first_name]

async def show_episode(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int, track_name: Optional[str] = None, show_random_button: bool = False):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    if str(ep) not in anime["episodes"]:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return

    chosen_track_name, track = _pick_track_for_episode(slug, ep, chat_id, track_name)
    if not track:
        await edit_caption_only(chat_id, context, "Нет доступных дорожек для этой серии.", build_main_menu_keyboard(chat_id))
        return

    # запоминаем выбранную озвучку
    CURRENT_TRACK.setdefault(chat_id, {})[slug] = chosen_track_name

    source = track.get("source")
    skip = track.get("skip")

    title = anime["title"]
    status = anime.get("status", "ongoing")
    status_label = "Онгоинг" if status == "ongoing" else "Завершён"
    caption_lines = [f"{title} ({status_label})\nСерия {ep}"]
    if chosen_track_name:
        label = chosen_track_name if chosen_track_name != "default" else "Без названия"
        caption_lines.append(f"Озвучка: {label}")
    if skip:
        caption_lines.append(f"⏩ Пропустить опенинг: {skip}")
    caption = "\n".join(caption_lines)

    kb = build_episode_keyboard(slug, ep, chat_id, show_random_button, chosen_track_name)
    # если source похож на file_id (т.е. телеграм) — передаем как file_id, иначе как путь
    await send_or_edit_video(chat_id, context, source, caption, kb)

    # сохраняем прогресс (после показа)
    USER_PROGRESS.setdefault(chat_id, {})
    USER_PROGRESS[chat_id][slug] = ep
    save_users()

    # сохраняем флаг случайного режима (чтобы кнопка рандома отображалась корректно)
    RANDOM_MODE_FLAG[chat_id] = show_random_button

# ===============================
# CONTINUE: только когда пользователь нажал NEXT или cont_play
# ===============================
def add_slug_to_continue(uid: int, slug: str):
    if uid not in USER_CONTINUE:
        USER_CONTINUE[uid] = deque(maxlen=20)
    dq = USER_CONTINUE[uid]
    # удаляем дубликат если есть (чтобы поместить в конец)
    if slug in dq:
        dq.remove(slug)
    dq.append(slug)
    # deque с maxlen сам отрежет самый старый если превышен
    save_users()

def remove_slug_from_continue(uid: int, slug: str):
    if uid in USER_CONTINUE and slug in USER_CONTINUE[uid]:
        USER_CONTINUE[uid].remove(slug)
        save_users()

# ===============================
# CALLBACK HANDLER
# ===============================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    # MENU
    if data == "menu":
        await show_main_menu(chat_id, context); return

    if data == "catalog":
        await show_genres(chat_id, context); return

    if data == "random":
        # выбираем случайный тайтл и показываем первую серию (и показываем кнопку "случайное" на экране)
        if not ANIME:
            await edit_caption_only(chat_id, context, "Пока нет доступных аниме 😔", build_main_menu_keyboard(chat_id))
            return
        slug = random.choice(list(ANIME.keys()))
        eps = sorted([int(k) for k in ANIME[slug]["episodes"].keys()]) if ANIME[slug].get("episodes") else []
        if not eps:
            await edit_caption_only(chat_id, context, "Нет серий у этого тайтла 😔", build_main_menu_keyboard(chat_id))
            return
        first_ep = eps[0]
        # пометим, что показ пришёл от рандома — чтобы показать кнопку "случайное" на экране
        await show_episode(chat_id, context, slug, first_ep, show_random_button=True)
        return

    if data == "ongoings":
        await show_ongoings(chat_id, context); return

    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]; await show_anime_by_genre(chat_id, context, genre, page=0); return

    if data.startswith("genre_page:"):
        _, genre, page_str = data.split(":", 2)
        try: page = int(page_str)
        except ValueError: page = 0
        await show_anime_by_genre(chat_id, context, genre, page=page); return

    if data.startswith("anime:"):
        slug = data.split(":", 1)[1]
        anime = ANIME.get(slug)
        if not anime or not anime.get("episodes"):
            await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id)); return
        first_ep = sorted([int(k) for k in anime["episodes"].keys()])[0]
        # показываем без кнопки "случайное"
        await show_episode(chat_id, context, slug, first_ep, show_random_button=False); return

    if data.startswith("list:"):
        slug = data.split(":", 1)[1]; await edit_caption_only(chat_id, context, f"Список серий для {ANIME[slug]['title']}", build_episode_list_keyboard(slug)); return

    if data.startswith("ep:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        # показываем без рандома
        await show_episode(chat_id, context, slug, ep, show_random_button=False); return

    # NEXT: пользователь нажал "Следующая"
    if data.startswith("next:"):
        _, slug, ep_str = data.split(":", 2)
        current = int(ep_str)
        next_ep = current + 1
        anime = ANIME.get(slug)
        if not anime:
            await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id)); return
        episodes = anime.get("episodes", {})
        # если следующей серии нет
        if str(next_ep) not in episodes:
            # если тайтл завершён — убираем из continue и добавляем в watched
            if anime.get("status", "ongoing") == "finish":
                remove_slug_from_continue(chat_id, slug)
                USER_WATCHED_TITLES.setdefault(chat_id, set()).add(slug)
                save_users()
                await edit_caption_only(chat_id, context, "Это была последняя серия — тайтл помечен как просмотренный.", build_main_menu_keyboard(chat_id))
                return
            else:
                # ongoing, просто уведомим
                await query.answer("Следующей серии пока нет (ожидается).", show_alert=True)
                return
        # есть следующая серия — показываем её и добавляем в continue
        some_track_name = None
        # выбираем трек если есть
        next_tracks = episodes[str(next_ep)].get("tracks", {})
        if next_tracks:
            some_track_name = next(iter(next_tracks.keys()))
        # показываем серию (после показа add_to_continue ниже)
        await show_episode(chat_id, context, slug, next_ep, track_name=some_track_name, show_random_button=RANDOM_MODE_FLAG.get(chat_id, False))
        # после показа — добавим тайтл в continue (только по нажатию next)
        add_slug_to_continue(chat_id, slug)
        return

    # next_other: следующая только в другой озвучке
    if data.startswith("next_other:"):
        _, slug, ep_str = data.split(":", 2)
        current = int(ep_str)
        next_ep = current + 1
        anime = ANIME.get(slug)
        if not anime:
            await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id)); return
        episodes = anime.get("episodes", {})
        if str(next_ep) not in episodes:
            await edit_caption_only(chat_id, context, "Следующей серии нет.", build_main_menu_keyboard(chat_id)); return
        tracks = episodes[str(next_ep)].get("tracks", {})
        if not tracks:
            await edit_caption_only(chat_id, context, "У следующей серии нет доступных дорожек.", build_main_menu_keyboard(chat_id)); return
        some_track_name = next(iter(tracks.keys()))
        await show_episode(chat_id, context, slug, next_ep, track_name=some_track_name, show_random_button=RANDOM_MODE_FLAG.get(chat_id, False))
        add_slug_to_continue(chat_id, slug)
        return

    if data.startswith("prev:"):
        _, slug, ep_str = data.split(":", 2)
        current = int(ep_str)
        await show_episode(chat_id, context, slug, current - 1, show_random_button=False); return

    if data.startswith("fav_add:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).add(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            ep = sorted([int(k) for k in anime.get("episodes", {}).keys()])[0] if anime and anime.get("episodes") else 1
        await show_episode(chat_id, context, slug, ep, show_random_button=False); return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            ep = sorted([int(k) for k in anime.get("episodes", {}).keys()])[0] if anime and anime.get("episodes") else 1
        await show_episode(chat_id, context, slug, ep, show_random_button=False); return

    if data.startswith("watch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).add(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            ep = sorted([int(k) for k in anime.get("episodes", {}).keys()])[0] if anime and anime.get("episodes") else 1
        # НЕ трогаем continue здесь (как ты просил)
        await show_episode(chat_id, context, slug, ep, show_random_button=False); return

    if data.startswith("unwatch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).discard(slug); save_users()
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            ep = sorted([int(k) for k in anime.get("episodes", {}).keys()])[0] if anime and anime.get("episodes") else 1
        await show_episode(chat_id, context, slug, ep, show_random_button=False); return

    if data.startswith("track:"):
        _, slug, ep_str, safe_tname = data.split(":", 3)
        ep = int(ep_str)
        track_name = safe_tname.replace("__colon__", ":")
        # смена дорожки — показываем серию с новой дорожкой (не меняя логику continue)
        await show_episode(chat_id, context, slug, ep, track_name=track_name, show_random_button=False); return

    # CONTINUE screens
    if data == "continue":
        await edit_caption_only(chat_id, context, "Тайтлы, которые ты сейчас смотришь:", build_continue_keyboard(chat_id, page=0)); return

    if data.startswith("continue:"):
        _, page_str = data.split(":", 1)
        try: page = int(page_str)
        except: page = 0
        await edit_caption_only(chat_id, context, "Тайтлы, которые ты сейчас смотришь:", build_continue_keyboard(chat_id, page=page)); return

    if data == "continue_list":
        await edit_caption_only(chat_id, context, "Тайтлы, которые ты сейчас смотришь:", build_continue_keyboard(chat_id, page=0)); return

    if data.startswith("cont:"):
        slug = data.split(":", 1)[1]
        await edit_caption_only(chat_id, context, "Что сделать с этим тайтлом?", build_continue_item_keyboard(chat_id, slug)); return

    if data.startswith("cont_play:"):
        slug = data.split(":", 1)[1]
        ep = USER_PROGRESS.get(chat_id, {}).get(slug)
        if not ep:
            await query.answer("Нет сохранённого прогресса для этого тайтла.", show_alert=True)
            await edit_caption_only(chat_id, context, "Тайтлы, которые ты сейчас смотришь:", build_continue_keyboard(chat_id, page=0))
            return
        # При нажатии cont_play — считаем это как продолжение (добавляем в continue)
        await show_episode(chat_id, context, slug, ep, show_random_button=False)
        add_slug_to_continue(chat_id, slug)
        return

    if data.startswith("cont_remove:"):
        slug = data.split(":", 1)[1]
        if chat_id in USER_CONTINUE and slug in USER_CONTINUE[chat_id]:
            USER_CONTINUE[chat_id].remove(slug)
            if not USER_CONTINUE[chat_id]:
                del USER_CONTINUE[chat_id]
            save_users()
        await query.answer("Убрано из продолжения.")
        await edit_caption_only(chat_id, context, "Тайтлы, которые ты сейчас смотришь:", build_continue_keyboard(chat_id, page=0))
        return

    # SEARCH
    if data == "search":
        SEARCH_MODE[chat_id] = True
        caption = "🔍 Введи название аниме сообщением (или его часть).\n(Текст потом удалю, реагирую только на кнопки)"
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id))
        return

    # favorites/watched pagination
    if data == "favorites":
        await edit_caption_only(chat_id, context, "Избранное:", build_favorites_keyboard(chat_id))
        return

    if data == "watched":
        await edit_caption_only(chat_id, context, "Просмотренные:", build_watched_titles_keyboard(chat_id, page=0))
        return

    if data.startswith("watched:"):
        _, page_str = data.split(":", 1)
        try: page = int(page_str)
        except: page = 0
        await edit_caption_only(chat_id, context, "Просмотренные:", build_watched_titles_keyboard(chat_id, page=page))
        return

# ===============================
# TEXT (SEARCH) — с удалением
# ===============================
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    if not SEARCH_MODE.get(chat_id, False):
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    q = text.lower()
    matches = []
    for slug, anime in ANIME.items():
        if q in anime.get("title", "").lower():
            matches.append(slug)

    try:
        await update.message.delete()
    except Exception:
        pass

    if not matches:
        await edit_caption_only(chat_id, context, "😔 Ничего не нашёл по этому названию.\nПопробуй другое слово.\n(Я реагирую только на кнопки)", build_main_menu_keyboard(chat_id))
        SEARCH_MODE[chat_id] = False
        return

    if len(matches) == 1:
        found_slug = matches[0]
        anime = ANIME.get(found_slug)
        if not anime or not anime.get("episodes"):
            await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id))
            SEARCH_MODE[chat_id] = False
            return
        first_ep = sorted([int(k) for k in anime["episodes"].keys()])[0]
        await show_episode(chat_id, context, found_slug, first_ep, show_random_button=False)
        SEARCH_MODE[chat_id] = False
        return

    kb = build_search_results_keyboard(matches)
    await edit_caption_only(chat_id, context, f"🔍 Нашёл несколько тайтлов по запросу «{text}»:\nВыбери нужный:", kb)
    SEARCH_MODE[chat_id] = False

# ===============================
# EXTRA CLEANUP
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
# ADMIN / UTIL COMMANDS
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

async def cmd_dump_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    if chat_id not in (ADMIN_ID, ADMIN2_ID):
        await msg.reply_text("⛔ Эта команда только для админов."); return
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

async def cmd_clear_slug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    if chat_id not in (ADMIN_ID, ADMIN2_ID):
        await msg.reply_text("⛔ Эта команда только для админов."); return
    if not context.args:
        await msg.reply_text("❗ Использование: /clear_slug <slug>"); return
    slug = context.args[0].strip()
    if slug not in ANIME:
        await msg.reply_text(f"⚠️ Тайтл с slug '{slug}' не найден."); return
    del ANIME[slug]
    # чистим у пользователей
    for uid in list(USER_PROGRESS.keys()):
        if slug in USER_PROGRESS[uid]:
            del USER_PROGRESS[uid][slug]
            if not USER_PROGRESS[uid]: del USER_PROGRESS[uid]
    for uid in list(USER_FAVORITES.keys()):
        USER_FAVORITES[uid].discard(slug)
    for uid in list(USER_WATCHED_TITLES.keys()):
        USER_WATCHED_TITLES[uid].discard(slug)
    for uid in list(CURRENT_TRACK.keys()):
        if slug in CURRENT_TRACK[uid]:
            del CURRENT_TRACK[uid][slug]
            if not CURRENT_TRACK[uid]: del CURRENT_TRACK[uid]
    for uid in list(USER_CONTINUE.keys()):
        if slug in USER_CONTINUE[uid]:
            USER_CONTINUE[uid].remove(slug)
            if not USER_CONTINUE[uid]: del USER_CONTINUE[uid]
    save_anime(); save_users()
    await msg.reply_text(f"✅ Тайтл '{slug}' и все связанные данные удалены.")

async def cmd_clear_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    chat_id = update.effective_chat.id
    if chat_id not in (ADMIN_ID, ADMIN2_ID):
        await msg.reply_text("⛔ Эта команда только для админов."); return
    if len(context.args) < 2:
        await msg.reply_text("❗ Использование: /clear_ep <slug> <ep>"); return
    slug = context.args[0].strip()
    ep_str = context.args[1].strip()
    try:
        ep = int(ep_str)
    except ValueError:
        await msg.reply_text("❌ Номер серии должен быть числом."); return
    anime = ANIME.get(slug)
    if not anime:
        await msg.reply_text(f"⚠️ Тайтл с slug '{slug}' не найден."); return
    episodes = anime.get("episodes", {})
    if str(ep) not in episodes:
        await msg.reply_text(f"⚠️ У тайтла '{slug}' нет серии {ep}."); return
    del episodes[str(ep)]
    if not episodes:
        del ANIME[slug]
        # чистим у всех пользователей
        for uid in list(USER_PROGRESS.keys()):
            if slug in USER_PROGRESS[uid]:
                del USER_PROGRESS[uid][slug]; 
                if not USER_PROGRESS[uid]: del USER_PROGRESS[uid]
        for uid in list(USER_FAVORITES.keys()):
            USER_FAVORITES[uid].discard(slug)
        for uid in list(USER_WATCHED_TITLES.keys()):
            USER_WATCHED_TITLES[uid].discard(slug)
        for uid in list(CURRENT_TRACK.keys()):
            if slug in CURRENT_TRACK[uid]:
                del CURRENT_TRACK[uid][slug]
                if not CURRENT_TRACK[uid]: del CURRENT_TRACK[uid]
        for uid in list(USER_CONTINUE.keys()):
            if slug in USER_CONTINUE[uid]:
                USER_CONTINUE[uid].remove(slug)
                if not USER_CONTINUE[uid]: del USER_CONTINUE[uid]
        save_anime(); save_users()
        await msg.reply_text(f"✅ Серия {ep} удалена. Тайтл '{slug}' полностью удалён.")
        return
    ANIME[slug]["episodes"] = episodes
    save_anime()
    await msg.reply_text(f"✅ У тайтла '{slug}' удалена серия {ep}.")

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

# debug get file_id
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
    token = BOT_TOKEN
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CommandHandler("fix", cmd_fix))
    app.add_handler(CommandHandler("dump_all", cmd_dump_all))
    app.add_handler(CommandHandler("clear_slug", cmd_clear_slug))
    app.add_handler(CommandHandler("clear_ep", cmd_clear_ep))
    app.add_handler(CallbackQueryHandler(handle_callback))
    # search text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Chat(SOURCE_CHAT_ID), handle_user_text))
    # source chat
    app.add_handler(MessageHandler(filters.Chat(SOURCE_CHAT_ID) & filters.VIDEO, handle_source_chat_message))
    # debug videos
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.Chat(SOURCE_CHAT_ID), debug_video))
    # cleanup
    app.add_handler(MessageHandler(filters.ALL, cleanup_non_command_messages))
    print("BOT STARTED...")
    app.run_polling()

if __name__ == "__main__":
    main()
