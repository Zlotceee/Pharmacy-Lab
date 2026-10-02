"""Telegram-бот для учёта домашней аптечки и сроков годности."""

import os
from datetime import date, datetime
from typing import List, Optional

import telebot
from telebot import types

import database as db

EXPIRY_WARNING_DAYS = 30
DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")
MAX_NAME_LENGTH = 100

BTN_LIST = "📋 Мои лекарства"
BTN_ADD = "➕ Добавить"
BTN_EXPIRY = "⏰ Сроки годности"
BTN_DELETE = "🗑 Удалить"

HELP_TEXT = (
    "Что я умею:\n"
    "/list — список лекарств (нажмите на название, чтобы открыть карточку)\n"
    "/new — добавить лекарство\n"
    "/time — проверить сроки годности\n"
    "/delete — удалить лекарство\n"
    "/cancel — прервать добавление"
)

token = os.getenv("BOT_TOKEN")
token = "8234821279:AAEkJP5kthRrdXazelhPVxLEoUKMvAftyjc"
if not token:
    raise SystemExit("Не найден токен: задайте переменную окружения BOT_TOKEN")

bot = telebot.TeleBot(token)


# --- Форматирование -------------------------------------------------------

def plural(n: int, one: str, few: str, many: str) -> str:
    """plural(1, 'день', 'дня', 'дней') -> 'день'; 3 -> 'дня'; 11 -> 'дней'."""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def days_word(n: int) -> str:
    return f"{n} {plural(n, 'день', 'дня', 'дней')}"


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def parse_date(text: str) -> Optional[date]:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def expiry_status(days_left: int) -> str:
    if days_left < 0:
        return f"просрочено на {days_word(-days_left)}"
    if days_left == 0:
        return "истекает сегодня"
    return f"осталось {days_word(days_left)}"


def medicine_card(med: db.Medicine, today: date) -> str:
    description = med.description or "Описание не указано"
    return (
        f"💊 {med.name}\n"
        f"{description}\n\n"
        f"Годен до: {format_date(med.expiry_date)} "
        f"({expiry_status(med.days_left(today))})\n"
        f"Количество: {med.quantity} шт."
    )


def build_expiry_report(medicines: List[db.Medicine], today: date) -> str:
    expired, expiring, fine = [], [], []

    for med in medicines:
        days = med.days_left(today)
        line = f"• {med.name} — {expiry_status(days)} ({med.quantity} шт.)"
        if days < 0:
            expired.append(line)
        elif days <= EXPIRY_WARNING_DAYS:
            expiring.append(line)
        else:
            fine.append(f"• {med.name} — годен до {format_date(med.expiry_date)}")

    sections = []
    if expired:
        sections.append("🚫 Просрочены:\n" + "\n".join(expired))
    if expiring:
        sections.append(
            f"⚠️ Истекают в ближайшие {days_word(EXPIRY_WARNING_DAYS)}:\n"
            + "\n".join(expiring)
        )
    if fine:
        sections.append("✅ В порядке:\n" + "\n".join(fine))
    return "\n\n".join(sections)


# --- Клавиатуры -----------------------------------------------------------

def main_menu() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(BTN_LIST, BTN_ADD)
    markup.row(BTN_EXPIRY, BTN_DELETE)
    return markup


def medicines_keyboard(medicines: List[db.Medicine], action: str,
                       icon: str = "") -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    for med in medicines:
        label = f"{icon}{med.name} (до {format_date(med.expiry_date)}, {med.quantity} шт.)"
        markup.add(types.InlineKeyboardButton(label, callback_data=f"{action}:{med.id}"))
    return markup


def card_keyboard(medicine_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("← К списку", callback_data="list"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"ask_delete:{medicine_id}"),
    )
    return markup


def confirm_keyboard(medicine_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Да, удалить", callback_data=f"delete:{medicine_id}"),
        types.InlineKeyboardButton("Отмена", callback_data="cancel"),
    )
    return markup


# --- Экраны (текст + клавиатура) ------------------------------------------
# Возвращают пару, чтобы один и тот же экран можно было и отправить новым
# сообщением, и подставить в уже существующее через edit_message_text.

def list_screen(user_id: int):
    medicines = db.get_medicines(user_id)
    if not medicines:
        return "📭 Аптечка пуста. Добавьте лекарство командой /new", None
    return "📚 Ваши лекарства:", medicines_keyboard(medicines, "show")


def delete_screen(user_id: int):
    medicines = db.get_medicines(user_id)
    if not medicines:
        return "📭 Удалять нечего — аптечка пуста.", None
    markup = medicines_keyboard(medicines, "ask_delete", icon="🗑 ")
    markup.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))
    return "Что удалить?", markup


# --- Команды и кнопки меню -----------------------------------------------

@bot.message_handler(commands=["start"])
def cmd_start(message):
    name = message.from_user.first_name or "друг"
    bot.send_message(
        message.chat.id,
        f"Привет, {name}! Я помогу вести учёт домашней аптечки "
        f"и следить за сроками годности.\n\n{HELP_TEXT}",
        reply_markup=main_menu(),
    )


@bot.message_handler(commands=["help", "instruction"])
def cmd_help(message):
    bot.send_message(message.chat.id, HELP_TEXT, reply_markup=main_menu())


@bot.message_handler(commands=["list"])
def cmd_list(message):
    text, markup = list_screen(message.from_user.id)
    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.message_handler(commands=["delete"])
def cmd_delete(message):
    text, markup = delete_screen(message.from_user.id)
    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.message_handler(commands=["time"])
def cmd_time(message):
    today = date.today()
    medicines = db.get_medicines(message.from_user.id)
    if not medicines:
        bot.send_message(message.chat.id, "📭 Аптечка пуста. Добавьте лекарство командой /new")
        return

    markup = None
    if any(med.days_left(today) < 0 for med in medicines):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "🗑 Удалить все просроченные", callback_data="delete_expired"))

    report = "📊 Сроки годности\n\n" + build_expiry_report(medicines, today)
    bot.send_message(message.chat.id, report, reply_markup=markup)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    # Сюда попадаем, только если никакого сценария сейчас не идёт.
    bot.send_message(message.chat.id, "Сейчас нечего отменять.", reply_markup=main_menu())


# --- Добавление лекарства (пошаговый диалог) ------------------------------

def is_cancelled(message) -> bool:
    """Любая команда во время диалога прерывает добавление."""
    if message.text and message.text.startswith("/"):
        bot.send_message(message.chat.id, "Добавление отменено.", reply_markup=main_menu())
        return True
    return False


def ask(chat_id: int, text: str, next_step, *args) -> None:
    msg = bot.send_message(chat_id, text)
    bot.register_next_step_handler(msg, next_step, *args)


@bot.message_handler(commands=["new"])
def cmd_new(message):
    bot.send_message(
        message.chat.id,
        "Добавляем лекарство. Чтобы прервать, отправьте /cancel",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    ask(message.chat.id, "Как называется лекарство?", receive_name)


def receive_name(message):
    if is_cancelled(message):
        return
    name = (message.text or "").strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        ask(message.chat.id,
            f"Название должно быть текстом до {MAX_NAME_LENGTH} символов. Попробуйте ещё раз:",
            receive_name)
        return
    ask(message.chat.id, "Добавьте описание (или отправьте «-», чтобы пропустить):",
        receive_description, name)


def receive_description(message, name):
    if is_cancelled(message):
        return
    if message.text is None:
        ask(message.chat.id, "Нужен текст. Введите описание или «-»:",
            receive_description, name)
        return
    description = "" if message.text.strip() == "-" else message.text.strip()
    ask(message.chat.id, "Срок годности? Например, 25.12.2026",
        receive_expiry, name, description)


def receive_expiry(message, name, description):
    if is_cancelled(message):
        return
    expiry_date = parse_date(message.text or "")
    if expiry_date is None:
        ask(message.chat.id, "Не получилось разобрать дату. Введите в формате ДД.ММ.ГГГГ:",
            receive_expiry, name, description)
        return
    ask(message.chat.id, "Сколько штук?", receive_quantity, name, description, expiry_date)


def receive_quantity(message, name, description, expiry_date):
    if is_cancelled(message):
        return
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) == 0:
        ask(message.chat.id, "Введите целое число больше нуля:",
            receive_quantity, name, description, expiry_date)
        return

    db.add_medicine(message.from_user.id, name, description, expiry_date, int(text))
    bot.send_message(message.chat.id, f"✅ «{name}» добавлено в аптечку", reply_markup=main_menu())


# Кнопки нижнего меню. Этот обработчик регистрируется последним среди
# текстовых, поэтому команды выше до него не доходят.
MENU_ACTIONS = {
    BTN_LIST: cmd_list,
    BTN_ADD: cmd_new,
    BTN_EXPIRY: cmd_time,
    BTN_DELETE: cmd_delete,
}


@bot.message_handler(content_types=["text"])
def on_text(message):
    action = MENU_ACTIONS.get(message.text)
    if action:
        action(message)
    else:
        bot.send_message(message.chat.id, "Не понял 🤔 Воспользуйтесь меню или /help",
                         reply_markup=main_menu())


# --- Инлайн-кнопки --------------------------------------------------------

def callback_id(call) -> int:
    return int(call.data.split(":", 1)[1])


def edit(call, text: str, markup=None) -> None:
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "list")
def on_list(call):
    bot.answer_callback_query(call.id)
    edit(call, *list_screen(call.from_user.id))


@bot.callback_query_handler(func=lambda call: call.data.startswith("show:"))
def on_show(call):
    med = db.get_medicine(call.from_user.id, callback_id(call))
    if med is None:
        bot.answer_callback_query(call.id, "Лекарство уже удалено", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    edit(call, medicine_card(med, date.today()), card_keyboard(med.id))


@bot.callback_query_handler(func=lambda call: call.data.startswith("ask_delete:"))
def on_ask_delete(call):
    med = db.get_medicine(call.from_user.id, callback_id(call))
    if med is None:
        bot.answer_callback_query(call.id, "Лекарство уже удалено", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    edit(call, f"Удалить «{med.name}»?", confirm_keyboard(med.id))


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete:"))
def on_delete(call):
    user_id = call.from_user.id
    med = db.get_medicine(user_id, callback_id(call))
    if med is None or not db.delete_medicine(user_id, med.id):
        bot.answer_callback_query(call.id, "Лекарство уже удалено", show_alert=True)
        return
    bot.answer_callback_query(call.id, "Удалено")
    edit(call, f"🗑 «{med.name}» удалено из аптечки")


@bot.callback_query_handler(func=lambda call: call.data == "delete_expired")
def on_delete_expired(call):
    count = db.delete_expired(call.from_user.id, date.today())
    bot.answer_callback_query(call.id)
    if count == 0:
        edit(call, "Просроченных лекарств уже нет")
    else:
        edit(call, f"🗑 Удалено просроченных позиций: {count}")


@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def on_cancel(call):
    bot.answer_callback_query(call.id)
    edit(call, "Удаление отменено")


if __name__ == "__main__":
    db.init_db()
    print("Бот запущен")
    bot.infinity_polling()
