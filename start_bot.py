import threading
import telegram as tg
import vkontakte as vk
import facebook as fb
import database as db

t1 = threading.Thread(target=tg.main)
t2 = threading.Thread(target=vk.main)
#t3 = threading.Thread(target=fb.main)
t4 = threading.Thread(target=db.main)

t1.start()
t2.start()
#t3.start()
t4.start()
