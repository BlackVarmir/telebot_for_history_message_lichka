# 📁 Інтеграція збереження медіа файлів

## 📋 Огляд

Версія 2.3.0 додає можливість збереження медіа файлів з Telegram повідомлень.

### Підтримувані типи медіа:
- 📷 **Фото** - JPG/PNG у найвищій якості
- 🎥 **Відео** - MP4 файли
- 📄 **Документи** - PDF, DOCX, ZIP та інші
- 🎵 **Аудіо** - MP3 файли з метаданими
- 🎤 **Голосові** - OGG файли
- 🎨 **Стікери** - WEBP файли
- 🎬 **Анімації** - GIF як MP4

---

## 🔧 Ініціалізація

### 1. Створіть глобальні змінні

Додайте після ініціалізації StorageBoxManager:

```python
# Глобальні менеджери
storage_manager = None
media_manager = None

def initialize_managers():
    """Ініціалізує менеджери сховища та медіа"""
    global storage_manager, media_manager

    try:
        # Створюємо Storage Manager (підтримує SFTP та S3)
        storage_manager = StorageManager()

        # Створюємо Media Manager
        media_manager = MediaManager(storage_manager)

        logger.info("✅ Менеджери ініціалізовано успішно")
        return True
    except Exception as e:
        logger.error(f"❌ Помилка ініціалізації менеджерів: {e}")
        return False
```

### 2. Викличте ініціалізацію при старті

Додайте в функцію `main()`:

```python
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Ініціалізуємо менеджери
    if not initialize_managers():
        logger.error("Не вдалося ініціалізувати менеджери. Вихід.")
        return

    # ... решта коду
```

---

## 💾 Використання в функції збереження повідомлень

### Оновіть функцію `quick_message_check()`:

```python
async def quick_message_check():
    """Швидка перевірка нових повідомлень кожні 0.5 секунди"""
    try:
        last_saved_id = get_last_message_id()
        new_messages_count = 0
        latest_message_id = last_saved_id

        data = load_messages()
        existing_ids = set(msg['message_id'] for msg in data['messages'])

        if settings['save_saved_messages']:
            async for message in client_app.get_chat_history("me"):
                # Пропускаємо повідомлення без тексту ТА медіа
                if not message.text and not has_media(message):
                    continue

                if message.id <= last_saved_id:
                    break

                if message.id not in existing_ids:
                    logger.info(f"⚡ ШВИДКЕ ЗБЕРЕЖЕННЯ (Saved): {message.id}")

                    message_data = {
                        "message_id": message.id,
                        "chat_id": message.chat.id,
                        "chat_type": "SAVED_MESSAGES",
                        "chat_title": "Збережені повідомлення",
                        "chat_username": None,
                        "from_user_id": message.from_user.id if message.from_user else ALLOWED_USER_ID,
                        "from_username": message.from_user.username if message.from_user else None,
                        "from_first_name": message.from_user.first_name if message.from_user else "Me",
                        "text": message.text or "[медіа]",
                        "date": message.date.isoformat(),
                        "is_outgoing": (message.from_user.id == ALLOWED_USER_ID) if message.from_user else True,
                        "is_edited": False
                    }

                    # ✨ ЗБЕРЕЖЕННЯ МЕДІА
                    if media_manager and has_media(message):
                        message_data = await media_manager.save_media(message, message_data)

                    save_message(message_data)
                    new_messages_count += 1
                    existing_ids.add(message.id)

                    if message.id > latest_message_id:
                        latest_message_id = message.id

        if latest_message_id > last_saved_id:
            save_last_message_id(latest_message_id)

        if new_messages_count > 0:
            logger.info(f"⚡ Швидко збережено {new_messages_count} повідомлень!")

    except Exception as e:
        logger.error(f"❌ Помилка швидкої перевірки: {e}")
```

### Додайте функцію перевірки медіа:

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

## 📊 Структура збереження

### JSON з медіа:

```json
{
  "message_id": 12345,
  "text": "Дивись яке фото!",
  "date": "2025-10-21T15:30:00",
  "media": {
    "type": "photo",
    "file_id": "AgACAgIAAxkBAAIBY2...",
    "file_unique_id": "AQADAgADq7...",
    "file_size": 156789,
    "width": 1280,
    "height": 720,
    "local_path": "media/photos/photo_12345_xxx.jpg",
    "remote_key": "media/photos/photo_12345_xxx.jpg"
  }
}
```

### Локальна структура папок:

```
media/
├── photos/
│   ├── photo_12345_xxx.jpg
│   └── photo_12346_yyy.jpg
├── videos/
│   └── video_12347_zzz.mp4
├── documents/
│   └── doc_12348_contract.pdf
├── audio/
│   └── audio_12349_song.mp3
├── voice/
│   └── voice_12350_voice.ogg
├── stickers/
│   └── sticker_12351_funny.webp
└── animations/
    └── animation_12352_cat.mp4
```

---

## 🔄 Оновлення функції `upload_to_storage_box()`

Оновіть функцію для використання нового StorageManager:

```python
async def upload_to_storage_box():
    """Відправляє файли на сховище"""
    data_file = get_current_data_file()

    if not os.path.exists(data_file):
        logger.info("Немає файлу для відправки сьогодні")
        return

    file_date = datetime.now().strftime("%Y-%m-%d")
    remote_filename = f"saved_messages_{file_date}.json"

    # Використовуємо новий StorageManager
    if storage_manager:
        if storage_manager.connect():
            success = storage_manager.upload_file(data_file, remote_filename)
            storage_manager.close()

            if success:
                logger.info(f"✅ Файл {data_file} успішно відправлено на сервер")
            else:
                logger.error("Не вдалося завантажити файл на сховище")
        else:
            logger.error("Не вдалося підключитися до сховища")
```

---

## ⚙️ Налаштування збереження медіа

### Додайте опції в settings:

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

    # Нові опції для медіа
    'save_media': True,  # Зберігати медіа
    'save_photos': True,  # Зберігати фото
    'save_videos': True,  # Зберігати відео
    'save_documents': True,  # Зберігати документи
    'save_audio': True,  # Зберігати аудіо
    'save_voice': True,  # Зберігати голосові
    'save_stickers': True,  # Зберігати стікери
    'save_animations': True,  # Зберігати GIF
}
```

### Оновіть MediaManager для перевірки налаштувань:

```python
async def save_media(self, message: Message, message_data: dict) -> dict:
    """Зберігає медіа з повідомлення"""
    try:
        # Перевіряємо чи увімкнено збереження медіа
        if not settings.get('save_media', True):
            return message_data

        media_info = {}

        # Визначаємо тип медіа з перевіркою налаштувань
        if message.photo and settings.get('save_photos', True):
            media_info = await self._save_photo(message)
        elif message.video and settings.get('save_videos', True):
            media_info = await self._save_video(message)
        elif message.document and settings.get('save_documents', True):
            media_info = await self._save_document(message)
        elif message.audio and settings.get('save_audio', True):
            media_info = await self._save_audio(message)
        elif message.voice and settings.get('save_voice', True):
            media_info = await self._save_voice(message)
        elif message.sticker and settings.get('save_stickers', True):
            media_info = await self._save_sticker(message)
        elif message.animation and settings.get('save_animations', True):
            media_info = await self._save_animation(message)

        if media_info:
            message_data['media'] = media_info
            logger.info(f"💾 Медіа збережено: {media_info['type']}")

        return message_data

    except Exception as e:
        logger.error(f"❌ Помилка збереження медіа: {e}")
        return message_data
```

---

## 🎯 Додаткові команди

### Додайте команду для перегляду статистики медіа:

```python
async def media_stats(update: Update, _context: ContextType) -> None:
    """Показує статистику збережених медіа"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        if update.message:
            await update.message.reply_text("Вибачте, у вас немає доступу.")
        return

    try:
        media_dir = "media"
        stats = {}

        for media_type in ['photos', 'videos', 'documents', 'audio', 'voice', 'stickers', 'animations']:
            path = os.path.join(media_dir, media_type)
            if os.path.exists(path):
                files = os.listdir(path)
                total_size = sum(os.path.getsize(os.path.join(path, f)) for f in files)
                stats[media_type] = {
                    'count': len(files),
                    'size': total_size / (1024 * 1024)  # MB
                }

        message = "📊 **Статистика медіа:**\n\n"

        emoji_map = {
            'photos': '📷',
            'videos': '🎥',
            'documents': '📄',
            'audio': '🎵',
            'voice': '🎤',
            'stickers': '🎨',
            'animations': '🎬'
        }

        total_count = 0
        total_size = 0

        for media_type, data in stats.items():
            emoji = emoji_map.get(media_type, '📁')
            message += f"{emoji} **{media_type.title()}:** {data['count']} файлів ({data['size']:.2f} MB)\n"
            total_count += data['count']
            total_size += data['size']

        message += f"\n📦 **Всього:** {total_count} файлів ({total_size:.2f} MB)"

        if update.message:
            await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Помилка статистики медіа: {e}")
        if update.message:
            await update.message.reply_text(f"❌ Помилка: {e}")

# Додайте handler
bot_app.add_handler(CommandHandler("mediastats", media_stats, ))
```

---

## ✅ Готово!

Тепер ваш бот зберігає всі медіа файли автоматично!

**Версія:** 2.3.0
**Дата:** 2025-10-21
