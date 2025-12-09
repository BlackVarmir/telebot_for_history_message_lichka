# 🚀 Міграція на Hetzner Object Storage (S3)

## 📋 Огляд

Версія 2.3.0 додає підтримку **Hetzner Object Storage** (S3-compatible) як альтернативу SFTP Storage Box.

### Переваги Object Storage:
- ✅ **Швидше** - оптимізована передача файлів
- ✅ **Надійніше** - автоматичне відновлення з'єднання
- ✅ **Масштабованість** - необмежений простір
- ✅ **Зручніше** - S3 API простіший ніж SFTP
- ✅ **Дешевше** - оплата тільки за використаний простір

---

## 🔧 Крок 1: Встановлення залежностей

```bash
pip install boto3==1.35.36
```

Або оновіть всі залежності:
```bash
pip install -r requirements.txt
```

---

## 📝 Крок 2: Отримання доступу до Object Storage

### Створення Object Storage в Hetzner Cloud Console:

1. Увійдіть в [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Виберіть проєкт
3. Перейдіть в **Object Storage**
4. Натисніть **Create Bucket**
5. Виберіть регіон (рекомендовано: `fsn1` - Falkenstein)
6. Введіть назву bucket (наприклад: `telegram-bot-backup`)
7. Створіть **Access Key** та **Secret Key**

### Ваші данні:
- **Endpoint**: `https://fsn1.your-objectstorage.com` (залежить від регіону)
- **Access Key**: `XXXXXXXXXX`
- **Secret Key**: `YYYYYYYYYY`
- **Bucket Name**: `telegram-bot-backup`
- **Region**: `fsn1` (або `nbg1`, `hel1`)

---

## ⚙️ Крок 3: Налаштування .env файлу

Відкрийте ваш `.env` файл та додайте/замініть:

```env
# ===== STORAGE CONFIGURATION =====
# Виберіть тип сховища
STORAGE_TYPE=s3

# Object Storage (S3) - Hetzner
S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
S3_ACCESS_KEY=your_access_key_here
S3_SECRET_KEY=your_secret_key_here
S3_BUCKET_NAME=telegram-bot-backup
S3_REGION=fsn1
```

### Якщо ви хочете залишити SFTP:

```env
# Залишити SFTP (legacy)
STORAGE_TYPE=sftp

# SFTP Storage Box
STORAGE_BOX_HOST=your_host.your-storagebox.de
STORAGE_BOX_USERNAME=your_username
STORAGE_BOX_PASSWORD=your_password
STORAGE_BOX_PATH=/backup/telegram_bot/
```

---

## 🔄 Крок 4: Міграція даних (опціонально)

Якщо у вас є старі файли на SFTP, ви можете мігрувати їх на S3:

### Варіант 1: Ручна міграція через s3cmd

1. Встановіть `s3cmd`:
```bash
pip install s3cmd
```

2. Налаштуйте s3cmd:
```bash
s3cmd --configure
```

3. Завантажте файли з SFTP на локальний комп'ютер

4. Завантажте на S3:
```bash
s3cmd put local_file.json s3://telegram-bot-backup/saved_messages_2025-10-20.json --host=fsn1.your-objectstorage.com --host-bucket="%(bucket)s.fsn1.your-objectstorage.com"
```

### Варіант 2: Автоматична міграція через бота (COMING SOON)

Буде додано команду `/migrate` для автоматичної міграції.

---

## 🚀 Крок 5: Запуск бота

Перезапустіть бота:

```bash
python hybrid_main.py
```

При старті ви побачите:
```
🔧 Використовується Object Storage (S3)
✅ Object Storage ініціалізовано успішно
✅ Bucket 'telegram-bot-backup' існує
📁 MediaManager ініціалізовано
```

---

## ✅ Крок 6: Перевірка роботи

### Перевірте підключення:

```
/teststorage
```

Ви побачите:
```
✅ Підключення до Object Storage успішне!
📦 Bucket: telegram-bot-backup
🌍 Region: fsn1
```

### Зробіть тестовий бекап:

```
/testbackup
```

---

## 📊 Порівняння SFTP vs S3

| Параметр | SFTP | S3 Object Storage |
|----------|------|-------------------|
| Швидкість | Повільніше | **Швидше** |
| Надійність | Залежить від з'єднання | **Автовідновлення** |
| Масштабованість | Обмежена | **Необмежена** |
| API | SSH/SFTP протокол | **S3 REST API** |
| Ціна | Фіксована | **Pay-as-you-go** |
| Multipart Upload | Немає | **Так** |

---

## 🆘 Вирішення проблем

### Помилка: "boto3 не встановлено"

```bash
pip install boto3
```

### Помилка: "Bucket не існує"

Бот автоматично створить bucket при першому запуску.

### Помилка: "Invalid Access Key"

Перевірте правильність `S3_ACCESS_KEY` та `S3_SECRET_KEY` в `.env` файлі.

### Помилка: "Could not connect to the endpoint URL"

Перевірте `S3_ENDPOINT_URL` - він має бути у форматі:
```
https://fsn1.your-objectstorage.com
```

---

## 📝 Структура файлів на S3

```
telegram-bot-backup/
├── saved_messages_2025-10-20.json
├── saved_messages_2025-10-21.json
├── logs/
│   ├── bot_2025-10-20.log
│   └── bot_2025-10-21.log
└── media/
    ├── photos/
    │   ├── photo_12345_xxx.jpg
    │   └── photo_12346_yyy.jpg
    ├── videos/
    │   └── video_12347_zzz.mp4
    ├── documents/
    ├── audio/
    ├── voice/
    ├── stickers/
    └── animations/
```

---

## 📚 Додаткові ресурси

- [Hetzner Object Storage Docs](https://docs.hetzner.com/storage/object-storage/)
- [AWS S3 API Documentation](https://docs.aws.amazon.com/s3/)
- [boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

---

## 🎉 Готово!

Тепер ваш бот використовує сучасне Object Storage!

**Версія:** 2.3.0
**Дата:** 2025-10-21
