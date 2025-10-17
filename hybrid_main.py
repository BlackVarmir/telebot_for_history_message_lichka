import logging
import sys
import json
import os
import paramiko
import uuid
import signal
import traceback
import warnings
import inspect
from datetime import datetime
from pyrogram import Client
from pyrogram.types import Message
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Message as TelegramMessage
from telegram.ext import Application, CommandHandler, MessageHandler, filters as tg_filters, CallbackQueryHandler, CallbackContext
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, List, Any
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

# Завантажуємо змінні з .env файлу
load_dotenv()

# Type alias для контексту (для сумісності з різними версіями IDE)
ContextType = CallbackContext[Any, Any, Any, Any]

# Придушуємо RuntimeWarning про незавершені корутини Pyrogram
# Це відома проблема Pyrogram - Dispatcher створює tasks які не очищаються
warnings.filterwarnings("ignore", message="coroutine.*was never awaited", category=RuntimeWarning)

# Функція для отримання імені файлу логів з датою
def get_log_filename():
    return f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"

# Налаштування логування
# Файл - все детально (як раніше в консолі), консоль - тільки компактні повідомлення
current_log_file = get_log_filename()
file_handler = logging.FileHandler(current_log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Консоль - тільки критичні помилки (компактні повідомлення виводимо через print)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.ERROR)  # Тільки ERROR в консоль
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)

# Включаємо детальне логування всіх бібліотек в файл (як раніше в консолі)
logging.getLogger("pyrogram").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("paramiko").setLevel(logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logging.getLogger("telegram").setLevel(logging.INFO)

# Конфігурація Telegram Client API
API_ID = os.getenv("API_ID")  # Отримайте на https://my.telegram.org
API_HASH = os.getenv("API_HASH")  # Отримайте на https://my.telegram.org
SESSION_NAME = "telegram_client"

# Конфігурація Bot API
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Отримайте у @BotFather

# Конфігурація Storage Box
STORAGE_BOX_HOST = os.getenv("STORAGE_BOX_HOST")
STORAGE_BOX_USERNAME = os.getenv("STORAGE_BOX_USERNAME")
STORAGE_BOX_PASSWORD = os.getenv("STORAGE_BOX_PASSWORD")
STORAGE_BOX_PATH = os.getenv("STORAGE_BOX_PATH")

# Конфігурація AI (додайте свої ключі)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Або вставте ключ тут
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Або вставте ключ тут
AI_PROVIDER = os.getenv("AI_PROVIDER")  # "openai" або "anthropic"

# Ініціалізація AI клієнтів
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
AI_ENABLED = bool(openai_client or anthropic_client)

# Імпорт модулів самооптимізації (після ініціалізації logger)
OPTIMIZATION_ENABLED = False
SelfOptimizer = None
PerformanceMonitor = None
CacheManager = None
AICodeImprover = None
PerformanceMetrics = None
performance_tracked = None
AdaptiveRateLimiter = None
CodeAnalyzer = None
AutoPatcher = None

try:
    from self_optimizer import SelfOptimizer as _SelfOptimizer, PerformanceMetrics as _PerformanceMetrics
    from performance_monitor import (
        PerformanceMonitor as _PerformanceMonitor,
        performance_tracked as _performance_tracked,
        CacheManager as _CacheManager,
        AdaptiveRateLimiter as _AdaptiveRateLimiter
    )
    from ai_code_improver import (
        AICodeImprover as _AICodeImprover,
        CodeAnalyzer as _CodeAnalyzer,
        AutoPatcher as _AutoPatcher
    )

    SelfOptimizer = _SelfOptimizer
    PerformanceMetrics = _PerformanceMetrics
    PerformanceMonitor = _PerformanceMonitor
    performance_tracked = _performance_tracked
    CacheManager = _CacheManager
    AdaptiveRateLimiter = _AdaptiveRateLimiter
    AICodeImprover = _AICodeImprover
    CodeAnalyzer = _CodeAnalyzer
    AutoPatcher = _AutoPatcher

    OPTIMIZATION_ENABLED = True
except ImportError as import_exc:
    print(f"⚠️ Модулі оптимізації не завантажені: {import_exc}")
    print("   Бот працюватиме без системи самооптимізації")

    # Визначаємо заглушки в except блоці
    _SelfOptimizer = None
    _PerformanceMetrics = None
    _PerformanceMonitor = None
    _performance_tracked = None
    _CacheManager = None
    _AdaptiveRateLimiter = None
    _AICodeImprover = None
    _CodeAnalyzer = None
    _AutoPatcher = None

    SelfOptimizer = None
    PerformanceMetrics = None
    PerformanceMonitor = None
    performance_tracked = None
    CacheManager = None
    AdaptiveRateLimiter = None
    AICodeImprover = None
    CodeAnalyzer = None
    AutoPatcher = None

# UUID для перевірки доступу до бота
ALLOWED_UUID = "f7e94a9f-347c-5090-affa-418526e99a29"
# User ID для Client API (отримайте через @userinfobot)
ALLOWED_USER_ID = 672513783  # Замініть на ваш Telegram ID

# Налаштування збереження повідомлень (можна змінювати через бота)
settings = {
    'save_saved_messages': True,   # Зберігати "Збережені повідомлення"
    'save_private_chats': True,    # Зберігати приватні чати (не секретні)
    'save_groups': False,           # Зберігати групи
    'save_channels': False,         # Зберігати канали
    'check_interval': 0.5,          # Інтервал перевірки "Збережених" (секунди)
    'dialogs_check_interval': 5,   # Інтервал перевірки діалогів (секунди)
    'dialogs_limit': 20,            # Кількість діалогів для перевірки
    'messages_per_dialog': 5,       # Кількість повідомлень з кожного діалогу
}

# Глобальна змінна для поточної дати
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")



# Функція для очищення старих локальних файлів
def cleanup_old_local_files():
    """Видаляє старі локальні файли з повідомленнями (не поточного дня)"""
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_file = f"saved_messages_{current_date}.json"

        # Знаходимо всі файли з повідомленнями
        message_files = [f for f in os.listdir('.') if f.startswith('saved_messages_') and f.endswith('.json')]

        deleted_count = 0
        for file in message_files:
            if file != current_file:
                try:
                    os.remove(file)
                    logger.info(f"🗑️ Видалено старий локальний файл: {file}")
                    deleted_count += 1
                except Exception as file_exc:
                    logger.error(f"❌ Помилка видалення файлу {file}: {file_exc}")

        if deleted_count > 0:
            logger.info(f"✅ Очищено {deleted_count} старих локальних файлів")
        else:
            logger.debug("📁 Немає старих локальних файлів для видалення")

    except Exception as cleanup_exc:
        logger.error(f"❌ Помилка при очищенні старих файлів: {cleanup_exc}")

# Глобальні змінні
user_viewing_state: Dict[str, Dict[str, Any]] = {}  # Ключ - str (user_id_filename)
files_cache: Dict[str, List[str]] = {}  # Ключ - str (user_id)

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
        except Exception as conn_exc:
            logger.error(f"Помилка підключення до Storage Box: {conn_exc}")
            return False
            
    def upload_file(self, local_path, remote_filename):
        try:
            sftp = self.ssh.open_sftp()

            # Визначаємо повний шлях (може містити підпапки, наприклад logs/bot_2025-10-08.log)
            full_remote_path = STORAGE_BOX_PATH + remote_filename

            # Витягуємо всі папки з шляху
            remote_dir = os.path.dirname(full_remote_path)
            path_parts = remote_dir.strip('/').split('/')
            current_path = ''

            # Створюємо всю структуру папок
            for part in path_parts:
                if not part:  # Пропускаємо порожні частини
                    continue
                current_path += '/' + part
                try:
                    sftp.chdir(current_path)
                    logger.debug(f"✅ Папка існує: {current_path}")
                except (IOError, OSError):
                    try:
                        sftp.mkdir(current_path)
                        logger.info(f"✅ Створено папку: {current_path}")
                    except Exception as mkdir_error:
                        logger.warning(f"⚠️ Не вдалося створити папку {current_path}: {mkdir_error}")

            # Завантажуємо файл
            sftp.put(local_path, full_remote_path)
            sftp.close()
            logger.info(f"✅ Файл {local_path} успішно завантажено на Storage Box як {remote_filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Помилка завантаження файлу: {e}")
            return False
            
    def list_files(self):
        try:
            sftp = self.ssh.open_sftp()
            try:
                sftp.chdir(STORAGE_BOX_PATH)
            except (IOError, OSError):
                logger.warning(f"⚠️ Папка {STORAGE_BOX_PATH} не існує - повертаю порожній список")
                sftp.close()
                return []

            files = sftp.listdir()
            sftp.close()

            # Фільтруємо тільки файли з повідомленнями
            message_files = [f for f in files if f.startswith('saved_messages_') and f.endswith('.json')]
            logger.info(f"📁 Знайдено файлів: {len(message_files)}")
            return sorted(message_files, reverse=True)
        except Exception as e:
            logger.error(f"❌ Помилка отримання списку файлів: {e}")
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

# AI Асистент для аналізу помилок
class AIAssistant:
    def __init__(self):
        self.error_history = []
        self.max_history = 10

    async def analyze_error(self, error_text: str, context: str = "") -> dict:
        """Аналізує помилку за допомогою AI"""
        try:
            # Формуємо промпт для AI
            prompt = f"""Ти - експерт Python розробник. Проаналізуй цю помилку в Telegram боті:

ПОМИЛКА:
{error_text}

КОНТЕКСТ:
{context}

КОД БОТА:
- Гібридний бот (Pyrogram Client API + python-telegram-bot Bot API)
- Збереження повідомлень в JSON
- Бекап на Hetzner Storage Box через SFTP
- Використовує asyncio, APScheduler

Надай:
1. 🔍 ПРИЧИНА: Чому виникла помилка (коротко)
2. 💡 РІШЕННЯ: Як виправити (конкретні кроки)
3. 🔧 КОД: Якщо потрібно - покажи виправлений код
4. ⚠️ ПОПЕРЕДЖЕННЯ: Що може статися якщо не виправити

Відповідай українською, коротко і зрозуміло."""

            if AI_PROVIDER == "openai" and openai_client:
                from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
                response = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",  # Швидка і дешева модель
                    messages=[
                        ChatCompletionSystemMessageParam(role="system", content="Ти експерт Python розробник, який допомагає виправляти помилки в коді."),
                        ChatCompletionUserMessageParam(role="user", content=prompt)
                    ],
                    max_tokens=1000,
                    temperature=0.7
                )
                analysis = response.choices[0].message.content

            elif AI_PROVIDER == "anthropic" and anthropic_client:
                from anthropic.types import MessageParam
                response = await anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=[
                        MessageParam(role="user", content=prompt)
                    ]
                )
                analysis = response.content[0].text
            else:
                return {
                    "success": False,
                    "error": "AI не налаштовано. Додайте API ключ в код."
                }

            # Зберігаємо в історію
            self.error_history.append({
                "timestamp": datetime.now().isoformat(),
                "error": error_text[:200],
                "analysis": analysis[:500]
            })

            # Обмежуємо історію
            if len(self.error_history) > self.max_history:
                self.error_history.pop(0)

            return {
                "success": True,
                "analysis": analysis,
                "provider": AI_PROVIDER
            }

        except Exception as e:
            logger.error(f"Помилка AI аналізу: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    async def suggest_fix(code_snippet: str, error_msg: str) -> str:
        """Пропонує виправлення коду"""
        try:
            prompt = f"""Виправ цей код Python:

КОД:
```python
{code_snippet}
```

ПОМИЛКА:
{error_msg}

Поверни ТІЛЬКИ виправлений код без пояснень."""

            if AI_PROVIDER == "openai" and openai_client:
                from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
                response = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        ChatCompletionSystemMessageParam(role="system", content="Ти експерт Python. Виправляй код без пояснень."),
                        ChatCompletionUserMessageParam(role="user", content=prompt)
                    ],
                    max_tokens=500,
                    temperature=0.3
                )
                return response.choices[0].message.content

            elif AI_PROVIDER == "anthropic" and anthropic_client:
                from anthropic.types import MessageParam
                response = await anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=500,
                    messages=[
                        MessageParam(role="user", content=prompt)
                    ]
                )
                return response.content[0].text
            else:
                return "AI не налаштовано"

        except Exception as e:
            logger.error(f"Помилка генерації виправлення: {e}")
            return f"Помилка: {e}"

# Глобальний AI асистент
ai_assistant = AIAssistant()

# Система моніторингу помилок
class ErrorMonitor:
    def __init__(self):
        self.errors = []
        self.max_errors = 50
        self.notification_sent = {}

    async def log_error(self, error: Exception, context: str = ""):
        """Логує помилку та відправляє сповіщення"""
        try:
            error_info = {
                "timestamp": datetime.now().isoformat(),
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "context": context
            }

            self.errors.append(error_info)
            if len(self.errors) > self.max_errors:
                self.errors.pop(0)

            # Логуємо в файл
            logger.error(f"❌ {context}: {error}", exc_info=True)

            # Відправляємо сповіщення адміну (не частіше 1 разу на 5 хвилин для однакових помилок)
            error_key = f"{type(error).__name__}_{context}"
            last_notification = self.notification_sent.get(error_key, 0)
            current_time = datetime.now().timestamp()

            if current_time - last_notification > 300:  # 5 хвилин
                await self.notify_admin(error_info)
                self.notification_sent[error_key] = current_time

        except Exception as e:
            logger.error(f"Помилка в ErrorMonitor: {e}")

    @staticmethod
    async def notify_admin(error_info: dict):
        """Відправляє сповіщення адміну про помилку"""
        try:
            if not bot_app:
                return

            message = f"""🚨 **ПОМИЛКА В БОТІ**

⏰ Час: {datetime.fromisoformat(error_info['timestamp']).strftime('%H:%M:%S')}
🔴 Тип: `{error_info['type']}`
📝 Контекст: {error_info['context']}

💬 Повідомлення:
```
{error_info['message'][:200]}
```

🤖 AI аналізує помилку..."""

            # Відправляємо повідомлення
            await bot_app.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=message,
                parse_mode='Markdown'
            )

            # Запускаємо AI аналіз
            analysis = await ai_assistant.analyze_error(
                error_text=error_info['traceback'][:1000],
                context=error_info['context']
            )

            if analysis['success']:
                await bot_app.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text=f"🤖 **AI Аналіз ({analysis['provider']}):**\n\n{analysis['analysis']}",
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Помилка відправки сповіщення: {e}")

    def get_recent_errors(self, limit: int = 10) -> list:
        """Повертає останні помилки"""
        return self.errors[-limit:]

# Глобальний монітор помилок
error_monitor = ErrorMonitor()

# Функція для створення головної клавіатури
def get_main_keyboard():
    """Створює головну клавіатуру бота"""
    keyboard = [
        [
            KeyboardButton("📊 Статус"),
            KeyboardButton("⚙️ Налаштування")
        ],
        [
            KeyboardButton("💾 Бекап"),
            KeyboardButton("📂 Історія")
        ],
        [
            KeyboardButton("🤖 AI Помічник"),
            KeyboardButton("📝 Логи")
        ],
        [
            KeyboardButton("🔧 Технічне"),
            KeyboardButton("ℹ️ Допомога")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функція для створення технічної клавіатури
def get_technical_keyboard():
    """Створює технічну клавіатуру"""
    keyboard = [
        [
            KeyboardButton("🔌 Статус Client API"),
            KeyboardButton("🧪 Тест")
        ],
        [
            KeyboardButton("🔍 Сканувати"),
            KeyboardButton("🗂️ Debug")
        ],
        [
            KeyboardButton("🗑️ Очистити старі файли")
        ],
        [
            KeyboardButton("🔙 Назад")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функція для створення клавіатури логів
def get_logs_keyboard():
    """Створює клавіатуру для роботи з логами"""
    keyboard = [
        [
            KeyboardButton("📤 Відправити логи"),
            KeyboardButton("🗑️ Очистити логи")
        ],
        [
            KeyboardButton("📋 Останні помилки"),
            KeyboardButton("🔙 Назад")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функція для створення AI клавіатури
def get_ai_keyboard():
    """Створює клавіатуру для AI помічника"""
    keyboard = [
        [
            KeyboardButton("🔍 Аналіз помилок"),
            KeyboardButton("📊 Історія аналізів")
        ],
        [
            KeyboardButton("⚙️ Налаштування AI"),
            KeyboardButton("🔙 Назад")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функції для роботи з даними
def get_current_data_file():
    """Повертає ім'я файлу даних для поточної дати"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    return f"saved_messages_{current_date}.json"

def load_messages():
    data_file = get_current_data_file()
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"messages": []}

def save_message(message_data):
    data = load_messages()
    data["messages"].append(message_data)

    data_file = get_current_data_file()
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    # Компактний вивід в консоль
    chat_name = message_data.get('chat_title', 'Збережені')
    msg_time = datetime.fromisoformat(message_data['date']).strftime('%H:%M:%S')
    msg_text = message_data.get('text', '[медіа]')[:50]  # Перші 50 символів

    print(f"💾 {chat_name} | {msg_time} | {msg_text}")

    logger.info(f"Збережено повідомлення: {message_data['message_id']}")

# Функція для відправки файлу на Storage Box
async def upload_to_storage_box():
    # Отримуємо файл поточного дня
    data_file = get_current_data_file()

    if not os.path.exists(data_file):
        logger.info("Немає файлу для відправки сьогодні")
        return

    # Створюємо унікальну назву файлу з датою
    file_date = datetime.now().strftime("%Y-%m-%d")
    remote_filename = f"saved_messages_{file_date}.json"

    # Завантажуємо файл на Storage Box
    storage_box = StorageBoxManager()
    if storage_box.connect():
        success = storage_box.upload_file(data_file, remote_filename)
        storage_box.close()

        if success:
            logger.info(f"✅ Файл {data_file} успішно відправлено на сервер")
            logger.info(f"📁 Локальний файл збережено до автоматичного очищення о 01:00")
        else:
            logger.error("Не вдалося завантажити файл на Storage Box - локальний файл збережено")
    else:
        logger.error("Не вдалося підключитися до Storage Box - локальний файл збережено")

# Функція для відправки логів на Storage Box
async def upload_logs_to_storage_box():
    """Відправляє старі лог-файли на Storage Box"""
    try:
        # Знаходимо всі лог-файли
        log_files = [f for f in os.listdir('.') if f.startswith('bot_') and f.endswith('.log')]

        if not log_files:
            logger.info("Немає лог-файлів для відправки")
            return

        storage_box = StorageBoxManager()
        if not storage_box.connect():
            logger.error("Не вдалося підключитися до Storage Box для відправки логів")
            return

        uploaded_count = 0
        for log_file in log_files:
            # Не відправляємо поточний лог-файл
            if log_file == get_log_filename():
                continue

            # Відправляємо на сервер
            remote_filename = f"logs/{log_file}"
            if storage_box.upload_file(log_file, remote_filename):
                uploaded_count += 1
                logger.info(f"✅ Лог {log_file} відправлено на сервер")
            else:
                logger.error(f"❌ Помилка відправки логу {log_file}")

        storage_box.close()
        logger.info(f"📤 Відправлено {uploaded_count} лог-файлів на Storage Box")

    except Exception as e:
        logger.error(f"Помилка при відправці логів: {e}")

# Функція для очищення старих логів
def cleanup_old_logs():
    """Видаляє ВСІ старі лог-файли (крім поточного)"""
    try:
        current_log = get_log_filename()
        deleted_count = 0

        # Знаходимо всі лог-файли
        log_files = [f for f in os.listdir('.') if f.startswith('bot_') and f.endswith('.log')]

        for log_file in log_files:
            # Не видаляємо поточний лог-файл
            if log_file == current_log:
                continue

            try:
                os.remove(log_file)
                deleted_count += 1
                logger.info(f"🗑️ Видалено старий лог: {log_file}")
            except Exception as e:
                logger.warning(f"Не вдалося видалити файл {log_file}: {e}")

        if deleted_count > 0:
            logger.info(f"✅ Видалено {deleted_count} старих лог-файлів")
        else:
            logger.debug("📁 Немає старих лог-файлів для видалення")

    except Exception as e:
        logger.error(f"❌ Помилка при очищенні логів: {e}")

# Глобальна змінна для event loop
main_loop: asyncio.AbstractEventLoop | None = None

# Функція-обгортка для асинхронного завантаження
def upload_to_storage_box_sync():
    if main_loop is not None and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(upload_to_storage_box(), main_loop)
    else:
        logger.warning("Event loop не доступний для завантаження")

# Функція-обгортка для відправки логів
def upload_logs_sync():
    if main_loop is not None and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(upload_logs_to_storage_box(), main_loop)
    else:
        logger.warning("Event loop не доступний для відправки логів")

# Функція-обгортка для автоматичного сканування
def auto_scan_sync():
    if main_loop is not None and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(fetch_recent_messages(), main_loop)
    else:
        logger.warning("Event loop не доступний для сканування")

# Планувальник для щоденного завантаження
def setup_scheduler():
    scheduler = BackgroundScheduler()

    # Запускаємо о 23:59 кожного дня
    scheduler.add_job(upload_to_storage_box_sync, 'cron', hour=23, minute=59)

    # Відправляємо логи о 23:58 (перед бекапом повідомлень)
    scheduler.add_job(upload_logs_sync, 'cron', hour=23, minute=58)

    # Очищаємо старі логи та файли о 01:00 (після бекапу)
    scheduler.add_job(cleanup_old_logs, 'cron', hour=1, minute=0)
    scheduler.add_job(cleanup_old_local_files, 'cron', hour=1, minute=0)

    scheduler.start()
    logger.info("Планувальник запущено:")
    logger.info("- Щоденне резервне копіювання о 23:59")
    logger.info("- Відправка логів на сервер о 23:58")
    logger.info("- Очищення старих логів та файлів о 01:00")
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
        if settings['save_saved_messages']:
            async for message in client_app.get_chat_history("me"):
                # Пропускаємо повідомлення без тексту
                if not message.text:
                    continue

                # Зупиняємося коли дійшли до останнього збереженого повідомлення
                if message.id <= last_saved_id:
                    break  # Оскільки повідомлення йдуть в порядку від нових до старих

                # Перевіряємо чи не збережено вже (для надійності)
                if message.id not in existing_ids:
                    logger.info(f"⚡ ШВИДКЕ ЗБЕРЕЖЕННЯ (Saved): {message.id} - {message.text[:50]}...")

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

# Глобальна змінна для відстеження останньої перевірки діалогів
last_dialogs_check = 0

async def check_private_chats():
    """Перевірка приватних чатів кожні 5 секунд"""
    global last_dialogs_check

    try:
        # Перевіряємо тільки якщо увімкнено збереження приватних чатів
        if not settings['save_private_chats'] and not settings['save_groups'] and not settings['save_channels']:
            return

        current_time = asyncio.get_event_loop().time()

        # Перевіряємо діалоги з налаштованим інтервалом
        if current_time - last_dialogs_check < settings['dialogs_check_interval']:
            return

        last_dialogs_check = current_time

        # Завантажуємо існуючі повідомлення
        data = load_messages()
        existing_ids = set(msg['message_id'] for msg in data['messages'])
        new_messages_count = 0

        # Перевіряємо останні діалоги з налаштованою кількістю
        dialog_count = 0
        async for dialog in client_app.get_dialogs(limit=settings['dialogs_limit']):
            dialog_count += 1
            chat = dialog.chat

            # Пропускаємо "Збережені повідомлення" (вони перевіряються окремо)
            if chat.id == ALLOWED_USER_ID:
                continue

            # Перевіряємо тип чату
            chat_type_str = str(chat.type).upper()

            # Визначаємо чи потрібно перевіряти цей чат
            should_check = False
            if 'PRIVATE' in chat_type_str and settings['save_private_chats']:
                should_check = True
            elif ('GROUP' in chat_type_str or 'SUPERGROUP' in chat_type_str) and settings['save_groups']:
                should_check = True
            elif 'CHANNEL' in chat_type_str and settings['save_channels']:
                should_check = True

            if not should_check:
                continue

            # Перевіряємо останні повідомлення з цього чату (з налаштуванням)
            try:
                message_count = 0
                async for message in client_app.get_chat_history(chat.id, limit=settings['messages_per_dialog']):
                    message_count += 1

                    # Пропускаємо повідомлення без тексту
                    if not message.text:
                        continue

                    # Перевіряємо чи не збережено вже
                    if message.id in existing_ids:
                        continue

                    logger.info(f"⚡ ШВИДКЕ ЗБЕРЕЖЕННЯ (Private): {message.id} від {chat.id} - {message.text[:50]}...")

                    # Визначаємо тип чату та назву
                    chat_type = str(chat.type)
                    chat_title = getattr(chat, 'title', None)

                    # Для приватних чатів додаємо ім'я
                    if 'PRIVATE' in chat_type.upper():
                        if hasattr(chat, 'first_name'):
                            chat_title = chat.first_name
                            if hasattr(chat, 'last_name') and chat.last_name:
                                chat_title += f" {chat.last_name}"

                    message_data = {
                        "message_id": message.id,
                        "chat_id": chat.id,
                        "chat_type": chat_type,
                        "chat_title": chat_title,
                        "chat_username": getattr(chat, 'username', None),
                        "from_user_id": message.from_user.id if message.from_user else ALLOWED_USER_ID,
                        "from_username": message.from_user.username if message.from_user else None,
                        "from_first_name": message.from_user.first_name if message.from_user else "Unknown",
                        "text": message.text,
                        "date": message.date.isoformat(),
                        "is_outgoing": (message.from_user.id == ALLOWED_USER_ID) if message.from_user else False,
                        "is_edited": False
                    }

                    save_message(message_data)
                    new_messages_count += 1
                    existing_ids.add(message.id)

            except Exception as e:
                logger.error(f"❌ Помилка перевірки чату {chat.id}: {e}")
                continue

        if new_messages_count > 0:
            logger.info(f"⚡ Швидко збережено {new_messages_count} повідомлень з приватних чатів!")

    except Exception as e:
        logger.error(f"❌ Помилка перевірки приватних чатів: {e}")

async def message_checker_loop():
    """Безкінечний цикл перевірки повідомлень"""
    logger.info(f"⚡ Запускаю швидку перевірку повідомлень кожні {settings['check_interval']} секунди...")
    logger.info(f"📱 Збережені повідомлення: {'✅' if settings['save_saved_messages'] else '❌'}")
    logger.info(f"💬 Приватні чати: {'✅' if settings['save_private_chats'] else '❌'}")
    logger.info(f"👥 Групи: {'✅' if settings['save_groups'] else '❌'}")
    logger.info(f"📢 Канали: {'✅' if settings['save_channels'] else '❌'}")

    while True:
        try:
            # Перевіряємо "Збережені повідомлення" з налаштованим інтервалом
            await quick_message_check()

            # Перевіряємо приватні чати (функція сама контролює частоту)
            await check_private_chats()

            await asyncio.sleep(settings['check_interval'])  # Затримка з налаштувань
        except Exception as e:
            logger.error(f"❌ Помилка в циклі перевірки: {e}")
            await asyncio.sleep(1)  # При помилці чекаємо довше

# Обробник RAW updates для миттєвого отримання повідомлень
@client_app.on_raw_update()
async def handle_raw_update(_client: Client, update, users, _chats):
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
                    logger.info(f"✅ МИТТЄВО збережено в {get_current_data_file()}")
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

# Функція для перевірки чи потрібно зберігати повідомлення з цього чату
def should_save_message(message: Message) -> bool:
    """Перевіряє чи потрібно зберігати повідомлення на основі налаштувань"""

    # Збережені повідомлення
    if message.chat.id == ALLOWED_USER_ID:
        return settings['save_saved_messages']

    # Перевіряємо тип чату
    chat_type = str(message.chat.type)

    # Приватні чати (не секретні)
    if 'PRIVATE' in chat_type.upper():
        return settings['save_private_chats']

    # Групи
    if 'GROUP' in chat_type.upper() or 'SUPERGROUP' in chat_type.upper():
        return settings['save_groups']

    # Канали
    if 'CHANNEL' in chat_type.upper():
        return settings['save_channels']

    return False

# Резервний обробник для звичайних повідомлень
@client_app.on_message()
async def handle_regular_messages(_client: Client, message: Message):
    try:
        global message_counter
        message_counter += 1

        logger.info(f"📱 ЗВИЧАЙНИЙ ОБРОБНИК! Повідомлення #{message_counter}")
        logger.info(f"📨 ID: {message.id}")
        logger.info(f"📝 Text: {message.text}")
        logger.info(f"💬 Chat: {message.chat.id} ({message.chat.type})")
        logger.info(f"👤 From: {message.from_user.id if message.from_user else 'None'}")
        logger.info(f"📤 Outgoing: {getattr(message, 'outgoing', 'Unknown')}")

        # Перевіряємо чи потрібно зберігати повідомлення з цього чату
        if not should_save_message(message):
            logger.info(f"⏭️ Пропускаємо чат {message.chat.id} ({message.chat.type}) - вимкнено в налаштуваннях")
            return

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

            # Для приватних чатів додаємо ім'я співрозмовника
            if 'PRIVATE' in chat_type.upper() and message.chat.id != ALLOWED_USER_ID:
                if message.from_user and message.from_user.id != ALLOWED_USER_ID:
                    chat_title = f"{message.from_user.first_name}"
                    if message.from_user.last_name:
                        chat_title += f" {message.from_user.last_name}"
                elif hasattr(message.chat, 'first_name'):
                    chat_title = message.chat.first_name
                    if hasattr(message.chat, 'last_name') and message.chat.last_name:
                        chat_title += f" {message.chat.last_name}"

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
            logger.info(f"✅ РЕЗЕРВНО збережено в {get_current_data_file()}")
        else:
            logger.info("⚠️ Пропускаємо (немає тексту)")

    except Exception as e:
        await error_monitor.log_error(e, "Обробка повідомлення Pyrogram")

# ============= TELEGRAM BOT (для управління) =============

# Ініціалізація бота
bot_app = Application.builder().token(BOT_TOKEN).build()

# Обробники команд бота
async def start(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if update.message:
        await update.message.reply_text(
            "🤖 **Гібридний бот для збереження повідомлень**\n\n"
            "📱 **Client API** зберігає всі ваші повідомлення автоматично\n"
            "🤖 **Bot API** дозволяє керувати процесом\n"
            "🧠 **AI Помічник** аналізує та виправляє помилки\n\n"
            "Використовуйте кнопки нижче для керування ботом! 👇",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )

async def status(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    data = load_messages()
    message_count = len(data["messages"])
    if update.message:
        await update.message.reply_text(f"📊 Статус: збережено {message_count} повідомлень за сьогодні ({CURRENT_DATE})")

async def backup_now(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if update.message:
        await update.message.reply_text("🔄 Початок миттєвого резервного копіювання...")
        await upload_to_storage_box()
        await update.message.reply_text("✅ Резервне копіювання завершено!")

async def clientstatus(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    try:
        if client_app.is_connected:
            me = await client_app.get_me()
            status_text = f"✅ Client API підключений\n👤 Користувач: {me.first_name} (@{me.username})"
        else:
            status_text = "❌ Client API не підключений"
    except Exception as check_error:
        status_text = f"❌ Помилка перевірки статусу Client API: {check_error}"

    if update.message:
        await update.message.reply_text(status_text)

async def view_history(update: Update, context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    await list_files(update, context, 0)

async def list_files(update: Update, context: ContextType, page: int = 0) -> None:
    user_id = update.effective_user.id

    # Отримуємо список файлів з Storage Box
    storage_box = StorageBoxManager()
    if not storage_box.connect():
        if update.message:
            await update.message.reply_text("❌ Не вдалося підключитися до Storage Box")
        return

    files = storage_box.list_files()
    storage_box.close()

    if not files:
        if update.message:
            await update.message.reply_text("📁 Файлів не знайдено.")
        return

    # Зберігаємо файли в кеш для цього користувача
    files_cache[str(user_id)] = files

    # Відображаємо файли з пагінацією
    await show_files_page(update, context, page, files)

async def show_files_page(update: Update, _context: ContextType, page: int, files: List[str]) -> None:
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
    elif update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def refresh_settings_message(update: Update, _context: ContextType) -> None:
    """Оновлює повідомлення з налаштуваннями"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    # Завантажуємо дані для статистики
    data = load_messages()
    stats = {
        'SAVED_MESSAGES': 0,
        'PRIVATE': 0,
        'GROUP': 0,
        'SUPERGROUP': 0,
        'CHANNEL': 0,
        'OTHER': 0
    }

    for msg in data['messages']:
        chat_type = msg.get('chat_type', 'UNKNOWN')
        if 'SAVED' in chat_type or msg.get('chat_id') == ALLOWED_USER_ID:
            stats['SAVED_MESSAGES'] += 1
        elif 'PRIVATE' in chat_type:
            stats['PRIVATE'] += 1
        elif 'SUPERGROUP' in chat_type:
            stats['SUPERGROUP'] += 1
        elif 'GROUP' in chat_type:
            stats['GROUP'] += 1
        elif 'CHANNEL' in chat_type:
            stats['CHANNEL'] += 1
        else:
            stats['OTHER'] += 1

    settings_text = (
        "⚙️ **Налаштування збереження повідомлень:**\n\n"
        f"📱 Збережені повідомлення: {'✅ Увімкнено' if settings['save_saved_messages'] else '❌ Вимкнено'}\n"
        f"💬 Приватні чати: {'✅ Увімкнено' if settings['save_private_chats'] else '❌ Вимкнено'}\n"
        f"👥 Групи: {'✅ Увімкнено' if settings['save_groups'] else '❌ Вимкнено'}\n"
        f"📢 Канали: {'✅ Увімкнено' if settings['save_channels'] else '❌ Вимкнено'}\n\n"
        "⚙️ **Технічні налаштування:**\n"
        f"⏱️ Інтервал перевірки Збережених: {settings['check_interval']} сек\n"
        f"⏱️ Інтервал перевірки діалогів: {settings['dialogs_check_interval']} сек\n"
        f"📊 Кількість діалогів: {settings['dialogs_limit']}\n"
        f"📝 Повідомлень з діалогу: {settings['messages_per_dialog']}\n\n"
        "📊 **Статистика збережених повідомлень:**\n"
        f"📱 Збережені: {stats['SAVED_MESSAGES']}\n"
        f"💬 Приватні: {stats['PRIVATE']}\n"
        f"👥 Групи: {stats['GROUP'] + stats['SUPERGROUP']}\n"
        f"📢 Канали: {stats['CHANNEL']}\n"
        f"❓ Інші: {stats['OTHER']}\n\n"
        "💡 Використовуйте кнопки нижче для зміни налаштувань"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                f"📱 Збережені: {'✅' if settings['save_saved_messages'] else '❌'}",
                callback_data='toggle_saved'
            ),
            InlineKeyboardButton(
                f"💬 Приватні: {'✅' if settings['save_private_chats'] else '❌'}",
                callback_data='toggle_private'
            )
        ],
        [
            InlineKeyboardButton(
                f"👥 Групи: {'✅' if settings['save_groups'] else '❌'}",
                callback_data='toggle_groups'
            ),
            InlineKeyboardButton(
                f"📢 Канали: {'✅' if settings['save_channels'] else '❌'}",
                callback_data='toggle_channels'
            )
        ],
        [
            InlineKeyboardButton("⚙️ Технічні налаштування", callback_data='tech_settings')
        ],
        [
            InlineKeyboardButton("🔄 Оновити", callback_data='refresh_settings')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(settings_text, parse_mode='Markdown', reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(settings_text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_tech_settings(update: Update, _context: ContextType) -> None:
    """Показує технічні налаштування"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    text = (
        "⚙️ **Технічні налаштування:**\n\n"
        f"⏱️ **Інтервал перевірки Збережених:** {settings['check_interval']} сек\n"
        "Як часто перевіряти \"Збережені повідомлення\"\n\n"
        f"⏱️ **Інтервал перевірки діалогів:** {settings['dialogs_check_interval']} сек\n"
        "Як часто сканувати приватні чати/групи/канали\n\n"
        f"📊 **Кількість діалогів:** {settings['dialogs_limit']}\n"
        "Скільки діалогів перевіряти за раз\n\n"
        f"📝 **Повідомлень з діалогу:** {settings['messages_per_dialog']}\n"
        "Скільки останніх повідомлень брати з кожного діалогу\n\n"
        "💡 Натисніть на кнопку щоб змінити значення"
    )

    keyboard = [
        [InlineKeyboardButton("⏱️ Інтервал Збережених", callback_data='dummy')],
        [
            InlineKeyboardButton("0.3 сек", callback_data='set_check_interval_0.3'),
            InlineKeyboardButton("0.5 сек", callback_data='set_check_interval_0.5'),
            InlineKeyboardButton("1 сек", callback_data='set_check_interval_1'),
            InlineKeyboardButton("2 сек", callback_data='set_check_interval_2')
        ],
        [InlineKeyboardButton("⏱️ Інтервал діалогів", callback_data='dummy')],
        [
            InlineKeyboardButton("3 сек", callback_data='set_dialogs_interval_3'),
            InlineKeyboardButton("5 сек", callback_data='set_dialogs_interval_5'),
            InlineKeyboardButton("10 сек", callback_data='set_dialogs_interval_10'),
            InlineKeyboardButton("30 сек", callback_data='set_dialogs_interval_30')
        ],
        [InlineKeyboardButton("📊 Кількість діалогів", callback_data='dummy')],
        [
            InlineKeyboardButton("10", callback_data='set_dialogs_limit_10'),
            InlineKeyboardButton("20", callback_data='set_dialogs_limit_20'),
            InlineKeyboardButton("50", callback_data='set_dialogs_limit_50'),
            InlineKeyboardButton("100", callback_data='set_dialogs_limit_100')
        ],
        [InlineKeyboardButton("📝 Повідомлень з діалогу", callback_data='dummy')],
        [
            InlineKeyboardButton("3", callback_data='set_messages_per_dialog_3'),
            InlineKeyboardButton("5", callback_data='set_messages_per_dialog_5'),
            InlineKeyboardButton("10", callback_data='set_messages_per_dialog_10'),
            InlineKeyboardButton("20", callback_data='set_messages_per_dialog_20')
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_settings')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_callback_query(update: Update, context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.callback_query.answer("❌ Вибачте, у вас немає доступу до цього бота.", show_alert=True)
        return

    query = update.callback_query
    data = query.data

    # Ігноруємо dummy кнопки (заголовки)
    if data == 'dummy':
        await query.answer()
        return

    # Обробка налаштувань
    if data == 'toggle_saved':
        settings['save_saved_messages'] = not settings['save_saved_messages']
        await query.answer(f"📱 Збережені повідомлення: {'✅ Увімкнено' if settings['save_saved_messages'] else '❌ Вимкнено'}")
        # Оновлюємо повідомлення
        await refresh_settings_message(update, context)

    elif data == 'toggle_private':
        settings['save_private_chats'] = not settings['save_private_chats']
        await query.answer(f"💬 Приватні чати: {'✅ Увімкнено' if settings['save_private_chats'] else '❌ Вимкнено'}")
        await refresh_settings_message(update, context)

    elif data == 'toggle_groups':
        settings['save_groups'] = not settings['save_groups']
        await query.answer(f"👥 Групи: {'✅ Увімкнено' if settings['save_groups'] else '❌ Вимкнено'}")
        await refresh_settings_message(update, context)

    elif data == 'toggle_channels':
        settings['save_channels'] = not settings['save_channels']
        await query.answer(f"📢 Канали: {'✅ Увімкнено' if settings['save_channels'] else '❌ Вимкнено'}")
        await refresh_settings_message(update, context)

    elif data == 'tech_settings':
        await query.answer()
        await show_tech_settings(update, context)

    elif data == 'refresh_settings':
        await query.answer("🔄 Оновлено")
        await refresh_settings_message(update, context)

    elif data.startswith('set_check_interval_'):
        value = float(data.split('_')[-1])
        settings['check_interval'] = value
        await query.answer(f"⏱️ Інтервал перевірки: {value} сек")
        await show_tech_settings(update, context)

    elif data.startswith('set_dialogs_interval_'):
        value = int(data.split('_')[-1])
        settings['dialogs_check_interval'] = value
        await query.answer(f"⏱️ Інтервал діалогів: {value} сек")
        await show_tech_settings(update, context)

    elif data.startswith('set_dialogs_limit_'):
        value = int(data.split('_')[-1])
        settings['dialogs_limit'] = value
        await query.answer(f"📊 Кількість діалогів: {value}")
        await show_tech_settings(update, context)

    elif data.startswith('set_messages_per_dialog_'):
        value = int(data.split('_')[-1])
        settings['messages_per_dialog'] = value
        await query.answer(f"📝 Повідомлень з діалогу: {value}")
        await show_tech_settings(update, context)

    elif data == 'back_to_settings':
        await query.answer()
        await refresh_settings_message(update, context)

    elif data == 'back_to_files':
        await query.answer()
        # Очищаємо кеш перегляду файлів для цього користувача
        user_id_str = str(user_id)
        keys_to_remove = [k for k in user_viewing_state.keys() if str(k).startswith(f"{user_id_str}_")]
        for key in keys_to_remove:
            del user_viewing_state[key]
        # Повертаємось до списку файлів
        if user_id_str in files_cache:
            await show_files_page(update, context, 0, files_cache[user_id_str])
        else:
            await query.edit_message_text("📁 Список файлів застарів. Використайте кнопку '📂 Історія' для оновлення.")

    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        user_id_str = str(user_id)
        if user_id_str in files_cache:
            await query.answer()
            await show_files_page(update, context, page, files_cache[user_id_str])
        else:
            await query.answer("📁 Список файлів застарів. Будь ласка, запросіть його знову.", show_alert=True)

    elif data.startswith("view_"):
        filename = data.split("_", 1)[1]
        await query.answer()
        await view_file(update, context, filename, page=0)

    elif data.startswith("msgpage_"):
        # Формат: msgpage_filename_page
        # Знаходимо останнє підкреслення - це номер сторінки
        last_underscore = data.rfind("_")
        if last_underscore > 8:  # після "msgpage_"
            filename = data[8:last_underscore]  # все між "msgpage_" і останнім "_"
            msg_page = int(data[last_underscore + 1:])  # все після останнього "_"
            await query.answer()
            await view_file(update, context, filename, msg_page)

    elif data.startswith("download_"):
        filename = data.split("_", 1)[1]
        await query.answer("📥 Завантажую файл...")
        await download_file_to_user(update, context, filename)

async def view_file(update: Update, _context: ContextType, filename: str, page: int = 0) -> None:
    """Показує повідомлення з файлу з пагінацією"""
    user_id = update.effective_user.id

    # Перевіряємо чи файл вже в кеші
    cache_key = f"{user_id}_{filename}"
    if cache_key not in user_viewing_state:
        # Скачуємо файл з Storage Box
        storage_box = StorageBoxManager()
        if not storage_box.connect():
            if update.callback_query and update.callback_query.message and isinstance(update.callback_query.message, TelegramMessage):
                await update.callback_query.message.reply_text("❌ Не вдалося підключитися до Storage Box")
            return

        local_path = storage_box.download_file(filename)
        storage_box.close()

        if not local_path:
            if update.callback_query and update.callback_query.message and isinstance(update.callback_query.message, TelegramMessage):
                await update.callback_query.message.reply_text("❌ Не вдалося завантажити файл.")
            return

        # Завантажуємо дані з файлу
        with open(local_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)

        # Видаляємо тимчасовий файл
        if os.path.exists(local_path):
            os.remove(local_path)

        # Зберігаємо в кеш
        user_viewing_state[cache_key] = {
            'filename': filename,
            'messages': file_data.get('messages', [])
        }

    # Отримуємо дані з кешу
    messages = user_viewing_state[cache_key]['messages']

    if not messages:
        text = "📁 Файл порожній."
        keyboard = [[InlineKeyboardButton("🔙 Назад до списку", callback_data="back_to_files")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        return

    # Пагінація
    messages_per_page = 5
    total_pages = (len(messages) + messages_per_page - 1) // messages_per_page

    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start_idx = page * messages_per_page
    end_idx = min(start_idx + messages_per_page, len(messages))

    # Форматуємо текст
    file_date = filename.replace('saved_messages_', '').replace('.json', '')
    text = f"📁 **Файл:** {file_date}\n"
    text += f"📊 **Всього повідомлень:** {len(messages)}\n"
    text += f"📄 **Сторінка:** {page + 1} з {total_pages}\n\n"

    # Показуємо повідомлення на поточній сторінці
    for i in range(start_idx, end_idx):
        msg = messages[i]
        date = datetime.fromisoformat(msg['date']).strftime("%d.%m %H:%M")
        direction = "➡️" if msg.get('is_outgoing', False) else "⬅️"
        sender = msg.get('from_first_name', 'Невідомо')
        chat_title = msg.get('chat_title', 'Невідомо')
        text_preview = (msg.get('text', '') or '')[:100]
        if len(msg.get('text', '')) > 100:
            text_preview += "..."

        text += f"**{i + 1}.** {direction} {date}\n"
        text += f"👤 **{sender}** → 💬 **{chat_title}**\n"
        text += f"📝 {text_preview}\n\n"

    # Створюємо клавіатуру навігації
    keyboard = []

    # Кнопки навігації по сторінках
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f"msgpage_{filename}_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="dummy"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Наступна ➡️", callback_data=f"msgpage_{filename}_{page+1}"))
    keyboard.append(nav_buttons)

    # Кнопки швидкої навігації
    quick_nav = []
    if page > 0:
        quick_nav.append(InlineKeyboardButton("⏮️ Перша", callback_data=f"msgpage_{filename}_0"))
    if page < total_pages - 1:
        quick_nav.append(InlineKeyboardButton("Остання ⏭️", callback_data=f"msgpage_{filename}_{total_pages-1}"))
    if quick_nav:
        keyboard.append(quick_nav)

    # Кнопки дій
    action_buttons = [
        InlineKeyboardButton("📥 Завантажити файл", callback_data=f"download_{filename}"),
        InlineKeyboardButton("🔙 До списку", callback_data="back_to_files")
    ]
    keyboard.append(action_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def download_file_to_user(update: Update, _context: ContextType, filename: str) -> None:
    """Завантажує файл користувачу"""
    # Скачуємо файл з Storage Box
    storage_box = StorageBoxManager()
    if not storage_box.connect():
        if update.callback_query and update.callback_query.message and isinstance(update.callback_query.message, TelegramMessage):
            await update.callback_query.message.reply_text("❌ Не вдалося підключитися до Storage Box")
        return

    local_path = storage_box.download_file(filename)
    storage_box.close()

    if not local_path:
        if update.callback_query and update.callback_query.message and isinstance(update.callback_query.message, TelegramMessage):
            await update.callback_query.message.reply_text("❌ Не вдалося завантажити файл.")
        return

    # Відправляємо файл користувачу
    try:
        if update.callback_query and update.callback_query.message and isinstance(update.callback_query.message, TelegramMessage):
            with open(local_path, 'rb') as f:
                await update.callback_query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📁 {filename}"
                )
    except Exception as exc:
        if update.callback_query and update.callback_query.message and isinstance(update.callback_query.message, TelegramMessage):
            await update.callback_query.message.reply_text(f"❌ Помилка відправки файлу: {exc}")
    finally:
        # Видаляємо тимчасовий файл
        if os.path.exists(local_path):
            os.remove(local_path)

async def myuuid(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    user_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(user_id)))
    if update.message:
        await update.message.reply_text(
            f"ℹ️ **Ваша інформація:**\n"
            f"🆔 Telegram ID: `{user_id}`\n"
            f"🔑 UUID: `{user_uuid}`\n\n"
            f"🔐 Дозволений UUID: `{ALLOWED_UUID}`\n\n"
            f"📝 Надайте ваш UUID адміністратору для отримання доступу.",
            parse_mode='Markdown'
        )

async def debug_settings(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
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
- Поточний файл: `{get_current_data_file()}`
- Існує: `{os.path.exists(get_current_data_file())}`

⚠️ **Перевірте:**
1. API_ID та API_HASH мають бути налаштовані
2. ALLOWED_USER_ID має відповідати вашому Telegram ID
3. Client API має бути запущений"""

    await update.message.reply_text(debug_info, parse_mode='Markdown')

# Функція для принудового отримання повідомлень
async def fetch_recent_messages():
    try:
        from datetime import datetime, timedelta

        logger.info("🔍 Принудово отримуємо повідомлення за сьогодні...")

        # Визначаємо початок сьогоднішнього дня (00:00:00)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Завантажуємо існуючі повідомлення з УСІХ локальних файлів
        existing_ids = set()

        # Шукаємо всі файли saved_messages_*.json
        for filename in os.listdir('.'):
            if filename.startswith('saved_messages_') and filename.endswith('.json'):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)
                        for msg in file_data.get('messages', []):
                            existing_ids.add(msg['message_id'])
                    logger.debug(f"📂 Завантажено ID з {filename}")
                except Exception as e:
                    logger.warning(f"⚠️ Не вдалося прочитати {filename}: {e}")

        logger.info(f"📊 Знайдено {len(existing_ids)} вже збережених повідомлень у всіх файлах")

        new_messages_count = 0
        checked_messages_count = 0

        # Отримуємо повідомлення з "Збережених повідомлень" без ліміту
        logger.info(f"📅 Шукаємо повідомлення з {today_start.strftime('%Y-%m-%d %H:%M:%S')}...")

        async for message in client_app.get_chat_history("me"):
            checked_messages_count += 1

            # Перевіряємо дату повідомлення
            if message.date < today_start:
                logger.info(f"⏹️ Досягнуто повідомлень до сьогоднішнього дня. Перевірено: {checked_messages_count}, нових: {new_messages_count}")
                break

            # Пропускаємо повідомлення без тексту
            if not message.text:
                continue

            # Перевіряємо чи це повідомлення ще не збережено
            if message.id not in existing_ids:
                logger.info(f"💾 Зберігаємо нове повідомлення: {message.id} - {message.text[:50]}...")

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
                existing_ids.add(message.id)
                new_messages_count += 1

        logger.info(f"✅ Завершено сканування Збережених. Перевірено: {checked_messages_count}, збережено нових: {new_messages_count}")

        # Тепер скануємо приватні чати, якщо увімкнено
        if settings['save_private_chats']:
            logger.info("🔍 Сканую приватні чати за сьогодні...")

            total_chats_scanned = 0
            total_new_messages = 0

            async for dialog in client_app.get_dialogs(limit=settings['dialogs_limit']):
                chat = dialog.chat

                # Пропускаємо "Збережені повідомлення"
                if chat.id == ALLOWED_USER_ID:
                    continue

                # Перевіряємо тільки приватні чати
                chat_type_str = str(chat.type).upper()
                if 'PRIVATE' not in chat_type_str:
                    continue

                total_chats_scanned += 1
                chat_new_messages = 0
                chat_checked_messages = 0
                chat_title = "Невідомо"  # Ініціалізуємо значення за замовчуванням

                try:
                    # Скануємо повідомлення з цього чату за сьогодні
                    async for message in client_app.get_chat_history(chat.id):
                        chat_checked_messages += 1

                        # Перевіряємо дату повідомлення
                        if message.date < today_start:
                            break

                        # Пропускаємо повідомлення без тексту
                        if not message.text:
                            continue

                        # Перевіряємо чи не збережено вже
                        if message.id in existing_ids:
                            continue

                        # Визначаємо назву чату
                        chat_title = getattr(chat, 'title', None)
                        if 'PRIVATE' in chat_type_str:
                            if hasattr(chat, 'first_name'):
                                chat_title = chat.first_name
                                if hasattr(chat, 'last_name') and chat.last_name:
                                    chat_title += f" {chat.last_name}"

                        logger.info(f"💾 Зберігаємо з {chat_title}: {message.id} - {message.text[:50]}...")

                        message_data = {
                            "message_id": message.id,
                            "chat_id": chat.id,
                            "chat_type": chat_type_str,
                            "chat_title": chat_title,
                            "chat_username": getattr(chat, 'username', None),
                            "from_user_id": message.from_user.id if message.from_user else None,
                            "from_username": message.from_user.username if message.from_user else None,
                            "from_first_name": message.from_user.first_name if message.from_user else None,
                            "text": message.text,
                            "date": message.date.isoformat(),
                            "is_outgoing": (message.from_user.id == ALLOWED_USER_ID) if message.from_user else False,
                            "is_edited": False
                        }

                        save_message(message_data)
                        existing_ids.add(message.id)
                        chat_new_messages += 1
                        total_new_messages += 1

                    if chat_new_messages > 0:
                        logger.info(f"✅ {chat_title}: перевірено {chat_checked_messages}, збережено {chat_new_messages}")

                except Exception as scan_exc:
                    logger.error(f"❌ Помилка при скануванні чату {chat.id}: {scan_exc}")

            logger.info(f"✅ Завершено сканування приватних чатів. Чатів: {total_chats_scanned}, нових повідомлень: {total_new_messages}")

    except Exception as e:
        logger.error(f"❌ Помилка при отриманні повідомлень: {e}")

async def test_client(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    try:
        global message_counter
        old_counter = message_counter

        # Надсилаємо тестове повідомлення через Client API
        me = await client_app.get_me()

        if update.message:
            await update.message.reply_text("🧪 Надсилаю тестове повідомлення...")

        # Надсилаємо повідомлення собі
        test_msg = await client_app.send_message("me", f"🧪 Тест #{message_counter + 1} від Client API")

        # Чекаємо трохи
        await asyncio.sleep(2)

        # Перевіряємо чи збільшився лічільник (через обробники)
        new_counter = message_counter

        # Принудово отримуємо повідомлення
        if update.message:
            await update.message.reply_text("🔍 Принудово отримую повідомлення...")
        old_messages_count = len(load_messages()['messages'])

        await fetch_recent_messages()

        new_messages_count = len(load_messages()['messages'])

        if update.message:
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
        current_file = get_current_data_file()
        if update.message:
            await update.message.reply_text(
                f"📁 **Стан файлу:**\n"
            f"📄 Файл: `{current_file}`\n"
            f"📊 Повідомлень у файлі: {len(data['messages'])}\n"
            f"💾 Файл існує: {os.path.exists(current_file)}",
            parse_mode='Markdown'
        )

    except Exception as test_exc:
        if update.message:
            await update.message.reply_text(f"❌ Помилка тесту Client API: {test_exc}")
        import traceback
        logger.error(traceback.format_exc())

async def scan_messages(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    try:
        from datetime import datetime

        today_str = datetime.now().strftime('%Y-%m-%d')

        await update.message.reply_text(
            f"🔍 **Сканую повідомлення за {today_str}...**\n\n"
            f"📱 Збережені повідомлення\n"
            f"💬 Приватні чати (якщо увімкнено)\n\n"
            f"⏳ Це може зайняти деякий час..."
        )

        old_count = len(load_messages()['messages'])
        await fetch_recent_messages()
        new_count = len(load_messages()['messages'])

        await update.message.reply_text(
            f"✅ **Сканування завершено!**\n\n"
            f"📅 Дата: {today_str}\n"
            f"📊 Повідомлень до: {old_count}\n"
            f"📊 Повідомлень після: {new_count}\n"
            f"📈 Додано: {new_count - old_count}",
            parse_mode='Markdown'
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка сканування: {e}")

async def auto_scan_status(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    global message_counter
    last_id = get_last_message_id()
    data = load_messages()

    if update.message:
        await update.message.reply_text(
            "⚡ **Швидке збереження повідомлень:**\n\n"
            "🔥 **Перевірка кожні 0.5 секунди** - майже миттєво!\n"
            "📱 Система постійно сканує 'Збережені повідомлення'\n"
            "💾 Нові повідомлення зберігаються за 0.5 секунди\n\n"
            f"📊 **Статистика:**\n"
            f"🔢 Оброблено оновлень: {message_counter}\n"
            f"🆔 Останній ID: {last_id}\n"
            f"📁 Поточний файл: `{get_current_data_file()}`\n"
            f"💾 Збережено повідомлень: {len(data['messages'])}\n\n"
            "**Команди:**\n"
            "/scan - Ручне сканування (резервний метод)\n"
            "/status - Перевірити збережені повідомлення\n"
            "/test - Тест системи",
            parse_mode='Markdown'
        )

async def settings_command(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    # Підраховуємо повідомлення по типах
    data = load_messages()
    messages = data.get('messages', [])

    stats = {
        'SAVED_MESSAGES': 0,
        'PRIVATE': 0,
        'GROUP': 0,
        'SUPERGROUP': 0,
        'CHANNEL': 0,
        'OTHER': 0
    }

    for msg in messages:
        chat_type = msg.get('chat_type', 'OTHER').upper()
        if 'SAVED' in chat_type:
            stats['SAVED_MESSAGES'] += 1
        elif 'PRIVATE' in chat_type:
            stats['PRIVATE'] += 1
        elif 'SUPERGROUP' in chat_type:
            stats['SUPERGROUP'] += 1
        elif 'GROUP' in chat_type:
            stats['GROUP'] += 1
        elif 'CHANNEL' in chat_type:
            stats['CHANNEL'] += 1
        else:
            stats['OTHER'] += 1

    settings_text = (
        "⚙️ **Налаштування збереження повідомлень:**\n\n"
        f"📱 Збережені повідомлення: {'✅ Увімкнено' if settings['save_saved_messages'] else '❌ Вимкнено'}\n"
        f"💬 Приватні чати: {'✅ Увімкнено' if settings['save_private_chats'] else '❌ Вимкнено'}\n"
        f"👥 Групи: {'✅ Увімкнено' if settings['save_groups'] else '❌ Вимкнено'}\n"
        f"📢 Канали: {'✅ Увімкнено' if settings['save_channels'] else '❌ Вимкнено'}\n\n"
        "⚙️ **Технічні налаштування:**\n"
        f"⏱️ Інтервал перевірки Збережених: {settings['check_interval']} сек\n"
        f"⏱️ Інтервал перевірки діалогів: {settings['dialogs_check_interval']} сек\n"
        f"📊 Кількість діалогів: {settings['dialogs_limit']}\n"
        f"📝 Повідомлень з діалогу: {settings['messages_per_dialog']}\n\n"
        "📊 **Статистика збережених повідомлень:**\n"
        f"📱 Збережені: {stats['SAVED_MESSAGES']}\n"
        f"💬 Приватні: {stats['PRIVATE']}\n"
        f"👥 Групи: {stats['GROUP'] + stats['SUPERGROUP']}\n"
        f"📢 Канали: {stats['CHANNEL']}\n"
        f"❓ Інші: {stats['OTHER']}\n\n"
        "💡 Використовуйте кнопки нижче для зміни налаштувань"
    )

    # Створюємо клавіатуру з кнопками
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = [
        [
            InlineKeyboardButton(
                f"📱 Збережені: {'✅' if settings['save_saved_messages'] else '❌'}",
                callback_data='toggle_saved'
            ),
            InlineKeyboardButton(
                f"💬 Приватні: {'✅' if settings['save_private_chats'] else '❌'}",
                callback_data='toggle_private'
            )
        ],
        [
            InlineKeyboardButton(
                f"👥 Групи: {'✅' if settings['save_groups'] else '❌'}",
                callback_data='toggle_groups'
            ),
            InlineKeyboardButton(
                f"📢 Канали: {'✅' if settings['save_channels'] else '❌'}",
                callback_data='toggle_channels'
            )
        ],
        [
            InlineKeyboardButton("⚙️ Технічні налаштування", callback_data='tech_settings')
        ],
        [
            InlineKeyboardButton("🔄 Оновити", callback_data='refresh_settings')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(settings_text, parse_mode='Markdown', reply_markup=reply_markup)

async def test_storage_connection(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if update.message:
        await update.message.reply_text("🔄 Тестую підключення до Storage Box...")

    storage_box = StorageBoxManager()
    if storage_box.connect():
        files = storage_box.list_files()
        storage_box.close()

        if update.message:
            await update.message.reply_text(
                f"✅ Підключення успішне!\n"
                f"📁 Знайдено файлів: {len(files)}\n"
                f"🌐 Сервер: {STORAGE_BOX_HOST}\n"
            f"👤 Користувач: {STORAGE_BOX_USERNAME}"
        )
    else:
        if update.message:
            await update.message.reply_text(
                f"❌ Помилка підключення!\n"
                f"🌐 Сервер: {STORAGE_BOX_HOST}\n"
                f"👤 Користувач: {STORAGE_BOX_USERNAME}\n"
                f"📂 Шлях: {STORAGE_BOX_PATH}"
            )

async def test_backup(update: Update, _context: ContextType) -> None:
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    # Створюємо тестовий файл
    test_data = {
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "messages": [
            {
                "message_id": 999999,
                "text": "Тестове повідомлення для перевірки бекапу",
                "date": datetime.now().isoformat()
            }
        ]
    }

    test_file = "test_backup.json"
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=4)

    await update.message.reply_text("🔄 Завантажую тестовий файл...")

    storage_box = StorageBoxManager()
    if storage_box.connect():
        success = storage_box.upload_file(test_file, f"test_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        storage_box.close()

        if success:
            await update.message.reply_text("✅ Тестовий бекап успішний!")
            os.remove(test_file)  # Видаляємо локальний тестовий файл
        else:
            await update.message.reply_text("❌ Помилка завантаження тестового файлу")
    else:
        await update.message.reply_text("❌ Не вдалося підключитися до Storage Box")

async def upload_logs_command(update: Update, _context: ContextType) -> None:
    """Команда для ручної відправки логів на сервер"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if update.message:
        await update.message.reply_text("📤 Відправляю логи на Storage Box...")

    await upload_logs_to_storage_box()

    if update.message:
        await update.message.reply_text("✅ Логи відправлено на сервер!")

async def cleanup_logs_command(update: Update, _context: ContextType) -> None:
    """Команда для ручного очищення старих логів"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if update.message:
        await update.message.reply_text("🗑️ Очищаю старі логи...")

    cleanup_old_logs()

    if update.message:
        await update.message.reply_text("✅ Старі логи видалено!")

async def cleanup_old_files_command(update: Update, _context: ContextType) -> None:
    """Команда для ручного очищення старих локальних файлів з повідомленнями"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if update.message:
        await update.message.reply_text("🗑️ Очищаю старі локальні файли з повідомленнями...")

    cleanup_old_local_files()

    if update.message:
        await update.message.reply_text("✅ Старі локальні файли видалено!")


async def optimization_stats_command(update: Update, _context: ContextType) -> None:
    """Команда для перегляду статистики оптимізації"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if not OPTIMIZATION_ENABLED:
        if update.message:
            await update.message.reply_text("⚠️ Система оптимізації не активована")
        return

    try:
        # Отримуємо статистику з глобальних змінних (потрібно буде додати)
        message = "📊 **СТАТИСТИКА САМООПТИМІЗАЦІЇ**\n\n"

        # Завантажуємо конфігурацію оптимізатора
        if os.path.exists("optimizer_config.json"):
            with open("optimizer_config.json", 'r', encoding='utf-8') as f:
                config = json.load(f)

            message += "⚙️ **Поточні параметри:**\n"
            message += f"  • Інтервал перевірки: {config.get('check_interval', 'N/A')}s\n"
            message += f"  • Розмір батчу: {config.get('batch_size', 'N/A')}\n"
            message += f"  • Таймаут: {config.get('timeout', 'N/A')}s\n"
            message += f"  • Оптимізацій: {config.get('optimization_count', 0)}\n"
            message += f"  • Остання: {config.get('last_optimization', 'N/A')}\n\n"

        # Статистика покращень
        if os.path.exists("code_improvements.json"):
            with open("code_improvements.json", 'r', encoding='utf-8') as f:
                improvements = json.load(f)

            message += f"🤖 **AI покращення:**\n"
            message += f"  • Аналізів: {len(improvements)}\n"

            total_improvements = sum(len(r.get('improvements', [])) for r in improvements)
            message += f"  • Покращень: {total_improvements}\n\n"

        # Статистика пропозицій
        if os.path.exists("optimization_suggestions.json"):
            with open("optimization_suggestions.json", 'r', encoding='utf-8') as f:
                suggestions = json.load(f)

            pending = [s for s in suggestions if not s.get('applied', False)]
            applied = [s for s in suggestions if s.get('applied', False)]

            message += f"💡 **Пропозиції:**\n"
            message += f"  • Всього: {len(suggestions)}\n"
            message += f"  • Застосовано: {len(applied)}\n"
            message += f"  • Очікують: {len(pending)}\n"

        if update.message and isinstance(update.message, TelegramMessage):
            await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as stats_exc:
        logger.error(f"Помилка отримання статистики: {stats_exc}")
        if update.message and isinstance(update.message, TelegramMessage):
            await update.message.reply_text(f"❌ Помилка: {stats_exc}")


async def analyze_code_command(update: Update, _context: ContextType) -> None:
    """Команда для AI аналізу коду"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу до цього бота.")
        return

    if not OPTIMIZATION_ENABLED or not AI_ENABLED:
        if update.message:
            await update.message.reply_text("⚠️ AI оптимізація не активована")
        return

    if update.message:
        await update.message.reply_text("🤖 Запускаю AI аналіз коду...\nЦе може зайняти хвилину...")

    try:
        # Створюємо AI покращувач
        ai_improver = AICodeImprover(
            anthropic_client=anthropic_client,
            openai_client=openai_client
        )

        # Аналізуємо головну функцію message_checker_loop
        code = inspect.getsource(message_checker_loop)

        result = await ai_improver.analyze_and_improve(
            code=code,
            context="Функція перевірки нових повідомлень в Telegram боті"
        )

        if result:
            improvements = result.get('improvements', [])
            message = f"✅ **AI АНАЛІЗ ЗАВЕРШЕНО**\n\n"
            message += f"📊 Знайдено покращень: {len(improvements)}\n\n"

            if improvements:
                message += "💡 **Топ-3 пропозиції:**\n"
                for i, imp in enumerate(improvements[:3], 1):
                    priority_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🟠', 'critical': '🔴'}
                    emoji = priority_emoji.get(imp.get('priority', 'low'), '⚪')
                    message += f"{i}. {emoji} {imp.get('description', 'N/A')}\n"

            message += f"\n📝 Оцінка: {result.get('overall_assessment', 'N/A')}"

            if update.message:
                await update.message.reply_text(message, parse_mode='Markdown')
        else:
            if update.message:
                await update.message.reply_text("❌ Не вдалося отримати результат аналізу")

    except Exception as analyze_exc:
        logger.error(f"Помилка AI аналізу: {analyze_exc}")
        if update.message:
            await update.message.reply_text(f"❌ Помилка: {analyze_exc}")

# Обробник текстових повідомлень (клавіатура)
async def handle_keyboard(update: Update, context: ContextType) -> None:
    """Обробляє натискання кнопок клавіатури"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        return

    if not update.message:
        return

    text = update.message.text

    # Головне меню
    if text == "📊 Статус":
        await status(update, context)
    elif text == "⚙️ Налаштування":
        await settings_command(update, context)
    elif text == "💾 Бекап":
        await backup_now(update, context)
    elif text == "📂 Історія":
        await view_history(update, context)
    elif text == "🤖 AI Помічник":
        await update.message.reply_text(
            "🤖 **AI Помічник**\n\n"
            "Виберіть дію:",
            reply_markup=get_ai_keyboard(),
            parse_mode='Markdown'
        )
    elif text == "📝 Логи":
        await update.message.reply_text(
            "📝 **Управління логами**\n\n"
            "Виберіть дію:",
            reply_markup=get_logs_keyboard(),
            parse_mode='Markdown'
        )
    elif text == "🔧 Технічне":
        await update.message.reply_text(
            "🔧 **Технічне меню**\n\n"
            "Виберіть дію:",
            reply_markup=get_technical_keyboard(),
            parse_mode='Markdown'
        )
    elif text == "ℹ️ Допомога":
        await start(update, context)

    # Технічне меню
    elif text == "🔌 Статус Client API":
        await clientstatus(update, context)
    elif text == "🧪 Тест":
        await test_client(update, context)
    elif text == "🔍 Сканувати":
        await scan_messages(update, context)
    elif text == "🗂️ Debug":
        await debug_settings(update, context)
    elif text == "🗑️ Очистити старі файли":
        await cleanup_old_files_command(update, context)

    # Меню логів
    elif text == "📤 Відправити логи":
        await upload_logs_command(update, context)
    elif text == "🗑️ Очистити логи":
        await cleanup_logs_command(update, context)
    elif text == "📋 Останні помилки":
        errors = error_monitor.get_recent_errors(5)
        if errors:
            error_text = "🚨 **Останні помилки:**\n\n"
            for i, err in enumerate(errors, 1):
                time = datetime.fromisoformat(err['timestamp']).strftime('%H:%M:%S')
                error_text += f"{i}. `{time}` - {err['type']}\n   {err['context']}\n\n"
            await update.message.reply_text(error_text, parse_mode='Markdown')
        else:
            await update.message.reply_text("✅ Помилок немає!")

    # AI меню
    elif text == "🔍 Аналіз помилок":
        errors = error_monitor.get_recent_errors(1)
        if errors:
            await update.message.reply_text("🤖 Аналізую останню помилку...")
            error = errors[-1]
            analysis = await ai_assistant.analyze_error(
                error_text=error['traceback'],
                context=error['context']
            )
            if analysis['success']:
                await update.message.reply_text(
                    f"🤖 **AI Аналіз:**\n\n{analysis['analysis']}",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"❌ Помилка AI: {analysis.get('error', 'Невідома помилка')}")
        else:
            await update.message.reply_text("✅ Помилок для аналізу немає!")

    elif text == "📊 Історія аналізів":
        if ai_assistant.error_history:
            history_text = "📊 **Історія AI аналізів:**\n\n"
            for i, item in enumerate(ai_assistant.error_history[-5:], 1):
                time = datetime.fromisoformat(item['timestamp']).strftime('%H:%M:%S')
                history_text += f"{i}. `{time}`\n{item['error'][:100]}...\n\n"
            await update.message.reply_text(history_text, parse_mode='Markdown')
        else:
            await update.message.reply_text("📭 Історія порожня")

    elif text == "⚙️ Налаштування AI":
        ai_status = "✅ Активний" if (openai_client or anthropic_client) else "❌ Не налаштовано"
        provider_name = "OpenAI GPT-4" if AI_PROVIDER == "openai" else "Anthropic Claude"

        await update.message.reply_text(
            f"⚙️ **Налаштування AI:**\n\n"
            f"Статус: {ai_status}\n"
            f"Провайдер: {provider_name}\n"
            f"Історія: {len(ai_assistant.error_history)} аналізів\n\n"
            f"Для зміни API ключів відредагуйте код.",
            parse_mode='Markdown'
        )

    # Кнопка "Назад"
    elif text == "🔙 Назад":
        await update.message.reply_text(
            "🏠 Головне меню",
            reply_markup=get_main_keyboard()
        )

# Додавання обробників до бота
bot_app.add_handler(CommandHandler("start", start, ))
bot_app.add_handler(CommandHandler("status", status, ))
bot_app.add_handler(CommandHandler("settings", settings_command, ))
bot_app.add_handler(CommandHandler("backup", backup_now, ))
bot_app.add_handler(CommandHandler("history", view_history, ))
bot_app.add_handler(CommandHandler("clientstatus", clientstatus, ))
bot_app.add_handler(CommandHandler("myuuid", myuuid, ))
bot_app.add_handler(CommandHandler("debug", debug_settings, ))
bot_app.add_handler(CommandHandler("test", test_client, ))
bot_app.add_handler(CommandHandler("scan", scan_messages, ))
bot_app.add_handler(CommandHandler("autoscan", auto_scan_status, ))
bot_app.add_handler(CommandHandler("teststorage", test_storage_connection, ))
bot_app.add_handler(CommandHandler("testbackup", test_backup, ))
bot_app.add_handler(CommandHandler("uploadlogs", upload_logs_command, ))
bot_app.add_handler(CommandHandler("cleanlogs", cleanup_logs_command, ))
bot_app.add_handler(CommandHandler("cleanfiles", cleanup_old_files_command, ))
bot_app.add_handler(CommandHandler("optstats", optimization_stats_command, ))
bot_app.add_handler(CommandHandler("analyzecode", analyze_code_command, ))
bot_app.add_handler(MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_keyboard, ))
bot_app.add_handler(CallbackQueryHandler(handle_callback_query, ))

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Створюємо Event для зупинки
    stop_event = asyncio.Event()

    # Обробник сигналів для коректного завершення
    def signal_handler():
        logger.info("⏹️ Отримано сигнал зупинки")
        stop_event.set()

    # Реєструємо обробники сигналів
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)  # type: ignore[arg-type]
    except NotImplementedError:
        # Windows не підтримує add_signal_handler
        pass

    # Ініціалізація системи самооптимізації
    optimizer = None
    performance_monitor = None
    ai_improver = None
    cache_manager = None
    optimization_enabled = OPTIMIZATION_ENABLED  # Локальна копія

    if optimization_enabled:
        try:
            logger.info("🤖 Ініціалізація системи самооптимізації...")

            # Створюємо оптимізатор з AI клієнтами
            optimizer = SelfOptimizer(
                openai_client=openai_client if AI_ENABLED else None,
                anthropic_client=anthropic_client if AI_ENABLED else None
            )

            # Створюємо монітор продуктивності
            performance_monitor = PerformanceMonitor(optimizer)

            # Створюємо AI покращувач коду
            ai_improver = AICodeImprover(
                anthropic_client=anthropic_client if AI_ENABLED else None,
                openai_client=openai_client if AI_ENABLED else None
            )

            # Створюємо менеджер кешу
            cache_manager = CacheManager(default_ttl=300)

            logger.info("✅ Система самооптимізації активована!")
            logger.info("   📊 Профілювання продуктивності: ✅")
            logger.info("   ⚙️ Адаптивна оптимізація параметрів: ✅")
            logger.info("   🤖 AI покращення коду: ✅")
            logger.info("   💾 Кешування: ✅")

        except Exception as e:
            logger.error(f"⚠️ Помилка ініціалізації оптимізації: {e}")
            optimization_enabled = False

    # Очищаємо старі локальні файли при старті
    logger.info("🧹 Перевіряю наявність старих локальних файлів...")
    cleanup_old_local_files()

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

    # Виводимо інформацію в консоль
    print("\n" + "="*60)
    print("🤖 БОТ ЗАПУЩЕНО")
    print("="*60)
    print(f"📱 Збережені повідомлення: {'✅' if settings['save_saved_messages'] else '❌'}")
    print(f"💬 Приватні чати: {'✅' if settings['save_private_chats'] else '❌'}")
    print(f"👥 Групи: {'✅' if settings['save_groups'] else '❌'}")
    print(f"📢 Канали: {'✅' if settings['save_channels'] else '❌'}")
    print(f"⏱️  Інтервал перевірки: {settings['check_interval']} сек")
    print("="*60)
    print("💾 Збережені повідомлення:\n")

    # Запускаємо швидкий цикл перевірки повідомлень
    message_checker_task = asyncio.create_task(message_checker_loop())

    # Запускаємо цикл самооптимізації якщо увімкнено
    optimization_task = None
    if optimization_enabled and optimizer:
        async def optimization_loop():
            """Цикл самооптимізації"""
            while True:
                try:
                    await asyncio.sleep(300)  # Кожні 5 хвилин

                    # Запускаємо цикл оптимізації
                    await optimizer.run_optimization_cycle()

                    # Виводимо статистику
                    if performance_monitor:
                        performance_monitor.log_stats()

                    if cache_manager:
                        cache_manager.clear_expired()
                        cache_manager.log_stats()

                    if ai_improver:
                        ai_improver.log_stats()

                except asyncio.CancelledError:
                    break
                except Exception as opt_error:
                    logger.error(f"Помилка в циклі оптимізації: {opt_error}")

        optimization_task = asyncio.create_task(optimization_loop())
        logger.info("🔄 Цикл самооптимізації запущено")

    try:
        # Тримаємо систему запущеною
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n⏹️  Отримано сигнал зупинки...")
        logger.info("⏹️ Отримано сигнал зупинки через виключення")
    finally:
        print("🔄 Зупиняю систему...")
        logger.info("🔄 Зупиняю систему...")

        # Скасовуємо задачу оптимізації
        if optimization_task and not optimization_task.done():
            optimization_task.cancel()
            try:
                await optimization_task
            except asyncio.CancelledError:
                pass

        # Скасовуємо задачу перевірки повідомлень
        if not message_checker_task.done():
            message_checker_task.cancel()
            try:
                await message_checker_task
            except asyncio.CancelledError:
                pass

        # Зупиняємо планувальник
        scheduler.shutdown(wait=False)

        # Зупиняємо Bot API
        try:
            await asyncio.wait_for(bot_app.updater.stop(), timeout=2.0)
            await asyncio.wait_for(bot_app.stop(), timeout=2.0)
            await asyncio.wait_for(bot_app.shutdown(), timeout=2.0)
            print("✅ Bot API зупинено")
            logger.info("✅ Bot API зупинено")
        except asyncio.TimeoutError:
            print("✅ Bot API зупинено (з timeout)")
            logger.info("✅ Bot API зупинено (з timeout)")
        except Exception as e:
            logger.debug(f"Деталі зупинки Bot API: {e}")

        # Зупиняємо Client API та очищаємо його tasks
        try:
            # Спочатку зупиняємо Client API
            try:
                await asyncio.wait_for(client_app.stop(), timeout=3.0)
                print("✅ Client API зупинено")
                logger.info("✅ Client API зупинено")
            except (asyncio.TimeoutError, RuntimeError):
                print("✅ Client API зупинено (з timeout)")
                logger.info("✅ Client API зупинено (з timeout)")

            # Тепер очищаємо всі незавершені tasks Pyrogram
            await asyncio.sleep(0.1)  # Даємо час на завершення
            current_task = asyncio.current_task()
            pending = [
                task for task in asyncio.all_tasks()
                if task != current_task and not task.done()
            ]

            if pending:
                logger.debug(f"🧹 Очищаю {len(pending)} незавершених Pyrogram tasks...")
                for task in pending:
                    task.cancel()
                # Чекаємо завершення з timeout
                await asyncio.wait(pending, timeout=1.0)
                logger.debug("✅ Pyrogram tasks очищено")

        except asyncio.CancelledError:
            print("✅ Client API зупинено (cancelled)")
            logger.info("✅ Client API зупинено (cancelled)")
        except Exception as e:
            logger.debug(f"Деталі зупинки Client API: {e}")

        print("\n" + "="*60)
        print("✅ СИСТЕМА ЗУПИНЕНА")
        print("="*60 + "\n")
        logger.info("✅ Система зупинена")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Програма зупинена користувачем")

    # ПРИМІТКА: При завершенні можуть з'являтися повідомлення:
    # "ERROR: Task was destroyed but it is pending! task: <Task ... Dispatcher.handler_worker()>"
    # Це відома проблема Pyrogram - Dispatcher не очищає свої внутрішні tasks.
    # Ці повідомлення МОЖНА ІГНОРУВАТИ - вони не впливають на роботу бота,
    # всі дані збережені, немає витоку пам'яті. Exit code 0 = успішне завершення.


