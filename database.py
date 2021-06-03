import config
import messages
from telebot import types
from vk_api.keyboard import VkKeyboard
import datetime
import time
import sqlite3 as sql
from helpers import vk_send_message, get_info, update_clients, log_report, bot, fb_bot, gc


# --------------------------------------------------
def update_db():
    """ First add new clients to DB, then update those who are not clients anymore """

    # Get current tariffs info
    fin_acc = gc.open_by_key(config.sheets_fin_token).worksheet('Тарифы')
    tariffs_info = [row[:5] for row in fin_acc.get_all_values()[1:]]
    time.sleep(1)

    # Get all actual clients info
    acc = gc.open_by_key(config.sheets_clients_token).worksheet('v2clients')
    all_values = acc.get_all_values()[4:]
    email = [i[4].lower() for i in all_values]
    date = [i[5] for i in all_values]
    tariff = [i[2] for i in all_values]
    sub = [i[6] for i in all_values]

    with sql.connect(config.db_file) as con:
        cur = con.cursor()

        # update tariffs info
        cur.execute(f"DELETE FROM tariffs")
        cur.executemany(f"INSERT INTO tariffs VALUES (?,?,?,?,?);", tariffs_info)

        # update clients info
        cur.execute("SELECT * FROM clients")
        res = cur.fetchall()

        db_emails = [i[0] for i in res]

        # Check for every client from google sheets
        for i, address in enumerate(email):
            client = (address, date[i], tariff[i], sub[i], 0, 0, 0, "CLOSED", "0", "0", "NO", 0, 0)

            # Insert new row
            if address not in db_emails:
                cur.execute(f"INSERT INTO clients VALUES ({','.join(['?' for _ in client])})", client)
                print(f"New client: {client[:3]}")

            # Update existing row
            else:
                cur.execute("UPDATE clients SET date = ?, tariff = ?, sub = ? WHERE email = ?",
                            client[1:4] + client[0:1])

        # Check for every client from DB that is off from google sheets and update his tariff info in DB
        for i, address in enumerate(db_emails):
            if address not in email:

                if address == "mdazhidkov@gmail.com":
                    continue

                cur.execute("UPDATE clients SET date = '-', tariff = '-', sub = '-' WHERE email = ?",
                            (address,))


# --------------------------------------------------
def reminder():
    """ Gather info about expiring tariffs and notify clients """

    with sql.connect(config.db_file) as con:
        cur = con.cursor()
        cur.execute("SELECT date, tg_id, vk_id, fb_id FROM clients")
        clients = cur.fetchall()

    today = datetime.datetime.today()
    notified_clients = set()

    for cl in clients:

        # Not our client anymore
        if cl[0] == "-":
            continue

        date = cl[0].split('.')  # Date is stored in dd.mm.yyyy format
        date = datetime.datetime(int(date[2]), int(date[1]), int(date[0]), 0, 0, 0)

        time_left = date - today
        time_left = (time_left.days * 24 * 60 * 60) + time_left.seconds

        for type_id, user_id in zip(['tg_id', 'vk_id', 'fb_id'], cl[1:4]):
            notify_clients(type_id, user_id, time_left, notified_clients)

    # Update pinned message with info about those who were reminded
    if notified_clients:
        text = "\U0001F514 Напомнил об оплате:\n"
        for i in notified_clients:
            text += i + "\n"

        # update_pinned_bottom(text)


# --------------------------------------------------
def notify_clients(type_id, id, time_left, notified_clients):
    """ Check if time_left is 3 days or 1 day in seconds (minus 18 hours so we remind at 18:00 Beijing).
     Gap is 59 seconds because cycle repeats every 60 seconds, so it will not repeat on 1-60 'borders' """

    if id == "0":
        return

    message = ""

    if 194341 <= time_left <= 194400:  # 3 days left
        message = messages.left3days
    elif 21541 <= time_left <= 21600:  # 1 day left
        message = messages.left1day
    elif -64859 <= time_left <= -64800:  # Tariff expired
        message = messages.left_today

    if message:
        time.sleep(1)
        if type_id == "tg_id":
            buttons = types.InlineKeyboardMarkup()
            buttons.add(types.InlineKeyboardButton(text="\U0001F4B4 Оплата", callback_data="pay"))
            bot.send_message(int(id), message, reply_markup=buttons)
        elif type_id == "vk_id":
            keyboard = VkKeyboard(inline=True)
            keyboard.add_button("\U0001F4B4Оплата")
            vk_send_message(id, message, keyboard.get_keyboard())
        elif type_id == "fb_id":
            fb_bot.send_text_message(int(id), message)

        update_clients([type_id, id], ['state', 'REMINDED'])
        notified_clients.add(get_info("email", type_id, id))

        print(f"{datetime.datetime.today().date()} Notification sent to {type_id} {id}\n")


# --------------------------------------------------
def main():
    print('\nDatabase running')
    while True:
        try:
            update_db()

            # Update DB every 15 minutes
            for i in range(15):
                reminder()
                time.sleep(60)

        except Exception as e:
            print("DB error, restarting")
            print(e)
            log_report("DB", e)
            time.sleep(3)
