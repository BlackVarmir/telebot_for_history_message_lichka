# Виправлення помилок завершення програми

## Проблема

При завершенні програми виникали наступні помилки:

```
asyncio.exceptions.CancelledError
RuntimeError: Task <Task cancelling name='Task-3'> got Future <Task pending name='Task-11' 
coro=<Dispatcher.handler_worker()>> attached to a different loop
```

## Причини

1. **Конфлікт Event Loops**: `BackgroundScheduler` використовував `asyncio.run()` всередині своїх функцій, що створювало новий event loop, який конфліктував з основним loop.

2. **Неправильне завершення Pyrogram Dispatcher**: При зупинці `client_app.stop()` намагався зупинити dispatcher з tasks, прикріпленими до різних event loops.

3. **Відсутність обробки CancelledError**: При завершенні програми не було правильної обробки скасування асинхронних задач.

## Виправлення

### 1. Виправлення BackgroundScheduler (рядки 188-214)

**Було:**
```python
def upload_to_storage_box_sync():
    asyncio.run(upload_to_storage_box())
```

**Стало:**
```python
main_loop = None  # Глобальна змінна для event loop

def upload_to_storage_box_sync():
    if main_loop and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(upload_to_storage_box(), main_loop)
    else:
        logger.warning("Event loop не доступний для завантаження")
```

**Пояснення**: Замість створення нового event loop через `asyncio.run()`, використовуємо `asyncio.run_coroutine_threadsafe()` для виконання корутини в існуючому основному loop.

### 2. Додано імпорт signal (рядок 7)

```python
import signal
```

**Пояснення**: Потрібен для обробки сигналів завершення (SIGTERM, SIGINT).

### 3. Покращена функція main() (рядки 905-1009)

#### 3.1. Збереження посилання на event loop

```python
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
```

**Пояснення**: Зберігаємо посилання на поточний event loop для використання в BackgroundScheduler.

#### 3.2. Додано обробник сигналів

```python
stop_event = asyncio.Event()

def signal_handler():
    logger.info("⏹️ Отримано сигнал зупинки")
    stop_event.set()

try:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
except NotImplementedError:
    # Windows не підтримує add_signal_handler
    pass
```

**Пояснення**: Замість використання `asyncio.Event().wait()`, створюємо власний Event і встановлюємо обробники сигналів для коректного завершення.

#### 3.3. Покращена обробка виключень

```python
try:
    await stop_event.wait()
except (KeyboardInterrupt, asyncio.CancelledError):
    logger.info("⏹️ Отримано сигнал зупинки через виключення")
```

**Пояснення**: Додано обробку `asyncio.CancelledError` разом з `KeyboardInterrupt`.

#### 3.4. Правильне скасування задач

```python
# Скасовуємо задачу перевірки повідомлень
if not message_checker_task.done():
    message_checker_task.cancel()
    try:
        await message_checker_task
    except asyncio.CancelledError:
        pass
```

**Пояснення**: Спочатку скасовуємо задачу, потім чекаємо на її завершення, ігноруючи `CancelledError`.

#### 3.5. Зупинка планувальника

```python
scheduler.shutdown(wait=False)
```

**Пояснення**: Зупиняємо планувальник без очікування завершення поточних задач.

#### 3.6. М'яке завершення Client API

```python
# Зупиняємо Client API
try:
    # Спочатку зупиняємо dispatcher, щоб уникнути конфліктів з tasks
    if hasattr(client_app, 'dispatcher') and client_app.dispatcher:
        try:
            # Скасовуємо всі handler tasks
            if hasattr(client_app.dispatcher, 'handler_worker_tasks'):
                for task in client_app.dispatcher.handler_worker_tasks:
                    if not task.done():
                        task.cancel()
                # Чекаємо на завершення tasks з timeout
                await asyncio.wait_for(
                    asyncio.gather(*client_app.dispatcher.handler_worker_tasks, return_exceptions=True),
                    timeout=2.0
                )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Timeout або помилка при зупинці dispatcher tasks: {e}")
    
    # Тепер зупиняємо client
    await asyncio.wait_for(client_app.stop(), timeout=5.0)
except asyncio.TimeoutError:
    logger.error("Timeout при зупинці Client API - примусове завершення")
except Exception as e:
    logger.error(f"Помилка при зупинці Client API: {e}")
```

**Пояснення**: 
- Спочатку скасовуємо всі handler tasks в dispatcher
- Чекаємо на їх завершення з timeout (2 секунди)
- Потім зупиняємо client з timeout (5 секунд)
- Всі помилки логуються, але не зупиняють процес завершення

## Результат

Після цих виправлень програма повинна коректно завершуватися без помилок:

1. ✅ Немає конфліктів event loops
2. ✅ Всі асинхронні задачі коректно скасовуються
3. ✅ Dispatcher tasks завершуються перед зупинкою client
4. ✅ Використовуються timeout для запобігання зависанню
5. ✅ Всі помилки обробляються і логуються

## Тестування

Для тестування виправлень:

1. Запустіть програму
2. Натисніть Ctrl+C для завершення
3. Програма повинна завершитися без помилок з повідомленням "✅ Система зупинена"

## Додаткові рекомендації

1. **Моніторинг логів**: Перевіряйте `bot.log` на наявність попереджень про timeout
2. **Timeout значення**: Якщо виникають timeout помилки, можна збільшити значення timeout (наразі 2 та 5 секунд)
3. **Windows обмеження**: На Windows `add_signal_handler` не працює, тому використовується fallback через `KeyboardInterrupt`

