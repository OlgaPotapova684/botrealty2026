#!/usr/bin/env python3
"""
Telegram-бот для агентства недвижимости.
Сценарий загружается из JSON-файла в этой папке.
Токен задаётся через переменную окружения BOT_TOKEN.
"""

import os
import json
from datetime import datetime
from pathlib import Path

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# Путь к JSON со сценарием (первый .json в папке скрипта)
SCRIPT_DIR = Path(__file__).resolve().parent

# Кнопка возврата в главное меню (показывается на последнем шаге каждой ветки)
RETURN_TO_MENU_BUTTON = "Вернуться в исходное меню"

# Файл с записями посещений (локально); на Vercel пишем в stdout
VISITS_LOG = SCRIPT_DIR / "visits.log"


def log_visit(update: Update, action: str = "message", text_preview: str = ""):
    """Пишет запись о посещении: локально в visits.log, на Vercel — в лог (stdout)."""
    if not update.effective_user:
        return
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    chat_id = update.effective_chat.id
    username = (update.effective_user.username or "").replace("\t", " ")
    first_name = (update.effective_user.first_name or "").replace("\t", " ")[:50]
    text_preview = (text_preview or "")[:80].replace("\t", " ").replace("\n", " ")
    line = f"{ts}\t{chat_id}\t{username}\t{first_name}\t{action}\t{text_preview}\n"
    if os.environ.get("VERCEL"):
        print("VISIT", line.strip(), flush=True)
    else:
        try:
            write_header = not VISITS_LOG.exists()
            with open(VISITS_LOG, "a", encoding="utf-8") as f:
                if write_header:
                    f.write("datetime_utc\tchat_id\tusername\tfirst_name\taction\ttext_preview\n")
                f.write(line)
        except OSError:
            print("VISIT", line.strip(), flush=True)


def load_scenario():
    """Загружает сценарий из JSON-файла в папке проекта."""
    # Сначала ищем scenario.json (надёжное имя для Vercel и др.)
    scenario_path = SCRIPT_DIR / "scenario.json"
    if scenario_path.exists():
        with open(scenario_path, "r", encoding="utf-8") as f:
            return json.load(f)
    files = list(SCRIPT_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"В папке {SCRIPT_DIR} не найден JSON-файл сценария (scenario.json или *.json).")
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def build_engine(data):
    """Строит движок диалога: сообщения по id, переходы по message_a_id."""
    messages = {m["id"]: m for m in data["messages"]}
    connections_by_from = {}
    for c in data["connections"]:
        a = c["message_a_id"]
        if a not in connections_by_from:
            connections_by_from[a] = []
        connections_by_from[a].append(c)

    # Стартовое сообщение: узел с condition "/start; ..." (message_type 4) -> его единственный переход
    start_msg_id = None
    for m in data["messages"]:
        if m.get("message_type") == 4 and m.get("condition"):
            cond = m["condition"].lower()
            if "start" in cond or "старт" in cond or "начать" in cond:
                outs = connections_by_from.get(m["id"], [])
                if outs:
                    start_msg_id = outs[0]["message_b_id"]
                break

    if start_msg_id is None:
        # Fallback: первый переход из любого узла
        for c in data["connections"]:
            if c["message_a_id"] in messages and c["message_b_id"] in messages:
                start_msg_id = c["message_b_id"]
                break

    return {
        "messages": messages,
        "connections_by_from": connections_by_from,
        "start_message_id": start_msg_id,
    }


def is_terminal_message(engine, message_id):
    """Сообщение считается последним шагом ветки, если нет исходящих переходов или message_type == 2."""
    msg = engine["messages"].get(message_id)
    if not msg:
        return False
    if msg.get("message_type") == 2:
        return True
    conns = engine["connections_by_from"].get(message_id, [])
    return len(conns) == 0


def get_buttons(engine, message_id):
    """Возвращает кнопки для сообщения: из connections (show_as_button) и из message.buttons."""
    msg = engine["messages"].get(message_id)
    conns = engine["connections_by_from"].get(message_id, [])
    buttons = []

    # Кнопки из переходов — сортируем по button_index (чтобы 1→2→3 комнатная и т.д.)
    conn_buttons = [
        (c.get("button_index", 0), (c.get("condition") or "").strip())
        for c in conns
        if c.get("show_as_button") and c.get("condition")
    ]
    conn_buttons.sort(key=lambda x: x[0])
    buttons.extend([text for _, text in conn_buttons if text])

    if not buttons and msg and msg.get("buttons"):
        try:
            raw = json.loads(msg["buttons"])
            for b in raw:
                if isinstance(b, dict) and b.get("text"):
                    buttons.append(b["text"])
        except (json.JSONDecodeError, TypeError):
            pass

    # На последнем шаге любой ветки добавляем кнопку возврата в меню
    if is_terminal_message(engine, message_id):
        buttons.append(RETURN_TO_MENU_BUTTON)

    return buttons


def get_answer_text(msg):
    """Текст ответа бота. #{none} не показываем."""
    if not msg:
        return ""
    text = (msg.get("answer") or "").strip()
    if text == "#{none}" or not text:
        return ""
    return text.replace("\r\n", "\n")


def find_next_message(engine, current_id, user_text):
    """
    По текущему сообщению и тексту пользователя находит следующее сообщение.
    Возвращает (message_b_id, connection) или (None, None).
    """
    user_text = (user_text or "").strip()
    conns = engine["connections_by_from"].get(current_id, [])

    for c in conns:
        if c.get("read_data"):
            # Любой ввод принимаем (например, телефон)
            return c["message_b_id"], c
        cond = (c.get("condition") or "").strip()
        if not cond:
            continue
        # Условие может быть "вариант1; вариант2"
        variants = [v.strip().lower() for v in cond.split(";") if v.strip()]
        if user_text.lower() in variants:
            return c["message_b_id"], c
        if user_text.lower() == cond.lower():
            return c["message_b_id"], c

    return None, None


# Глобальный движок и хранилище состояний (chat_id -> current_message_id)
_engine = None
_states = {}


def get_engine():
    global _engine
    if _engine is None:
        data = load_scenario()
        _engine = build_engine(data)
    return _engine


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — показываем приветствие и переводим в первый шаг сценария."""
    log_visit(update, action="start")
    engine = get_engine()
    chat_id = update.effective_chat.id
    start_id = engine["start_message_id"]
    if not start_id:
        await update.message.reply_text("Сценарий не настроен.")
        return

    _states[chat_id] = start_id
    msg = engine["messages"].get(start_id)
    text = get_answer_text(msg)
    buttons = get_buttons(engine, start_id)

    if text:
        if buttons:
            keyboard = [[KeyboardButton(b)] for b in buttons]
            await update.message.reply_text(
                text,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            )
        else:
            await update.message.reply_text(text)


async def show_main_menu_buttons_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать только кнопки главного меню, без текста «Добро пожаловать…»."""
    engine = get_engine()
    chat_id = update.effective_chat.id
    start_id = engine["start_message_id"]
    if not start_id:
        await update.message.reply_text("Сценарий не настроен.")
        return

    _states[chat_id] = start_id
    buttons = get_buttons(engine, start_id)
    if not buttons:
        await update.message.reply_text("Выберите действие:")
        return
    keyboard = [[KeyboardButton(b)] for b in buttons]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового сообщения пользователя."""
    user_text = (update.message and update.message.text) or ""
    log_visit(update, action="message", text_preview=user_text)
    engine = get_engine()
    chat_id = update.effective_chat.id

    # Нажатие «Вернуться в исходное меню» — только кнопки, без повтора приветствия
    if user_text and user_text.strip() == RETURN_TO_MENU_BUTTON:
        await show_main_menu_buttons_only(update, context)
        return

    current_id = _states.get(chat_id)
    if current_id is None:
        # Нет состояния — как /start
        await start(update, context)
        return

    next_id, _ = find_next_message(engine, current_id, user_text)
    if next_id is None:
        # Пользователь написал текст вместо нажатия кнопки — показываем сообщение и кнопку возврата
        keyboard = [[KeyboardButton(RETURN_TO_MENU_BUTTON)]]
        await update.message.reply_text(
            "Спасибо, ожидайте.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    _states[chat_id] = next_id
    msg = engine["messages"].get(next_id)
    text = get_answer_text(msg)
    buttons = get_buttons(engine, next_id)

    if text:
        if buttons:
            keyboard = [[KeyboardButton(b)] for b in buttons]
            await update.message.reply_text(
                text,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            )
        else:
            await update.message.reply_text(text)


def create_application():
    """Создаёт приложение с обработчиками (для локального polling и для webhook)."""
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Задайте переменную окружения BOT_TOKEN.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("Задайте переменную окружения BOT_TOKEN с токеном бота.")
        print("Пример: export BOT_TOKEN=123456:ABC-DEF...")
        raise SystemExit(1)

    app = create_application()
    print("Бот запущен. Остановка: Ctrl+C")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
