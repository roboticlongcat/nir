"""
Модуль для обработки документов: выделение сущностей
Один запрос на весь документ — максимальная скорость
"""

import json
import requests
import time
import re
import os
from typing import Dict, List, Any, Optional
import config

# Создаём папку для отладки
DEBUG_DIR = "debug_responses"
os.makedirs(DEBUG_DIR, exist_ok=True)

def load_input_data(filepath: str) -> Dict[str, Any]:
    """Загрузка входного JSON-файла"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Файл не найден: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        return None

def extract_full_text(doc: Dict[str, Any]) -> str:
    """
    Извлечение всего текста из документа целиком
    """
    full_text = ""
    for page in doc.get("pages", []):
        content = page.get("content", "")
        if isinstance(content, str):
            # Убираем маркеры, но сохраняем текст
            clean_text = content.replace("[PARAGRAPH_END]", "\n\n").replace("[PAGE_END]", "\n\n")
            # Убираем маркеры формул и изображений
            clean_text = re.sub(r'\[FORMULA\]', '', clean_text)
            clean_text = re.sub(r'\[ИЗОБРАЖЕНИЕ\]', '', clean_text)
            full_text += clean_text + "\n\n"

    return full_text.strip()

def clean_json_response(text: Any) -> str:
    """Очистка ответа от LLM от возможного мусора"""
    if not isinstance(text, str):
        print(f"   ⚠️ clean_json_response получил не строку: {type(text)}")
        return "{}"

    # Сохраняем сырой ответ для отладки
    with open(f"{DEBUG_DIR}/raw_response_{int(time.time())}.txt", "w", encoding="utf-8") as f:
        f.write(text)

    # Убираем markdown-форматирование
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)

    # Убираем всё до первого {
    first_brace = text.find('{')
    if first_brace > 0:
        text = text[first_brace:]

    # Убираем всё после последнего }
    last_brace = text.rfind('}')
    if last_brace > 0:
        text = text[:last_brace+1]

    text = text.strip()

    if not text:
        return "{}"

    return text

def create_entity_extraction_prompt(full_text: str) -> str:
    """
    Создание промпта для выделения сущностей из всего текста
    """
    # Ограничиваем длину текста для токенов
    if len(full_text) > 80000:
        full_text = full_text[:80000] + "... (текст обрезан для обработки)"

    prompt = f"""Ты — система анализа научных статей. Твоя задача — выделить ключевые смысловые сущности из всего текста и определить их онтологические классы.

### 📥 Входные данные:
Весь текст документа (единым блоком, абзацы разделены двойным переносом строки \n\n):

{full_text}

### 🎯 Задача:
1. Проанализируй весь текст и выдели **все ключевые смысловые сущности** — термины, понятия, важные для понимания текста.
2. Для каждой уникальной сущности определи её **онтологический класс** (обобщающая категория).
3. Верни **словарь всех сущностей** с их классами.
4. Для каждого абзаца (начиная с номера 0) укажи список сущностей, которые в нём встречаются.

ВАЖНО: Слова могут быть разных регистров, проверяй это и не добавляй в словарь дубликаты.

### 📌 КРИТЕРИИ ОНТОЛОГИЧЕСКОГО КЛАССА:

Онтологический класс — это **устойчивая категория сущностей**, а не событие, не свойство и не конкретный экземпляр.

**Правильные классы:**
- Обозначают класс объектов или сущностей
- Обладают устойчивыми существенными признаками
- Не являются чрезмерно общими

**Неправильные классы:**
- События ("сбил", "произошло", "выполнил")
- Свойства или атрибуты ("красный", "быстрый", "важный")
- Конкретные экземпляры ("Иван Петров", "Windows 10")
- Общие слова ("ситуация", "схема", "область", "действие", "процесс")
- Связки по типу "Тип объекта - Объект" (только если не термин)
- Параметры и формулы ("(3)", "γ", "x_i") — это не слова

### 📌 ПРАВИЛА ВЫДЕЛЕНИЯ КАНОНИЧЕСКОЙ ФОРМЫ:

Каноническая форма сохраняет идентичность объекта.

1. **Если удаление слова не меняет объект — слово не включается.**
   ✅ "компания Метаграф" → сущность "Метаграф"
   ✅ "корпорация Microsoft" → сущность "Microsoft"

2. **Если оба компонента обязательны — сохраняем полностью.**
   ✅ "интеграл Ито" — полное название
   ✅ "метод конечных элементов" — полное название

3. **Полные официальные названия — единая сущность.**
   ✅ "Московский Государственный Технический Университет"

4. **Формулы без описания — не сущности.**
   ❌ "(3)", "γ", "x_i"
   ✅ "коэффициент γ" → "коэффициент гамма"

### 📌 ПРИМЕРЫ ОНТОЛОГИЧЕСКИХ КЛАССОВ:

| Сущность | Онтологический класс |
|----------|---------------------|
| база данных | Хранилище данных |
| алгоритм | Метод |
| пакет | Единица данных |
| браузер | Приложение |
| интеграл Ито | Математический метод |
| Microsoft | Компания |
| метод конечных элементов | Численный метод |
| пользователь | Субъект |
| сервер | Оборудование |
| протокол | Стандарт |

### 📤 Формат вывода (строго JSON):
{{
  "dictionary": {{
    "сущность_1": "класс_1",
    "сущность_2": "класс_2",
    "сущность_3": "класс_3"
  }},
  "paragraph_entities": [
    {{
      "num": 0,
      "entities": ["сущность_1", "сущность_2"]
    }},
    {{
      "num": 1,
      "entities": ["сущность_2", "сущность_3"]
    }},
    {{
      "num": 2,
      "entities": ["сущность_1", "сущность_3"]
    }}
  ]
}}

Где:
- dictionary — словарь всех сущностей с их классами
- paragraph_entities — массив объектов, где для каждого абзаца указан его номер (num) и список сущностей (entities)

ВАЖНО: Верни ТОЛЬКО JSON, без пояснений, без markdown, без текста до или после JSON."""

    return prompt

def call_openrouter(prompt: str, doc_id: int) -> Optional[Dict[str, Any]]:
    """Один запрос к OpenRouter API на весь документ"""

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": f"Document Processor {doc_id}"
    }

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS_PER_REQUEST
    }

    try:
        print(f"   📤 Отправка запроса (документ {doc_id})...")
        response = requests.post(
            config.OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=config.REQUEST_TIMEOUT
        )

        print(f"   📥 Статус ответа: {response.status_code}")

        if response.status_code != 200:
            print(f"   ❌ Ошибка HTTP {response.status_code}")
            if response.text:
                print(f"   Ответ: {response.text[:500]}")
            return None

        # Сохраняем полный ответ API для отладки
        debug_file = f"{DEBUG_DIR}/api_response_{doc_id}_{int(time.time())}.json"
        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump(response.json(), f, ensure_ascii=False, indent=2)

        return response.json()

    except Exception as e:
        print(f"   ❌ Ошибка соединения: {e}")
        return None

def parse_llm_response(response_text: Any, doc_id: int) -> Optional[Dict[str, Any]]:
    """Парсинг ответа от LLM"""
    if not isinstance(response_text, str):
        print(f"   ❌ parse_llm_response получил не строку: {type(response_text)}")
        return None

    # Сохраняем сырой текст ответа
    debug_file = f"{DEBUG_DIR}/llm_response_{doc_id}_{int(time.time())}.txt"
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(response_text)

    cleaned = clean_json_response(response_text)

    try:
        result = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        print(f"   ❌ Ошибка парсинга JSON: {e}")
        print(f"   Очищенный текст (первые 200 символов): {cleaned[:200]}")

        # Пробуем найти JSON вручную
        try:
            # Ищем любой JSON объект
            import re
            json_pattern = r'\{[^{}]*\}'
            matches = re.findall(json_pattern, response_text)
            if matches:
                # Берём самый длинный (скорее всего нужный)
                best_match = max(matches, key=len)
                result = json.loads(best_match)
                print(f"   ✅ JSON восстановлен вручную (найден фрагмент)")
                return result
        except:
            pass

        return None

def process_document(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Обработка одного документа — ОДИН ЗАПРОС на весь документ
    """

    doc_id = doc.get("doc_id", "unknown")
    print(f"\n📄 Обработка документа: {doc.get('source_file', 'unknown')}")
    print(f"   ID: {doc_id}, язык: {doc.get('language', 'unknown')}")

    # Извлекаем весь текст целиком
    full_text = extract_full_text(doc)
    text_len = len(full_text)
    print(f"   📊 Длина текста: {text_len} символов")

    if text_len < 100:
        print("   ⚠️ Текст слишком короткий")
        return None

    # Один запрос на весь документ
    print(f"\n🔨 ОБРАБОТКА ДОКУМЕНТА (ОДИН ЗАПРОС)")

    prompt = create_entity_extraction_prompt(full_text)
    response = call_openrouter(prompt, doc_id)

    if not response:
        print("   ❌ Нет ответа от API")
        return None

    # Извлекаем текст ответа
    try:
        if "choices" not in response or not response["choices"]:
            print("   ❌ Нет choices в ответе")
            return None

        message = response["choices"][0].get("message", {})
        if "content" not in message:
            print("   ❌ Нет content в message")
            return None

        result_text = message["content"]
    except Exception as e:
        print(f"   ❌ Ошибка извлечения ответа: {e}")
        return None

    # Парсим ответ
    parsed = parse_llm_response(result_text, doc_id)

    if not parsed:
        print("   ❌ Не удалось распарсить ответ")
        return None

    # Проверяем наличие обязательных полей
    if "dictionary" not in parsed:
        print("   ❌ Ответ не содержит dictionary")
        print(f"   Ключи в ответе: {list(parsed.keys())}")
        return None

    if "paragraph_entities" not in parsed:
        print("   ❌ Ответ не содержит paragraph_entities")
        print(f"   Ключи в ответе: {list(parsed.keys())}")
        return None

    # Проверяем, что словарь не пустой
    if not parsed["dictionary"]:
        print("   ⚠️ Словарь сущностей пуст")

    print(f"\n   📚 Найдено сущностей: {len(parsed['dictionary'])}")
    print(f"   📚 Обработано абзацев: {len(parsed['paragraph_entities'])}")

    # Формируем результат
    result = {
        "doc_id": doc_id,
        "source_file": doc.get("source_file", ""),
        "language": doc.get("language", ""),
        "dictionary": parsed["dictionary"],
        "paragraph_entities": parsed["paragraph_entities"]
    }

    return result
