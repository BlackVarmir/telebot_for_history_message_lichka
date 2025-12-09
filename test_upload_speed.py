#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест швидкості завантаження з прогресом
"""
import os
import sys
import time
from dotenv import load_dotenv

# Налаштовуємо UTF-8 для консолі Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

print("=" * 60)
print("TEST: S3 Upload Speed with Progress")
print("=" * 60)

# Конфігурація S3
bucket_name = os.getenv('S3_BUCKET_NAME')
prefix = os.getenv('S3_PREFIX', '').strip()
if prefix and not prefix.endswith('/'):
    prefix += '/'

# Створюємо S3 клієнт
s3_client = boto3.client(
    's3',
    endpoint_url=os.getenv('S3_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
    region_name=os.getenv('S3_REGION', 'fsn1')
)

# Знаходимо лог-файл
log_files = [f for f in os.listdir('.') if f.startswith('bot_') and f.endswith('.log')]
if not log_files:
    print("No log files found!")
    sys.exit(1)

test_file = log_files[0]
local_path = os.path.abspath(test_file)
file_size = os.path.getsize(local_path)
file_size_mb = file_size / (1024 * 1024)

print(f"\nFile: {test_file}")
print(f"Size: {file_size_mb:.2f} MB ({file_size:,} bytes)")
print(f"Bucket: {bucket_name}")
print(f"Prefix: {prefix}")

remote_key = f"{prefix}test-logs/{test_file}"
print(f"Remote key: {remote_key}")

# Callback для прогресу
class ProgressPercentage:
    def __init__(self, filename, filesize):
        self._filename = filename
        self._size = filesize
        self._seen_so_far = 0
        self._lock = None
        self._start_time = time.time()
        self._last_print = 0

    def __call__(self, bytes_amount):
        self._seen_so_far += bytes_amount
        percentage = (self._seen_so_far / self._size) * 100
        elapsed = time.time() - self._start_time

        # Друкуємо кожні 5%
        if percentage - self._last_print >= 5 or self._seen_so_far == self._size:
            speed_mbps = (self._seen_so_far / (1024 * 1024)) / elapsed if elapsed > 0 else 0
            print(f"  {percentage:5.1f}% | {self._seen_so_far / (1024*1024):7.2f} MB / {self._size / (1024*1024):7.2f} MB | {speed_mbps:5.2f} MB/s | {elapsed:5.1f}s")
            self._last_print = percentage

# Конфігурація multipart
config = TransferConfig(
    multipart_threshold=100 * 1024 * 1024,  # 100 MB
    max_concurrency=10,
    multipart_chunksize=25 * 1024 * 1024,  # 25 MB
    use_threads=True
)

print(f"\n{'='*60}")
print("Starting upload...")
print(f"{'='*60}\n")

start_time = time.time()

try:
    s3_client.upload_file(
        local_path,
        bucket_name,
        remote_key,
        ExtraArgs={'ContentType': 'text/plain'},
        Config=config,
        Callback=ProgressPercentage(test_file, file_size)
    )

    elapsed = time.time() - start_time
    avg_speed = file_size_mb / elapsed

    print(f"\n{'='*60}")
    print(f"SUCCESS!")
    print(f"Time: {elapsed:.1f} seconds")
    print(f"Average speed: {avg_speed:.2f} MB/s")
    print(f"{'='*60}")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
