import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
from aiogram import F
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types.error_event import ErrorEvent
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, ChatMemberUpdated
from aiogram.filters import MEMBER, IS_NOT_MEMBER
import re
import mysql.connector
import os


TOKEN = os.getenv('TOKEN')
bot = Bot(TOKEN)
dp = Dispatcher()
ADMIN_ID = os.getenv('MAIN_ADMIN')

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASSWORD')
DB_DB = os.getenv('DB_NAME')


class FIO_INPUT(StatesGroup):
    text = State()

start_menu = types.ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text="/start")]],resize_keyboard=True)



async def connect():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_DB,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci'
    )
    cursor = conn.cursor()
    return conn, cursor

async def select_fio(fio:str)->tuple:
    conn, cursor = await connect()
    sql = "SELECT * FROM employee_table WHERE FIO = %s"
    val = (fio,)
    cursor.execute(sql, val)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

async def select_via_user_id(id:str)->tuple:
    conn, cursor = await connect()
    sql = "SELECT * FROM employee_table WHERE USER_ID=%s"
    val = (id,)
    cursor.execute(sql, val)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

async def update_fired(user_id:str)->None:
    conn, cursor = await connect()
    sql = "UPDATE employee_table SET FIRED=1 WHERE USER_ID=%s"
    val = (user_id,)
    cursor.execute(sql, val)
    conn.commit()
    cursor.close()
    conn.close()

async def update_employee(user_id:str, username:str, id:int)->None:
    conn, cursor = await connect()
    sql = "UPDATE employee_table SET USER_ID=%s, USERNAME=%s WHERE ID=%s"
    val = (user_id, username, id)
    cursor.execute(sql, val)
    conn.commit()
    cursor.close()
    conn.close()

async def select_chat_id(dep:str)->tuple:
    conn, cursor = await connect()
    sql = "SELECT CHAT_ID FROM chats_table WHERE DEPARTMENT=%s"
    val = (dep,)
    cursor.execute(sql, val)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

async def select_admins(dep:str)->tuple:
    conn, cursor = await connect()
    sql = "SELECT USER_ID FROM admins_table WHERE DEPARTMENT=%s"
    val = (dep,)
    cursor.execute(sql, val)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result

async def select_where_fired()->list:
    conn, cursor = await connect()
    sql = "SELECT * FROM employee_table WHERE FIRED=1"
    cursor.execute(sql)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result

async def select_admins_in_dep(dep:str)->list:
    conn, cursor = await connect()
    sql = "SELECT USER_ID FROM admins_table WHERE DEPARTMENT=%s"
    val = (dep,)
    cursor.execute(sql, val)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result

async def reminder():
    while True:
        await asyncio.sleep(60)
        result = await select_where_fired()
        for user in result:
            dep = user[2]
            chat_res = await select_chat_id(dep)
            chat_id = int(chat_res[0])
            try:
                member = await bot.get_chat_member(chat_id, user[4])
            except:
                continue
            status = member.status
            if status in ['creator','administrator','member']:
                admins = await select_admins_in_dep(dep)
                for admin in admins:
                    try:
                        await bot.send_message(int(admin[0]),f"{user[1]} (username: @{user[5]} user_id: {user[4]}) находится в чате отдела {dep}, но сотрудником уже не является")
                    except:
                        continue
        


@dp.message(Command('check_id'))
async def check_id(message: Message)->None:
    await message.answer(f"ID: {message.chat.id}")

@dp.message(F.chat.type=='private', Command('start'))
async def private_handler(message: Message,state:FSMContext)->None:
    await message.answer("Добрый день! Это бот PT, я отвечаю за распределение сотрудников по чатам. Пожалуйста, введите своё ФИО в формате: Иванов Иван Иванович-n\n\nГде -n - это число, которое вам выдал ваш руководитель, если такой сотрудник уже есть в базе данных. Его может не быть.",reply_markup=start_menu)
    await state.set_state(FIO_INPUT.text)
    info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) начал процесс привязки сотрудника к чату")

    
@dp.message(F.chat.type=='private', FIO_INPUT.text)
async def FIO_handler(message: Message,state:FSMContext)->None:
    fio_pattern = re.compile(r'[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+(?:-\d+)?')
    fio = message.text
    fios = fio_pattern.findall(fio)
    if len(fios)==0:
        await message.answer("Неправильный формат ФИО. Пожалуйста, введите своё ФИО в формате: Иванов Иван Иванович")
        return None
    result0 = await select_via_user_id(str(message.from_user.id))
    if result0 is not None:
        if fios[0] != result0[1]:
            await bot.send_message(ADMIN_ID,f'Событие безопасности. Пользователь с user_id: {message.from_user.id} и username @{message.from_user.username} пытается привязать к себе другого сотрудника. Пользователь: {fios[0]}')
            await message.answer('Вы попытались привязать к себе другого сотрудника. Администратор был предупреждён о ваших подозрительных действиях')
            info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) пытается привязать к себе другого сотрудника")
            return None
    result = await select_fio(fios[0])
    if result is None:
        await message.answer("Сотрудник не найден. Пожалуйста, проверьте правильность ввода ФИО и введите снова")
        info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) ввёл неправильное ФИО")
        return None
    db_id = result[0]
    dep = result[2]
    db_fired = result[3]
    db_user_id = result[4]
    if db_fired == 1:
        await message.answer("Вы не являетесь сотрудником PT, если считаете, что это ошибка, то обратитесь к администратору.")
        info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) пытается войти в чат под уволенным сотрудником")
        return None
    username = message.from_user.username
    user_id = message.from_user.id
    chat_id = await select_chat_id(dep)
    if chat_id is None:
        await message.answer("Чат для вашего отдела не найден. Обратитесь к администратору.")
        info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) пытается войти в несуществующий чат отдела")
        return None
    chat_id = int(chat_id[0])
    if db_user_id is not None:
        if str(db_user_id) != str(user_id):
            await message.answer("Пользователь с таким ФИО уже привязан к другому аккаунту. Обратитесь к администратору.")
            info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) пытается привязать уже существующего сотрудника")
            return None
        else:
            member = await bot.get_chat_member(chat_id, user_id)
            status = member.status
            if status in ['creator','administrator','member']:
                await message.answer("Вы уже в чате, наслаждайтесь",reply_markup=start_menu)
                info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) уже находится в чате")
                return None
            else:
                invite_link = await bot.create_chat_invite_link(chat_id,member_limit=1)
                await message.answer(f"Здравствуйте, {fios[0]}. Вероятно, вы случайно вышли из чата и потеряли свою инвайт-ссылку. Так вот же она: {invite_link.invite_link}",reply_markup=start_menu)
                info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) перезапросил ссылку в чат")
                return None
    await update_employee(str(user_id), username, db_id)
    invite_link = await bot.create_chat_invite_link(chat_id,member_limit=1)
    end_pattern = re.compile(r'-\d+')
    found = end_pattern.findall(fios[0])
    if found:
        fios[0] = fios[0].replace(found[0],'')
    await message.answer(f"Добро пожаловать, {fios[0]}. Вы принадлежите к отделу {dep}. Вот ваша инвайт-ссылка в чат отдела: {invite_link.invite_link}")
    await state.clear()
    info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) успешно привязал себя к чату отдела {dep}")

@dp.message(F.chat.type=='private',Command('fired'), F.from_user.id==ADMIN_ID)
async def fired_handler(message: Message)->None:
    spliter = message.text.split(' ')
    if len(spliter)!=2:
        await message.answer("Неправильный формат команды. Пожалуйста, введите команду в формате: /fired user_id")
        return None
    if spliter[1] == '':
        await message.answer("Неправильный формат команды. Пожалуйста, введите команду в формате: /fired user_id")
        return None
    if not spliter[1].isdigit():
        await message.answer("Неправильный формат команды. Пожалуйста, введите команду в формате: /fired user_id")
        return None
    user_id = str(spliter[1])
    await update_fired(user_id)
    await message.answer(f"Пользователь с user_id: {user_id} уволен")
    info_logger.info(f"Пользователь {message.from_user.username}({message.from_user.id}, {message.from_user.username}) уволил сотрудника с user_id: {user_id}")
    
@dp.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> MEMBER))
async def on_user_join(event: ChatMemberUpdated)->None:
    user_id = event.from_user.id
    result = await select_via_user_id(str(user_id))
    if result is None:
        await bot.ban_chat_member(event.chat.id, user_id)
        info_logger.info(f"Пользователь {event.from_user.username}({event.from_user.id}, {event.from_user.username}) пытается присоединиться к чату, но не находится в бд")
        return None
    dep = result[2]
    result_admin = await select_admins(dep)
    for admin in result_admin:
        await bot.send_message(admin[0],f"{result[1]} (username: @{result[5]} user_id: {result[4]}) присоединился к чату отдела {dep}")
    info_logger.info(f"Пользователь {result[1]}({result[4], result[5]}) присоединился к чату отдела {dep}Администраторы предупреждены")
    

    

### Error handlers
@dp.error(F.update.message.as_("message"))
async def handle_my_custom_exception(event: ErrorEvent, message: Message,state:FSMContext):
    text = ''
    if message.text is not None:
        text = message.text
    elif message.caption is not None:
        text = message.caption
    async with asyncio.Lock():
        error_logger.error(f"Ошибка: {event.exception} \nСообщение: {text} \nПользователь: {message.from_user.username}({message.from_user.id}, {message.from_user.username})")
    await bot.send_message(ADMIN_ID,f"Ошибка: {event.exception} \n\nСообщение: {text} \n\nПользователь: {message.from_user.username}({message.from_user.id}, {message.from_user.username})")
    await state.clear()

async def on_startup():
    print('Bot has been started')
    async with asyncio.Lock():
        info_logger.info('Bot has been started')

async def on_shutdown():
    print('Shutting down...')
    async with asyncio.Lock():
        info_logger.info('Shutting down...')
    logging.shutdown()

async def notify(message:str):
    if len(message)>3000:
        message = message[:3000]
    await bot.send_message(ADMIN_ID,message)

async def main():
    await on_startup()
    asyncio.create_task(reminder())
    await dp.start_polling(bot)

if __name__ == "__main__":
    info_logger = logging.getLogger("info")
    info_handler = TimedRotatingFileHandler("logs/info.log", when="midnight", interval=1, backupCount=120,errors='replace')
    info_logger.setLevel(logging.INFO)  # Изменено на INFO
    info_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    info_handler.setFormatter(info_formatter)
    info_logger.addHandler(info_handler)

    # Создание логгера для ошибок
    error_logger = logging.getLogger("error")
    error_hd = TimedRotatingFileHandler("logs/error.log", when="midnight", interval=1, backupCount=120,errors='replace')
    error_logger.setLevel(logging.ERROR)
    error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    error_hd.setFormatter(error_formatter)
    error_logger.addHandler(error_hd)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        asyncio.run(on_shutdown())
    except Exception as e:
        error_logger.error(f"Ошибка: {e}")
        asyncio.run(notify(f"Ошибка: {e}"))
