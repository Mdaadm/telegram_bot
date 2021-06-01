import config
import messages
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard
import datetime
import re
import time
from helpers import vk_send_message, get_info, open_dialogue, update_clients, db_find_value, new_client, \
    info_soon_check, client_info_msg, log_report, bot, vk_session, vk, autopay


# --------------------------------------------------
def reply_keyboard():
    """ Return default reply keyboard """

    keyboard = VkKeyboard()
    keyboard.add_button("\U0001F4B4Оплата")
    keyboard.add_button("\U0001F193Попробовать")
    keyboard.add_line()
    keyboard.add_button("\U0001F1F9\U0001F1F2Туркменистан")
    keyboard.add_button("\U0001F4F0Узнать больше")
    keyboard.add_line()
    keyboard.add_button("\U0001F6D2ZGC SHOP")
    keyboard.add_button("\U0001F91DСотрудничество")
    keyboard.add_line()
    keyboard.add_button("\U00002753Связаться с поддержкой")

    return keyboard.get_keyboard()


def vk_support(user_id, urgent=False):
    """ Handles every attempt to open support dialogue. Does not open if not urgent and not in working time """

    time.sleep(1)
    keyboard = VkKeyboard(inline=True)

    if not urgent:

        # User trying to contact support in non working time
        if not 17 <= datetime.datetime.today().hour < 22 or datetime.datetime.today().isoweekday() in [6, 7]:
            keyboard.add_button("Срочная связь")

            vk_send_message(user_id, messages.non_working, keyboard.get_keyboard())

            return

    open_dialogue("vk_id", user_id)

    keyboard.add_button("Первичная настройка")
    keyboard.add_line()
    keyboard.add_button("Другое")
    keyboard.add_line()
    keyboard.add_button("ZGC SHOP")

    # Ask user to choose problem type
    msg = messages.type_support
    user_info = db_find_value('vk_id', user_id)
    sub = user_info['sub']
    if sub != '-' and int(user_info['verified']):
        msg += f"\U000026A1 Ваша подписка: {sub}"
    vk_send_message(user_id, msg, keyboard.get_keyboard())


def buttons_handler(user_id, button_text):
    """ Handles all available buttons """

    if button_text == "\U0001F4B4Оплата":
        open_dialogue("vk_id", user_id, state="PAY")

        keyboard = VkKeyboard(inline=True)
        keyboard.add_button("В рублях ₽ или в гривнах ₴")
        keyboard.add_line()
        keyboard.add_button("В юанях ¥")
        keyboard.add_line()
        keyboard.add_button("\U00002753Связаться с поддержкой")

        vk_send_message(user_id, messages.pay_type, keyboard.get_keyboard())

    elif button_text == "В рублях ₽ или в гривнах ₴":
        vk_send_message(user_id, messages.rub_text_vk, reply_keyboard())

    elif button_text == "В юанях ¥":
        vk_send_message(user_id, messages.yuan_text_vk, reply_keyboard())

    elif button_text == "\U0001F193Попробовать":
        keyboard = VkKeyboard(inline=True)

        keyboard.add_button("\U0001F4B4Оплата")
        keyboard.add_line()
        keyboard.add_button("\U00002753Связаться с поддержкой")

        vk_send_message(user_id, messages.trial_text_vk, keyboard.get_keyboard())

    elif button_text == "\U00002753Связаться с поддержкой":
        vk_support(user_id)

    elif button_text == "Срочная связь":
        vk_support(user_id, urgent=True)

    elif button_text == "Первичная настройка":
        vk_send_message(user_id, messages.first_install, reply_keyboard())

    elif button_text == "Другое":
        vk_send_message(user_id, messages.support_vk, reply_keyboard())

    elif button_text == "ZGC SHOP":
        open_dialogue("vk_id", user_id)
        vk_send_message(user_id, "Здравствуйте! Укажите, пожалуйста, продукт и вопросы по нему", reply_keyboard())

    elif button_text == "\U0001F4F0Узнать больше":
        keyboard = VkKeyboard(inline=True)

        keyboard.add_openlink_button("Блог", "https://market.zgc.su/zgcvpnblog")

        vk_send_message(user_id, "Узнайте как заблокировать рекламу, какие появились сервера и многое другое",
                        keyboard.get_keyboard())

    elif button_text == "\U0001F1F9\U0001F1F2Туркменистан":
        keyboard = VkKeyboard(inline=True)

        keyboard.add_openlink_button("Сайт обслуживания", "http://tm.zgc.su")
        keyboard.add_line()
        keyboard.add_openlink_button("Как подключить?", "https://sites.google.com/view/zgcvpn/try?authuser=0")

        vk_send_message(user_id, messages.turk, keyboard.get_keyboard())

    elif button_text == "\U0001F6D2ZGC SHOP":
        keyboard = VkKeyboard(inline=True)

        keyboard.add_openlink_button("\U0001F6D2 ZGC SHOP", "https://market.zgc.su")
        keyboard.add_line()
        keyboard.add_button("Связаться с поддержкой")

        vk_send_message(user_id, messages.shop, keyboard.get_keyboard())

    elif button_text == "Связаться с поддержкой":
        open_dialogue("vk_id", user_id)
        vk_send_message(user_id, "Здравствуйте! Укажите, пожалуйста, продукт и вопросы по нему", reply_keyboard())

    elif button_text == "\U0001F91DСотрудничество":
        keyboard = VkKeyboard(inline=True)

        keyboard.add_openlink_button("Сделать предложение", "https://zgcvpn.ru/partnership")

        vk_send_message(user_id, messages.coop, keyboard.get_keyboard())

    # If user rated quality less than 5 and pushed feedback button, open dialogue for one message only
    elif button_text == "\U0001F4A1 Оставить пожелание":
        vk_send_message(user_id, messages.get_better)
        update_clients(["vk_id", user_id], ["state", "ONE MESSAGE"], ["review_time", f"{int(time.time())}"])

    # Buttons to rate the quality of support
    elif button_text in ["\U0001F92C 1", "\U00002639 2", "\U0001F610 3", "\U0001F642 4", "\U0001F600 5"]:
        keyboard = VkKeyboard(inline=True)

        # User has already rated
        if get_info("rate", "vk_id", user_id) != "0":
            vk_send_message(user_id, "Вы уже поставили оценку, спасибо!")
            return

        rating = button_text[-1]

        # Ask user to make review if he gave the highest rate
        if rating == "5":
            keyboard.add_openlink_button("\U0001F49B Оставить отзыв", config.review_link)

            vk_send_message(user_id, "Если вам понравился наш сервис - оставьте отзыв, "
                                     "и мы предоставим вам 10 дней бесплатного VPN!\n\n"
                                     "Когда оставите отзыв свяжитесь с нами для получения бонуса",
                            keyboard=keyboard.get_keyboard())

        # Ask user to write feedback
        else:
            keyboard.add_button("\U0001F4A1 Оставить пожелание")
            vk_send_message(user_id, "Мы можем что-то улучшить в обслуживании?", keyboard=keyboard.get_keyboard())

        time.sleep(1)
        bot.send_message(config.group_id, f"Клиент `{user_id}` поставил вам {rating}", parse_mode='Markdown')
        update_clients(["vk_id", user_id], ["rate", rating])


def vk_message_handler(event):
    """ Check if user id in base or ask for email, transfer message to TG group if identified client """

    user_id = event.user_id
    text = event.message
    user_info = db_find_value("vk_id", user_id)

    # User ID not found in DB
    if not user_info:

        # Check if message text has '@' between some non-space symbols
        if not text or not re.findall(r"\S+@\S+", text):
            vk_send_message(user_id, messages.send_email, reply_keyboard())
            return

        # Suppose user entered email, look for it in database
        email = re.findall(r"\S+@\S+", text)[0].lower()
        email_info = db_find_value("email", email)

        # Email not found, insert new row in DB with that email and user ID
        if not email_info:
            new_client(email, "vk_id", user_id)
            vk_send_message(user_id, messages.buttons_menu, reply_keyboard())

        # Email is already used by user with other ID, ask to immediately contact us
        elif email_info['vk_id'] != "0":
            new_client("-", "vk_id", user_id)
            open_dialogue("vk_id", user_id)
            vk_send_message(user_id, messages.email_already_used, reply_keyboard())

        # Email found in DB and not used by other ID, update DB
        else:
            update_clients(["email", email], ["vk_id", user_id])
            vk_send_message(user_id, messages.buttons_menu, reply_keyboard())

        return

    # User pushed button
    if text in ["\U0001F4B4Оплата", "\U0001F193Попробовать", "\U0001F1F9\U0001F1F2Туркменистан",
                "\U0001F4F0Узнать больше", "\U0001F6D2ZGC SHOP", "\U0001F91DСотрудничество",
                "\U00002753Связаться с поддержкой", "Срочная связь", "В рублях ₽ или в гривнах ₴",
                "В юанях ¥", "Первичная настройка", "Другое", "\U0001F92C 1", "\U00002639 2",
                "\U0001F610 3", "\U0001F642 4", "\U0001F600 5", "\U0001F4A1 Оставить пожелание",
                "ZGC SHOP", "Связаться с поддержкой"]:
        buttons_handler(user_id, text)

        return

    user_state = user_info['state']
    # User identified, dialogue is open, transfer message to support
    if user_state in ["OPEN", "REMINDED", "PAY"]:
        forward_vk_to_tg(event, user_state=user_state)

        # Notify user that we received his message (once per dialogue)
        if user_info['received']:
            vk_send_message(user_id, "Ваше сообщение передано в поддержку. "
                                     "Мы постараемся ответить как можно быстрее!", reply_keyboard())
            update_clients(["vk_id", user_id], ["received", "YES"])

        if user_state == "REMINDED":
            open_dialogue("vk_id", user_id, state="PAY")

        return

    # User identified, dialogue is closed, ask him to use buttons
    if user_state == "CLOSED":
        vk_send_message(user_id, messages.push_buttons, reply_keyboard())

        return

    # User pushed the feedback button after previous support conversation was closed.
    # Suppose user entering one-message review
    if user_state == "ONE MESSAGE":
        time_past = int(time.time()) - int(user_info['review_time'])

        # If user pushed the button more than a day ago, don't send his message to support
        if time_past // 3600 >= 24:
            vk_send_message(user_id, messages.buttons_menu)

        # Send review to support
        else:
            forward_vk_to_tg(event, review=True, user_state=user_state)
            vk_send_message(user_id, "Спасибо за отзыв!")

        update_clients(["vk_id", user_id], ["state", "CLOSED"])


# --------------------------------------------------
def forward_vk_to_tg(event, review=False, user_state='OPEN'):
    """ Send client message to support with attachments and client tariff info """

    time.sleep(1)
    user = vk.users.get(user_id=event.user_id)

    # Upper part of the message with emoji and name of the user
    top = "\U0001F4E2 Отзыв\n" if review else f"\U0001F4AC {user[0]['first_name']} {user[0]['last_name']}\n"

    # Bottom part of the message with id and social network name, so we can reply back
    check = "\U00002705" if get_info("verified", "vk_id", event.user_id) else ''
    bottom = f"{str(event.user_id)} Vkontakte{check}"
    attachments = vk.messages.getById(message_ids=event.message_id)['items'][0]['attachments']

    if attachments:

        # Checker to avoid sending more than one caption
        caption_sent = False

        # Checker to make sure attachment successfully sent to support
        attachment_sent = False

        for att in get_attachments(event.message_id):
            if att.get('filter') == 'photo':

                # Send photo only with ID info caption, without message text
                if caption_sent:
                    message = top + "\n" + bottom
                    bot.send_photo(config.group_id, att.get('url'), caption=message)
                    continue

                # Make sure we get string type anyway
                text = event.message or ""

                message = top + text + "\n\n"

                # Add client tariff info
                if not info_soon_check(event.user_id, 'vk_id'):
                    message += client_info_msg("vk_id", event.user_id)

                message += bottom
                bot.send_photo(config.group_id, att.get('url'), caption=message)
                attachment_sent = True

                # Change this so we don't send the same caption with other photo
                caption_sent = True

                # Autoprocess payment using OCR
                if user_state == 'PAY':
                    autopay(event.user_id, 'vk_id', att.get('url'), is_url=True)

        # notify support that user attached unsupported filetype
        if not attachment_sent:
            text = event.message or ""
            message = top + text + "\n_ОТ БОТА: клиент приложил в сообщение вконтакте файл, " \
                                   "который нельзя отправить в телеграм_\n\n"

            if not info_soon_check(event.user_id, 'vk_id'):
                message += client_info_msg("vk_id", event.user_id)

            message += bottom
            bot.send_message(config.group_id, message, parse_mode='Markdown')

    else:
        message = top + event.message + "\n\n"

        # Add client tariff info
        if not info_soon_check(event.user_id, 'vk_id'):
            message += "\n" + client_info_msg("vk_id", event.user_id)

        message += bottom
        bot.send_message(config.group_id, message)


# --------------------------------------------------
def get_attachments(msg):
    """ Collect message media, return list with attachments  """

    msg_attachments = vk.messages.getById(message_ids=msg)['items'][0]['attachments']
    attach_list = []

    for att in msg_attachments:

        # Collect photos
        if att.get('type') == 'photo':
            max_resolution_img = sorted(att['photo']['sizes'], key=lambda img: img.get('height'))[-1]
            max_resolution_img['filter'] = 'photo'
            attach_list.append(max_resolution_img)

        # collect voice messages
        elif att.get('type') == 'audio_message':
            att['filter'] = 'audio'
            attach_list.append(att)

    return attach_list


# --------------------------------------------------
def main():
    while True:
        try:
            print('\nVkontakte running')
            longpoll = VkLongPoll(vk_session)
            for event in longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                    vk_message_handler(event)

        except Exception as e:
            print("VK error, restarting")
            print(e)
            log_report("VK", e)
            time.sleep(3)