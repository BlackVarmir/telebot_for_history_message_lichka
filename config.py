"""
Конфігураційний файл для Telegram бота
Читає налаштування зі змінних середовища або використовує значення за замовчуванням
"""
import os

# Конфігурація Telegram Client API
API_ID = os.getenv("API_ID", "23266897")
API_HASH = os.getenv("API_HASH", "26ee63262a2274088768653a14fa6b35")
SESSION_NAME = os.getenv("SESSION_NAME", "telegram_client")

# Конфігурація Bot API
BOT_TOKEN = os.getenv("BOT_TOKEN", "8160502358:AAG4c9N5PGLqmnEPE-HsdE3ctRhosW0dtg4")

# Конфігурація Storage Box
STORAGE_BOX_HOST = os.getenv("STORAGE_BOX_HOST", "u475460.your-storagebox.de")
STORAGE_BOX_USERNAME = os.getenv("STORAGE_BOX_USERNAME", "u475460")
STORAGE_BOX_PASSWORD = os.getenv("STORAGE_BOX_PASSWORD", "Mair558807.")
STORAGE_BOX_PATH = os.getenv("STORAGE_BOX_PATH", "/backup/telegram_bot/pomichnik_for_meassage_saved_bot/")

# Конфігурація AI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "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")
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")

# Шляхи до файлів (для Docker)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
LOGS_DIR = os.getenv("LOGS_DIR", "/app/logs")
TEMP_DIR = os.getenv("TEMP_DIR", "/app/temp")

# Створюємо директорії якщо їх немає
for directory in [DATA_DIR, LOGS_DIR, TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

