import asyncio
import datetime as dt
import functools
import logging
import os
import time
import pyimgur
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot, Dispatcher, types, executor
from aiogram import exceptions

from config import API_TOKEN, OWNER_ID, REQUESTS_PROXY, IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET, IMGUR_REFRESH_TOKEN, \
    IMGUR_ALBUM_ID
from dateutil import relativedelta as rd
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('asquik')

loop = asyncio.get_event_loop()
bot = Bot(token=API_TOKEN, loop=loop, parse_mode=types.ParseMode.MARKDOWN, proxy=REQUESTS_PROXY)
dp = Dispatcher(bot, loop=loop)

bot.users = {}
bot.start_time = dt.datetime.fromtimestamp(time.perf_counter())
bot.error_msg = None
_executor = ThreadPoolExecutor(10)

def bot_action(func):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        retval = None
        try:
            retval = await func(*args, **kwargs)
        except exceptions.BotBlocked:
            log.error(f"Unable to run {func.__name__}: blocked by user")
        except exceptions.ChatNotFound:
            log.error(f"Unable to run {func.__name__} invalid user ID")
        except exceptions.RetryAfter as e:
            log.error(f"Unable to run {func.__name__} Flood limit is exceeded. Sleep {e.timeout} seconds.")
            await asyncio.sleep(e.timeout)
            retval = await wrapped(*args, **kwargs)  # Recursive call
        except exceptions.UserDeactivated:
            log.error(f"Unable to run {func.__name__} user is deactivated")
        except exceptions.TelegramAPIError:
            log.exception(f"Unable to run {func.__name__} failed")
        return retval

    return wrapped


def access(access_number=0):
    def decorator(func):
        @wraps(func)
        async def wrapper(message, *args):
            user_access = bot.users[message.from_user.id]['access'] if message.from_user.id in bot.users else 0
            if user_access >= access_number:
                await func(message, *args)
            elif user_access > 0:
                if isinstance(message, types.CallbackQuery):
                    await answer_callback(message.id, "Not allowed!")
                else:
                    await send_message(message.from_user.id, "Not allowed!")

        return wrapper

    return decorator


@bot_action
async def send_message(chat_id, text, parse_mode=None, disable_web_page_preview=None, disable_notification=None,
                       reply_to_message_id=None, reply_markup=None):
    return await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=disable_web_page_preview,
                                  reply_to_message_id=reply_to_message_id, reply_markup=reply_markup,
                                  parse_mode=parse_mode, disable_notification=disable_notification)


@bot_action
async def edit_message(text, chat_id=None, message_id=None, inline_message_id=None, parse_mode=None,
                       disable_web_page_preview=None, reply_markup=None):
    return await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id,
                                       inline_message_id=inline_message_id,
                                       parse_mode=parse_mode,
                                       disable_web_page_preview=disable_web_page_preview, reply_markup=reply_markup)


@bot_action
async def edit_markup(chat_id=None, message_id=None, inline_message_id=None, reply_markup=None):
    return await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id,
                                               inline_message_id=inline_message_id, reply_markup=reply_markup)


@bot_action
async def delete_message(chat_id, message_id):
    return await bot.delete_message(chat_id=chat_id, message_id=message_id)


@bot_action
async def forward_message(chat_id, from_chat_id, message_id, disable_notification=None):
    return await bot.forward_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id,
                                     disable_notification=disable_notification)


@bot_action
async def send_chat_action(chat_id, action):
    return await bot.send_chat_action(chat_id=chat_id, action=action)


@bot_action
async def send_photo(chat_id, photo, caption=None, reply_to_message_id=None, reply_markup=None,
                     disable_notification=None):
    photo_arg = types.InputFile(photo) if os.path.exists(photo) else photo
    return await bot.send_photo(chat_id=chat_id, photo=photo_arg, caption=caption,
                                reply_to_message_id=reply_to_message_id,
                                reply_markup=reply_markup,
                                disable_notification=disable_notification)


@bot_action
async def answer_callback(callback_query_id, text=None, show_alert=None, url=None, cache_time=None):
    return await bot.answer_callback_query(callback_query_id=callback_query_id, text=text, show_alert=show_alert,
                                           url=url,
                                           cache_time=cache_time)


@bot_action
async def send_document(chat_id, document, reply_to_message_id=None, caption=None, reply_markup=None,
                        parse_mode=None, disable_notification=None):
    doc_arg = types.InputFile(document) if os.path.exists(document) else document
    return await bot.send_document(chat_id=chat_id, document=doc_arg, reply_to_message_id=reply_to_message_id,
                                   caption=caption, reply_markup=reply_markup,
                                   parse_mode=parse_mode, disable_notification=disable_notification)


async def msg_to_owner(text):
    return await send_message(OWNER_ID, str(text))


@dp.message_handler(types.ChatType.is_private, commands=['broadcast'])
@access(2)
async def broadcast_message(message):
    try:
        param = message.text.split()[1:]
    except IndexError:
        await send_message(message.chat.id, text="А что передавать?")
        return
    msg = f"Сообщение от {message.from_user.username}:\n{' '.join(param)}"
    # with session_scope() as session:
    #     for user, in session.query(User.user_id).filter(User.access >= 1).all():
    #         if user != message.chat.id:
    for user in bot.users:
        await send_message(user, msg)
        await asyncio.sleep(.05)
    await send_message(message.chat.id, text="Броадкаст отправлен.")


@dp.message_handler(types.ChatType.is_private, commands=['uptime'])
@access(1)
async def uptime(message):
    cur_time = dt.datetime.fromtimestamp(time.perf_counter())
    attrs = ['years', 'months', 'days', 'hours', 'minutes', 'seconds']
    date_parts = ["Лет", "Месяцев", "Дней", "Часов", "Минут", "Секунд"]

    def human_readable(delta):
        return ['{date_part}: {amount}'.format(amount=getattr(delta, attr), date_part=date_parts[n])
                for n, attr in enumerate(attrs) if getattr(delta, attr)]
    diff = ' '.join(human_readable(rd.relativedelta(cur_time, bot.start_time)))
    await send_message(message.chat.id, "Бот работает уже:\n" + diff)

def load_users():
    log.debug("Loading users")
    # with session_scope() as session:
    #     bot.users = {user: {"access": access, "limit": limit} for user, access, limit in
    #                  session.query(User.user_id, User.access, User.limit).all()}
    if not bot.users:
        bot.users = {OWNER_ID: {"access": 100}}
    log.debug(f'Loaded users: {", ".join(str(user) for user in bot.users.keys())}')

load_users()

async def in_thread(func, *args, **kwargs):
    return await loop.run_in_executor(_executor, functools.partial(func, *args, **kwargs))


def gen_imgur_markup(url):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton(text="Direct", url=url))
    markup.row(types.InlineKeyboardButton(text="IQDB", url=f"http://iqdb.org/?url={url}"),
               types.InlineKeyboardButton(text="Google",
                                    url=f"https://www.google.com/searchbyimage?image_url={url}&hl=ru&newwindow=1"))
    markup.row(types.InlineKeyboardButton(text="Trace.moe", url=f"https://trace.moe/?url={url}"),
               types.InlineKeyboardButton(text="SauceNao",
                                    url=f"https://saucenao.com/search.php?db=999&dbmaski=32768&url={url}"),
               types.InlineKeyboardButton(text="TinEye", url=f"https://tineye.com/search?url={url}"))
    return markup


@dp.message_handler(types.ChatType.is_private, content_types=types.ContentType.PHOTO)
async def imgurize(message):
    im = pyimgur.Imgur(IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET)
    im.refresh_token = IMGUR_REFRESH_TOKEN
    im.refresh_access_token()

    file_id = message.photo[-1].file_id
    file_obj = await bot.get_file(file_id)
    dest = file_obj.file_path.replace('photos/', '')
    await bot.download_file(file_obj.file_path, dest)
    await send_chat_action(message.chat.id, 'upload_photo')
    log.debug(f"Image uploading begin")
    uploaded_image = await in_thread(im.upload_image, path=dest, album=IMGUR_ALBUM_ID)
    log.debug(f"Image uploaded")
    await send_photo(message.chat.id,types.InputMediaPhoto(file_id),uploaded_image.link)
    await send_message(message.chat.id, "Ссылка на Imgur'е", reply_markup=gen_imgur_markup(uploaded_image.link))
    os.remove(dest)


if __name__ == '__main__':
    executor.start_polling(dp)
