import json
import requests
from datetime import datetime
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import os


info_logger = logging.getLogger("info")
info_handler = TimedRotatingFileHandler("info.log", when="midnight", interval=10, backupCount=30,errors='replace')
info_logger.setLevel(logging.INFO)
info_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
info_handler.setFormatter(info_formatter)
info_logger.addHandler(info_handler)


oAuth = os.getenv('oAuth')


async def IAM_token_remaker():
    global IAM_token
    
    info_logger.info('Starting IAM token remaker...')
    inside_part = '"yandexPassportOauthToken"'+":"+f'"{oAuth}"'
    data = '{'+inside_part+'}'
    tokenURL = 'https://iam.api.cloud.yandex.net/iam/v1/tokens'
    
    counter = 0
    while counter<=5:
        async with asyncio.Lock():
            info_logger.info('Getting new IAM token...')
            r = requests.post(tokenURL, data=data)
            from_json = json.loads(r.text)
            new_token = from_json.get('iamToken')
            if new_token:
                info_logger.info('New IAM token accepted')
                IAM_token = new_token
                counter = 0
            else:
                info_logger.error('New IAM token not accepted. Retrying...')
                counter+=1
                await asyncio.sleep(10)
                continue 
        await asyncio.sleep(60*60)# каждый час обновлять IAM токен, как в рекомендациях Яндекса
    info_logger.info('IAM token remaking failed. Too many retries. Exiting...')
    
async def expire_date_stoper():
    global IAM_token
    
    info_logger.info('Starting expire_date_stoper...')
    headers = {'Authorization': f'Bearer {IAM_token}'}
    cloud_listingURL = 'https://resource-manager.api.cloud.yandex.net/resource-manager/v1/clouds'
    counter = 0
    
    await asyncio.sleep(10) # Ждём 10 секунд получения IAM токена перед стартом работы
    
    while counter<=5:
        async with asyncio.Lock(): ## Блокировка, чтобы не было смены IAM токена во время работы
            ## Перебор всех облаков
            r = requests.get(cloud_listingURL, headers=headers)
            if r.status_code!=200:
                info_logger.error(f'Error in getting clouds. Status_code: {r.status_code} responce: {r.text}')
                counter+=1
                await asyncio.sleep(10)
                continue        
            from_json = json.loads(r.text)
            clouds = from_json.get('clouds')
            ## Перебор всех облаков
            
            ## Проверка существования облаков
            if not clouds:
                info_logger.error('clouds not found')
                counter+=1
                await asyncio.sleep(10)
                continue
            ## Проверка существования облаков
            for cl in clouds:
                ## Проверка существования id
                cloud_id = cl.get('id')
                if not cloud_id:
                    info_logger.error(f'cloud_id not found in cloud {cl}')
                    continue
                ## Проверка существования id
                info_logger.info(f'Checking cloud {cloud_id}...')
                
                ## Перебор всех папок внутри облака
                request_url = f'https://resource-manager.api.cloud.yandex.net/resource-manager/v1/folders?cloudId={cloud_id}'
                r = requests.get(request_url, headers=headers)
                if r.status_code!=200:
                    info_logger.error(f'Error in getting folders from cloud {cloud_id} status_code: {r.status_code} responce: {r.text}')
                    counter+=1
                    await asyncio.sleep(10)
                    continue
                from_json = json.loads(r.text)
                folders = from_json.get('folders')
                ## Перебор всех папок внутри облака
                
                ## Проверка существования папок
                if not folders:
                    info_logger.error(f'folders in cloud {cloud_id} not found')
                    continue
                ## Проверка существования папок
                for f in folders:
                    ## Проверка существования id
                    folder_id = f.get('id')
                    if not folder_id:
                        continue
                    ## Проверка существования id
                    info_logger.info(f'Checking folder {folder_id} in cloud {cloud_id}...')
                    
                    ## Перебор всех инстансов внутри папки
                    instance_url = f'https://compute.api.cloud.yandex.net/compute/v1/instances?folderId={folder_id}'
                    r = requests.get(instance_url, headers=headers)
                    if r.status_code!=200:
                        info_logger.error(f'Error in getting instances from folder {folder_id} status_code: {r.status_code} responce: {r.text}')
                        continue
                    from_json = json.loads(r.text)
                    instances = from_json.get('instances')
                    ## Перебор всех инстансов внутри папки
                    
                    ## Проверка существования инстансов
                    if not instances:
                        info_logger.error(f'instances not found in folder {folder_id} in cloud {cloud_id}')
                        continue
                    ## Проверка существования инстансов
                    for ins in instances:
                        ## Проверка существования id, labels, expire_date, status
                        instance_id = ins.get('id')
                        labels = ins.get('labels')
                        expire_date = labels.get('expired_date')
                        status = ins.get('status')
                        ## Проверка существования id, labels, expired_date, status
                        info_logger.info(f'Checking instance {instance_id} in folder {folder_id} in cloud {cloud_id}...')
                        
                        ## Остановка инстанса, если он просрочен
                        if labels and expire_date:
                            counter = 0
                            expire_date = datetime.strptime(expire_date, "%d.%m.%Y")
                            current_date = datetime.now()
                            if expire_date < current_date and status == 'RUNNING':
                                info_logger.info(f'Stopping instance {instance_id} in folder {folder_id} in cloud {cloud_id}')
                                stop_url = f'https://compute.api.cloud.yandex.net/compute/v1/instances/{instance_id}:stop'
                                r = requests.post(stop_url, headers=headers)
                                from_json = json.loads(r.text)
                                if r.status_code==200:
                                    info_logger.info(f'Instance {instance_id} in folder {folder_id} in cloud {cloud_id} stopped successfully')
                                else:
                                    info_logger.error(f'Error in stopping instance {instance_id} in folder {folder_id} in cloud {cloud_id} status_code: {r.status_code} responce: {r.text}')
                            else:
                                info_logger.info(f'Instance {instance_id} in folder {folder_id} in cloud {cloud_id} is not expired or not running')
                        else:
                            info_logger.error(f'expire_date or labels not found in instance {ins} in folder {folder_id} in cloud {cloud_id}')        
        await asyncio.sleep(60*60)  # Каждый час проверять статус инстансов
    info_logger.info('expire_date_stoper failed. Too many retries. Exiting...')
                        

async def main():
    info_logger.info('Starting...')
    t1 = asyncio.create_task(IAM_token_remaker())
    t2 = asyncio.create_task(expire_date_stoper())

    await asyncio.gather(t1, t2)

if __name__ == "__main__":
    asyncio.run(main())