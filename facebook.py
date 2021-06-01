import config
import messages
from pymessenger import Button
import requests
import json
import datetime
import re
import time
from flask import Flask, request
from helpers import get_info, open_dialogue, update_clients, db_find_value, log_report,  \
                    new_client, info_soon_check, client_info_msg, bot, fb_bot

app = Flask(__name__)


# --------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def receive_message():

    # Facebook verification
    if request.method == 'GET':
        token_sent = request.args['hub.verify_token']
        return verify_fb_token(token_sent)

    else:
        output = request.get_json()

        for event in output['entry']:
            messaging = event['messaging']

            for message in messaging:
                message_handler(message)

        return "Message Processed"


# --------------------------------------------------
def message_handler(message):
    """ Check if user ID in base or ask for email, transfer message to TG group if identified client """

    time.sleep(1)
    user_id = message['sender']['id']

    # Do not react on our own messages
    if user_id == config.fb_group_id:
        return

    text = message['message'].get('text') if message.get('message') else ""
    payload = message['postback'].get('payload') if message.get('postback') else None
    user_info = db_find_value("fb_id", user_id)

    # User ID not found in DB
    if not user_info:

        # Check if message text has '@' between some non-space symbols
        if not text or not re.findall(r"\S+@\S+", text):
            fb_bot.send_text_message(user_id, messages.send_email)
            return

        # Suppose user entered email, look for it in database
        email = re.findall(r"\S+@\S+", text)[0].lower()
        email_info = db_find_value("email", email)

        # Email not found, insert new row in DB with that email and user ID
        if not email_info:
            new_client(email, "fb_id", user_id)
            send_initial_buttons(user_id)

        # Email is already used by user with other ID, ask to immediately contact us
        elif email_info['fb_id'] != "0":
            new_client("-", "fb_id", user_id)
            open_dialogue("fb_id", user_id)
            fb_bot.send_text_message(user_id, messages.email_already_used)

        # Email found in DB and not used by other ID, update DB
        else:
            update_clients(["email", email], ["fb_id", user_id])
            send_initial_buttons(user_id)

        return

    # User pushed buttons
    if payload in ["pay", "trial", "sup", "turk", "urgent", "other", "rub", "yuan", "install", "sup_other",
                   "wish", "2", "4", "5"]:
        buttons_handler(user_id, payload)

        return

    user_state = user_info['state']
    # User identified, dialogue is open, transfer message to support
    if user_state in ["OPEN", "REMINDED", "PAY"]:
        forward_fb_to_tg(message)

        # Notify user that we received his message (once per dialogue)
        if user_info['received']:
            fb_bot.send_text_message(user_id, "Ваше сообщение передано в поддержку. "
                                              "Мы постараемся ответить как можно быстрее!")
            update_clients(["fb_id", user_id], ["received", "YES"])

        if user_state == "REMINDED":
            open_dialogue("fb_id", user_id)

        return

    # User identified, dialogue is closed, ask him to use buttons
    elif user_state == "CLOSED":
        send_initial_buttons(user_id, reply=True)
        return

    # User pushed the feedback button after previous support conversation was closed.
    # Suppose user entering one-message review
    elif user_state == "ONE MESSAGE":
        time_past = int(time.time()) - int(user_info['review_time'])

        if time_past // 3600 >= 24:
            fb_bot.send_text_message(user_id, messages.buttons_menu)

        else:
            forward_fb_to_tg(message, review=True)
            fb_bot.send_text_message(user_id, "Спасибо за отзыв!")

        update_clients(["fb_id", user_id], ["state", "CLOSED"])


# --------------------------------------------------
def send_initial_buttons(id, reply=False):
    """ Send message with starting buttons """

    time.sleep(1)
    buttons = [Button(title='\U0001F4B4Оплата', type='postback', payload='pay'),
               Button(title='\U00002753Поддержка', type='postback', payload='sup'),
               Button(title='Другое', type='postback', payload='other')]

    text = messages.push_buttons if reply else messages.buttons_menu
    fb_bot.send_button_message(recipient_id=id, text=text, buttons=buttons)


# --------------------------------------------------
def support(user_id, urgent=False):
    """ Handles every attempt to open support dialogue. Do not open if not urgent and not in working time """

    time.sleep(1)
    if not urgent:

        # User trying to contact support in non working time
        if not 17 <= datetime.datetime.today().hour < 22 or datetime.datetime.today().isoweekday() in [6, 7]:
            buttons = [Button(title='Срочно', type='postback', payload='urgent')]

            fb_bot.send_button_message(user_id, messages.non_working, buttons)

            return

    open_dialogue("fb_id", user_id)

    buttons = [Button(title='Настройка', type='postback', payload='install'),
               Button(title='Другое', type='postback', payload='sup_other')]

    # Ask user to choose problem type
    msg = messages.type_support
    sub = get_info("sub", "fb_id", user_id)
    if sub != '-' and int(get_info("verified", "fb_id", user_id)):
        msg += f"\U000026A1 Ваша подписка: {sub}"
    fb_bot.send_button_message(user_id, msg, buttons)


# --------------------------------------------------
def buttons_handler(user_id, payload):
    """ Handles all available buttons """

    time.sleep(1)
    if payload == "pay":
        open_dialogue("fb_id", user_id, state="PAY")

        buttons = [Button(title='Рубли ₽ / Гривны ₴', type='postback', payload='rub'),
                   Button(title='Юани ¥', type='postback', payload='yuan'),
                   Button(title='\U00002753Поддержка', type='postback', payload='sup')]

        fb_bot.send_button_message(user_id, messages.pay_type, buttons)

    elif payload == "trial":

        buttons = [Button(title='\U0001F4B4Оплата', type='postback', payload='pay'),
                   Button(title='\U00002753Поддержка', type='postback', payload='sup')]

        fb_bot.send_button_message(user_id, messages.trial_text_vk, buttons)

    elif payload == "turk":

        buttons = [Button(title="Сайт обслуживания", type='web_url', url="http://tm.zgc.su"),
                   Button(title="Как подключить?", type='web_url',
                          url="https://sites.google.com/view/zgcvpn/try?authuser=0")]
        fb_bot.send_button_message(user_id, messages.turk, buttons)

    elif payload == "sup":
        support(user_id)

    elif payload == "urgent":
        support(user_id, urgent=True)

    elif payload == "other":

        buttons= [Button(title='\U0001F193Попробовать', type='postback', payload='trial'),
                  Button(title='\U0001F1F9\U0001F1F2Туркменистан', type='postback', payload='turk'),
                  Button(title='\U0001F6D2ZGC SHOP', type='web_url', url='https://market.zgc.su')]
        fb_bot.send_button_message(user_id, messages.buttons_menu, buttons)

    elif payload == "rub":
        fb_bot.send_text_message(user_id, messages.rub_text_vk)

    elif payload == "yuan":
        fb_bot.send_text_message(user_id, messages.yuan_text_vk)

    elif payload == "install":
        fb_bot.send_text_message(user_id, messages.first_install)

    elif payload == "sup_other":
        fb_bot.send_text_message(user_id, messages.support_vk)

    # If user rated quality less than 5 and pushed feedback button, open dialogue for one message only
    elif payload == "wish":
        fb_bot.send_text_message(user_id, messages.get_better)
        update_clients(["fb_id", user_id], ["state", "ONE MESSAGE"], ["review_time", f"{int(time.time())}"])

    # Buttons to rate the quality of support
    elif payload in ["2", "4", "5"]:

        # User has already rated
        if get_info("rate", "fb_id", user_id) != "0":
            fb_bot.send_text_message(user_id, "Вы уже поставили оценку, спасибо!")
            return

        # Ask user to make review if he gave the highest rate
        if payload == "5":
            buttons = [Button(title="\U0001F49B Отзыв", type='web_url',
                              url=config.review_link)]

            fb_bot.send_button_message(user_id, "Если вам понравился наш сервис - оставьте отзыв, "
                                                "и мы предоставим вам 10 дней бесплатного VPN!\n\n"
                                                "Когда оставите отзыв свяжитесь с нами для получения бонуса",
                                       buttons)

        # Ask user to write feedback
        else:
            buttons = [Button(title='\U0001F4A1 Пожелание', type='postback', payload='wish')]
            fb_bot.send_button_message(user_id, "Мы можем что-то улучшить в обслуживании?", buttons)

        bot.send_message(config.group_id, f"Клиент `{user_id}` поставил вам {payload}", parse_mode='Markdown')
        update_clients(["fb_id", user_id], ["rate", payload])


# --------------------------------------------------
def forward_fb_to_tg(message, review=False):
    """ Send client message to support with client tariff info"""

    time.sleep(1)
    user_id = message['sender']['id']

    # Get user info by FB ID
    req = requests.get(
        f"https://graph.facebook.com/{user_id}?fields=first_name,last_name&access_token={config.fb_access_token}")
    user_info = json.loads(req.text)

    # Upper part of the message with emoji and name of the user
    top = "\U0001F4E2 Отзыв\n" if review else f"\U0001F4AC {user_info['first_name']} {user_info['last_name']}\n"

    # Bottom part of the message with id and social network name, so we can reply back
    bottom = f"{str(user_id)} Facebook"

    text = message['message'].get('text') or ''
    attachments = message['message'].get('attachments')

    if attachments:

        # Check if already sent caption
        caption_send = 0

        for att in attachments:
            message = top

            # Send photo only with ID info caption, without message text
            if not caption_send:
                message += text + "\n"

                # Change this so we don't send the same caption with other photo
                caption_send = 1

            message += "\n"

            # Add client tariff info
            if not info_soon_check(user_id, 'vk_id'):
                message += "\n" + client_info_msg("fb_id", user_id)

            message += bottom

            if att['type'] == 'image':
                bot.send_photo(config.group_id, att['payload']['url'], message)
    else:
        message = top + text + "\n\n"

        # Add client tariff info
        if not info_soon_check(user_id, 'fb_id'):
            message += "\n" + client_info_msg("fb_id", user_id)

        message += bottom

        bot.send_message(config.group_id, message)


# --------------------------------------------------
def verify_fb_token(token_sent):
    """ FB verification function """

    if token_sent == config.fb_verify_token:
        return request.args['hub.challenge']
    else:
        return 'Invalid verification token'


# --------------------------------------------------
def main():
    while True:
        try:
            print('\nFacebook running')
            app.run(port=6262,
                    ssl_context=(config.ssl_context1, config.ssl_context2))

        except Exception as e:
            print("FB error, restarting")
            log_report("FB", e)
            time.sleep(3)