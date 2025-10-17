"""
📊 МОНІТОР ПРОДУКТИВНОСТІ
Відслідковує та аналізує продуктивність бота в реальному часі
"""

import time
import asyncio
import functools
import logging
import psutil
import os
from typing import Callable, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Монітор продуктивності"""
    
    def __init__(self, optimizer=None):
        self.optimizer = optimizer
        self.process = psutil.Process(os.getpid())
        self.start_time = time.time()
        self.monitoring_enabled = True
        
    def get_memory_usage(self) -> float:
        """Отримати використання пам'яті (MB)"""
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def get_cpu_usage(self) -> float:
        """Отримати використання CPU (%)"""
        try:
            return self.process.cpu_percent(interval=0.1)
        except Exception:
            return 0.0
    
    def get_uptime(self) -> float:
        """Отримати час роботи (секунди)"""
        return time.time() - self.start_time
    
    def get_system_stats(self) -> dict:
        """Отримати системну статистику"""
        try:
            return {
                'memory_mb': self.get_memory_usage(),
                'cpu_percent': self.get_cpu_usage(),
                'uptime_seconds': self.get_uptime(),
                'threads': self.process.num_threads(),
                'open_files': len(self.process.open_files()),
            }
        except Exception as e:
            logger.error(f"Помилка отримання статистики: {e}")
            return {}
    
    def log_stats(self):
        """Вивести статистику в лог"""
        stats = self.get_system_stats()
        if stats:
            logger.info(
                f"📊 Статистика: "
                f"RAM: {stats['memory_mb']:.1f}MB | "
                f"CPU: {stats['cpu_percent']:.1f}% | "
                f"Uptime: {stats['uptime_seconds']/3600:.1f}h | "
                f"Threads: {stats['threads']}"
            )


def performance_tracked(func: Callable) -> Callable:
    """Декоратор для відстеження продуктивності функції"""
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        success = True
        error = None
        result = None
        
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            execution_time = time.time() - start_time
            
            # Логування якщо функція виконувалася довго
            if execution_time > 1.0:
                logger.warning(
                    f"⚠️ Повільна функція: {func.__name__} "
                    f"виконувалася {execution_time:.3f}s"
                )
            
            # Записуємо метрику в оптимізатор якщо він доступний
            try:
                # Шукаємо оптимізатор в args (self)
                if args and hasattr(args[0], 'optimizer'):
                    optimizer = args[0].optimizer
                    if optimizer and hasattr(optimizer, 'profiler'):
                        from self_optimizer import PerformanceMetrics
                        
                        metric = PerformanceMetrics(
                            timestamp=start_time,
                            function_name=func.__name__,
                            execution_time=execution_time,
                            success=success,
                            error=error
                        )
                        optimizer.profiler.record_metric(metric)
            except Exception as e:
                logger.debug(f"Не вдалося записати метрику: {e}")
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        success = True
        error = None
        result = None
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            execution_time = time.time() - start_time
            
            if execution_time > 1.0:
                logger.warning(
                    f"⚠️ Повільна функція: {func.__name__} "
                    f"виконувалася {execution_time:.3f}s"
                )
    
    # Повертаємо відповідний wrapper
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


class CacheManager:
    """Менеджер кешування для оптимізації"""
    
    def __init__(self, default_ttl: int = 300):
        self.cache = {}
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
        
    def get(self, key: str) -> Any:
        """Отримати значення з кешу"""
        if key in self.cache:
            entry = self.cache[key]
            if time.time() < entry['expires']:
                self.hits += 1
                return entry['value']
            else:
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Зберегти значення в кеш"""
        if ttl is None:
            ttl = self.default_ttl
        
        self.cache[key] = {
            'value': value,
            'expires': time.time() + ttl,
            'created': time.time()
        }
    
    def clear_expired(self):
        """Очистити застарілі записи"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time >= entry['expires']
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"🧹 Очищено {len(expired_keys)} застарілих записів кешу")
    
    def get_stats(self) -> dict:
        """Отримати статистику кешу"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate
        }
    
    def log_stats(self):
        """Вивести статистику кешу"""
        stats = self.get_stats()
        logger.info(
            f"💾 Кеш: розмір={stats['size']} | "
            f"hits={stats['hits']} | "
            f"misses={stats['misses']} | "
            f"hit_rate={stats['hit_rate']:.1f}%"
        )


def cached(ttl: int = 300):
    """Декоратор для кешування результатів функції"""
    
    def decorator(func: Callable) -> Callable:
        cache = {}
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Створюємо ключ кешу
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Перевіряємо кеш
            if cache_key in cache:
                entry = cache[cache_key]
                if time.time() < entry['expires']:
                    logger.debug(f"💾 Кеш HIT: {func.__name__}")
                    return entry['value']
                else:
                    del cache[cache_key]
            
            # Виконуємо функцію
            logger.debug(f"💾 Кеш MISS: {func.__name__}")
            result = await func(*args, **kwargs)
            
            # Зберігаємо в кеш
            cache[cache_key] = {
                'value': result,
                'expires': time.time() + ttl,
                'created': time.time()
            }
            
            return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            if cache_key in cache:
                entry = cache[cache_key]
                if time.time() < entry['expires']:
                    logger.debug(f"💾 Кеш HIT: {func.__name__}")
                    return entry['value']
                else:
                    del cache[cache_key]
            
            logger.debug(f"💾 Кеш MISS: {func.__name__}")
            result = func(*args, **kwargs)
            
            cache[cache_key] = {
                'value': result,
                'expires': time.time() + ttl,
                'created': time.time()
            }
            
            return result
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class AdaptiveRateLimiter:
    """Адаптивний обмежувач швидкості"""
    
    def __init__(self, initial_rate: float = 1.0):
        self.rate = initial_rate  # запитів на секунду
        self.last_call = 0
        self.success_count = 0
        self.error_count = 0
        self.adjustment_threshold = 10
        
    async def wait(self):
        """Почекати перед наступним запитом"""
        current_time = time.time()
        time_since_last = current_time - self.last_call
        required_delay = 1.0 / self.rate
        
        if time_since_last < required_delay:
            await asyncio.sleep(required_delay - time_since_last)
        
        self.last_call = time.time()
    
    def record_success(self):
        """Записати успішний запит"""
        self.success_count += 1
        self._adjust_rate()
    
    def record_error(self):
        """Записати помилку"""
        self.error_count += 1
        self._adjust_rate()
    
    def _adjust_rate(self):
        """Адаптувати швидкість"""
        total = self.success_count + self.error_count
        
        if total >= self.adjustment_threshold:
            error_rate = self.error_count / total
            
            if error_rate > 0.1:  # Більше 10% помилок
                # Зменшуємо швидкість
                self.rate = max(0.1, self.rate * 0.8)
                logger.info(f"⬇️ Зменшено швидкість запитів до {self.rate:.2f} req/s")
            elif error_rate < 0.01:  # Менше 1% помилок
                # Збільшуємо швидкість
                self.rate = min(10.0, self.rate * 1.2)
                logger.info(f"⬆️ Збільшено швидкість запитів до {self.rate:.2f} req/s")
            
            # Скидаємо лічильники
            self.success_count = 0
            self.error_count = 0

