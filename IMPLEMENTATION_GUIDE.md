# 🛠️ Гайд по впровадженню змін версії 2.3.0

## 📋 Огляд

Цей документ містить покрокову інструкцію по впровадженню всіх нових функцій версії 2.3.0 в існуючий код `hybrid_main.py`.

---

## ✅ Що вже зроблено

1. ✅ Додано класи `ObjectStorageManager`, `StorageManager`, `MediaManager` в `hybrid_main.py`
2. ✅ Додано команду `/commands`
3. ✅ Оновлено `requirements.txt` (додано boto3)
4. ✅ Оновлено `.env.example` (додано S3 конфігурацію)
5. ✅ Оновлено `.gitignore` (додано media/)
6. ✅ Створено документацію (MIGRATION_S3.md, MEDIA_INTEGRATION.md, WHATS_NEW_2.3.0.md)
7. ✅ Оновлено README.md та CHANGELOG.md

---

## ⚠️ Що потрібно зробити вручну

### 1. Ініціалізація глобальних менеджерів

Знайдіть в коді (біля рядка 70-80) де визначені глобальні змінні:

```python
# Конфігурація Storage Box
STORAGE_BOX_HOST = os.getenv("STORAGE_BOX_HOST")
STORAGE_BOX_USERNAME = os.getenv("STORAGE_BOX_USERNAME")
STORAGE_BOX_PASSWORD = os.getenv("STORAGE_BOX_PASSWORD")
STORAGE_BOX_PATH = os.getenv("STORAGE_BOX_PATH")
```

**Після цього блоку** додайте:

```python
# Глобальні менеджери (ініціалізуються при старті)
storage_manager = None
media_manager = None

def initialize_managers():
    """Ініціалізує менеджери сховища та медіа"""
    global storage_manager, media_manager

    try:
        # Створюємо Storage Manager (підтримує SFTP та S3)
        storage_manager = StorageManager()

        # Перевіряємо підключення
        if not storage_manager.connect():
            logger.error("❌ Не вдалося підключитися до сховища")
            return False

        # Створюємо Media Manager
        media_manager = MediaManager(storage_manager)

        logger.info("✅ Менеджери ініціалізовано успішно")
        return True
    except Exception as e:
        logger.error(f"❌ Помилка ініціалізації менеджерів: {e}")
        return False
```

---

### 2. Оновлення функції upload_to_storage_box()

Знайдіть функцію `upload_to_storage_box()` (біля рядка 629) та замініть її на:

```python
async def upload_to_storage_box():
    """Відправляє файли на сховище"""
    # Отримуємо файл поточного дня
    data_file = get_current_data_file()

    if not os.path.exists(data_file):
        logger.info("Немає файлу для відправки сьогодні")
        return

    # Створюємо унікальну назву файлу з датою
    file_date = datetime.now().strftime("%Y-%m-%d")
    remote_filename = f"saved_messages_{file_date}.json"

    # Використовуємо новий StorageManager
    if storage_manager:
        if storage_manager.connect():
            success = storage_manager.upload_file(data_file, remote_filename)
            storage_manager.close()

            if success:
                logger.info(f"✅ Файл {data_file} успішно відправлено на сервер")
                logger.info(f"📁 Локальний файл збережено до автоматичного очищення о 01:00")
            else:
                logger.error("Не вдалося завантажити файл на сховище - локальний файл збережено")
        else:
            logger.error("Не вдалося підключитися до сховища - локальний файл збережено")
    else:
        logger.error("StorageManager не ініціалізовано")
```

---

### 3. Оновлення функції upload_logs_to_storage_box()

Знайдіть функцію `upload_logs_to_storage_box()` (біля рядка 656) та замініть:

```python
# Було:
storage_box = StorageBoxManager()
if not storage_box.connect():
    logger.error("Не вдалося підключитися до Storage Box для відправки логів")
    return

# Стане:
if not storage_manager:
    logger.error("StorageManager не ініціалізовано")
    return

if not storage_manager.connect():
    logger.error("Не вдалося підключитися до сховища для відправки логів")
    return
```

І далі замініть всі `storage_box` на `storage_manager`.

---

### 4. Додавання функції has_media()

Додайте цю функцію **після** `get_last_message_id()` (біля рядка 792):

```python
def has_media(message: Message) -> bool:
    """Перевіряє чи містить повідомлення медіа"""
    return bool(
        message.photo or
        message.video or
        message.document or
        message.audio or
        message.voice or
        message.sticker or
        message.animation
    )
```

---

### 5. Оновлення quick_message_check()

Знайдіть функцію `quick_message_check()` (біля рядка 794) та внесіть зміни:

**Було:**
```python
# Пропускаємо повідомлення без тексту
if not message.text:
    continue
```

**Стане:**
```python
# Пропускаємо повідомлення без тексту ТА медіа
if not message.text and not has_media(message):
    continue
```

**І додайте перед `save_message(message_data)`:**

```python
# Зберігаємо медіа якщо є
if media_manager and has_media(message):
    message_data = await media_manager.save_media(message, message_data)
```

**Також оновіть text:**
```python
"text": message.text or "[медіа]",
```

---

### 6. Оновлення check_private_chats()

Знайдіть функцію `check_private_chats()` (біля рядка 859) та внесіть ті ж зміни:

```python
# Пропускаємо повідомлення без тексту ТА медіа
if not message.text and not has_media(message):
    continue
```

І перед `save_message(message_data)`:

```python
# Зберігаємо медіа якщо є
if media_manager and has_media(message):
    message_data = await media_manager.save_media(message, message_data)
```

---

### 7. Додавання команди /mediastats

Додайте цю функцію після інших команд (наприклад після `analyze_code_command`):

```python
async def media_stats_command(update: Update, _context: ContextType) -> None:
    """Показує статистику збережених медіа"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу.")
        return

    try:
        media_dir = "media"
        if not os.path.exists(media_dir):
            if update.message:
                await update.message.reply_text("📁 Папка з медіа ще не створена")
            return

        stats = {}
        emoji_map = {
            'photos': '📷',
            'videos': '🎥',
            'documents': '📄',
            'audio': '🎵',
            'voice': '🎤',
            'stickers': '🎨',
            'animations': '🎬'
        }

        for media_type in ['photos', 'videos', 'documents', 'audio', 'voice', 'stickers', 'animations']:
            path = os.path.join(media_dir, media_type)
            if os.path.exists(path):
                files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
                total_size = sum(os.path.getsize(os.path.join(path, f)) for f in files)
                stats[media_type] = {
                    'count': len(files),
                    'size': total_size / (1024 * 1024)  # MB
                }
            else:
                stats[media_type] = {'count': 0, 'size': 0}

        message = "📊 **Статистика медіа:**\n\n"

        total_count = 0
        total_size = 0

        for media_type, data in stats.items():
            if data['count'] > 0:
                emoji = emoji_map.get(media_type, '📁')
                message += f"{emoji} **{media_type.title()}:** {data['count']} файлів ({data['size']:.2f} MB)\n"
                total_count += data['count']
                total_size += data['size']

        if total_count == 0:
            message = "📊 **Статистика медіа:**\n\nПоки що немає збережених медіа файлів."
        else:
            message += f"\n📦 **Всього:** {total_count} файлів ({total_size:.2f} MB)"

        if update.message:
            await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Помилка статистики медіа: {e}")
        if update.message:
            await update.message.reply_text(f"❌ Помилка: {e}")
```

**Додайте handler:**

```python
bot_app.add_handler(CommandHandler("mediastats", media_stats_command, ))
```

---

### 8. Ініціалізація при старті

Знайдіть функцію `main()` (в кінці файлу) та **на самому початку** функції додайте:

```python
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Ініціалізуємо менеджери сховища та медіа
    logger.info("🔧 Ініціалізація менеджерів...")
    if not initialize_managers():
        logger.error("❌ Не вдалося ініціалізувати менеджери. Вихід.")
        return

    # ... решта коду
```

---

### 9. Оновлення налаштувань settings

Знайдіть змінну `settings` (біля рядка 154) та додайте нові опції:

```python
settings = {
    'save_saved_messages': True,
    'save_private_chats': True,
    'save_groups': False,
    'save_channels': False,
    'check_interval': 0.5,
    'dialogs_check_interval': 5,
    'dialogs_limit': 20,
    'messages_per_dialog': 5,

    # Нові опції для медіа (v2.3.0)
    'save_media': True,  # Зберігати медіа
    'save_photos': True,
    'save_videos': True,
    'save_documents': True,
    'save_audio': True,
    'save_voice': True,
    'save_stickers': True,
    'save_animations': True,
}
```

---

## 🧪 Тестування

### 1. Перевірте синтаксис:

```bash
python -m py_compile hybrid_main.py
```

### 2. Встановіть залежності:

```bash
pip install -r requirements.txt
```

### 3. Налаштуйте .env:

Скопіюйте `.env.example` в `.env` та заповніть:

```env
STORAGE_TYPE=s3
S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
S3_ACCESS_KEY=your_key
S3_SECRET_KEY=your_secret
S3_BUCKET_NAME=telegram-bot-backup
S3_REGION=fsn1
```

### 4. Запустіть бота:

```bash
python hybrid_main.py
```

### 5. Перевірте команди:

```
/start
/commands
/mediastats
/teststorage
```

---

## 🐛 Вирішення проблем

### Помилка: "boto3 не встановлено"

```bash
pip install boto3
```

### Помилка: "StorageManager не ініціалізовано"

Перевірте що `initialize_managers()` викликається в `main()`.

### Помилка: "Bucket не існує"

Бот автоматично створить bucket при першому запуску.

### Медіа не зберігаються

Перевірте:
1. `settings['save_media']` = True
2. `media_manager` не None
3. Логи на наявність помилок завантаження

---

## 📝 Додаткові налаштування

### Якщо хочете залишити SFTP:

```env
STORAGE_TYPE=sftp
```

Всі старі налаштування працюватимуть.

### Якщо хочете відключити медіа:

```python
settings['save_media'] = False
```

---

## ✅ Checklist впровадження

- [ ] Додано функцію `initialize_managers()`
- [ ] Додано глобальні змінні `storage_manager`, `media_manager`
- [ ] Оновлено `upload_to_storage_box()`
- [ ] Оновлено `upload_logs_to_storage_box()`
- [ ] Додано функцію `has_media()`
- [ ] Оновлено `quick_message_check()`
- [ ] Оновлено `check_private_chats()`
- [ ] Додано команду `/mediastats`
- [ ] Додано виклик `initialize_managers()` в `main()`
- [ ] Оновлено `settings` з опціями медіа
- [ ] Встановлено `boto3`
- [ ] Налаштовано `.env`
- [ ] Протестовано бота

---

## 🎉 Готово!

Після виконання всіх кроків ваш бот буде підтримувати:
- ✅ Збереження медіа файлів
- ✅ Object Storage (S3)
- ✅ Команду /commands
- ✅ Команду /mediastats

**Версія:** 2.3.0
**Дата:** 2025-10-21
