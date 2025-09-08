import logging
import json
import os
import paramiko
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, List, Any

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфігурація
BOT_TOKEN = "8160502358:AAG4c9N5PGLqmnEPE-HsdE3ctRhosW0dtg4"
STORAGE_BOX_HOST = "u475460.your-storagebox.de"
STORAGE_BOX_USERNAME = "u475460"
STORAGE_BOX_PASSWORD = "Mair558807."
STORAGE_BOX_PATH = "/backup/telegram_bot/pomichnik_for_meassage_saved_bot/"

# UUID для перевірки доступу
ALLOWED_UUID = "f7e94a9f-347c-5090-affa-418526e99a29"  # Замініть на ваш UUID

# Поточний файл даних
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
DATA_FILE = f"saved_messages_{CURRENT_DATE}.json"

# Глобальні змінні для стану перегляду
user_viewing_state: Dict[int, Dict[str, Any]] = {}
files_cache: Dict[str, List[str]] = {}


# Функція для перевірки доступу
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


# Функція для перевірки та завантаження старих файлів при запуску
async def check_old_files_on_startup():
    # Шукаємо файли з попередніх днів
    for filename in os.listdir('.'):
        if filename.startswith('saved_messages_') and filename.endswith('.json'):
            file_date_str = filename.replace('saved_messages_', '').replace('.json', '')

            # Перевіряємо чи це не поточний день
            if file_date_str != CURRENT_DATE:
                logger.info(f"Знайдено файл з попереднього дня: {filename}")

                # Завантажуємо його на Storage Box
                file_date = file_date_str
                remote_filename = f"saved_messages_{file_date}.json"

                storage_box = StorageBoxManager()
                if storage_box.connect():
                    success = storage_box.upload_file(filename, remote_filename)
                    storage_box.close()

                    if success:
                        try:
                            os.remove(filename)
                            logger.info(f"Файл {filename} успішно завантажено та видалено")
                        except Exception as e:
                            logger.error(f"Помилка при видаленні файлу {filename}: {e}")
                    else:
                        logger.error(f"Не вдалося завантажити файл {filename} на Storage Box")
                else:
                    logger.error(f"Не вдалося підключитися до Storage Box для файлу {filename}")


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


# Функції для перегляду файлів
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    # Отримуємо список файлів з Storage Box
    storage_box = StorageBoxManager()
    if not storage_box.connect():
        await update.message.reply_text("Не вдалося підключитися до Storage Box")
        return

    files = storage_box.list_files()
    storage_box.close()

    if not files:
        await update.message.reply_text("Файлів не знайдено.")
        return

    # Зберігаємо файли в кеш для цього користувача
    files_cache[user_id] = files

    # Відображаємо файли з пагінацією
    await show_files_page(update, context, page, files)


async def show_files_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, files: List[str]):
    user_id = update.effective_user.id

    # Розраховуємо пагінацію
    items_per_page = 12
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
        keyboard.append([InlineKeyboardButton(file_date, callback_data=f"view_{files[i]}")])

    # Додаємо кнопки навігації
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f"page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Наступна ➡️", callback_data=f"page_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"Файли з повідомленнями (сторінка {page + 1} з {total_pages}):"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def view_file(update: Update, context: ContextTypes.DEFAULT_TYPE, filename: str):
    user_id = update.effective_user.id

    # Скачуємо файл з Storage Box
    storage_box = StorageBoxManager()
    if not storage_box.connect():
        await update.callback_query.message.reply_text("Не вдалося підключитися до Storage Box")
        return

    local_path = storage_box.download_file(filename)
    storage_box.close()

    if not local_path:
        await update.callback_query.message.reply_text("Не вдалося завантажити файл.")
        return

    # Завантажуємо дані з файлу
    with open(local_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)

    # Зберігаємо стан перегляду для користувача
    user_viewing_state[user_id] = {
        'viewing_file': local_path,
        'filename': filename,
        'last_message_id': load_messages()['messages'][-1]['message_id'] if load_messages()['messages'] else None
    }

    # Форматуємо повідомлення для перегляду
    messages = file_data.get('messages', [])
    if not messages:
        text = "Файл порожній."
    else:
        text = f"📁 Файл: {filename}\n📊 Повідомлень: {len(messages)}\n\n"
        for msg in messages[:5]:  # Показуємо перші 5 повідомлень
            date = datetime.fromisoformat(msg['date']).strftime("%Y-%m-%d %H:%M")
            text += f"📅 {date}: {msg.get('text', '')[:100]}...\n"

        if len(messages) > 5:
            text += f"\n... і ще {len(messages) - 5} повідомлень."

    # Додаємо кнопку для позначки перегляду
    keyboard = [[InlineKeyboardButton("✅ Переглянуто", callback_data="mark_viewed")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


async def mark_viewed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_viewing_state:
        await update.callback_query.message.reply_text("Не знайдено активного перегляду.")
        return

    # Видаляємо тимчасовий файл
    viewing_file = user_viewing_state[user_id]['viewing_file']
    if os.path.exists(viewing_file):
        os.remove(viewing_file)

    # Перевіряємо чи є нові повідомлення
    current_data = load_messages()
    last_message_id = user_viewing_state[user_id].get('last_message_id')

    if last_message_id and current_data['messages']:
        new_messages = []
        for msg in current_data['messages']:
            if msg['message_id'] > last_message_id:
                new_messages.append(msg)

        if new_messages:
            text = "📨 Нові повідомлення, що надійшли під час перегляду:\n\n"
            for msg in new_messages[:10]:  # Показуємо перші 10 нових повідомлень
                date = datetime.fromisoformat(msg['date']).strftime("%H:%M")
                text += f"🆕 {date}: {msg.get('text', '')}\n"

            if len(new_messages) > 10:
                text += f"\n... і ще {len(new_messages) - 10} повідомлень."

            await update.callback_query.message.reply_text(text)

    # Видаляємо стан перегляду
    del user_viewing_state[user_id]

    await update.callback_query.edit_message_text("✅ Перегляд завершено. Тимчасовий файл видалено.", reply_markup=None)


# Обробники команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await update.message.reply_text(
        "Вітаю! Цей бот зберігає ваші повідомлення та створює резервні копії.\n\n"
        "Доступні команди:\n"
        "/start - Початок роботи\n"
        "/status - Статус збережених повідомлень\n"
        "/backup - Миттєве резервне копіювання\n"
        "/history - Перегляд історії файлів\n"
        "/my_uuid - Отримати ваш UUID"
    )


async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await update.message.reply_text("Початок миттєвого резервного копіювання...")
    await upload_to_storage_box()
    await update.message.reply_text("Резервне копіювання завершено!")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    data = load_messages()
    message_count = len(data["messages"])
    await update.message.reply_text(f"Статус: збережено {message_count} повідомлень за сьогодні ({CURRENT_DATE})")


async def view_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await list_files(update, context, 0)


async def my_uuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(user_id)))
    await update.message.reply_text(
        f"Ваш Telegram ID: {user_id}\n"
        f"Ваш згенерований UUID: {user_uuid}\n\n"
        f"Для доступу до бота використовується UUID: {ALLOWED_UUID}\n\n"
        f"Надайте цей UUID адміністратору для отримання доступу до бота."
    )


# Обробка повідомлень
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        # Для неавторизованих користувачів пропонуємо отримати UUID
        await update.message.reply_text(
            "Ви не маєте доступу до цього бота.\n"
            "Використовуйте команду /my_uuid щоб отримати ваш UUID для подальшого надання адміністратору."
        )
        return

    # Перевіряємо чи користувач переглядає історію
    if user_id in user_viewing_state:
        # Повідомлення буде збережено, але не показано до завершення перегляду
        pass

    message = update.message
    message_data = {
        "message_id": message.message_id,
        "chat_id": message.chat_id,
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "text": message.text,
        "date": message.date.isoformat(),
        "is_deleted": False,
        "is_edited": False
    }

    save_message(message_data)


# Обробка відредагованих повідомлень
async def handle_deleted_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return

    message = update.effective_message
    data = load_messages()

    for msg in data["messages"]:
        if msg["message_id"] == message.message_id:
            msg["text"] = message.text  # Оновлюємо текст повідомлення
            msg["is_edited"] = True
            logger.info(f"Позначено як відредаговане: {message.message_id}")

            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            break


# Обробник callback-запитів (для кнопок)
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.callback_query.answer("Вибачте, у вас немає доступу до цього бота.", show_alert=True)
        return

    query = update.callback_query
    data = query.data

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        if user_id in files_cache:
            await query.answer()
            await show_files_page(update, context, page, files_cache[user_id])
        else:
            await query.answer("Список файлів застарів. Будь ласка, запросіть його знову.", show_alert=True)

    elif data.startswith("view_"):
        filename = data.split("_", 1)[1]
        await query.answer()
        await view_file(update, context, filename)

    elif data == "mark_viewed":
        await query.answer()
        await mark_viewed(update, context)


async def main():
    # Ініціалізація бота
    application = Application.builder().token(BOT_TOKEN).build()

    # Перевіряємо та завантажуємо старі файли при запуску
    await check_old_files_on_startup()

    # Налаштування планувальника
    scheduler = setup_scheduler()

    # Додавання обробників
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("backup", backup_now))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("history", view_history))
    application.add_handler(CommandHandler("my_uuid", my_uuid))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, handle_deleted_message))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Запуск бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("Бот запущений!")

    try:
        # Тримаємо бота запущеним
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Отримано сигнал зупинки")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Програма зупинена користувачем")