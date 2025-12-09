#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test cleanup functions
"""
import os
import sys
from dotenv import load_dotenv

# Налаштовуємо UTF-8 для консолі Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

# Import the storage manager and cleanup functions from hybrid_main
import logging
from datetime import datetime

# Налаштовуємо логування
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Create minimal StorageManager
import boto3
from boto3.s3.transfer import TransferConfig

class ObjectStorageManager:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
            region_name=os.getenv('S3_REGION', 'fsn1')
        )
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        self.prefix = os.getenv("S3_PREFIX", "").strip()
        if self.prefix and not self.prefix.endswith('/'):
            self.prefix += '/'
        logger.info(f"✅ S3 Manager initialized (prefix: {self.prefix})")

    def upload_file(self, local_path, remote_key):
        try:
            full_key = self.prefix + remote_key
            file_size_mb = os.path.getsize(local_path) / (1024 * 1024)

            logger.info(f"📤 Uploading: {local_path} -> {full_key} ({file_size_mb:.2f} MB)")

            # Multipart config
            config = TransferConfig(
                multipart_threshold=100 * 1024 * 1024,
                max_concurrency=10,
                multipart_chunksize=25 * 1024 * 1024,
                use_threads=True
            )

            self.s3_client.upload_file(
                local_path,
                self.bucket_name,
                full_key,
                Config=config
            )

            logger.info(f"✅ Upload successful: {full_key}")
            return True
        except Exception as e:
            logger.error(f"❌ Upload failed: {e}")
            return False

    def list_files(self, prefix=''):
        try:
            full_prefix = self.prefix + prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=full_prefix
            )

            if 'Contents' not in response:
                return []

            files = [obj['Key'] for obj in response['Contents']]

            # Remove self.prefix from results
            if self.prefix:
                files = [f[len(self.prefix):] if f.startswith(self.prefix) else f for f in files]

            logger.info(f"📁 Found {len(files)} files on S3")
            return sorted(files, reverse=True)
        except Exception as e:
            logger.error(f"❌ Error listing files: {e}")
            return []

class StorageManager:
    def __init__(self):
        self.storage = ObjectStorageManager()
        self.storage_type = "s3"

    def upload_file(self, local_path, remote_filename):
        return self.storage.upload_file(local_path, remote_filename)

def get_log_filename():
    return f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"

# Initialize storage manager
storage_manager = StorageManager()

# Test cleanup
def cleanup_old_logs():
    """Видаляє ВСІ старі лог-файли (крім поточного), попередньо завантаживши їх на S3"""
    global storage_manager

    if not storage_manager:
        logger.warning("⚠️ StorageManager не ініціалізовано")
        return

    try:
        current_log = get_log_filename()
        deleted_count = 0
        uploaded_count = 0

        logger.info(f"🔍 Current log file: {current_log}")

        # Знаходимо всі лог-файли
        log_files = [f for f in os.listdir('.') if f.startswith('bot_') and f.endswith('.log')]
        logger.info(f"📁 Found {len(log_files)} log files: {log_files}")

        # Перевіряємо які файли вже на S3
        try:
            remote_log_files = storage_manager.storage.list_files(prefix='logs/')
            # Видаляємо префікс 'logs/' зі списку
            remote_log_names = [f.split('/')[-1].replace('.gz', '').replace('.log', '') for f in remote_log_files if '/logs/' in f or f.startswith('logs/')]
            logger.info(f"☁️ Files on S3 (in logs/): {remote_log_names}")
        except Exception as e:
            logger.warning(f"⚠️ Не вдалося отримати список файлів з S3: {e}")
            remote_log_names = []

        for log_file in log_files:
            # Не видаляємо поточний лог-файл
            if log_file == current_log:
                logger.info(f"⏭️ Skipping current log: {log_file}")
                continue

            try:
                # Перевіряємо чи файл вже є на S3 (з .gz або без)
                log_name_base = log_file.replace('.log', '')
                is_on_s3 = any(log_name_base in remote_name for remote_name in remote_log_names)

                logger.info(f"🔍 Checking {log_file}: on S3 = {is_on_s3}")

                # Якщо файлу немає на S3, завантажуємо його
                if not is_on_s3:
                    logger.info(f"📤 Завантажую старий лог на S3: {log_file}")
                    local_path = os.path.abspath(log_file)
                    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)

                    # Стискаємо великі файли
                    upload_path = local_path
                    remote_filename = f"logs/{log_file}"

                    if file_size_mb > 50:
                        import gzip
                        import shutil
                        gz_path = local_path + '.gz'
                        logger.info(f"🗜️ Compressing (file > 50MB): {log_file}")
                        with open(local_path, 'rb') as f_in:
                            with gzip.open(gz_path, 'wb', compresslevel=9) as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        upload_path = gz_path
                        remote_filename = f"logs/{log_file}.gz"

                    # Завантажуємо
                    if storage_manager.upload_file(upload_path, remote_filename):
                        uploaded_count += 1
                        logger.info(f"✅ Лог завантажено на S3: {remote_filename}")
                        # Видаляємо .gz файл якщо створювали
                        if upload_path != local_path and os.path.exists(upload_path):
                            os.remove(upload_path)
                    else:
                        logger.warning(f"⚠️ Не вдалося завантажити {log_file}, пропускаю видалення")
                        continue

                # Тепер видаляємо локальний файл
                logger.info(f"🗑️ Deleting local file: {log_file}")
                os.remove(log_file)
                deleted_count += 1
                logger.info(f"✅ Видалено старий лог: {log_file}")
            except Exception as e:
                logger.warning(f"❌ Не вдалося обробити файл {log_file}: {e}")
                import traceback
                traceback.print_exc()

        if uploaded_count > 0:
            logger.info(f"📤 Завантажено на S3: {uploaded_count} лог-файлів")
        if deleted_count > 0:
            logger.info(f"✅ Видалено локально: {deleted_count} старих лог-файлів")
        else:
            logger.info("📁 Немає старих лог-файлів для видалення")

    except Exception as e:
        logger.error(f"❌ Помилка при очищенні логів: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("TEST: Cleanup Old Logs")
    print("="*60)

    cleanup_old_logs()

    print("="*60)
    print("TEST COMPLETE")
    print("="*60)
