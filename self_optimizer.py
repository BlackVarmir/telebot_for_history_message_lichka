"""
🤖 МОДУЛЬ САМООПТИМІЗАЦІЇ БОТА
Автоматично аналізує, оптимізує та покращує роботу бота
"""

import asyncio
import time
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import statistics
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Метрики продуктивності"""
    timestamp: float
    function_name: str
    execution_time: float
    memory_usage: Optional[float] = None
    cpu_usage: Optional[float] = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class OptimizationSuggestion:
    """Пропозиція оптимізації"""
    timestamp: float
    category: str  # 'performance', 'parameters', 'code'
    priority: str  # 'low', 'medium', 'high', 'critical'
    description: str
    current_value: Any
    suggested_value: Any
    expected_improvement: str
    auto_apply: bool = False
    applied: bool = False


class PerformanceProfiler:
    """Профілювання продуктивності"""
    
    def __init__(self, max_history: int = 1000):
        self.metrics: deque = deque(maxlen=max_history)
        self.function_stats: Dict[str, List[float]] = {}
        
    def record_metric(self, metric: PerformanceMetrics):
        """Записати метрику"""
        self.metrics.append(metric)
        
        if metric.function_name not in self.function_stats:
            self.function_stats[metric.function_name] = []
        
        self.function_stats[metric.function_name].append(metric.execution_time)
        
    def get_function_stats(self, function_name: str) -> Dict[str, float]:
        """Отримати статистику функції"""
        if function_name not in self.function_stats:
            return {}
        
        times = self.function_stats[function_name]
        if not times:
            return {}
        
        return {
            'count': len(times),
            'total': sum(times),
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'min': min(times),
            'max': max(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0
        }
    
    def get_slow_functions(self, threshold: float = 1.0) -> List[tuple]:
        """Знайти повільні функції"""
        slow_functions = []
        
        for func_name, times in self.function_stats.items():
            if not times:
                continue
            
            avg_time = statistics.mean(times)
            if avg_time > threshold:
                slow_functions.append((func_name, avg_time, len(times)))
        
        return sorted(slow_functions, key=lambda x: x[1], reverse=True)
    
    def analyze_trends(self, function_name: str, window: int = 100) -> Dict[str, Any]:
        """Аналіз трендів продуктивності"""
        if function_name not in self.function_stats:
            return {}
        
        times = list(self.function_stats[function_name])
        if len(times) < window:
            return {'trend': 'insufficient_data'}
        
        recent = times[-window:]
        older = times[-window*2:-window] if len(times) >= window*2 else times[:-window]
        
        if not older:
            return {'trend': 'insufficient_data'}
        
        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)
        
        change_percent = ((recent_avg - older_avg) / older_avg) * 100
        
        if change_percent > 10:
            trend = 'degrading'
        elif change_percent < -10:
            trend = 'improving'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'recent_avg': recent_avg,
            'older_avg': older_avg,
            'change_percent': change_percent
        }


class AdaptiveParameterOptimizer:
    """Адаптивна оптимізація параметрів"""
    
    def __init__(self, config_file: str = "optimizer_config.json"):
        self.config_file = config_file
        self.parameters = self.load_config()
        self.performance_history = deque(maxlen=1000)
        
    def load_config(self) -> Dict[str, Any]:
        """Завантажити конфігурацію"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Помилка завантаження конфігурації: {e}")
        
        # Дефолтні параметри
        return {
            'check_interval': 0.5,
            'batch_size': 10,
            'timeout': 30,
            'max_retries': 3,
            'cache_ttl': 300,
            'optimization_enabled': True,
            'last_optimization': None,
            'optimization_count': 0
        }
    
    def save_config(self):
        """Зберегти конфігурацію"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.parameters, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Помилка збереження конфігурації: {e}")
    
    def record_performance(self, messages_count: int, processing_time: float):
        """Записати показники продуктивності"""
        self.performance_history.append({
            'timestamp': time.time(),
            'messages_count': messages_count,
            'processing_time': processing_time,
            'check_interval': self.parameters['check_interval']
        })
    
    def optimize_check_interval(self) -> Optional[float]:
        """Оптимізувати інтервал перевірки"""
        if len(self.performance_history) < 10:
            return None
        
        recent = list(self.performance_history)[-10:]
        avg_messages = statistics.mean([r['messages_count'] for r in recent])
        avg_time = statistics.mean([r['processing_time'] for r in recent])
        
        current_interval = self.parameters['check_interval']
        
        # Якщо багато повідомлень - зменшуємо інтервал
        if avg_messages > 5 and current_interval > 0.1:
            new_interval = max(0.1, current_interval * 0.8)
            return new_interval
        
        # Якщо мало повідомлень - збільшуємо інтервал
        if avg_messages < 1 and current_interval < 2.0:
            new_interval = min(2.0, current_interval * 1.2)
            return new_interval
        
        # Якщо обробка повільна - збільшуємо інтервал
        if avg_time > 1.0 and current_interval < 1.0:
            new_interval = min(1.0, current_interval * 1.1)
            return new_interval
        
        return None
    
    def apply_optimization(self, parameter: str, new_value: Any) -> bool:
        """Застосувати оптимізацію"""
        old_value = self.parameters.get(parameter)
        self.parameters[parameter] = new_value
        self.parameters['last_optimization'] = datetime.now().isoformat()
        self.parameters['optimization_count'] = self.parameters.get('optimization_count', 0) + 1
        self.save_config()
        
        logger.info(f"🔧 Оптимізація: {parameter} змінено з {old_value} на {new_value}")
        return True
    
    def get_current_parameters(self) -> Dict[str, Any]:
        """Отримати поточні параметри"""
        return self.parameters.copy()


class AICodeOptimizer:
    """AI-асистент для оптимізації коду"""
    
    def __init__(self, openai_client=None, anthropic_client=None):
        self.openai_client = openai_client
        self.anthropic_client = anthropic_client
        self.suggestions_file = "optimization_suggestions.json"
        self.suggestions: List[OptimizationSuggestion] = []
        self.load_suggestions()
        
    def load_suggestions(self):
        """Завантажити пропозиції"""
        if os.path.exists(self.suggestions_file):
            try:
                with open(self.suggestions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.suggestions = [OptimizationSuggestion(**s) for s in data]
            except Exception as e:
                logger.error(f"Помилка завантаження пропозицій: {e}")
    
    def save_suggestions(self):
        """Зберегти пропозиції"""
        try:
            with open(self.suggestions_file, 'w', encoding='utf-8') as f:
                data = [asdict(s) for s in self.suggestions]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Помилка збереження пропозицій: {e}")
    
    async def analyze_code_with_ai(self, code_snippet: str, context: str) -> Optional[str]:
        """Аналіз коду через AI"""
        if not self.anthropic_client:
            return None
        
        try:
            prompt = f"""Проаналізуй цей Python код і запропонуй оптимізації:

Контекст: {context}

Код:
```python
{code_snippet}
```

Запропонуй конкретні оптимізації для:
1. Швидкості виконання
2. Використання пам'яті
3. Читабельності коду
4. Обробки помилок

Відповідь у форматі JSON:
{{
  "optimizations": [
    {{
      "type": "performance|memory|readability|error_handling",
      "description": "опис проблеми",
      "suggestion": "конкретна пропозиція",
      "code": "оптимізований код"
    }}
  ]
}}"""
            
            response = await self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Помилка AI аналізу: {e}")
            return None
    
    def add_suggestion(self, suggestion: OptimizationSuggestion):
        """Додати пропозицію"""
        self.suggestions.append(suggestion)
        self.save_suggestions()
        
        priority_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🟠', 'critical': '🔴'}
        emoji = priority_emoji.get(suggestion.priority, '⚪')
        
        logger.info(f"{emoji} Нова пропозиція оптимізації: {suggestion.description}")
    
    def get_pending_suggestions(self) -> List[OptimizationSuggestion]:
        """Отримати непідтверджені пропозиції"""
        return [s for s in self.suggestions if not s.applied]


class SelfOptimizer:
    """Головний клас самооптимізації"""
    
    def __init__(self, openai_client=None, anthropic_client=None):
        self.profiler = PerformanceProfiler()
        self.parameter_optimizer = AdaptiveParameterOptimizer()
        self.ai_optimizer = AICodeOptimizer(openai_client, anthropic_client)
        self.optimization_interval = 300  # 5 хвилин
        self.last_optimization = time.time()
        self.enabled = True
        
    async def run_optimization_cycle(self):
        """Запустити цикл оптимізації"""
        if not self.enabled:
            return
        
        current_time = time.time()
        if current_time - self.last_optimization < self.optimization_interval:
            return
        
        logger.info("🔄 Запуск циклу самооптимізації...")
        
        # 1. Аналіз продуктивності
        slow_functions = self.profiler.get_slow_functions(threshold=0.5)
        if slow_functions:
            logger.warning(f"⚠️ Знайдено {len(slow_functions)} повільних функцій:")
            for func_name, avg_time, count in slow_functions[:5]:
                logger.warning(f"  - {func_name}: {avg_time:.3f}s (викликів: {count})")
        
        # 2. Оптимізація параметрів
        new_interval = self.parameter_optimizer.optimize_check_interval()
        if new_interval:
            self.parameter_optimizer.apply_optimization('check_interval', new_interval)
        
        # 3. Генерація пропозицій
        await self.generate_suggestions()
        
        self.last_optimization = current_time
        logger.info("✅ Цикл оптимізації завершено")
    
    async def generate_suggestions(self):
        """Генерувати пропозиції оптимізації"""
        # Аналіз трендів
        for func_name in self.profiler.function_stats.keys():
            trend = self.profiler.analyze_trends(func_name)
            
            if trend.get('trend') == 'degrading':
                suggestion = OptimizationSuggestion(
                    timestamp=time.time(),
                    category='performance',
                    priority='medium',
                    description=f"Функція {func_name} сповільнилася на {trend['change_percent']:.1f}%",
                    current_value=trend['recent_avg'],
                    suggested_value=trend['older_avg'],
                    expected_improvement=f"Повернення до попередньої швидкості",
                    auto_apply=False
                )
                self.ai_optimizer.add_suggestion(suggestion)

