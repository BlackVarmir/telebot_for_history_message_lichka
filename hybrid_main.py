import logging
import sys
import json
import os
import paramiko
import uuid
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters as tg_filters, CallbackQueryHandler
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, List, Any

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Включаємо детальне логування для pyrogram
logging.getLogger("pyrogram").setLevel(logging.DEBUG)

# Конфігурація Telegram Client API
API_ID = "23266897"  # Отримайте на https://my.telegram.org
API_HASH = "26ee63262a2274088768653a14fa6b35"  # Отримайте на https://my.telegram.org
SESSION_NAME = "telegram_client"

# Конфігурація Bot API
BOT_TOKEN = "8160502358:AAG4c9N5PGLqmnEPE-HsdE3ctRhosW0dtg4"

# Конфігурація Storage Box
STORAGE_BOX_HOST = "u475460.your-storagebox.de"
STORAGE_BOX_USERNAME = "u475460"
STORAGE_BOX_PASSWORD = "Mair558807."
STORAGE_BOX_PATH = "/backup/telegram_bot/pomichnik_for_meassage_saved_bot/"

# UUID для перевірки доступу до бота
ALLOWED_UUID = "f7e94a9f-347c-5090-affa-418526e99a29"
# User ID для Client API (отримайте через @userinfobot)
ALLOWED_USER_ID = 672513783  # Замініть на ваш Telegram ID

# Поточний файл даних
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
DATA_FILE = f"saved_messages_{CURRENT_DATE}.json"

# Глобальні змінні
user_viewing_state: Dict[int, Dict[str, Any]] = {}
files_cache: Dict[str, List[str]] = {}

# Функція для перевірки доступу до бота
def check_access(user_id):
    user_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(user_id)))
    return user_uuid == ALLOWED_UUID or str(user_id) == ALLOWED_UUID

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

# Функція-обгортка для автоматичного сканування
def auto_scan_sync():
    asyncio.run(fetch_recent_messages())

# Планувальник для щоденного завантаження
def setup_scheduler():
    scheduler = BackgroundScheduler()
    # Запускаємо о 23:59 кожного дня
    scheduler.add_job(upload_to_storage_box_sync, 'cron', hour=23, minute=59)
    scheduler.start()
    logger.info("Планувальник запущено:")
    logger.info("- Щоденне резервне копіювання о 23:59")
    logger.info("- Швидка перевірка повідомлень кожні 0.5 секунди")
    return scheduler

# ============= TELEGRAM CLIENT (для збереження повідомлень) =============

# Ініціалізація клієнта з додатковими налаштуваннями
client_app = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=False,  # Зберігаємо сесію на диску
    workers=1  # Один воркер для простоти
)

# Глобальний лічільник для тестування
message_counter = 0

# Файл для збереження останнього ID повідомлення
LAST_MESSAGE_ID_FILE = "last_message_id.txt"

def get_last_message_id():
    if os.path.exists(LAST_MESSAGE_ID_FILE):
        with open(LAST_MESSAGE_ID_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def save_last_message_id(message_id):
    with open(LAST_MESSAGE_ID_FILE, 'w') as f:
        f.write(str(message_id))

async def quick_message_check():
    """Швидка перевірка нових повідомлень кожні 0.5 секунди"""
    try:
        last_saved_id = get_last_message_id()
        new_messages_count = 0
        latest_message_id = last_saved_id

        # Завантажуємо існуючі повідомлення один раз для швидкості
        data = load_messages()
        existing_ids = set(msg['message_id'] for msg in data['messages'])

        # Перевіряємо "Збережені повідомлення" без ліміту
        # Але зупиняємося коли знаходимо старе повідомлення
        async for message in client_app.get_chat_history("me"):
            # Пропускаємо повідомлення без тексту
            if not message.text:
                continue

            # Зупиняємося коли дійшли до останнього збереженого повідомлення
            if message.id <= last_saved_id:
                break  # Оскільки повідомлення йдуть в порядку від нових до старих

            # Перевіряємо чи не збережено вже (для надійності)
            if message.id not in existing_ids:
                logger.info(f"⚡ ШВИДКЕ ЗБЕРЕЖЕННЯ: {message.id} - {message.text[:50]}...")

                message_data = {
                    "message_id": message.id,
                    "chat_id": message.chat.id,
                    "chat_type": "SAVED_MESSAGES",
                    "chat_title": "Збережені повідомлення",
                    "chat_username": None,
                    "from_user_id": message.from_user.id if message.from_user else ALLOWED_USER_ID,
                    "from_username": message.from_user.username if message.from_user else None,
                    "from_first_name": message.from_user.first_name if message.from_user else "Me",
                    "text": message.text,
                    "date": message.date.isoformat(),
                    "is_outgoing": (message.from_user.id == ALLOWED_USER_ID) if message.from_user else True,
                    "is_edited": False
                }

                save_message(message_data)
                new_messages_count += 1

                # Додаємо до існуючих ID щоб уникнути дублікатів в цій же ітерації
                existing_ids.add(message.id)

                # Оновлюємо останній ID
                if message.id > latest_message_id:
                    latest_message_id = message.id

        # Зберігаємо останній ID
        if latest_message_id > last_saved_id:
            save_last_message_id(latest_message_id)

        if new_messages_count > 0:
            logger.info(f"⚡ Швидко збережено {new_messages_count} повідомлень!")

    except Exception as e:
        logger.error(f"❌ Помилка швидкої перевірки: {e}")

async def message_checker_loop():
    """Безкінечний цикл перевірки повідомлень кожні 0.5 секунди"""
    logger.info("⚡ Запускаю швидку перевірку повідомлень кожні 0.5 секунди...")

    while True:
        try:
            await quick_message_check()
            await asyncio.sleep(0.5)  # Затримка 0.5 секунди
        except Exception as e:
            logger.error(f"❌ Помилка в циклі перевірки: {e}")
            await asyncio.sleep(1)  # При помилці чекаємо довше

# Обробник RAW updates для миттєвого отримання повідомлень
@client_app.on_raw_update()
async def handle_raw_update(client: Client, update, users, chats):
    global message_counter

    try:
        # Логуємо ТИП оновлення для діагностики
        update_type = type(update).__name__
        logger.info(f"🔍 RAW UPDATE TYPE: {update_type}")

        # Обробляємо різні типи оновлень
        message_to_process = None

        # 1. Пряме повідомлення
        if hasattr(update, 'message') and update.message:
            message_to_process = update.message
            logger.info("📨 Знайдено пряме повідомлення")

        # 2. Оновлення з новим повідомленням
        elif hasattr(update, 'updates') and update.updates:
            logger.info(f"📦 Знайдено {len(update.updates)} вкладених оновлень")
            for sub_update in update.updates:
                sub_type = type(sub_update).__name__
                logger.info(f"   🔸 Підтип: {sub_type}")

                if hasattr(sub_update, 'message') and sub_update.message:
                    message_to_process = sub_update.message
                    logger.info("   📨 Знайдено повідомлення у вкладеному оновленні")
                    break

        # 3. UpdateNewMessage
        elif update_type == 'UpdateNewMessage' and hasattr(update, 'message'):
            message_to_process = update.message
            logger.info("📨 Знайдено UpdateNewMessage")

        # 4. UpdateShortMessage
        elif update_type == 'UpdateShortMessage':
            logger.info("📨 Знайдено UpdateShortMessage")
            # Створюємо псевдо-повідомлення з UpdateShortMessage
            if hasattr(update, 'message') and hasattr(update, 'user_id'):
                message_to_process = type('Message', (), {
                    'id': update.id,
                    'message': update.message,
                    'date': update.date,
                    'out': getattr(update, 'out', False),
                    'from_id': type('PeerUser', (), {'user_id': update.user_id})(),
                    'peer_id': type('PeerUser', (), {'user_id': ALLOWED_USER_ID})()
                })()
                logger.info("   📨 Створено псевдо-повідомлення з UpdateShortMessage")

        # Обробляємо знайдене повідомлення
        if message_to_process:
            message_counter += 1
            logger.info(f"🔥 ОБРОБЛЯЄМО ПОВІДОМЛЕННЯ #{message_counter}")

            # Отримуємо ID повідомлення
            msg_id = getattr(message_to_process, 'id', None)
            logger.info(f"📨 Message ID: {msg_id}")

            # Отримуємо текст
            message_text = getattr(message_to_process, 'message', None)
            logger.info(f"📝 Text: {message_text}")

            # Отримуємо дату
            msg_date = getattr(message_to_process, 'date', None)
            logger.info(f"📅 Date: {msg_date}")

            # Отримуємо інформацію про відправника
            from_user_id = None
            if hasattr(message_to_process, 'from_id') and message_to_process.from_id:
                if hasattr(message_to_process.from_id, 'user_id'):
                    from_user_id = message_to_process.from_id.user_id

            # Отримуємо інформацію про чат
            chat_id = None
            if hasattr(message_to_process, 'peer_id') and message_to_process.peer_id:
                if hasattr(message_to_process.peer_id, 'user_id'):
                    chat_id = message_to_process.peer_id.user_id
                elif hasattr(message_to_process.peer_id, 'chat_id'):
                    chat_id = -message_to_process.peer_id.chat_id
                elif hasattr(message_to_process.peer_id, 'channel_id'):
                    chat_id = -1000000000000 - message_to_process.peer_id.channel_id

            logger.info(f"👤 From User ID: {from_user_id}")
            logger.info(f"💬 Chat ID: {chat_id}")
            logger.info(f"🎯 Allowed User ID: {ALLOWED_USER_ID}")

            # Зберігаємо якщо є текст
            if message_text and msg_id:
                # Знаходимо інформацію про користувача
                user_info = None
                if users and from_user_id:
                    for user in users:
                        if user.id == from_user_id:
                            user_info = user
                            break

                # Якщо не знайшли в users, створюємо базову інформацію
                if not user_info and from_user_id:
                    user_info = type('User', (), {
                        'id': from_user_id,
                        'username': None,
                        'first_name': 'Unknown User'
                    })()

                if user_info or from_user_id == ALLOWED_USER_ID:
                    logger.info("💾 МИТТЄВО ЗБЕРІГАЄМО повідомлення!")

                    message_data = {
                        "message_id": msg_id,
                        "chat_id": chat_id or from_user_id,
                        "chat_type": "SAVED_MESSAGES" if chat_id == ALLOWED_USER_ID else "PRIVATE",
                        "chat_title": "Збережені повідомлення" if chat_id == ALLOWED_USER_ID else None,
                        "chat_username": getattr(user_info, 'username', None) if user_info else None,
                        "from_user_id": from_user_id or ALLOWED_USER_ID,
                        "from_username": getattr(user_info, 'username', None) if user_info else None,
                        "from_first_name": getattr(user_info, 'first_name', 'Unknown') if user_info else 'Me',
                        "text": message_text,
                        "date": datetime.fromtimestamp(msg_date).isoformat() if msg_date else datetime.now().isoformat(),
                        "is_outgoing": from_user_id == ALLOWED_USER_ID or getattr(message_to_process, 'out', False),
                        "is_edited": False
                    }
                    save_message(message_data)
                    logger.info(f"✅ МИТТЄВО збережено в {DATA_FILE}")
                else:
                    logger.info("⚠️ Не знайдено інформацію про користувача")
            else:
                logger.info(f"⚠️ Пропускаємо (немає тексту: {bool(message_text)} або ID: {bool(msg_id)})")
        else:
            logger.info(f"ℹ️ Оновлення {update_type} не містить повідомлення")

    except Exception as e:
        logger.error(f"💥 ПОМИЛКА RAW UPDATE: {e}")
        import traceback
        logger.error(traceback.format_exc())

# Резервний обробник для звичайних повідомлень
@client_app.on_message()
async def handle_regular_messages(client: Client, message: Message):
    global message_counter
    message_counter += 1

    logger.info(f"📱 ЗВИЧАЙНИЙ ОБРОБНИК! Повідомлення #{message_counter}")
    logger.info(f"📨 ID: {message.id}")
    logger.info(f"📝 Text: {message.text}")
    logger.info(f"💬 Chat: {message.chat.id} ({message.chat.type})")
    logger.info(f"👤 From: {message.from_user.id if message.from_user else 'None'}")
    logger.info(f"📤 Outgoing: {getattr(message, 'outgoing', 'Unknown')}")

    # Перевіряємо чи це повідомлення вже збережено (уникаємо дублікатів)
    data = load_messages()
    existing_ids = [msg['message_id'] for msg in data['messages']]

    if message.id in existing_ids:
        logger.info(f"⚠️ Повідомлення {message.id} вже збережено, пропускаємо")
        return

    # Зберігаємо якщо є текст
    if message.text:
        logger.info("💾 РЕЗЕРВНЕ ЗБЕРЕЖЕННЯ!")

        # Визначаємо тип чату
        chat_type = "SAVED_MESSAGES" if message.chat.id == ALLOWED_USER_ID else str(message.chat.type)
        chat_title = "Збережені повідомлення" if message.chat.id == ALLOWED_USER_ID else getattr(message.chat, 'title', None)

        message_data = {
            "message_id": message.id,
            "chat_id": message.chat.id,
            "chat_type": chat_type,
            "chat_title": chat_title,
            "chat_username": getattr(message.chat, 'username', None),
            "from_user_id": message.from_user.id if message.from_user else ALLOWED_USER_ID,
            "from_username": message.from_user.username if message.from_user else None,
            "from_first_name": message.from_user.first_name if message.from_user else "Me",
            "text": message.text,
            "date": message.date.isoformat(),
            "is_outgoing": (message.from_user.id == ALLOWED_USER_ID) if message.from_user else True,
            "is_edited": False
        }
        save_message(message_data)
        logger.info(f"✅ РЕЗЕРВНО збережено в {DATA_FILE}")
    else:
        logger.info("⚠️ Пропускаємо (немає тексту)")

# ============= TELEGRAM BOT (для управління) =============

# Ініціалізація бота
bot_app = Application.builder().token(BOT_TOKEN).build()

# Обробники команд бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await update.message.reply_text(
        "🤖 **Гібридний бот для збереження повідомлень**\n\n"
        "📱 **Client API** зберігає всі ваші повідомлення автоматично\n"
        "🤖 **Bot API** дозволяє керувати процесом\n\n"
        "**Доступні команди:**\n"
        "/start - Початок роботи\n"
        "/status - Статус збережених повідомлень\n"
        "/backup - Миттєве резервне копіювання\n"
        "/history - Перегляд історії файлів\n"
        "/clientstatus - Статус Client API\n"
        "/myuuid - Отримати ваш UUID\n"
        "/debug - Показати налаштування\n"
        "/test - Тест Client API\n"
        "/scan - Принудове сканування повідомлень\n"
        "/autoscan - Статус автоматичного сканування",
        parse_mode='Markdown'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    data = load_messages()
    message_count = len(data["messages"])
    await update.message.reply_text(f"📊 Статус: збережено {message_count} повідомлень за сьогодні ({CURRENT_DATE})")

async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await update.message.reply_text("🔄 Початок миттєвого резервного копіювання...")
    await upload_to_storage_box()
    await update.message.reply_text("✅ Резервне копіювання завершено!")

async def clientstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    try:
        if client_app.is_connected:
            me = await client_app.get_me()
            status_text = f"✅ Client API підключений\n👤 Користувач: {me.first_name} (@{me.username})"
        else:
            status_text = "❌ Client API не підключений"
    except:
        status_text = "❌ Помилка перевірки статусу Client API"
    
    await update.message.reply_text(status_text)

async def view_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await list_files(update, context, 0)

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    user_id = update.effective_user.id

    # Отримуємо список файлів з Storage Box
    storage_box = StorageBoxManager()
    if not storage_box.connect():
        await update.message.reply_text("❌ Не вдалося підключитися до Storage Box")
        return

    files = storage_box.list_files()
    storage_box.close()

    if not files:
        await update.message.reply_text("📁 Файлів не знайдено.")
        return

    # Зберігаємо файли в кеш для цього користувача
    files_cache[user_id] = files

    # Відображаємо файли з пагінацією
    await show_files_page(update, context, page, files)

async def show_files_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, files: List[str]):
    # Розраховуємо пагінацію
    items_per_page = 10
    total_pages = (len(files) + items_per_page - 1) // items_per_page

    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(files))

    # Створюємо клавіатуру з файлами
    keyboard = []
    for i in range(start_idx, end_idx):
        file_date = files[i].replace('saved_messages_', '').replace('.json', '')
        keyboard.append([InlineKeyboardButton(f"📅 {file_date}", callback_data=f"view_{files[i]}")])

    # Додаємо кнопки навігації
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Наступна ➡️", callback_data=f"page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"📁 **Файли з повідомленнями** (сторінка {page+1} з {total_pages}):\n\n📊 Всього файлів: {len(files)}"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.callback_query.answer("❌ Вибачте, у вас немає доступу до цього бота.", show_alert=True)
        return

    query = update.callback_query
    data = query.data

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        if user_id in files_cache:
            await query.answer()
            await show_files_page(update, context, page, files_cache[user_id])
        else:
            await query.answer("📁 Список файлів застарів. Будь ласка, запросіть його знову.", show_alert=True)

    elif data.startswith("view_"):
        filename = data.split("_", 1)[1]
        await query.answer()
        await view_file(update, context, filename)

async def view_file(update: Update, context: ContextTypes.DEFAULT_TYPE, filename: str):
    # Скачуємо файл з Storage Box
    storage_box = StorageBoxManager()
    if not storage_box.connect():
        await update.callback_query.message.reply_text("❌ Не вдалося підключитися до Storage Box")
        return

    local_path = storage_box.download_file(filename)
    storage_box.close()

    if not local_path:
        await update.callback_query.message.reply_text("❌ Не вдалося завантажити файл.")
        return

    # Завантажуємо дані з файлу
    with open(local_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)

    # Форматуємо повідомлення для перегляду
    messages = file_data.get('messages', [])
    if not messages:
        text = "📁 Файл порожній."
    else:
        text = f"📁 **Файл:** `{filename}`\n📊 **Повідомлень:** {len(messages)}\n\n"

        # Показуємо останні 5 повідомлень
        for msg in messages[-5:]:
            date = datetime.fromisoformat(msg['date']).strftime("%d.%m %H:%M")
            direction = "➡️" if msg.get('is_outgoing', False) else "⬅️"
            sender = msg.get('from_first_name', 'Невідомо')
            text_preview = (msg.get('text', '') or '')[:50]
            if len(text_preview) == 50:
                text_preview += "..."
            text += f"{direction} {date} **{sender}:** {text_preview}\n"

        if len(messages) > 5:
            text += f"\n📝 Показано останні 5 з {len(messages)} повідомлень"

    # Видаляємо тимчасовий файл
    if os.path.exists(local_path):
        os.remove(local_path)

    await update.callback_query.edit_message_text(text, parse_mode='Markdown')

async def myuuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(user_id)))
    await update.message.reply_text(
        f"ℹ️ **Ваша інформація:**\n"
        f"🆔 Telegram ID: `{user_id}`\n"
        f"🔑 UUID: `{user_uuid}`\n\n"
        f"🔐 Дозволений UUID: `{ALLOWED_UUID}`\n\n"
        f"📝 Надайте ваш UUID адміністратору для отримання доступу.",
        parse_mode='Markdown'
    )

async def debug_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    debug_info = f"""🔧 **Налаштування системи:**

📱 **Client API:**
- API_ID: `{API_ID}`
- API_HASH: `{'*' * len(str(API_HASH)) if API_HASH != 'YOUR_API_HASH' else 'НЕ НАЛАШТОВАНО'}`
- Дозволений User ID: `{ALLOWED_USER_ID}`

🤖 **Bot API:**
- Дозволений UUID: `{ALLOWED_UUID}`
- Ваш UUID: `{str(uuid.uuid5(uuid.NAMESPACE_OID, str(user_id)))}`

📁 **Файли:**
- Поточний файл: `{DATA_FILE}`
- Існує: `{os.path.exists(DATA_FILE)}`

⚠️ **Перевірте:**
1. API_ID та API_HASH мають бути налаштовані
2. ALLOWED_USER_ID має відповідати вашому Telegram ID
3. Client API має бути запущений"""

    await update.message.reply_text(debug_info, parse_mode='Markdown')

# Функція для принудового отримання повідомлень
async def fetch_recent_messages():
    try:
        logger.info("🔍 Принудово отримуємо останні повідомлення...")

        # Отримуємо повідомлення з "Збережених повідомлень"
        async for message in client_app.get_chat_history("me", limit=5):
            logger.info(f"📨 Знайдено повідомлення: {message.id} - {message.text}")

            if message.text and message.from_user:
                # Перевіряємо чи це повідомлення ще не збережено
                data = load_messages()
                existing_ids = [msg['message_id'] for msg in data['messages']]

                if message.id not in existing_ids:
                    logger.info(f"💾 Зберігаємо нове повідомлення: {message.id}")
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
                        "is_outgoing": message.from_user.id == ALLOWED_USER_ID,
                        "is_edited": False
                    }
                    save_message(message_data)
                else:
                    logger.info(f"⚠️ Повідомлення {message.id} вже збережено")

    except Exception as e:
        logger.error(f"❌ Помилка при отриманні повідомлень: {e}")

async def test_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    try:
        global message_counter
        old_counter = message_counter

        # Надсилаємо тестове повідомлення через Client API
        me = await client_app.get_me()

        await update.message.reply_text("🧪 Надсилаю тестове повідомлення...")

        # Надсилаємо повідомлення собі
        test_msg = await client_app.send_message("me", f"🧪 Тест #{message_counter + 1} від Client API")

        # Чекаємо трохи
        await asyncio.sleep(2)

        # Перевіряємо чи збільшився лічільник (через обробники)
        new_counter = message_counter

        # Принудово отримуємо повідомлення
        await update.message.reply_text("🔍 Принудово отримую повідомлення...")
        old_messages_count = len(load_messages()['messages'])

        await fetch_recent_messages()

        new_messages_count = len(load_messages()['messages'])

        await update.message.reply_text(
            f"✅ **Результат тесту:**\n\n"
            f"👤 Підключений як: {me.first_name} (@{me.username})\n"
            f"📤 Надіслано повідомлення ID: {test_msg.id}\n\n"
            f"**Обробники повідомлень:**\n"
            f"🔢 Лічільник до: {old_counter}\n"
            f"🔢 Лічільник після: {new_counter}\n"
            f"📊 Різниця: {new_counter - old_counter}\n"
            f"{'✅ Обробники працюють!' if new_counter > old_counter else '❌ Обробники НЕ працюють!'}\n\n"
            f"**Принудове отримання:**\n"
            f"📁 Повідомлень до: {old_messages_count}\n"
            f"📁 Повідомлень після: {new_messages_count}\n"
            f"📊 Додано: {new_messages_count - old_messages_count}\n"
            f"{'✅ Принудове отримання працює!' if new_messages_count > old_messages_count else '❌ Принудове отримання НЕ працює!'}",
            parse_mode='Markdown'
        )

        # Перевіряємо файл
        data = load_messages()
        await update.message.reply_text(
            f"📁 **Стан файлу:**\n"
            f"📄 Файл: `{DATA_FILE}`\n"
            f"📊 Повідомлень у файлі: {len(data['messages'])}\n"
            f"💾 Файл існує: {os.path.exists(DATA_FILE)}",
            parse_mode='Markdown'
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка тесту Client API: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def scan_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    try:
        await update.message.reply_text("🔍 Сканую останні повідомлення...")

        old_count = len(load_messages()['messages'])
        await fetch_recent_messages()
        new_count = len(load_messages()['messages'])

        await update.message.reply_text(
            f"✅ **Сканування завершено!**\n\n"
            f"📊 Повідомлень до: {old_count}\n"
            f"📊 Повідомлень після: {new_count}\n"
            f"📈 Додано: {new_count - old_count}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка сканування: {e}")

async def auto_scan_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    global message_counter
    last_id = get_last_message_id()
    data = load_messages()

    await update.message.reply_text(
        "⚡ **Швидке збереження повідомлень:**\n\n"
        "🔥 **Перевірка кожні 0.5 секунди** - майже миттєво!\n"
        "📱 Система постійно сканує 'Збережені повідомлення'\n"
        "💾 Нові повідомлення зберігаються за 0.5 секунди\n\n"
        f"📊 **Статистика:**\n"
        f"🔢 Оброблено оновлень: {message_counter}\n"
        f"🆔 Останній ID: {last_id}\n"
        f"📁 Поточний файл: `{DATA_FILE}`\n"
        f"💾 Збережено повідомлень: {len(data['messages'])}\n\n"
        "**Команди:**\n"
        "/scan - Ручне сканування (резервний метод)\n"
        "/status - Перевірити збережені повідомлення\n"
        "/test - Тест системи",
        parse_mode='Markdown'
    )

# Додавання обробників до бота
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("status", status))
bot_app.add_handler(CommandHandler("backup", backup_now))
bot_app.add_handler(CommandHandler("history", view_history))
bot_app.add_handler(CommandHandler("clientstatus", clientstatus))
bot_app.add_handler(CommandHandler("myuuid", myuuid))
bot_app.add_handler(CommandHandler("debug", debug_settings))
bot_app.add_handler(CommandHandler("test", test_client))
bot_app.add_handler(CommandHandler("scan", scan_messages))
bot_app.add_handler(CommandHandler("autoscan", auto_scan_status))
bot_app.add_handler(CallbackQueryHandler(handle_callback_query))

async def main():
    # Налаштування планувальника
    scheduler = setup_scheduler()
    
    logger.info("🚀 Запускаю гібридну систему...")
    
    # Запускаємо Client API
    logger.info("📱 Запускаю Telegram Client API...")
    await client_app.start()
    me = await client_app.get_me()
    logger.info(f"✅ Client API запущений для користувача: {me.first_name} (@{me.username})")
    
    # Запускаємо Bot API
    logger.info("🤖 Запускаю Telegram Bot API...")
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    
    logger.info("🎉 Гібридна система запущена!")
    logger.info("📱 Client API зберігає всі повідомлення")
    logger.info("🤖 Bot API доступний для управління")

    # Запускаємо швидкий цикл перевірки повідомлень
    message_checker_task = asyncio.create_task(message_checker_loop())

    try:
        # Тримаємо систему запущеною
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("⏹️ Отримано сигнал зупинки")
        message_checker_task.cancel()
    finally:
        logger.info("🔄 Зупиняю систему...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await client_app.stop()
        logger.info("✅ Система зупинена")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Програма зупинена користувачем")
