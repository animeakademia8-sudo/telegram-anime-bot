import os
import random
import json
from typing import Optional

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
# CONFIG
# ===============================
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8421608017:AAGd5ikJ7bAU2OIpkCU8NI4Okbzi2Ed9upQ"
WELCOME_PHOTO = "images/welcome.jpg"
DATA_FILE = "anime_data.json"

MAX_RECENT_TITLES = 5  # сколько последних тайтлов запоминать на "Продолжить"

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: dict[int, int] = {}           # chat_id -> message_id
LAST_MESSAGE_TYPE: dict[int, str] = {}      # chat_id -> "photo" or "video"
SEARCH_MODE: dict[int, bool] = {}           # chat_id -> bool

# user data (будет грузиться/сохраняться в файл)
USER_PROGRESS: dict[int, dict] = {}         # chat_id -> {"slug": str, "ep": int}
USER_HISTORY: dict[int, dict] = {}          # chat_id -> {slug: last_ep}
USER_FAVORITES: dict[int, set] = {}         # chat_id -> set(slug)

# ===============================
# DATA: ANIME
# ===============================
ANIME = {
    "neumeli": {
        "title": "Неумелый сэмпай",
        "genres": ["романтика", "комедия", "школа", "повседневность"],
        "episodes": {
            1: {"source": "BAACAgIAAxkBAAMVaRj24OIri4siBrWlRsZDIX0u_VgAAv57AAKaSjhI2zDVA1kRZnI2BA"},
            2: {"source": "BAACAgIAAxkBAAMfaRj4h-gAAYH9gLc9O6FG1xHfewqqAAIJfAACmko4SKEM3U0QuAvWNgQ"},
            3: {"source": "BAACAgIAAxkBAAMlaRj67-vSO4t9NKFnjP-6vOLnaFAAAhl8AAKaSjhINlo5cuQDLRI2BA"},
            4: {"source": "BAACAgIAAxkBAAIDMmkkT1cOajJ0bhZH_JkcdsmLIhoYAAImfAACmko4SBiUcwmxTisJNgQ"},
            5: {"source": "BAACAgIAAxkBAAIDNGkkT19_lQuYPe5ZlJT4WBfTixbKAAI2fAACmko4SHS9zmMgKBTlNgQ"},
            6: {"source": "BAACAgIAAxkBAAIDNmkkT2e8e2gDOB5QzCY2YpqxVsICAALDiQACvhFxSOWK_q1jWB_oNgQ"},
            7: {"source": "BAACAgIAAxkBAAIDOGkkT3sX7FezBJOOD21FK44fRlYpAAI4jAACOEG4SHs_SAcgSxfLNgQ"},
            8: {"source": "BAACAgIAAxkBAAIDOmkkT4Wtw_DjOR9XXr0KghSvDBOPAAJakAACPgwBSZFA_Js7a4KVNgQ"},
        },
    },
    "pridvorni_mag": {
        "title": "Придворный маг с навыком поддержки",
        "genres": ["приключения", "фэнтези", "экшен"],
        "episodes": {
            1: {"source": "BAACAgIAAxkBAAIC3GkkOM-7t-w06khdsdltYWevP4uGAALAigACC2whSaYsDQuBaW6oNgQ"},
            2: {"source": "BAACAgIAAxkBAAIC5mkkO1KvLt1dgCdWBIbCy0pzRCXyAALBigACC2whSUTWBHO3NgTZNgQ"},
            3: {"source": "BAACAgIAAxkBAAIC6GkkO1xpW64VhQi9QH7CFVYpwT5JAALDigACC2whSeRl-8aKAnmpNgQ"},
            4: {"source": "BAACAgIAAxkBAAIC6mkkO2cxrUllPgkSkWeoFZJo_liEAALFigACC2whSdoyTGtBVN4mNgQ"},
            5: {"source": "BAACAgIAAxkBAAIC7GkkO3RChv68Mm4frnbEj1SlxK-qAALHigACC2whSYpzVplj8OSdNgQ"},
            6: {"source": "BAACAgIAAxkBAAIC7mkkO4IGNJBEoBj7QCprmG1JM55aAALKigACC2whSYoiXyJgaPYnNgQ"},
            7: {"source": "BAACAgIAAxkBAAIC8GkkO4_XK3w-fG52q2Oy0ze8_6f5AALNigACC2whSUqvmz2y8VwdNgQ"},
            8: {"source": "BAACAgIAAxkBAAIC8mkkO5jQLbJVRXj0SPWO9CHLiwUeAALOigACC2whSfxA3xX4o_weNgQ"},
        },
    },
    "ga4iakyta": {
        "title": "Гачиакута",
        "genres": ["приключения", "фэнтези", "экшен", "суперспособности", "антиутопия"],
        "episodes": {
            1: {"source": "BAACAgIAAxkBAAICSWkZ-Kgi797xty9gUQiwHzQ6IhbwAAIqiAAC0E_RSDiNDuk9slE9NgQ"},
            2: {"source": "BAACAgIAAxkBAAICS2kZ-gp2odRw6qYgozEwuNRBQ46TAAIviAAC0E_RSPxJtnNeXZtINgQ"},
            3: {"source": "BAACAgIAAxkBAAICTWkZ-kcUrLcvkZhT39ttt7Rup3m6AAI6iAAC0E_RSHKHjGzKzKTMNgQ"},
            4: {"source": "BAACAgIAAxkBAAICT2kZ-vmEFLFV6rX-6Ep2ZWpjwE0lAAJWiAAC0E_RSOdsxn-Wg4sUNgQ"},
            5: {"source": "BAACAgIAAxkBAAICUWkZ-5roUcoWh_qa_qsy45dkxe__AAJfiAAC0E_RSPgmA_eRnuKfNgQ"},
            6: {"source": "BAACAgIAAxkBAAICU2kZ-7l8XzyBuT7jPFWK-FZjaEbEAAJniAAC0E_RSPiyqILZiXJtNgQ"},
            7: {"source": "BAACAgIAAxkBAAICVWkZ_C6qngsxNyoOrllSxERJonInAAJ0iAAC0E_RSMbgHGNLAb9ENgQ"},
            8: {"source": "BAACAgIAAxkBAAICV2kZ_FJI_oa57aSAtVfiUdq1ey_-AAJ-iAAC0E_RSLIke7Ve4EY0NgQ"},
            9: {"source": "BAACAgIAAxkBAAICWWkZ_H5UeUlRJC-QySc0GBfh57_4AAKBiAAC0E_RSF_ZYjUbNznxNgQ"},
            10: {"source": "BAACAgIAAxkBAAICW2kZ_LxjqEn7MDnu1kOIdd9uunnIAAKMiAAC0E_RSHk0LKSHRXWDNgQ"},
            11: {"source": "BAACAgIAAxkBAAICXWkZ_QL0bmkIvNBj49_t49EnDiDeAAKNiAAC0E_RSNpRpeqlP6aNNgQ"},
            12: {"source": "BAACAgIAAxkBAAICX2kZ_UjXMmzO1Qf2AuKV_SDf_dT4AAKQiAAC0E_RSD5LbrkS6nUvNgQ"},
            13: {"source": "BAACAgIAAxkBAAICYWkZ_YlepRDBQOOGc_kdUD34Cnf3AAKViAAC0E_RSMQQyY0orZ7CNgQ"},
            14: {"source": "BAACAgIAAxkBAAICY2kZ_celXJtd6nD5_jGxQDek4emEAAKkiAAC0E_RSAzuzSQ6ZRyYNgQ"},
            15: {"source": "BAACAgIAAxkBAAICZWkZ_gABwEuWT7mgqgehEtiAOEWp1wACrogAAtBP0UietkuvDP662DYE"},
            16: {"source": "BAACAgIAAxkBAAICZ2kZ_knyHpiyraYEURELR6ejO0zaAAK6iAAC0E_RSHxdpJIJCcMfNgQ"},
            17: {"source": "BAACAgIAAxkBAAICaWkZ_nkLwaofkObeDnC1CtRg8oDEAALBiAAC0E_RSJ7nifrQs1O2NgQ"},
            18: {"source": "BAACAgIAAxkBAAICa2kZ_u9372Z0SVNL2twsXli-Raj9AALEiAAC0E_RSJQB19aj5RlWNgQ"},
            19: {"source": "BAACAgIAAxkBAAICrWkazh87OUkjfSYK1UeHti1CeuYpAAIFkAAC0E_ZSII3zt7YJHrYNgQ"},
            20: {"source": "BAACAgIAAxkBAAICvWkkJXvdgQABfqZCK4ORx7nCVjODUwAClIkAAgtsIUmO-cMUGJ8nRzYE"},
        },
    },
}

# ===============================
# SAVE / LOAD USER DATA
# ===============================
def load_user_data():
    global USER_PROGRESS, USER_FAVORITES, USER_HISTORY
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        USER_PROGRESS = {int(k): v for k, v in data.get("progress", {}).items()}
        USER_FAVORITES = {int(k): set(v) for k, v in data.get("favorites", {}).items()}
        USER_HISTORY = {int(k): {slug: int(ep) for slug, ep in v.items()} for k, v in data.get("history", {}).items()}
    except Exception:
        pass


def save_user_data():
    data = {
        "progress": USER_PROGRESS,
        "favorites": {k: list(v) for k, v in USER_FAVORITES.items()},
        "history": USER_HISTORY,
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_total_episodes(slug: str) -> int:
    anime = ANIME.get(slug)
    if not anime:
        return 0
    return len(anime["episodes"])


def get_last_watched_ep(chat_id: int, slug: str) -> int:
    return USER_HISTORY.get(chat_id, {}).get(slug, 0)


def update_history(chat_id: int, slug: str, ep: int):
    USER_HISTORY.setdefault(chat_id, {})
    USER_HISTORY[chat_id][slug] = max(ep, USER_HISTORY[chat_id].get(slug, 0))


def get_recent_titles(chat_id: int) -> list[str]:
    hist = USER_HISTORY.get(chat_id, {})
    if not hist:
        return []
    sorted_slugs = sorted(hist.keys(), key=lambda s: hist[s], reverse=True)
    return sorted_slugs[:MAX_RECENT_TITLES]


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
        [InlineKeyboardButton("💖 Избранное", callback_data="favorites")],
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


def build_anime_by_genre_keyboard(genre: str, chat_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        if genre in anime.get("genres", []):
            last_ep = get_last_watched_ep(chat_id, slug)
            total = get_total_episodes(slug)
            if last_ep > 0:
                title = f"{anime['title']} ({last_ep}/{total})"
            else:
                title = anime["title"]
            keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
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
        fav_button = InlineKeyboardButton("💖 Добавить в избранное", callback_data=f"fav_add:{slug}")

    rows = [
        [
            InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}"),
            # кнопка "К списку" теперь ведёт на список эпизодов
            InlineKeyboardButton("⬅️ К списку", callback_data=f"back_to_anime:{slug}"),
        ],
        [fav_button],
        [InlineKeyboardButton("✅ Отметить как просмотренную", callback_data=f"mark_seen:{slug}:{ep}")],
    ]
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_episode_list_keyboard(slug: str, chat_id: int) -> InlineKeyboardMarkup:
    eps = sorted(ANIME[slug]["episodes"].keys())
    last_ep = get_last_watched_ep(chat_id, slug)

    rows = []
    row = []
    for e in eps:
        if last_ep == 0:
            label = f"Серия {e}"
        elif e < last_ep:
            label = f"Серия {e} ✅"
        elif e == last_ep:
            label = f"Серия {e} ▶️"
        else:
            label = f"Серия {e}"
        row.append(InlineKeyboardButton(label, callback_data=f"ep:{slug}:{e}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Назад к тайтлу", callback_data=f"back_to_anime:{slug}")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_anime_menu(chat_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for slug, anime in ANIME.items():
        last_ep = get_last_watched_ep(chat_id, slug)
        total = get_total_episodes(slug)
        if last_ep > 0:
            title = f"{anime['title']} ({last_ep}/{total})"
        else:
            title = anime["title"]
        keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def build_favorites_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    favs = USER_FAVORITES.get(chat_id, set())
    rows = []
    for slug in favs:
        anime = ANIME.get(slug)
        if not anime:
            continue
        last_ep = get_last_watched_ep(chat_id, slug)
        total = get_total_episodes(slug)
        if last_ep > 0:
            title = f"{anime['title']} ({last_ep}/{total})"
        else:
            title = anime["title"]
        rows.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    if not rows:
        rows = [[InlineKeyboardButton("Пусто", callback_data="menu")]]
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def build_continue_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    recent = get_recent_titles(chat_id)
    rows = []
    for slug in recent:
        anime = ANIME.get(slug)
        if not anime:
            continue
        last_ep = get_last_watched_ep(chat_id, slug)
        total = get_total_episodes(slug)
        title = f"{anime['title']} ({last_ep}/{total})"
        rows.append([InlineKeyboardButton(title, callback_data=f"resume:{slug}")])
    rows.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ===============================
# HELPERS: single-message logic
# ===============================
async def send_or_edit_photo(chat_id: int, context: ContextTypes.DEFAULT_TYPE, photo_path: str, caption: str, reply_markup: InlineKeyboardMarkup):
    msg_id = LAST_MESSAGE.get(chat_id)
    if msg_id:
        try:
            with open(photo_path, "rb") as f:
                await context.bot.edit_message_media(
                    media=InputMediaPhoto(media=f, caption=caption),
                    chat_id=chat_id,
                    message_id=msg_id,
                )
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup)
            LAST_MESSAGE_TYPE[chat_id] = "photo"
            return msg_id
        except Exception:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    with open(photo_path, "rb") as f:
        sent = await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption, reply_markup=reply_markup)
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
        with open(WELCOME_PHOTO, "rb") as f:
            sent = await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption, reply_markup=reply_markup)
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
    kb = build_anime_by_genre_keyboard(genre, chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_episode(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int, mark_progress: bool = True):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено 😔\nВозвращаю в меню.", build_main_menu_keyboard(chat_id))
        return
    episode = anime["episodes"].get(ep)
    if not episode:
        await edit_caption_only(chat_id, context, "Такой серии нет 😅\nВозвращаю в меню.", build_main_menu_keyboard(chat_id))
        return

    caption = f"{anime['title']}\nСерия {ep}"
    kb = build_episode_keyboard(slug, ep, chat_id)
    await send_or_edit_video(chat_id, context, episode["source"], caption, kb)

    if mark_progress:
        USER_PROGRESS[chat_id] = {"slug": slug, "ep": ep}
        update_history(chat_id, slug, ep)
        save_user_data()

    SEARCH_MODE[chat_id] = False


async def show_episode_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено 😔\nВозвращаю в меню.", build_main_menu_keyboard(chat_id))
        return
    caption = f"{anime['title']}\nВыбери серию:"
    kb = build_episode_list_keyboard(slug, chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_random(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    slug = random.choice(list(ANIME.keys()))
    await show_episode(chat_id, context, slug, 1)


async def show_favorites(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    caption = "Избранное:"
    kb = build_favorites_keyboard(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_continue_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    recent = get_recent_titles(chat_id)
    if not recent:
        await edit_caption_only(chat_id, context, "Ты ещё ничего не смотрел 🙂", build_main_menu_keyboard(chat_id))
        return
    caption = "Продолжить просмотр:\nВыбери тайтл:"
    kb = build_continue_keyboard(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)


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
        await show_continue_menu(chat_id, context)
        return

    if data == "search":
        SEARCH_MODE[chat_id] = True
        caption = "🔍 Введи название аниме сообщением (или его часть).\n\nЯ отвечу в этом же сообщении бота."
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id))
        return

    if data == "favorites":
        await show_favorites(chat_id, context)
        return

    if data.startswith("genre:"):
        genre = data.split(":", 1)[1]
        await show_anime_by_genre(chat_id, context, genre)
        return

    if data.startswith("anime:"):
        slug = data.split(":", 1)[1]
        last_ep = get_last_watched_ep(chat_id, slug)
        ep = last_ep if last_ep > 0 else 1
        await show_episode(chat_id, context, slug, ep)
        return

    # ---- FIXED: back_to_anime теперь открывает список эпизодов ----
    if data.startswith("back_to_anime:"):
        slug = data.split(":", 1)[1]
        await show_episode_list(chat_id, context, slug)
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
        save_user_data()
        last_ep = get_last_watched_ep(chat_id, slug)
        ep = last_ep if last_ep > 0 else 1
        await show_episode(chat_id, context, slug, ep, mark_progress=False)
        return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        save_user_data()
        last_ep = get_last_watched_ep(chat_id, slug)
        ep = last_ep if last_ep > 0 else 1
        await show_episode(chat_id, context, slug, ep, mark_progress=False)
        return

    if data.startswith("resume:"):
        slug = data.split(":", 1)[1]
        last_ep = get_last_watched_ep(chat_id, slug)
        ep = last_ep if last_ep > 0 else 1
        await show_episode(chat_id, context, slug, ep)
        return

    if data.startswith("mark_seen:"):
        _, slug, ep_str = data.split(":")
        ep = int(ep_str)
        update_history(chat_id, slug, ep)
        USER_PROGRESS[chat_id] = {"slug": slug, "ep": ep}
        save_user_data()
        await show_episode(chat_id, context, slug, ep, mark_progress=False)
        return


# ===============================
# TEXT (SEARCH)
# ===============================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not SEARCH_MODE.get(chat_id, False):
        try:
            await update.message.reply_text(
                "Я реагирую на кнопки 😊\n"
                "Если хочешь найти аниме по названию — нажми 🔍 Поиск."
            )
        except Exception:
            pass
        return

    q = text.lower()
    found_slugs = []
    for slug, anime in ANIME.items():
        if q in anime["title"].lower():
            found_slugs.append(slug)

    try:
        await update.message.delete()
    except Exception:
        pass

    if not found_slugs:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔁 Ещё поиск", callback_data="search")],
                [InlineKeyboardButton("🍄 Меню", callback_data="menu")],
            ]
        )
        await edit_caption_only(
            chat_id,
            context,
            "😔 Ничего не нашёл по этому названию.\nПопробуй другое слово.",
            kb,
        )
        SEARCH_MODE[chat_id] = False
        return

    if len(found_slugs) == 1:
        await show_episode(chat_id, context, found_slugs[0], 1)
        SEARCH_MODE[chat_id] = False
        return

    keyboard = []
    for slug in found_slugs:
        anime = ANIME[slug]
        last_ep = get_last_watched_ep(chat_id, slug)
        total = get_total_episodes(slug)
        if last_ep > 0:
            title = f"{anime['title']} ({last_ep}/{total})"
        else:
            title = anime["title"]
        keyboard.append([InlineKeyboardButton(title, callback_data=f"anime:{slug}")])
    keyboard.append([InlineKeyboardButton("🍄 Меню", callback_data="menu")])
    kb = InlineKeyboardMarkup(keyboard)

    await edit_caption_only(
        chat_id,
        context,
        "Нашёл несколько вариантов, выбери нужный:",
        kb,
    )
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
    load_user_data()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VIDEO, debug_video))

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
