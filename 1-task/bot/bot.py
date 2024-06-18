import requests
import mysql.connector
from aiogram import Bot
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import schedule
import time
import os


GITLAB_URL = os.getenv('GITLAB_URL')
PROJECT_ID = os.getenv('PROJECT_ID')
GITLAB_TOKEN = os.getenv('GITLAB_TOKEN')
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASSWORD')
DB_DB = os.getenv('DB_NAME')
TOKEN = os.getenv('TOKEN')



bot = Bot(TOKEN)

if not os.path.exists('logs'):
    os.mkdir('logs')

error_logger = logging.getLogger("error")
error_hd = TimedRotatingFileHandler("logs/error.log", when="midnight", interval=5, backupCount=120,errors='replace')
error_logger.setLevel(logging.ERROR)
error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
error_hd.setFormatter(error_formatter)
error_logger.addHandler(error_hd)


info_logger = logging.getLogger("info")
info_handler = TimedRotatingFileHandler("logs/info.log", when="midnight", interval=5, backupCount=120,errors='replace')
info_logger.setLevel(logging.INFO)  # Изменено на INFO
info_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
info_handler.setFormatter(info_formatter)
info_logger.addHandler(info_handler)


def connect():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_DB
    )
    cursor = conn.cursor()
    return conn, cursor

def select_via_gitlab_id(gitlab_id:int)->tuple[int]:
    conn, cursor = connect()
    sql = "SELECT TG_ID FROM gitlab_table WHERE GITLAB_ID = %s"
    val = (gitlab_id,)
    cursor.execute(sql, val)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

async def sender(text:str,user_id:int)->None:
    try:
        await bot.send_message(user_id,text)
    except Exception as e:
        error_logger.error(f'Ошибка при отправка сообщения: {e}')
    finally:
        await bot.session.close()

def get_merge_requests()->str:
    url = f"{GITLAB_URL}/projects/{PROJECT_ID}/merge_requests"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    params = {
        "state": "opened",
        "scope": "all"
    }
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        error_logger.error(f'Ошибка при запросе merge requests status_code: {response.status_code} response: {response.text}')
        return []

def get_approvals(mr_iid)->list[int]:
    url = f"{GITLAB_URL}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/approvals"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        from_json = response.json()
        if from_json.get('approved_by') == []:
            return None
        else:
            return [x['user']['id'] for x in from_json.get('approved_by')]
    else:
        error_logger.error(f'Ошибка в получение всех апрувов мерджа: {mr_iid} status_code: {response.status_code} response: {response.text}')
        return None



def main():
    merge_requests = get_merge_requests()
    for mr in merge_requests:
        info_logger.info(f'Работаю с запросом {mr}')
        reviewer_ids = set([x['id'] for x in mr['reviewers']] if mr['reviewers'] is not None else [])
        approved_ids = get_approvals(mr['iid'])
        if approved_ids is None:
            approved_ids = set([])
        else:
            approved_ids = set(approved_ids)
        if len(reviewer_ids) == len(approved_ids):
            author_id = mr['author']['id']
            result = select_via_gitlab_id(author_id)
            if result:
                title = mr['title']
                desrc = mr['description']
                text = f'Здравствуйте! Вас ждёт полностью аппрувнутый merge request с названием "{title}" и описанием "{desrc}" \n\nСмёрджите его, пожалуйста'
                user_id = result[0]
                asyncio.run(sender(text,user_id))
            else:
                error_logger.error(f'Пользователь с gitlab_id: {author_id} не найден в базе данных')
        else:
            diff = reviewer_ids-approved_ids
            title = mr['title']
            desrc = mr['description']
            text = f'Здравствуйте! Merge request "{title}" и описанием "{desrc}" ожидает вашего ревью, посмотрите, пожалуйста'
            for d in diff:
                result = select_via_gitlab_id(d)
                if result:
                    user_id = result[0]
                    asyncio.run(sender(text,user_id))
                else:
                    error_logger.error(f'Пользователь с gitlab_id: {d} не найден в базе данных')
                    

schedule.every().day.at("09:00").do(main)
schedule.every().day.at("14:00").do(main)
schedule.every().day.at("18:00").do(main)

if __name__ == "__main__":
    time.sleep(10)
    main()
    while True:
        schedule.run_pending()
        time.sleep(1)