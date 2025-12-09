# 🔧 Швидке виправлення та налаштування

## ✅ Що виправлено

### 1. Попередження від бібліотек
- ✅ Додано фільтр для попереджень paramiko (TripleDES)
- ✅ Додано httpx==0.27.2 для сумісності з openai
- ✅ Додано python-dotenv для роботи з .env

### 2. Ініціалізація менеджерів
- ✅ Додано глобальні змінні `storage_manager` та `media_manager`
- ✅ Створено функцію `initialize_managers()`
- ✅ Додано виклик в `main()`
- ✅ Оновлено `upload_to_storage_box()` для використання StorageManager
- ✅ Оновлено `upload_logs_to_storage_box()` для використання StorageManager

### 3. Діагностика
- ✅ Додано виведення STORAGE_TYPE при ініціалізації
- ✅ Додано детальне логування типу сховища

---

## 🚀 Як запустити

### Крок 1: Оновіть залежності

```bash
pip install --upgrade httpx==0.27.2 python-dotenv==1.0.1
```

### Крок 2: Перевірте/створіть .env файл

У кореневій папці проєкту створіть файл `.env` (якщо його немає):

```env
# Telegram API
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token

# === ВАЖЛИВО: Виберіть тип сховища ===
# Варіант 1: SFTP (default, працює зараз)
STORAGE_TYPE=sftp
STORAGE_BOX_HOST=your_host.your-storagebox.de
STORAGE_BOX_USERNAME=your_username
STORAGE_BOX_PASSWORD=your_password
STORAGE_BOX_PATH=/backup/telegram_bot/

# Варіант 2: S3 Object Storage (швидше, рекомендовано)
# STORAGE_TYPE=s3
# S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
# S3_ACCESS_KEY=your_access_key
# S3_SECRET_KEY=your_secret_key
# S3_BUCKET_NAME=telegram-bot-backup
# S3_REGION=fsn1

# AI (опціонально)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
AI_PROVIDER=openai
```

### Крок 3: Запустіть бота

```bash
python hybrid_main.py
```

---

## 📊 Що ви побачите при запуску

### Якщо використовується SFTP:

```
🔧 Ініціалізація менеджерів сховища та медіа...
📋 STORAGE_TYPE з .env: sftp
🔧 Використовується SFTP Storage Box
✅ StorageManager ініціалізовано (тип: sftp)
✅ SFTP підключення встановлено
✅ MediaManager ініціалізовано
🎉 Всі менеджери успішно ініціалізовано!
```

### Якщо використовується S3:

```
🔧 Ініціалізація менеджерів сховища та медіа...
📋 STORAGE_TYPE з .env: s3
🔧 Використовується Object Storage (S3)
✅ Object Storage ініціалізовано успішно
✅ Bucket 'telegram-bot-backup' існує
✅ StorageManager ініціалізовано (тип: s3)
✅ S3 Object Storage готовий до використання
✅ MediaManager ініціалізовано
🎉 Всі менеджери успішно ініціалізовано!
```

---

## 🔄 Як перемкнутися на S3

### 1. Отримайте доступ до Hetzner Object Storage

1. Увійдіть в [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Створіть Object Storage bucket
3. Отримайте Access Key та Secret Key

### 2. Оновіть .env файл

```env
STORAGE_TYPE=s3
S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
S3_ACCESS_KEY=ваш_access_key
S3_SECRET_KEY=ваш_secret_key
S3_BUCKET_NAME=telegram-bot-backup
S3_REGION=fsn1
```

### 3. Встановіть boto3

```bash
pip install boto3==1.35.36
```

### 4. Перезапустіть бота

```bash
python hybrid_main.py
```

---

## ⚠️ Важливі примітки

### SFTP (Storage Box)
- ✅ Працює зараз
- ✅ Не потребує змін
- ❌ Повільніше ніж S3
- ❌ Обмежений простір

### S3 (Object Storage)
- ✅ Швидше
- ✅ Необмежений простір
- ✅ Автоматичне створення buckets
- ⚠️ Потребує налаштування
- ⚠️ Потребує boto3

---

## 🐛 Вирішення проблем

### Помилка: "ModuleNotFoundError: No module named 'boto3'"

```bash
pip install boto3
```

### Помилка: "boto3 не встановлено"

Встановіть boto3 та перезапустіть:

```bash
pip install boto3==1.35.36
python hybrid_main.py
```

### Помилка: "Could not connect to the endpoint URL"

Перевірте `S3_ENDPOINT_URL` в .env файлі.

### Помилка: "Invalid Access Key"

Перевірте `S3_ACCESS_KEY` та `S3_SECRET_KEY` в .env файлі.

### Попередження про TripleDES зникли?

Так! Додано фільтр:
```python
warnings.filterwarnings("ignore", category=DeprecationWarning, module="paramiko")
```

---

## ✅ Checklist

- [ ] Оновлено httpx та python-dotenv
- [ ] Створено/перевірено .env файл
- [ ] Встановлено STORAGE_TYPE (sftp або s3)
- [ ] Якщо S3 - встановлено boto3
- [ ] Якщо S3 - заповнено S3_* налаштування
- [ ] Запущено бота
- [ ] Перевірено логи при старті
- [ ] Протестовано збереження повідомлень

---

## 📝 Що далі?

### Поточна версія працює на SFTP
Якщо ви хочете залишити SFTP - нічого робити не потрібно, все працює!

### Щоб перейти на S3
1. Налаштуйте Hetzner Object Storage
2. Оновіть .env (STORAGE_TYPE=s3)
3. Встановіть boto3
4. Перезапустіть бота

### Збереження медіа
Медіа автоматично зберігатиметься в папку `media/` та завантажуватиметься на сервер (SFTP або S3).

---

**Версія:** 2.3.0
**Дата:** 2025-10-21
**Статус:** ✅ Готово до використання
