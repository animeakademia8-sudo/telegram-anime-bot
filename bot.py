import os
import random
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

# ===============================
# IN-MEM STORAGE
# ===============================
LAST_MESSAGE: dict[int, int] = {}           # chat_id -> message_id
LAST_MESSAGE_TYPE: dict[int, str] = {}      # chat_id -> "photo" or "video"
SEARCH_MODE: dict[int, bool] = {}           # chat_id -> bool

USER_PROGRESS: dict[int, dict] = {}         # chat_id -> {"slug": str, "ep": int}
USER_FAVORITES: dict[int, set] = {}         # chat_id -> set(slug)

# стек экранов: chat_id -> list[dict(...)]
USER_STACK: dict[int, list] = {}

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
# STACK HELPERS
# ===============================

def push_screen(chat_id: int, screen: dict):
    USER_STACK.setdefault(chat_id, []).append(screen)


def pop_screen(chat_id: int) -> Optional[dict]:
    stack = USER_STACK.get(chat_id) or []
    if not stack:
        return None
    return stack.pop()


def clear_stack(chat_id: int):
    USER_STACK[chat_id] = []


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
        fav_button = InlineKeyboardButton("💖 Добавить в избранное", callback_data=f"fav_add:{slug}")

    rows = [
        [
            InlineKeyboardButton("📺 Серии", callback_data=f"list:{slug}"),
            InlineKeyboardButton("⬅️ К списку", callback_data="back"),
        ],
        [fav_button],
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


# ===============================
# HELPERS: single-message logic
# ===============================

async def send_or_edit_photo(chat_id: int, context: ContextTypes.DEFAULT_TYPE, photo_path: str, caption: str, reply_markup: InlineKeyboardMarkup):
    msg_id = LAST_MESSAGE.get(chat_id)
    if msg_id:
        try:
            await context.bot.edit_message_media(
                media=InputMediaPhoto(media=open(photo_path, "rb"), caption=caption),
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

    sent = await context.bot.send_photo(chat_id=chat_id, photo=open(photo_path, "rb"), caption=caption, reply_markup=reply_markup)
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
        sent = await context.bot.send_photo(chat_id=chat_id, photo=open(WELCOME_PHOTO, "rb"), caption=caption, reply_markup=reply_markup)
        LAST_MESSAGE[chat_id] = sent.message_id
        LAST_MESSAGE_TYPE[chat_id] = "photo"
        return sent.message_id


# ===============================
# SCREENS
# ===============================

async def show_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, push_prev: bool = True):
    if push_prev:
        push_screen(chat_id, {"screen": "main_menu"})
    caption = "Приятного просмотра ✨\nВыбери опцию:"
    kb = build_main_menu_keyboard(chat_id)
    await send_or_edit_photo(chat_id, context, WELCOME_PHOTO, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_genres(chat_id: int, context: ContextTypes.DEFAULT_TYPE, push_prev: bool = True):
    if push_prev:
        push_screen(chat_id, {"screen": "genres"})
    caption = "Выбери жанр:"
    kb = build_genre_keyboard()
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_anime_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, push_prev: bool = True):
    if push_prev:
        push_screen(chat_id, {"screen": "anime_list"})
    caption = "Список аниме:"
    kb = build_anime_menu(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_anime_by_genre(chat_id: int, context: ContextTypes.DEFAULT_TYPE, genre: str, push_prev: bool = True):
    if push_prev:
        push_screen(chat_id, {"screen": "by_genre", "genre": genre})
    caption = f"Жанр: {genre.capitalize()}\nВыбери аниме:"
    kb = build_anime_by_genre_keyboard(genre)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_episode(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, ep: int, push_prev: bool = True, mark_progress: bool = True):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return
    episode = anime["episodes"].get(ep)
    if not episode:
        await edit_caption_only(chat_id, context, "Такой серии нет", build_main_menu_keyboard(chat_id))
        return

    if push_prev:
        push_screen(chat_id, {"screen": "episode", "slug": slug, "ep": ep})

    caption = f"{anime['title']}\nСерия {ep}"
    kb = build_episode_keyboard(slug, ep, chat_id)
    await send_or_edit_video(chat_id, context, episode["source"], caption, kb)
    if mark_progress:
        USER_PROGRESS[chat_id] = {"slug": slug, "ep": ep}
    SEARCH_MODE[chat_id] = False


async def show_episode_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, slug: str, push_prev: bool = True):
    anime = ANIME.get(slug)
    if not anime:
        await edit_caption_only(chat_id, context, "Аниме не найдено", build_main_menu_keyboard(chat_id))
        return

    if push_prev:
        push_screen(chat_id, {"screen": "episode_list", "slug": slug})

    caption = f"{anime['title']}\nВыбери серию:"
    kb = build_episode_list_keyboard(slug)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def show_random(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    slug = random.choice(list(ANIME.keys()))
    await show_episode(chat_id, context, slug, 1)


async def show_favorites(chat_id: int, context: ContextTypes.DEFAULT_TYPE, push_prev: bool = True):
    if push_prev:
        push_screen(chat_id, {"screen": "favorites"})
    caption = "Избранное:"
    kb = build_favorites_keyboard(chat_id)
    await edit_caption_only(chat_id, context, caption, kb)
    SEARCH_MODE[chat_id] = False


async def go_back(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    state = pop_screen(chat_id)
    if not state:
        await show_main_menu(chat_id, context, push_prev=False)
        return

    screen = state.get("screen")
    if screen == "main_menu":
        await show_main_menu(chat_id, context, push_prev=False)
    elif screen == "genres":
        await show_genres(chat_id, context, push_prev=False)
    elif screen == "anime_list":
        await show_anime_list(chat_id, context, push_prev=False)
    elif screen == "by_genre":
        await show_anime_by_genre(chat_id, context, state.get("genre", ""), push_prev=False)
    elif screen == "episode_list":
        await show_episode_list(chat_id, context, state.get("slug", ""), push_prev=False)
    elif screen == "episode":
        await show_episode(chat_id, context, state.get("slug", ""), state.get("ep", 1), push_prev=False, mark_progress=False)
    elif screen == "favorites":
        await show_favorites(chat_id, context, push_prev=False)
    else:
        await show_main_menu(chat_id, context, push_prev=False)


# ===============================
# CALLBACKS
# ===============================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "menu":
        clear_stack(chat_id)
        await show_main_menu(chat_id, context, push_prev=False)
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
        push_screen(chat_id, {"screen": "search_prompt"})
        await edit_caption_only(chat_id, context, caption, build_main_menu_keyboard(chat_id))
        return

    if data == "favorites":
        await show_favorites(chat_id, context)
        return

    if data == "back":
        await go_back(chat_id, context)
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
        prog = USER_PROGRESS.get(chat_id)
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        else:
            ep = 1
        await show_episode(chat_id, context, slug, ep, push_prev=False)
        return

    if data.startswith("fav_remove:"):
        slug = data.split(":", 1)[1]
        USER_FAVORITES.setdefault(chat_id, set()).discard(slug)
        prog = USER_PROGRESS.get(chat_id)
        if prog and prog.get("slug") == slug:
            ep = prog.get("ep", 1)
        else:
            ep = 1
        await show_episode(chat_id, context, slug, ep, push_prev=False)
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

    # переход к серии, стек уже содержит состояние search_prompt
    await show_episode(chat_id, context, found_slug, 1)
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

    clear_stack(chat_id)
    await show_main_menu(chat_id, context, push_prev=False)

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
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", send_start_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VIDEO, debug_video))

    print("BOT STARTED...")
    app.run_polling()


if __name__ == "__main__":
    main()
