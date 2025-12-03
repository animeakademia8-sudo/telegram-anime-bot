# bot.py
import os
import json
import random
from typing import Optional
from collections import OrderedDict

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
ADMIN2_ID = 8505295670  # второй админ

# ===============================
# ACHIEVEMENTS (просмотренные тайтлы)
# ===============================

ACHIEVEMENTS = {
    1: ("images/ach_1.jpg", "💀 Вы сделали первый шаг в море аниме.\n💰 Награда за вашу голову: 1 000 белли.\nМорская стража пока вас игнорирует."),
    5: ("images/ach_5.jpg", "🏴‍☠️ Ваше имя впервые замечено на ветрах Гранд Лайн.\n💰 Награда за вашу голову: 5 000 000 белли.\nВ тавернах начинают перешёптываться о новом пирате."),
    10: ("images/ach_10.jpg", "💣 Вы становитесь серьёзной силой.\n💰 Награда за вашу голову: 16 000 000 белли.\nМаринфорд включил вас в список наблюдения."),
    25: ("images/ach_25.jpg", "🔥 Вы — капитан собственной команды.\n💰 Награда за вашу голову: 77 000 000 белли.\nВаш корабль уже вызывает тревогу у патрулей."),
    50: ("images/ach_50.jpg", "💥 Ваше имя гремит по всем морям.\n💰 Награда за вашу голову: 470 000 000 белли.\nВы больше не просто пират — вы угроза."),
    100: ("images/ach_100.jpg", "👑 Ваше влияние взлетает до небес.\n💰 Награда за вашу голову: 1 000 000 000 белли.\nО вас говорят как о будущем Йонко."),
    200: ("images/ach_200.jpg", "⚔️ Ваше имя шепчут с трепетом.\n💰 Награда за вашу голову: 1 965 000 000 белли.\nДаже сильнейшие начинают задумываться о союзе… или бегстве."),
    300: ("images/ach_300.jpg", "🏴‍☠️ Ваш флаг узнают в каждом порту.\n💰 Награда за вашу голову: 3 000 000 000 белли.\nВы официально стали одним из Йонко — властелином морей."),
    500: ("images/ach_500.jpg", "🐉 Ваш путь вымощен победами и тайтлами.\n💰 Награда за вашу голову: 4 048 900 000 белли.\nВы стоите в шаге от титула Короля Пиратов."),
    1000: ("images/ach_1000.jpg", "👑 Вы — Король Пиратов.\n💰 Награда за вашу голову: 5 564 800 000 белли.\nМир склоняется перед тем, кто достиг вершины."),
    2000: ("images/ach_2000.jpg", "🌌 Вы вышли за пределы легенд.\n💰 Награда за вашу голову: ??? белли — сумма скрыта мировым правительством.\nВаше имя запрещено произносить вслух, и даже Йонко рассказывают истории о вас."),
}

ACHIEVEMENT_THRESHOLDS = sorted(ACHIEVEMENTS.keys())

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: dict[int, int] = {}
LAST_MESSAGE_TYPE: dict[int, str] = {}
SEARCH_MODE: dict[int, bool] = {}

# user_id -> OrderedDict(slug -> ep)  --> продолжить (ограничение 20, порядок вставки)
USER_PROGRESS: dict[int, OrderedDict] = {}

# user_id -> set(slug)
USER_FAVORITES: dict[int, set[str]] = {}

# user_id -> set(slug)  # просмотренные
USER_WATCHED_TITLES: dict[int, set[str]] = {}

# user_id -> {slug: track_name}
CURRENT_TRACK: dict[int, dict[str, str]] = {}

# slug -> anime data
ANIME: dict[str, dict] = {}

# last "screen mode" per chat (None / "random" / "genre" / "search")
LAST_SCREEN_MODE: dict[int, Optional[str]] = {}

# limits
CONTINUE_MAX = 20
CONTINUE_PAGE_SIZE = 10

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
            title = anime.get("title", "")
            genres = anime.get("genres", [])
            status = anime.get("status", "ongoing")
            episodes_raw = anime.get("episodes", {})
            episodes: dict[int, dict] = {}
            for ep_str, ep_data in episodes_raw.items():
                try:
                    ep_int = int(ep_str)
                except ValueError:
                    continue
                if isinstance(ep_data, dict) and "tracks" in ep_data:
                    tracks = ep_data.get("tracks", {})
                    norm_tracks = {}
                    for tname, tdata in tracks.items():
                        if isinstance(tdata, dict):
                            source = tdata.get("source")
                            skip = tdata.get("skip")
                        else:
                            source = tdata
                            skip = None
                        if source:
                            norm_tracks[tname] = {"source": source, "skip": skip}
                    if norm_tracks:
                        episodes[ep_int] = {"tracks": norm_tracks}
                else:
                    if not isinstance(ep_data, dict):
                        continue
                    source = ep_data.get("source")
                    if not source:
                        continue
                    skip = ep_data.get("skip")
                    ozv = ep_data.get("ozv") or "default"
                    episodes[ep_int] = {"tracks": {ozv: {"source": source, "skip": skip}}}
            fixed_data[slug] = {"title": title, "genres": genres, "status": status, "episodes": episodes}
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
                tracks = ep_data.get("tracks", {})
                ep_obj["tracks"] = {}
                for tname, tinfo in tracks.items():
                    ep_obj["tracks"][tname] = {"source": tinfo.get("source"), "skip": tinfo.get("skip")}
                eps_json[str(ep_int)] = ep_obj
            data_to_save[slug] = {"title": anime.get("title", ""), "genres": anime.get("genres", []), "status": anime.get("status", "ongoing"), "episodes": eps_json}
        with open(ANIME_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save anime.json:", e)

# ===============================
# JSON SAVE/LOAD: USERS
# ===============================
def load_users() -> None:
    global USER_PROGRESS, USER_FAVORITES, USER_WATCHED_TITLES, CURRENT_TRACK
    if not os.path.exists(USERS_JSON_PATH):
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        CURRENT_TRACK = {}
        return
    try:
        with open(USERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # progress: user_id -> list of [ [slug, ep], ... ] preserving order
        USER_PROGRESS = {}
        for user_id_str, prog_list in data.get("progress", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(prog_list, list):
                od = OrderedDict()
                for pair in prog_list:
                    if isinstance(pair, list) and len(pair) == 2:
                        slug, ep = pair
                        if isinstance(slug, str) and isinstance(ep, int):
                            od[slug] = ep
                if od:
                    USER_PROGRESS[user_id] = od
        # favorites
        USER_FAVORITES = {}
        for user_id_str, fav_list in data.get("favorites", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(fav_list, list):
                USER_FAVORITES[user_id] = set([slug for slug in fav_list if isinstance(slug, str)])
            else:
                USER_FAVORITES[user_id] = set()
        # watched_titles
        USER_WATCHED_TITLES = {}
        for user_id_str, wt_list in data.get("watched_titles", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(wt_list, list):
                USER_WATCHED_TITLES[user_id] = set([slug for slug in wt_list if isinstance(slug, str)])
            else:
                USER_WATCHED_TITLES[user_id] = set()
        # current_track
        CURRENT_TRACK = {}
        for user_id_str, track_map in data.get("current_track", {}).items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if isinstance(track_map, dict):
                res = {}
                for slug, tname in track_map.items():
                    if isinstance(slug, str) and isinstance(tname, str):
                        res[slug] = tname
                if res:
                    CURRENT_TRACK[user_id] = res
        print("Loaded users from users.json")
    except Exception as e:
        print("Failed to load users.json:", e)
        USER_PROGRESS = {}
        USER_FAVORITES = {}
        USER_WATCHED_TITLES = {}
        CURRENT_TRACK = {}

def save_users() -> None:
    try:
        data_to_save = {"progress": {}, "favorites": {}, "watched_titles": {}, "current_track": {}}
        # progress: save as ordered list per user
        for user_id, prog_od in USER_PROGRESS.items():
            if isinstance(prog_od, OrderedDict):
                data_to_save["progress"][str(user_id)] = [[slug, ep] for slug, ep in prog_od.items()]
            elif isinstance(prog_od, dict):
                data_to_save["progress"][str(user_id)] = [[slug, ep] for slug, ep in prog_od.items()]
        # favorites
        for user_id, fav_set in USER_FAVORITES.items():
            data_to_save["favorites"][str(user_id)] = list(fav_set)
        # watched titles
        for user_id, wt_set in USER_WATCHED_TITLES.items():
            data_to_save["watched_titles"][str(user_id)] = list(wt_set)
        # current_track
        for user_id, track_map in CURRENT_TRACK.items():
            data_to_save["current_track"][str(user_id)] = track_map
        with open(USERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to save users.json:", e)

# ===============================
# UTILS: достижения
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
    return {"slug": data["slug"], "title": data["title"], "ep": ep_num, "genres": genres_list, "skip": data.get("skip"), "ozv": data.get("ozv"), "status": status}

def add_or_update_anime_from_message(msg: Message) -> Optional[str]:
    if not msg.video:
        return "❌ В сообщении нет видео."
    meta = parse_caption_to_meta(msg.caption or "")
    if not meta:
        return ("❌ Подпись не в нужном формате. Нужны строки:\n"
                "slug: ...\n"
                "title: ...\n"
                "ep: ...\n"
                "[status: ongoing/finish]\n"
                "[ozv: ...]\n"
                "[skip: ...]\n"
                "[genres: ...]")
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
    ep_obj = ANIME[slug]["episodes"].setdefault(ep, {"tracks": {}})
    tracks = ep_obj.setdefault("tracks", {})
    tracks[ozv] = {"source": file_id, "skip": skip}
    save_anime()
    return f"✅ Обновлено: {title} (slug: {slug}), серия {ep}, статус: {status}, озвучка: {ozv}"

# ===============================
# HELPERS: continue management (ordered + limit)
# ===============================
def _ensure_user_progress_struct(chat_id: int):
    if chat_id not in USER_PROGRESS or not isinstance(USER_PROGRESS[chat_id], OrderedDict):
        USER_PROGRESS[chat_id] = OrderedDict()

def add_to_continue(chat_id: int, slug: str, ep: int):
    """
    Добавляет/обновляет запись в USER_PROGRESS (OrderedDict), перемещая в конец.
    Ограничивает до CONTINUE_MAX — удаляет самый старый элемент.
    """
    _ensure_user_progress_struct(chat_id)
    od: OrderedDict = USER_PROGRESS[chat_id]
    if slug in od:
        # обновляем эпизод и двигаем в конец (как последний)
        od.pop(slug, None)
    od[slug] = ep
    # enforce limit
    while len(od) > CONTINUE_MAX:
        # popitem(last=False) удаляет самый старый
        od.popitem(last=False)
    save_users()

def remove_from_continue(chat_id: int, slug: str):
    if chat_id in USER_PROGRESS and slug in USER_PROGRESS[chat_id]:
        USER_PROGRESS[chat_id].pop(slug, None)
        if not USER_PROGRESS[chat_id]:
            del USER_PROGRESS[chat_id]
        save_users()

def update_continue_entry(chat_id: int, slug: str, ep: int):
    """
    Когда пользователь открывает серию: решим добавлять/удалять из 'продолжить' по правилам:
    - если есть следующая серия (ep+1 in episodes) -> добавляем/обновляем
    - если нет следующей и тайтл status == 'finish' -> удаляем
    - если нет следующей и статус != 'finish' (ongoing) -> добавляем (чтобы продолжение оставалось)
    """
    anime = ANIME.get(slug)
    if not anime:
        return
    episodes = anime.get("episodes", {})
    has_next = (ep + 1) in episodes
    status = anime.get("status", "ongoing")
    if has_next:
        add_to_continue(chat_id, slug, ep)
    else:
        if status == "finish":
            remove_from_continue(chat_id, slug)
        else:
            # ongoing with no next yet — keep in continue
            add_to_continue(chat_id, slug, ep)

# ===============================
# UI BUILDERS
# ===============================
def build_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📚 Каталог", callback_data="catalog"), InlineKeyboardButton("🎲 Случайное", callback_data="random")],
        [InlineKeyboardButton("▶ Онгоинги", callback_data="ongoings"), InlineKeyboardButton("⭐ Продолжить", callback_data="continue")],
        [InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("💖 Избранное", callback_data="favorites"), InlineKeyboardButton("👁 Просмотренное", callback_data="watched:0")],
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
    items: list[tuple[str, dict]] = []
    for slug, anime in ANIME.items():
        if genre in anime.get("genres", []):
            items.append((slug, anime))
    items.sort(key=lambda x: x[1].get("title", "").lower())
    keyboard: list[list[InlineKeyboardButton]] = []
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
        nav_row: list[InlineKeyboardButton] = []
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

def build_tracks_keyboard(slug: str, ep: int, current_track: Optional[str]) -> list[list[InlineKeyboardButton]]:
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
        safe_tname = tname.replace(":", "__colon__")
        rows.append([InlineKeyboardButton(btn_text, callback_data=f"track:{slug}:{ep}:{safe_tname}")])
    return rows

def build_episode_keyboard(slug: str, ep: int, chat_id: int, current_track: Optional[str]) -> InlineKeyboardMarkup:
    episodes = ANIME[slug]["episodes"]
    user_tracks = CURRENT_TRACK.get(chat_id, {})
    stored_track = user_tracks.get(slug)
    if stored_track:
        current_track = stored_track
    has_prev = (ep - 1) in episodes
    # determine next in same/other track
    has_next_same_track = False
    has_next_other_track = False
    # find next episode tracks
    if (ep + 1) in episodes:
        next_tracks = episodes[ep + 1].get("tracks", {})
        if current_track and current_track in next_tracks:
            has_next_same_track = True
        elif next_tracks:
            has_next_other_track = True
    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"prev:{slug}:{ep}"))
    if has_next_same_track:
        nav.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"next:{slug}:{ep}"))
    elif has_next_other_track:
        nav.append(InlineKeyboardButton("Следущая (другая озвучка) ▶️", callback_data=f"next_other:{slug}:{ep}"))
    # Add "random" button if last screen mode for this chat is 'random'
    last_mode = LAST_SCREEN_MODE.get(chat_id)
    if last_mode == "random":
        # add random button next to nav (keeps it visible on episode screen)
        nav.append(InlineKeyboardButton("🎲 Случайное", callback_data="random"))
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
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}")],
        [fav_button],
        [watched_button],
    ]
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
    keyboard: list[list[InlineKeyboardButton]] = []
    if not watched_list:
        keyboard.append([InlineKeyboardButton("Пусто", callback_data="menu")])
        keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
        return InlineKeyboardMarkup(keyboard)
    total = len(watched_list)
    total_pages = (total + per_page - 1) // per_page
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    start = page * per_page
    end = start + per_page
    page_slugs = watched_list[start:end]
    for slug in page_slugs:
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing":
            title = f"{title} [Онг.]"
        keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"watched:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"watched:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)

def build_continue_keyboard(chat_id: int, page: int = 0, per_page: int = CONTINUE_PAGE_SIZE) -> InlineKeyboardMarkup:
    _ensure_user_progress_struct(chat_id)
    od = USER_PROGRESS.get(chat_id, OrderedDict())
    slugs = list(od.keys())
    # show page entries
    total = len(slugs)
    if total == 0:
        rows = [[InlineKeyboardButton("Пока нечего продолжать", callback_data="menu")], [InlineKeyboardButton("🍄 Меню", callback_data="menu")]]
        return InlineKeyboardMarkup(rows)
    total_pages = (total + per_page - 1) // per_page
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    start = page * per_page
    end = start + per_page
    page_slugs = slugs[start:end]
    rows = []
    for slug in page_slugs:
        ep = od.get(slug)
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing":
            title = f"{title} [Онг.]"
        label = f"{title} — с {ep} серии"
        rows.append([InlineKeyboardButton(label, callback_data=f"cont:{slug}")])
    # pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"continue_page:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"continue_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_continue_item_keyboard(chat_id: int, slug: str) -> InlineKeyboardMarkup:
    ep = None
    if chat_id in USER_PROGRESS:
        ep = USER_PROGRESS[chat_id].get(slug)
    anime = ANIME.get(slug, {})
    title = anime.get("title", slug)
    status = anime.get("status", "ongoing")
    if status == "ongoing":
        title = f"{title} [Онг.]"
    rows = []
    if ep:
        rows.append([InlineKeyboardButton(f"▶ Продолжить «{title}» c {ep} серии", callback_data=f"cont_play:{slug}")])
    rows.append([InlineKeyboardButton(f"✖ Убрать «{title}» из продолжения", callback_data=f"cont_remove:{slug}")])
    rows.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data="continue_list")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def build_search_results_keyboard(matches: list[str]) -> InlineKeyboardMarkup:
    matches_sorted = sorted(matches, key=lambda s: ANIME.get(s, {}).get("title", s).lower())
    rows = []
    for slug in matches_sorted:
        anime = ANIME.get(slug, {})
        title = anime.get("title", slug)
        status = anime.get("status", "ongoing")
        if status == "ongoing":
            title = f"{title} [Онг.]"
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows = [[InlineKeyboardButton("Ничего не найдено", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

# ===============================
# HELPERS: single-message logic
# ===============================
async def send_or_edit_photo(chat_id: int, context: ContextTypes.DEFAULT_TYPE, photo_path: str, caption: str, reply_markup: InlineKeyboardMarkup):
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
# SCREENS
# ===============================
async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Приятного просмотра ✨\nВсе управление через кнопки ниже."
    kb = build_main_menu_keyboard(chat_id)
    LAST_SCREEN_MODE[chat_id] = None
    await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_genres(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Выбери жанр:"
    kb = build_genre_keyboard()
    LAST_SCREEN_MODE[chat_id] = None
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_anime_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Список аниме:"
    kb = build_anime_menu(chat_id)
    LAST_SCREEN_MODE[chat_id] = None
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_anime_by_genre(chat_id: int, context: ContextTypes.DEFAULT_TYPE, genre: str, page: int = 0):
    caption = f"Жанр: {genre.capitalize()}\nВыбери аниме:"
    kb = build_anime_by_genre_keyboard(genre, page=page)
    LAST_SCREEN_MODE[chat_id] = None
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_ongoings(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Онгоинги (ещё выходят):"
    kb = build_ongoings_keyboard()
    LAST_SCREEN_MODE[chat_id] = None
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

def _pick_track_for_episode(slug: str, ep: int, chat_id: int, track_name: Optional[str]) -> tuple[Optional[str], Optional[dict]]:
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
    user_tracks = CURRENT_TRACK.get(chat_id, {})
    stored_track = user_tracks.get(slug)
    if stored_track and stored_track in tracks:
        return stored_track, tracks[stored_track]
    first_name = next(iter(tracks.keys()))
    return first_name, tracks[first_name]

async def show_episode(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int, track_name: Optional[str] = None):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    if ep not in anime["episodes"]:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return
    chosen_track_name, track = _pick_track_for_episode(slug, ep, chat_id, track_name)
    if not track:
        await edit_caption_only(chat_id, context, "Нет доступных дорожек для этой серии.", build_main_menu_keyboard(chat_id))
        return
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
    kb = build_episode_keyboard(slug, ep, chat_id, chosen_track_name)
    await send_or_edit_video(chat_id, context, source, caption, kb)
    # update progress + smart continue rules
    _ensure_user_progress_struct(chat_id)
    USER_PROGRESS.setdefault(chat_id, OrderedDict())[slug] = ep
    # ensure ordering: move slug to end
    if slug in USER_PROGRESS[chat_id]:
        USER_PROGRESS[chat_id].pop(slug, None)
    USER_PROGRESS[chat_id][slug] = ep
    # apply smart rules (add / remove according to next episode / status)
    update_continue_entry(chat_id, slug, ep)
    save_users()
    SEARCH_MODE[chat_id] = False

async def show_episode_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    title = anime['title']
    status = anime.get("status", "ongoing")
    status_label = "Онгоинг" if status == "ongoing" else "Завершён"
    caption = f"{title} ({status_label})\nВыбери серию:"
    kb = build_episode_list_keyboard(slug)
    LAST_SCREEN_MODE[chat_id] = None
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_random(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not ANIME:
        await edit_caption_only(chat_id, context, "Пока нет доступных аниме 😔", build_main_menu_keyboard(chat_id))
        return
    # mark that we are in random flow
    LAST_SCREEN_MODE[chat_id] = "random"
    slug = random.choice(list(ANIME.keys()))
    eps = sorted(ANIME[slug]["episodes"].keys())
    if not eps:
        await edit_caption_only(chat_id, context, "Нет серий у этого тайтла 😔", build_main_menu_keyboard(chat_id))
        LAST_SCREEN_MODE[chat_id] = None
        return
    # choose first available episode (or random episode?) -> previous behavior: first episode
    # to emulate earlier behavior, choose FIRST episode
    first_ep = eps[0]
    await show_episode(chat_id, context, slug, first_ep)

async def show_favorites(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Избранное:"
    kb = build_favorites_keyboard(chat_id)
    LAST_SCREEN_MODE[chat_id] = None
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_watched_titles(chat_id: int, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    count = len(USER_WATCHED_TITLES.get(chat_id, set()))
    achievement = get_achievement_for_count(count)
    kb = build_watched_titles_keyboard(chat_id, page=page)
    LAST_SCREEN_MODE[chat_id] = None
    if achievement:
        img_path, text = achievement
        full_text = f"{text}\n\n👁 Просмотрено тайтлов: {count}"
        await send_or_edit_photo(chat_id, context, img_path, full_text, kb)
    else:
        caption = f"Просмотренные тайтлы (всего: {count}):"
        await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False

async def show_continue_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    caption = "Тайтлы, которые ты сейчас смотришь:"
    kb = build_continue_keyboard(chat_id, page=page)
    LAST_SCREEN_MODE[chat_id] = None
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
    data = query.data
    chat_id = query.message.chat_id

    if data == "menu":
        await show_main_menu(chat_id, context); return
    if data == "catalog":
        await show_genres(chat_id, context); return
    if data == "random":
        await show_random(chat_id, context); return
    if data == "ongoings":
        await show_ongoings(chat_id, context); return
    if data == "continue":
        await show_continue_list(chat_id, context, page=0); return
    if data == "continue_list":
        await show_continue_list(chat_id, context, page=0); return
    if data.startswith("cont:"):
        slug = data.split(":", 1)[1]
        caption = "Что сделать с этим тайтлом?"
        kb = build_continue_item_keyboard(chat_id, slug)
        await edit_caption_only(chat_id, context, caption, kb); return
    if data.startswith("cont_play:"):
        slug = data.split(":", 1)[1]
        ep = USER_PROGRESS.get(chat_id, OrderedDict()).get(slug)
        if not ep:
            await query.answer("Нет сохранённого прогресса для этого тайтла.", show_alert=True)
            await show_continue_list(chat_id, context)
            return
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("cont_remove:"):
        slug = data.split(":", 1)[1]
        if chat_id in USER_PROGRESS and slug in USER_PROGRESS[chat_id]:
            del USER_PROGRESS[chat_id][slug]
            if not USER_PROGRESS[chat_id]:
                del USER_PROGRESS[chat_id]
            save_users()
        await query.answer("Убрано из продолжения.")
        await show_continue_list(chat_id, context); return
    if data == "search":
        SEARCH_MODE[chat_id] = True
        LAST_SCREEN_MODE[chat_id] = "search"
        caption = "🔍 Введи название аниме сообщением (или его часть).\n(Текст потом удалю, реагирую только на кнопки)"
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id)); return
    if data == "favorites":
        await show_favorites(chat_id, context); return
    if data == "watched":
        await show_watched_titles(chat_id, context, page=0); return
    if data.startswith("watched:"):
        _, page_str = data.split(":", 1)
        try: page = int(page_str)
        except ValueError: page = 0
        await show_watched_titles(chat_id, context, page=page); return
    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        await show_anime_by_genre(chat_id, context, genre, page=0); return
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
        first_ep = sorted(anime["episodes"].keys())[0]
        # entering anime list from catalog -> clear last screen mode
        LAST_SCREEN_MODE[chat_id] = None
        await show_episode(chat_id, context, slug, first_ep); return
    if data.startswith("list:"):
        slug = data.split(":", 1)[1]
        await show_episode_list(chat_id, context, slug); return
    if data.startswith("ep:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("next:"):
        _, slug, ep_str = data.split(":")
        current = int(ep_str)
        next_ep = current + 1
        await show_episode(chat_id, context, slug, next_ep); return
    if data.startswith("next_other:"):
        _, slug, ep_str = data.split(":")
        current = int(ep_str)
        next_ep = current + 1
        anime = ANIME.get(slug)
        if not anime:
            await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id)); return
        episodes = anime.get("episodes", {})
        ep_obj = episodes.get(next_ep)
        if not ep_obj:
            await edit_caption_only(chat_id, context, "Следующей серии нет.", build_main_menu_keyboard(chat_id)); return
        tracks = ep_obj.get("tracks", {})
        if not tracks:
            await edit_caption_only(chat_id, context, "У следующей серии нет доступных дорожек.", build_main_menu_keyboard(chat_id)); return
        some_track_name = next(iter(tracks.keys()))
        await show_episode(chat_id, context, slug, next_ep, track_name=some_track_name); return
    if data.startswith("prev:"):
        _, slug, ep_str = data.split(":")
        current = int(ep_str)
        await show_episode(chat_id, context, slug, current - 1); return
    if data.startswith("fav_add:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).add(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, OrderedDict()).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, OrderedDict()).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("watch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).add(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, OrderedDict()).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("unwatch_title:"):
        slug = data.split(":", 1)[1]
        USER_WATCHED_TITLES.setdefault(chat_id, set()).discard(slug)
        save_users()
        ep = USER_PROGRESS.get(chat_id, OrderedDict()).get(slug)
        if ep is None:
            anime = ANIME.get(slug)
            if anime and anime.get("episodes"):
                ep = sorted(anime["episodes"].keys())[0]
            else:
                ep = 1
        await show_episode(chat_id, context, slug, ep); return
    if data.startswith("track:"):
        _, slug, ep_str, safe_tname = data.split(":", 3)
        ep = int(ep_str)
        track_name = safe_tname.replace("__colon__", ":")
        await show_episode(chat_id, context, slug, ep, track_name=track_name); return
    if data.startswith("genre_page:"):
        # handled above earlier; keep for safety
        _, genre, page_str = data.split(":", 2)
        try: page = int(page_str)
        except ValueError: page = 0
        await show_anime_by_genre(chat_id, context, genre, page=page); return
    if data.startswith("continue_page:"):
        _, page_str = data.split(":", 1)
        try: page = int(page_str)
        except ValueError: page = 0
        await show_continue_list(chat_id, context, page=page); return

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
    matches: list[str] = []
    for slug, anime in ANIME.items():
        if q in anime["title"].lower():
            matches.append(slug)
    # Удаляем сообщение с текстом поиска
    try:
        await update.message.delete()
    except Exception:
        pass
    if not matches:
        await edit_caption_only(chat_id, context, "😔 Ничего не нашёл по этому названию.\nПопробуй другое слово.\n(Я реагирую только на кнопки)", build_main_menu_keyboard(chat_id))
        SEARCH_MODE[chat_id] = False
        LAST_SCREEN_MODE[chat_id] = None
        return
    if len(matches) == 1:
        found_slug = matches[0]
        anime = ANIME.get(found_slug)
        if not anime or not anime.get("episodes"):
            await edit_caption_only(chat_id, context, "У этого тайтла ещё нет серий.", build_main_menu_keyboard(chat_id))
            SEARCH_MODE[chat_id] = False
            LAST_SCREEN_MODE[chat_id] = None
            return
        first_ep = sorted(anime["episodes"].keys())[0]
        # mark search mode item
        LAST_SCREEN_MODE[chat_id] = "search"
        await show_episode(chat_id, context, found_slug, first_ep)
        SEARCH_MODE[chat_id] = False
        return
    kb = build_search_results_keyboard(matches)
    await edit_caption_only(chat_id, context, f"🔍 Нашёл несколько тайтлов по запросу «{text}»:\nВыбери нужный:", kb)
    SEARCH_MODE[chat_id] = False
    LAST_SCREEN_MODE[chat_id] = "search"

# =============================== EXTRA CLEANUP ХЭНДЛЕР
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
async def cmd_dump_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    if chat_id not in (ADMIN_ID, ADMIN2_ID):
        await msg.reply_text("⛔ Эта команда только для админов.")
        return
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
# /clear_slug
async def cmd_clear_slug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    if chat_id not in (ADMIN_ID, ADMIN2_ID):
        await msg.reply_text("⛔ Эта команда только для админов.")
        return
    if not context.args:
        await msg.reply_text("❗ Использование: /clear_slug <slug>")
        return
    slug = context.args[0].strip()
    if slug not in ANIME:
        await msg.reply_text(f"⚠️ Тайтл с slug '{slug}' не найден.")
        return
    del ANIME[slug]
    for uid in list(USER_PROGRESS.keys()):
        if slug in USER_PROGRESS[uid]:
            del USER_PROGRESS[uid][slug]
            if not USER_PROGRESS[uid]:
                del USER_PROGRESS[uid]
    for uid in list(USER_FAVORITES.keys()):
        if slug in USER_FAVORITES[uid]:
            USER_FAVORITES[uid].discard(slug)
    for uid in list(USER_WATCHED_TITLES.keys()):
        if slug in USER_WATCHED_TITLES[uid]:
            USER_WATCHED_TITLES[uid].discard(slug)
    for uid in list(CURRENT_TRACK.keys()):
        if slug in CURRENT_TRACK[uid]:
            del CURRENT_TRACK[uid][slug]
            if not CURRENT_TRACK[uid]:
                del CURRENT_TRACK[uid]
    save_anime()
    save_users()
    await msg.reply_text(f"✅ Тайтл '{slug}' и все связанные данные удалены.")

# ===============================
# /clear_ep
async def cmd_clear_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat_id = update.effective_chat.id
    if chat_id not in (ADMIN_ID, ADMIN2_ID):
        await msg.reply_text("⛔ Эта команда только для админов.")
        return
    if len(context.args) < 2:
        await msg.reply_text("❗ Использование: /clear_ep <slug> <ep>")
        return
    slug = context.args[0].strip()
    ep_str = context.args[1].strip()
    try:
        ep = int(ep_str)
    except ValueError:
        await msg.reply_text("❌ Номер серии должен быть числом.")
        return
    anime = ANIME.get(slug)
    if not anime:
        await msg.reply_text(f"⚠️ Тайтл с slug '{slug}' не найден.")
        return
    episodes = anime.get("episodes", {})
    if ep not in episodes:
        await msg.reply_text(f"⚠️ У тайтла '{slug}' нет серии {ep}.")
        return
    del episodes[ep]
    if not episodes:
        del ANIME[slug]
        for uid in list(USER_PROGRESS.keys()):
            if slug in USER_PROGRESS[uid]:
                del USER_PROGRESS[uid][slug]
                if not USER_PROGRESS[uid]:
                    del USER_PROGRESS[uid]
        for uid in list(USER_FAVORITES.keys()):
            if slug in USER_FAVORITES[uid]:
                USER_FAVORITES[uid].discard(slug)
        for uid in list(USER_WATCHED_TITLES.keys()):
            if slug in USER_WATCHED_TITLES[uid]:
                USER_WATCHED_TITLES[uid].discard(slug)
        for uid in list(CURRENT_TRACK.keys()):
            if slug in CURRENT_TRACK[uid]:
                del CURRENT_TRACK[uid][slug]
                if not CURRENT_TRACK[uid]:
                    del CURRENT_TRACK[uid]
        save_anime()
        save_users()
        await msg.reply_text(f"✅ Серия {ep} удалена. У тайтла не осталось серий, тайтл '{slug}' полностью удалён.")
        return
    ANIME[slug]["episodes"] = episodes
    save_anime()
    await msg.reply_text(f"✅ У тайтла '{slug}' удалена серия {ep}.")

# ===============================
# /start
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
async def debug_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.video:
        return
    file_id = update.message.video.file_id
    await update.message.reply_text(f"VIDEO FILE_ID:\n{file_id}")

# ===============================
# BOOT
def main():
    load_anime()
    load_users()
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CommandHandler("fix", cmd_fix))
    app.add_handler(CommandHandler("dump_all", cmd_dump_all))
    app.add_handler(CommandHandler("clear_slug", cmd_clear_slug))
    app.add_handler(CommandHandler("clear_ep", cmd_clear_ep))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Chat(SOURCE_CHAT_ID), handle_user_text))
    app.add_handler(MessageHandler(filters.Chat(SOURCE_CHAT_ID) & filters.VIDEO, handle_source_chat_message))
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.Chat(SOURCE_CHAT_ID), debug_video))
    app.add_handler(MessageHandler(filters.ALL, cleanup_non_command_messages))
    print("BOT STARTED...")
    app.run_polling()

if __name__ == "__main__":
    main()
