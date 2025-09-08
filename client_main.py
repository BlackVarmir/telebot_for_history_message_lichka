import logging
import json
import os
import paramiko
import uuid
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, List, Any

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфігурація Telegram Client API
API_ID = "YOUR_API_ID"  # Отримайте на https://my.telegram.org
API_HASH = "YOUR_API_HASH"  # Отримайте на https://my.telegram.org
SESSION_NAME = "telegram_client"

# Конфігурація Storage Box
STORAGE_BOX_HOST = "u475460.your-storagebox.de"
STORAGE_BOX_USERNAME = "u475460"
STORAGE_BOX_PASSWORD = "Mair558807."
STORAGE_BOX_PATH = "/backup/telegram_bot/pomichnik_for_meassage_saved_bot/"

# UUID для перевірки доступу (ваш Telegram ID)
ALLOWED_USER_ID = 123456789  # Замініть на ваш Telegram ID

# Поточний файл даних
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
DATA_FILE = f"saved_messages_{CURRENT_DATE}.json"

# Глобальні змінні
user_viewing_state: Dict[int, Dict[str, Any]] = {}
files_cache: Dict[str, List[str]] = {}

class StorageBoxManager:
    def __init__(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
    def connect(self):
        try:
            self.ssh.connect(
                STORAGE_BOX_HOST,
                username=STORAGE_BOX_USERNAME,
                password=STORAGE_BOX_PASSWORD
            )
            return True
        except Exception as e:
            logger.error(f"Помилка підключення до Storage Box: {e}")
            return False
            
    def upload_file(self, local_path, remote_filename):
        try:
            sftp = self.ssh.open_sftp()
            
            # Перевіряємо чи існує директорія, якщо ні - створюємо
            try:
                sftp.chdir(STORAGE_BOX_PATH)
            except:
                sftp.mkdir(STORAGE_BOX_PATH)
                sftp.chdir(STORAGE_BOX_PATH)
            
            remote_path = os.path.join(STORAGE_BOX_PATH, remote_filename)
            sftp.put(local_path, remote_path)
            sftp.close()
            logger.info(f"Файл {local_path} успішно завантажено на Storage Box як {remote_filename}")
            return True
        except Exception as e:
            logger.error(f"Помилка завантаження файлу: {e}")
            return False
            
    def list_files(self):
        try:
            sftp = self.ssh.open_sftp()
            try:
                sftp.chdir(STORAGE_BOX_PATH)
            except:
                return []
            
            files = sftp.listdir()
            sftp.close()
            
            # Фільтруємо тільки файли з повідомленнями
            message_files = [f for f in files if f.startswith('saved_messages_') and f.endswith('.json')]
            return sorted(message_files, reverse=True)
        except Exception as e:
            logger.error(f"Помилка отримання списку файлів: {e}")
            return []
            
    def download_file(self, remote_filename):
        try:
            sftp = self.ssh.open_sftp()
            remote_path = os.path.join(STORAGE_BOX_PATH, remote_filename)
            
            # Створюємо тимчасову директорію
            if not os.path.exists("temp"):
                os.makedirs("temp")
                
            local_path = os.path.join("temp", remote_filename)
            sftp.get(remote_path, local_path)
            sftp.close()
            
            return local_path
        except Exception as e:
            logger.error(f"Помилка скачування файлу {remote_filename}: {e}")
            return None
            
    def close(self):
        self.ssh.close()

# Функції для роботи з даними
def load_messages():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"messages": []}

def save_message(message_data):
    data = load_messages()
    data["messages"].append(message_data)
    
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    logger.info(f"Збережено повідомлення: {message_data['message_id']}")

# Функція для відправки файлу на Storage Box
async def upload_to_storage_box():
    global DATA_FILE, CURRENT_DATE
    
    if not os.path.exists(DATA_FILE):
        logger.info("Немає файлу для відправки сьогодні")
        return

    # Створюємо унікальну назву файлу з датою
    file_date = datetime.now().strftime("%Y-%m-%d")
    remote_filename = f"saved_messages_{file_date}.json"

    # Завантажуємо файл на Storage Box
    storage_box = StorageBoxManager()
    if storage_box.connect():
        success = storage_box.upload_file(DATA_FILE, remote_filename)
        storage_box.close()

        if success:
            # Очищаємо локальний файл тільки після успішного завантаження
            try:
                os.remove(DATA_FILE)
                logger.info(f"Локальний файл {DATA_FILE} видалено після успішного завантаження")
            except Exception as e:
                logger.error(f"Помилка при видаленні локального файлу: {e}")

            # Оновлюємо назву поточного файлу для нового дня
            CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
            DATA_FILE = f"saved_messages_{CURRENT_DATE}.json"
        else:
            logger.error("Не вдалося завантажити файл на Storage Box - локальний файл збережено")
    else:
        logger.error("Не вдалося підключитися до Storage Box - локальний файл збережено")

# Функція-обгортка для асинхронного завантаження
def upload_to_storage_box_sync():
    asyncio.run(upload_to_storage_box())

# Планувальник для щоденного завантаження
def setup_scheduler():
    scheduler = BackgroundScheduler()
    # Запускаємо о 23:59 кожного дня
    scheduler.add_job(upload_to_storage_box_sync, 'cron', hour=23, minute=59)
    scheduler.start()
    logger.info("Планувальник запущено - щоденне резервне копіювання о 23:59")
    return scheduler

# Ініціалізація клієнта
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

# Обробник всіх повідомлень
@app.on_message()
async def handle_all_messages(client: Client, message: Message):
    # Зберігаємо всі повідомлення, які отримує або надсилає користувач
    if message.from_user and message.from_user.id == ALLOWED_USER_ID:
        # Повідомлення від вас
        message_data = {
            "message_id": message.id,
            "chat_id": message.chat.id,
            "chat_type": str(message.chat.type),
            "chat_title": getattr(message.chat, 'title', None),
            "chat_username": getattr(message.chat, 'username', None),
            "from_user_id": message.from_user.id,
            "from_username": message.from_user.username,
            "from_first_name": message.from_user.first_name,
            "text": message.text,
            "date": message.date.isoformat(),
            "is_outgoing": True,
            "is_edited": False
        }
        save_message(message_data)
        
    elif hasattr(message.chat, 'type') and message.chat.type.name == 'PRIVATE':
        # Повідомлення до вас в приватному чаті
        if message.from_user:
            message_data = {
                "message_id": message.id,
                "chat_id": message.chat.id,
                "chat_type": str(message.chat.type),
                "chat_title": None,
                "chat_username": getattr(message.chat, 'username', None),
                "from_user_id": message.from_user.id,
                "from_username": message.from_user.username,
                "from_first_name": message.from_user.first_name,
                "text": message.text,
                "date": message.date.isoformat(),
                "is_outgoing": False,
                "is_edited": False
            }
            save_message(message_data)

# Обробник команд (тільки від авторизованого користувача)
@app.on_message(filters.command(["status", "backup", "history", "stop"]) & filters.user(ALLOWED_USER_ID))
async def handle_commands(client: Client, message: Message):
    command = message.command[0]
    
    if command == "status":
        data = load_messages()
        message_count = len(data["messages"])
        await message.reply_text(f"Статус: збережено {message_count} повідомлень за сьогодні ({CURRENT_DATE})")
    
    elif command == "backup":
        await message.reply_text("Початок миттєвого резервного копіювання...")
        await upload_to_storage_box()
        await message.reply_text("Резервне копіювання завершено!")
    
    elif command == "history":
        storage_box = StorageBoxManager()
        if storage_box.connect():
            files = storage_box.list_files()
            storage_box.close()
            
            if files:
                text = "📁 Доступні файли з повідомленнями:\n\n"
                for i, file in enumerate(files[:10]):  # Показуємо перші 10 файлів
                    date = file.replace('saved_messages_', '').replace('.json', '')
                    text += f"{i+1}. {date}\n"
                
                if len(files) > 10:
                    text += f"\n... і ще {len(files)-10} файлів."
            else:
                text = "Файлів не знайдено."
        else:
            text = "Не вдалося підключитися до Storage Box"
        
        await message.reply_text(text)
    
    elif command == "stop":
        await message.reply_text("Зупиняю клієнт...")
        await app.stop()

async def main():
    # Налаштування планувальника
    scheduler = setup_scheduler()
    
    logger.info("Запускаю Telegram Client...")
    await app.start()
    
    # Отримуємо інформацію про користувача
    me = await app.get_me()
    logger.info(f"Клієнт запущений для користувача: {me.first_name} (@{me.username})")
    
    # Тримаємо клієнт запущеним
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Програма зупинена користувачем")
