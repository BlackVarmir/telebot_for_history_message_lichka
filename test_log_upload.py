#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовий скрипт для перевірки відправки логів на S3
"""
import os
import sys
from dotenv import load_dotenv

# Налаштовуємо UTF-8 для консолі Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Завантажуємо .env
load_dotenv()

print("=" * 60)
print("TEST: S3 Log Upload")
print("=" * 60)

# Перевіряємо конфігурацію
print("\n📋 Конфігурація:")
print(f"   STORAGE_TYPE: {os.getenv('STORAGE_TYPE')}")
print(f"   S3_BUCKET_NAME: {os.getenv('S3_BUCKET_NAME')}")
print(f"   S3_PREFIX: {os.getenv('S3_PREFIX')}")
print(f"   S3_ENDPOINT_URL: {os.getenv('S3_ENDPOINT_URL')}")
print(f"   S3_REGION: {os.getenv('S3_REGION')}")

# Імпортуємо S3 клієнт
try:
    import boto3
    from botocore.exceptions import ClientError
    print("\n✅ boto3 встановлено")
except ImportError as e:
    print(f"\n❌ Помилка імпорту boto3: {e}")
    sys.exit(1)

# Створюємо S3 клієнт
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv('S3_ENDPOINT_URL'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
        region_name=os.getenv('S3_REGION', 'fsn1')
    )
    print("✅ S3 клієнт створено")
except Exception as e:
    print(f"❌ Помилка створення S3 клієнта: {e}")
    sys.exit(1)

# Перевіряємо bucket
bucket_name = os.getenv('S3_BUCKET_NAME')
try:
    s3_client.head_bucket(Bucket=bucket_name)
    print(f"✅ Bucket '{bucket_name}' існує і доступний")
except ClientError as e:
    print(f"❌ Помилка доступу до bucket: {e}")
    sys.exit(1)

# Знаходимо лог-файли
print("\n📁 Пошук лог-файлів...")
log_files = [f for f in os.listdir('.') if f.startswith('bot_') and f.endswith('.log')]
print(f"   Знайдено: {len(log_files)} файлів")

if not log_files:
    print("❌ Немає лог-файлів для відправки")
    sys.exit(0)

# Виводимо список
for i, log_file in enumerate(log_files, 1):
    size_mb = os.path.getsize(log_file) / (1024 * 1024)
    print(f"   {i}. {log_file} ({size_mb:.2f} MB)")

# Відправляємо перший файл як тест
test_file = log_files[0]
local_path = os.path.abspath(test_file)
prefix = os.getenv('S3_PREFIX', '').strip()
if prefix and not prefix.endswith('/'):
    prefix += '/'

remote_key = f"{prefix}logs/{test_file}"

print(f"\n📤 Тестова відправка файлу:")
print(f"   Local: {local_path}")
print(f"   Bucket: {bucket_name}")
print(f"   Remote key: {remote_key}")

try:
    s3_client.upload_file(
        local_path,
        bucket_name,
        remote_key,
        ExtraArgs={'ContentType': 'text/plain'}
    )
    print(f"\n✅ УСПІХ! Файл {test_file} відправлено на S3!")
    print(f"   Повний шлях: s3://{bucket_name}/{remote_key}")
except Exception as e:
    print(f"\n❌ ПОМИЛКА відправки: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Перевіряємо що файл з'явився
print(f"\n🔍 Перевірка наявності файлу на S3...")
try:
    s3_client.head_object(Bucket=bucket_name, Key=remote_key)
    print(f"✅ Файл підтверджено на S3!")
except ClientError as e:
    print(f"❌ Файл не знайдено на S3: {e}")

print("\n" + "=" * 60)
print("✅ ТЕСТ ЗАВЕРШЕНО УСПІШНО!")
print("=" * 60)
