import config
import messages
import telebot
from telebot import types
import vk_api
from vk_api.keyboard import VkKeyboard
from pymessenger import Button
from pymessenger.bot import Bot
import gspread
import datetime
import re
import time
import random
import sys
import sqlite3 as sql
import json
import requests

# Telegram bot
bot = telebot.TeleBot(config.tg_token, skip_pending=True)

# Vkontakte bot
vk_session = vk_api.VkApi(token=config.token_vk)
vk = vk_session.get_api()

# Facebook bot
fb_bot = Bot(config.fb_access_token)

# Google sheets authorization
gc = gspread.service_account(filename=config.cred_final)


def send_msg_to_tg(message_data):
    bot.send_message(config.group_id, message_data)


def get_email_from_message(message):
    lines = message.split('\n')
    email = ""

    for line in lines:
        if line.startswith("email:"):
            email = line.split(":")[1].strip()
            break

    return email


# --------------------------------------------------
def vk_send_message(user_id, message, keyboard=None):
    """ Send message to VK user """

    time.sleep(1)
    random_id = random.randint(0, 2147483646)

    if keyboard:
        vk.messages.send(user_id=int(user_id), random_id=random_id, message=message, keyboard=keyboard)

    else:
        vk.messages.send(user_id=int(user_id), random_id=random_id, message=message)


# --------------------------------------------------
def db_find_value(col_name, value):
    """ Check if value exists in database and return dict with info from corresponding row.
        Argument 'col_name' must be name of DB column.
        Columns: email, date, tariff, sub, tg_id, vk_id, fb_id, state, rate, review_time, received, verified, prev_info_time """

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        cur.execute(f"SELECT * FROM clients WHERE {col_name} = ?", (str(value).lower(),))
        res = cur.fetchall()

        if res:
            columns = ('email', 'date', 'tariff', 'sub', 'tg_id', 'vk_id', 'fb_id', 'state',
                       'rate', 'review_time', 'received', 'verified', 'prev_info_time')

            return {col: value for col, value in zip(columns, res[0])}

        return 0


# --------------------------------------------------
def get_info(wanted_col, search_col, search_val):
    """ Find some column value by other corresponding column value """

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        cur.execute(f"SELECT {wanted_col} FROM clients WHERE {search_col} = '{search_val}'")
        info = cur.fetchall()

        if info:
            return info[0][0]

        return 0


# --------------------------------------------------
def client_info_msg(col_name, value):
    """ Make a message with client tariff info """

    info = db_find_value(col_name, value)
    if not info:
        return "No info about client"

    message = f"\U00002139\nemail: {info['email']}\n" \
              f"date: {info['date']}\n" \
              f"tariff: {info['tariff']}\n" \
              f"sub: {info['sub']}\n"

    return message


# --------------------------------------------------
def info_soon_check(user_id, type_id):
    """ Check if previous client info message was less than 5 minutes ago """

    previous = get_info('prev_info_time', type_id, user_id)
    time_past = int(time.time() - previous)

    if time_past < 300:
        return True
    else:
        update_clients([type_id, user_id], ['prev_info_time', time.time()])
        return False


# -------------------------------------------------
def get_open_dialogues():
    """ Returns list of clients with open dialogues
        If client has several IDs, pick one with priority tg > vk > fb
        ID is written in monospaced font (`number`) so we can easily copy it for search"""

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        cur.execute("SELECT tg_id, vk_id, fb_id FROM clients WHERE state in ('OPEN', 'PAY')")
        clients_open = cur.fetchall()

        for i, numbers in enumerate(clients_open):
            if numbers[0] != '0':

                try:
                    name = bot.get_chat(numbers[0]).first_name
                except Exception as e:
                    name = "Unknown"

                clients_open[i] = f"<code>{numbers[0]}</code> {name}"
                continue

            elif numbers[1] != '0':

                try:
                    name = vk.users.get(user_id=numbers[1])[0]['first_name']
                except Exception as e:
                    name = "Unknown"

                clients_open[i] = f"<code>{numbers[1]}</code> {name}"
                continue

            elif numbers[2] != '0':
                clients_open[i] = f"<code>{numbers[2]}</code> FB"
                continue

        return clients_open


# --------------------------------------------------
def update_pinned_top():
    """ Update upper part of pinned message that contains IDs of clients with open dialogues """

    # Pinned message text is stored in file
    with open(config.pinned_msg_path, "r+", encoding='utf-8') as file:
        op = get_open_dialogues()
        top = "\U0001F5E3 Открытые диалоги:\n" + "\n".join(op)
        bottom = file.read().split("==========")[1]
        new_full = top + "\n==========" + bottom

    with open(config.pinned_msg_path, "w", encoding='utf-8') as file:
        file.write(new_full)

    try:
        bot.edit_message_text(new_full, config.group_id, config.pinned_msg, parse_mode='HTML')
    except telebot.apihelper.ApiTelegramException:
        pass


# -------------------------------------------------
def update_pinned_bottom(emails_list):
    """ Update bottom part of pinned message that contains emails of clients who were reminded about expiring tariff """

    # Pinned message text is stored in file
    with open(config.pinned_msg_path, "r+") as file:
        top = file.read().split("==========")[0]
        bottom = emails_list
        new_full = top + "==========\n" + bottom

    with open(config.pinned_msg_path, "w") as file:
        file.write(new_full)

    bot.edit_message_text(new_full, config.group_id, config.pinned_msg, parse_mode='HTML')


# --------------------------------------------------
def update_clients(search_pair, *change_pairs):
    """ Update local database with new relation
        Search_pair and change_pairs args must be [DB column name, value] pairs and be even length
        DB columns in order: email, date, tariff, sub, tg_id, vk_id, fb_id, state, rate, review_time, received, verified """

    with sql.connect(config.db_file) as con:

        # Example: "tg_id = '123', vk_id = '456', fb_id = '789'"
        pairs = ", ".join([f"{i[0]} = '{i[1]}'" for i in change_pairs])

        cur = con.cursor()
        cur.execute(f"UPDATE clients SET {pairs} WHERE {search_pair[0]} = '{search_pair[1]}'")
        con.commit()


# --------------------------------------------------
def new_client(email, type_id, id):
    """ Add new row in database. For users who have specified mail that is not in the database """

    client = [email.lower(), "-", "-", "-", "0", "0", "0", "CLOSED", "0", "0", "NO", 0, 0]

    if type_id == "tg_id":
        client[4] = id
    elif type_id == "vk_id":
        client[5] = id
    elif type_id == "fb_id":
        client[6] = id

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        cur.execute(f"INSERT INTO clients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", client)

        con.commit()


# -------------------------------------------------
def delete_client(search_col, search_val):
    """ Delete row from DB (if only single row was found) """

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        cur.execute(f"SELECT * FROM clients WHERE {search_col} = ?", (search_val,))

        if len(cur.fetchall()) > 1:
            return f"В базе несколько значений с {search_col} = {search_val}! Отмена"

        cur.execute(f"DELETE FROM clients WHERE {search_col} = ?", (search_val,))
        con.commit()
        return f"Запись с {search_col} = {search_val} удалена\n"


# --------------------------------------------------
def open_dialogue(type_id, id, state="OPEN"):
    """ Change client state in DB to OPEN (or other) and update pinned message with new info"""

    update_clients([type_id, id], ["state", state])
    update_pinned_top()


# --------------------------------------------------
def close_dialogue(type_id, id, pay=False, silent=False, notify_admin_group=True):
    """ Change client state in DB to CLOSED and update pinned message with new info
        Optionally send client closing message """

    time.sleep(1)
    user_state = get_info('state', type_id, id)

    # Return if client not found in DB
    if not user_state:
        return

    # Point that dialogue is already closed and return to prevent multiple closing messages for client
    if user_state in ["CLOSED", "ONE MESSAGE"]:
        bot.send_message(config.group_id, "Диалог уже закрыт")
        return

    update_clients([type_id, id], ["state", "CLOSED"], ["rate", "0"], ["review_time", "0"], ["received", "NO"])

    if notify_admin_group:
        bot.send_message(config.group_id, f"Диалог закрыт\n{id}")

    update_pinned_top()

    if pay:
        update_clients([type_id, id], ["verified", 1])

    # Do not send any message to client
    if silent or pay:
        return

    if type_id == "tg_id":
        # Ask client to rate support
        buttons = types.InlineKeyboardMarkup()
        buttons.add(types.InlineKeyboardButton(text="\U0001F92C 1", callback_data="1"))
        buttons.add(types.InlineKeyboardButton(text="\U00002639	2", callback_data="2"))
        buttons.add(types.InlineKeyboardButton(text="\U0001F610 3", callback_data="3"))
        buttons.add(types.InlineKeyboardButton(text="\U0001F642 4", callback_data="4"))
        buttons.add(types.InlineKeyboardButton(text="\U0001F600 5", callback_data="5"))

        bot.send_message(id, messages.close, reply_markup=buttons)

    elif type_id == "vk_id":
        keyboard = VkKeyboard(inline=True)

        keyboard.add_button("\U0001F92C 1")
        keyboard.add_line()
        keyboard.add_button("\U00002639	2")
        keyboard.add_line()
        keyboard.add_button("\U0001F610 3")
        keyboard.add_line()
        keyboard.add_button("\U0001F642 4")
        keyboard.add_line()
        keyboard.add_button("\U0001F600 5")

        vk_send_message(id, messages.close, keyboard=keyboard.get_keyboard())

    elif type_id == "fb_id":
        buttons = [Button(title='\U0001F92C Плохо', type='postback', payload='2'),
                   Button(title='\U0001F610 Нормально', type='postback', payload='4'),
                   Button(title='\U0001F600 Отлично', type='postback', payload='5')]

        fb_bot.send_button_message(recipient_id=id, text=messages.close, buttons=buttons)


# --------------------------------------------------
def get_tariffs(*condition_pairs):
    """ Get list of tariffs by their price by condition pairs
        condition_pairs args must be [DB column name, value] pairs """

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        # condition string example: "tariff = '2' AND currency = 'Ю'"
        condition = " AND ".join([f"{i[0]} = '{i[1]}'" for i in condition_pairs])
        condition = "WHERE " + condition if condition else ''
        cur.execute(f"SELECT * FROM tariffs {condition}")
        result = cur.fetchall()

    return result


# --------------------------------------------------
def autopay(user_id, type_id, file, is_url=False):
    """ Detect text on image using OCR and process payment """

    # Check if the same image has been sent before
    if file == "File already in folder":
        return

    payload = {'isOverlayRequired': False,
               'apikey': config.ocr_token,
               'language': "eng",
               'OCREngine': '2'}

    if is_url:
        payload['url'] = file
        r = requests.post('https://api.ocr.space/parse/image', data=payload)
    else:
        with open(file, 'rb') as f:
            r = requests.post('https://api.ocr.space/parse/image', files={file: f}, data=payload)

    answer = json.loads(r.content.decode())
    process_payment(answer['ParsedResults'][0]['ParsedText'], user_id, type_id)


# --------------------------------------------------
def process_payment(parsed_text, user_id, type_id):
    """ Search for numbers that correspond to the current tariffs, consider it as payment if found """

    # Make dict containing all tariffs using price as key
    tariffs_dict = {
        t[0]: {'tariff_id': t[1], 'days': t[2], 'currency': t[3], 'description': t[4]}
        for t in get_tariffs()
    }

    # Find all matches for the "digits with or without dot or comma" pattern, for example "239,00", "1990"
    no_space_text = ''.join(parsed_text.split())
    for match in re.findall(r'[0-9]+[.,]?[0-9]*', no_space_text):

        # All tariffs prices are in roubles, so convert yuan to roubles, simply multiplying by 10
        if '.' in match or ',' in match:
            left_part = re.split(r'[,.]', match)[0]
            amount = str(int(left_part) * 10)
        else:
            amount = match

        if amount == '0':
            continue

        # Detected number corresponds to the current tariffs, confirm payment
        if amount in tariffs_dict:
            if type_id == 'email':
                email = user_id
            else:
                email = get_info('email', type_id, user_id)
                close_dialogue(type_id, user_id, pay=True, notify_admin_group=False)

            tariff, days, _, _ = tariffs_dict[amount].values()
            write_payment(email, amount)
            msg = f'\U0001F5F3 #автоплатеж\n_Email_: {email}\n_Сумма_: {amount}\n_Тариф_: {tariff}\n_Дней_: {days}'
            bot.send_message(config.group_id, msg, parse_mode='Markdown')
            time.sleep(1)
            return


# --------------------------------------------------
def write_payment(email, amount):
    """ Write payment info in .csv file """

    with open(config.base_file, 'a+') as file:
        text = f"{email};;;{amount}\n"
        file.write(text)


# --------------------------------------------------
def log_report(message, error):
    """ Write error info in log file """

    line_number = sys.exc_info()[2].tb_lineno

    with open('log.txt', 'a+') as log:
        log.write(f"{datetime.datetime.today()}\n{message}\n"
                  f"Line {line_number}\n{error}\n##################################\n\n")
