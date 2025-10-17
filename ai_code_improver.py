"""
🤖 AI ПОКРАЩУВАЧ КОДУ
Використовує AI для аналізу та автоматичного покращення коду
"""

import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import ast
import inspect

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Аналізатор коду"""
    
    @staticmethod
    def extract_function_code(func) -> str:
        """Витягти код функції"""
        try:
            return inspect.getsource(func)
        except Exception as e:
            logger.error(f"Не вдалося витягти код функції: {e}")
            return ""
    
    @staticmethod
    def analyze_complexity(code: str) -> Dict[str, Any]:
        """Аналіз складності коду"""
        try:
            tree = ast.parse(code)
            
            # Підрахунок різних елементів
            stats = {
                'lines': len(code.split('\n')),
                'functions': 0,
                'classes': 0,
                'loops': 0,
                'conditions': 0,
                'try_except': 0,
                'complexity_score': 0
            }
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    stats['functions'] += 1
                elif isinstance(node, ast.ClassDef):
                    stats['classes'] += 1
                elif isinstance(node, (ast.For, ast.While)):
                    stats['loops'] += 1
                elif isinstance(node, ast.If):
                    stats['conditions'] += 1
                elif isinstance(node, ast.Try):
                    stats['try_except'] += 1
            
            # Простий розрахунок складності
            stats['complexity_score'] = (
                stats['loops'] * 2 +
                stats['conditions'] * 1 +
                stats['try_except'] * 1
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Помилка аналізу складності: {e}")
            return {}
    
    @staticmethod
    def find_potential_issues(code: str) -> List[str]:
        """Знайти потенційні проблеми в коді"""
        issues = []
        
        # Перевірка на довгі рядки
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append(f"Рядок {i}: занадто довгий ({len(line)} символів)")
        
        # Перевірка на вкладені цикли
        if 'for' in code and code.count('for') > 2:
            issues.append("Можливо занадто багато вкладених циклів")
        
        # Перевірка на відсутність docstring
        if 'def ' in code and '"""' not in code and "'''" not in code:
            issues.append("Відсутня документація (docstring)")
        
        # Перевірка на bare except
        if 'except:' in code:
            issues.append("Використання bare except (краще вказати тип помилки)")
        
        return issues


class AICodeImprover:
    """AI покращувач коду"""
    
    def __init__(self, anthropic_client=None, openai_client=None):
        self.anthropic_client = anthropic_client
        self.openai_client = openai_client
        self.improvements_file = "code_improvements.json"
        self.improvements_history = []
        self.load_history()
        
    def load_history(self):
        """Завантажити історію покращень"""
        if os.path.exists(self.improvements_file):
            try:
                with open(self.improvements_file, 'r', encoding='utf-8') as f:
                    self.improvements_history = json.load(f)
            except Exception as e:
                logger.error(f"Помилка завантаження історії: {e}")
    
    def save_history(self):
        """Зберегти історію покращень"""
        try:
            with open(self.improvements_file, 'w', encoding='utf-8') as f:
                json.dump(self.improvements_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Помилка збереження історії: {e}")
    
    async def analyze_and_improve(self, code: str, context: str = "") -> Optional[Dict[str, Any]]:
        """Аналізувати та покращити код через AI"""
        if not self.anthropic_client:
            logger.warning("AI клієнт не налаштований")
            return None
        
        try:
            # Аналіз складності
            complexity = CodeAnalyzer.analyze_complexity(code)
            issues = CodeAnalyzer.find_potential_issues(code)
            
            # Формуємо промпт для AI
            prompt = f"""Проаналізуй та покращи цей Python код.

Контекст: {context}

Поточний код:
```python
{code}
```

Статистика коду:
- Рядків: {complexity.get('lines', 0)}
- Функцій: {complexity.get('functions', 0)}
- Циклів: {complexity.get('loops', 0)}
- Умов: {complexity.get('conditions', 0)}
- Складність: {complexity.get('complexity_score', 0)}

Знайдені проблеми:
{chr(10).join(f"- {issue}" for issue in issues) if issues else "Немає явних проблем"}

Запропонуй покращення для:
1. **Продуктивність** - як зробити код швидшим
2. **Читабельність** - як зробити код зрозумілішим
3. **Надійність** - як покращити обробку помилок
4. **Оптимізація** - як зменшити використання ресурсів

Відповідь у форматі JSON:
{{
  "improvements": [
    {{
      "category": "performance|readability|reliability|optimization",
      "priority": "low|medium|high|critical",
      "description": "що покращити",
      "reason": "чому це важливо",
      "improved_code": "покращений код",
      "expected_benefit": "очікувана користь"
    }}
  ],
  "overall_assessment": "загальна оцінка коду",
  "recommendation": "головна рекомендація"
}}"""
            
            logger.info("🤖 Відправляю код на аналіз AI...")
            
            response = await self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            
            # Витягуємо JSON з відповіді
            try:
                # Шукаємо JSON в відповіді
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start != -1 and end > start:
                    json_str = response_text[start:end]
                    result = json.loads(json_str)
                else:
                    result = {'raw_response': response_text}
            except json.JSONDecodeError:
                result = {'raw_response': response_text}
            
            # Зберігаємо в історію
            improvement_record = {
                'timestamp': datetime.now().isoformat(),
                'context': context,
                'original_code_lines': complexity.get('lines', 0),
                'complexity_score': complexity.get('complexity_score', 0),
                'issues_found': len(issues),
                'improvements': result.get('improvements', []),
                'assessment': result.get('overall_assessment', ''),
                'recommendation': result.get('recommendation', '')
            }
            
            self.improvements_history.append(improvement_record)
            self.save_history()
            
            logger.info(f"✅ AI аналіз завершено. Знайдено {len(result.get('improvements', []))} покращень")
            
            return result
            
        except Exception as e:
            logger.error(f"Помилка AI аналізу коду: {e}")
            return None
    
    async def generate_optimization_patch(self, function_name: str, current_code: str) -> Optional[str]:
        """Згенерувати патч для оптимізації функції"""
        if not self.anthropic_client:
            return None
        
        try:
            prompt = f"""Створи оптимізований варіант цієї Python функції.

Функція: {function_name}

Поточний код:
```python
{current_code}
```

Вимоги:
1. Зберегти всю функціональність
2. Покращити продуктивність
3. Додати кешування якщо можливо
4. Покращити обробку помилок
5. Додати type hints якщо їх немає

Поверни ТІЛЬКИ покращений код функції, без пояснень."""

            response = await self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            improved_code = response.content[0].text
            
            # Витягуємо код з markdown якщо є
            if '```python' in improved_code:
                start = improved_code.find('```python') + 9
                end = improved_code.find('```', start)
                improved_code = improved_code[start:end].strip()
            
            return improved_code
            
        except Exception as e:
            logger.error(f"Помилка генерації патчу: {e}")
            return None
    
    def get_improvement_stats(self) -> Dict[str, Any]:
        """Отримати статистику покращень"""
        if not self.improvements_history:
            return {}
        
        total_improvements = sum(
            len(record.get('improvements', []))
            for record in self.improvements_history
        )
        
        categories = {}
        priorities = {}
        
        for record in self.improvements_history:
            for improvement in record.get('improvements', []):
                cat = improvement.get('category', 'unknown')
                pri = improvement.get('priority', 'unknown')
                
                categories[cat] = categories.get(cat, 0) + 1
                priorities[pri] = priorities.get(pri, 0) + 1
        
        return {
            'total_analyses': len(self.improvements_history),
            'total_improvements': total_improvements,
            'by_category': categories,
            'by_priority': priorities,
            'last_analysis': self.improvements_history[-1]['timestamp'] if self.improvements_history else None
        }
    
    def log_stats(self):
        """Вивести статистику покращень"""
        stats = self.get_improvement_stats()
        if stats:
            logger.info(
                f"🤖 AI покращення: "
                f"аналізів={stats['total_analyses']} | "
                f"покращень={stats['total_improvements']}"
            )


class AutoPatcher:
    """Автоматичне застосування патчів"""
    
    def __init__(self, backup_dir: str = "code_backups"):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        
    def create_backup(self, file_path: str) -> str:
        """Створити бекап файлу"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{os.path.basename(file_path)}.{timestamp}.backup"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"💾 Створено бекап: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Помилка створення бекапу: {e}")
            return ""
    
    def apply_patch(self, file_path: str, new_code: str, dry_run: bool = True) -> bool:
        """Застосувати патч до файлу"""
        try:
            if dry_run:
                logger.info(f"🔍 DRY RUN: Патч для {file_path}")
                logger.info(f"Новий код:\n{new_code}")
                return True
            
            # Створюємо бекап
            backup_path = self.create_backup(file_path)
            if not backup_path:
                logger.error("Не вдалося створити бекап, патч не застосовано")
                return False
            
            # Застосовуємо патч
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_code)
            
            logger.info(f"✅ Патч застосовано до {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Помилка застосування патчу: {e}")
            return False

