"""
Модуль для обработки документов: выделение сущностей
БЕЗ нормализации текста — только словарь и связи абзац-сущность
"""

import json
import requests
import time
import re
from typing import Dict, List, Any, Optional
import config

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

def extract_paragraphs(doc: Dict[str, Any]) -> List[str]:
    """
    Извлечение всех абзацев из документа
    Учитывает разделители [PARAGRAPH_END] и [PAGE_END]
    """
    paragraphs = []

    for page in doc.get("pages", []):
        content = page.get("content", "")
        if not isinstance(content, str):
            continue

        # Разбиваем по маркерам абзацев
        page_paragraphs = content.split("[PARAGRAPH_END]")

        for para in page_paragraphs:
            # Убираем маркеры страниц и лишние пробелы
            clean_para = para.replace("[PAGE_END]", "").strip()
            # Пропускаем пустые абзацы и абзацы только с формулами/изображениями
            if clean_para and not clean_para.startswith("[FORMULA]") and not clean_para.startswith("[ИЗОБРАЖЕНИЕ]"):
                paragraphs.append(clean_para)

    return paragraphs

def clean_json_response(text: Any) -> str:
    """
    Очистка ответа от LLM от возможного мусора
    """
    # Проверяем тип входных данных
    if not isinstance(text, str):
        print(f"   ⚠️ clean_json_response получил не строку: {type(text)}")
        return "{}"

    # Убираем markdown-форматирование
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)

    # Убираем лишние пробелы и переводы строк в начале и конце
    text = text.strip()

    # Если текст пустой, возвращаем пустой объект
    if not text:
        return "{}"

    # Проверяем, начинается ли текст с '{' и заканчивается ли '}'
    if not (text.startswith('{') and text.endswith('}')):
        # Пробуем найти JSON в тексте
        json_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            print(f"   ⚠️ Не удалось найти JSON в ответе")
            return "{}"

    return text


def create_entity_extraction_prompt(paragraphs: List[str], start_idx: int) -> str:
    """
    Создание промпта для выделения сущностей из абзацев
    """
    paragraphs_text = ""
    for i, p in enumerate(paragraphs):
        paragraphs_text += f"[АБЗАЦ {start_idx + i}]: {p}\n\n"

    prompt = f"""Ты — система анализа научных статей. Твоя задача — выделить ключевые смысловые сущности из каждого абзаца и определить их онтологические классы.

### 📥 Входные данные:
Текст, разбитый на абзацы (каждый абзац имеет номер):

{paragraphs_text}

### 🎯 Задача:
1. Для каждого абзаца выдели **ключевые смысловые сущности** — термины, понятия, важные для понимания текста.
2. Для каждой уникальной сущности определи её **онтологический класс** (обобщающая категория).
3. Верни **словарь всех сущностей** с их классами.
4. Верни **связи абзац-сущность** — для каждого абзаца список сущностей (только названия, без классов).

Слова могут быть разных регистров, проверяй это и не добавляй в словарь слова, которые уже есть!

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
- Общие слова ("ситуация", "схема", "область", "действие")
- Связки по типу "Тип объекта - Объект" или "Объект - Объект" (только если он не относится к категории терминов), не нужно плодить лишнее
- Какие-либо параметры ("(3)", "γ") — формулы зависят от статьи и автора, это не слова

### 📌 ПРАВИЛА ВЫДЕЛЕНИЯ КАНОНИЧЕСКОЙ ФОРМЫ СУЩНОСТИ:

Каноническая форма — это строка, которую ты извлекаешь из текста. Она выбирается так, чтобы **сохранять идентичность объекта**.

**Основные принципы:**

1. **Если удаление слова не меняет того, к какому объекту относится запись, такое слово не включается в каноническую форму.**
   - ✅ Пример: в конструкции "компания Метаграф" сущностью является "Метаграф", а слово "компания" не входит в каноническую запись
   - ✅ Пример: "корпорация Microsoft" → сущность "Microsoft"

2. **Если оба компонента обязательны, так как удаление одного приводит к другому понятию — сохраняем полностью.**
   - ✅ Пример: "интеграл Ито" — оба компонента обязательны, удаление "Ито" приводит к другому понятию
   - ✅ Пример: "метод конечных элементов" — полное название
   - ✅ Пример: "теория относительности" — полное название

3. **Полные официальные названия фиксируются как единая сущность.**
   - ✅ Пример: "Московский Государственный Технический Университет" — единая сущность
   - ✅ Пример: "Институт системного программирования РАН" — единая сущность

4. **Математические формулы и обозначения без словесного описания не выделяются как сущности.**
   - ❌ Неправильно: "(3)", "γ", "x_i", "∑"
   - ✅ Правильно: "коэффициент γ" → сущность "коэффициент гамма"

### 📌 ПРИМЕРЫ ОНТОЛОГИЧЕСКИХ КЛАССОВ:

| Сущность | Онтологический класс | Пояснение |
|----------|---------------------|-----------|
| база данных | Хранилище данных | Класс объектов для хранения информации |
| алгоритм | Метод | Класс последовательностей действий |
| пакет | Единица данных | Класс структурированных блоков информации |
| браузер | Приложение | Класс программ для просмотра веб-страниц |
| интеграл Ито | Математический метод | Полное название, удаление "Ито" меняет смысл |
| Microsoft | Компания | Имя собственное, слово "корпорация" не входит |
| метод конечных элементов | Численный метод | Полное название как единая сущность |

### 📤 Формат вывода (строго JSON):
{{
  "dictionary": {{
    "сущность_1": "класс_1",
    "сущность_2": "класс_2",
    "сущность_3": "класс_3"
  }},
  "paragraph_entities": [
    {{
      "num": {start_idx},
      "entities": ["сущность_1", "сущность_2"]
    }},
    {{
      "num": {start_idx + 1},
      "entities": ["сущность_3", "сущность_4"]
    }}
  ]
}}

Верни ТОЛЬКО JSON, без пояснений."""

    return prompt

def call_openrouter(prompt: str, request_type: str, doc_id: int, batch_num: int = 0) -> Optional[Dict[str, Any]]:
    """Отправка запроса к OpenRouter API"""

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
        print(f"   📤 Отправка {request_type} запроса (документ {doc_id}{f', часть {batch_num}' if batch_num else ''})...")
        response = requests.post(
            config.OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=config.REQUEST_TIMEOUT
        )

        print(f"   📥 Статус ответа: {response.status_code}")

        if response.status_code != 200:
            print(f"   ❌ Ошибка HTTP {response.status_code}")
            print(f"   Ответ: {response.text[:200]}")
            return None

        # Пробуем распарсить JSON ответа от API
        try:
            return response.json()
        except json.JSONDecodeError as e:
            print(f"   ❌ Ошибка парсинга ответа API: {e}")
            print(f"   Сырой ответ: {response.text[:200]}")
            return None

    except requests.exceptions.Timeout:
        print("   ❌ Таймаут соединения")
        return None
    except requests.exceptions.ConnectionError:
        print("   ❌ Ошибка соединения")
        return None
    except Exception as e:
        print(f"   ❌ Ошибка соединения: {e}")
        return None

def parse_llm_response(response_text: Any) -> Optional[Dict[str, Any]]:
    """
    Парсинг ответа от LLM с обработкой ошибок
    """
    # Проверяем тип входных данных
    if not isinstance(response_text, str):
        print(f"   ❌ parse_llm_response получил не строку: {type(response_text)}")
        if response_text is None:
            print("   Ответ от API пустой (None)")
        return None

    try:
        # Очищаем ответ
        cleaned = clean_json_response(response_text)

        # Пробуем распарсить
        result = json.loads(cleaned)
        return result

    except json.JSONDecodeError as e:
        print(f"   ❌ Ошибка парсинга JSON: {e}")
        print(f"   Проблемный текст (первые 200 символов): {response_text[:200]}")

        # Пробуем найти JSON вручную
        try:
            # Ищем начало и конец JSON
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = response_text[start:end+1]
                result = json.loads(json_str)
                print(f"   ✅ JSON восстановлен вручную")
                return result
        except:
            pass

        return None

def process_document(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Обработка одного документа — выделение сущностей и связей
    БЕЗ нормализации текста
    """

    doc_id = doc.get("doc_id", "unknown")
    print(f"\n📄 Обработка документа: {doc.get('source_file', 'unknown')}")
    print(f"   ID: {doc_id}, язык: {doc.get('language', 'unknown')}")

    # Извлекаем абзацы
    paragraphs = extract_paragraphs(doc)
    print(f"   📊 Найдено абзацев: {len(paragraphs)}")

    if not paragraphs:
        print("   ⚠️ Нет абзацев для обработки")
        return None

    # Разбиваем на батчи
    batches = []
    for i in range(0, len(paragraphs), config.MAX_PARAGRAPHS_PER_BATCH):
        end_idx = min(i + config.MAX_PARAGRAPHS_PER_BATCH, len(paragraphs))
        batches.append((i, paragraphs[i:end_idx]))

    print(f"   📦 Разбито на {len(batches)} батчей")

    # Собираем результаты со всех батчей
    all_dictionaries = []
    all_paragraph_entities = []

    for batch_idx, (start_idx, batch_paragraphs) in enumerate(batches, 1):
        print(f"\n   📦 Батч {batch_idx}/{len(batches)} (абзацы {start_idx}-{start_idx + len(batch_paragraphs) - 1})")

        prompt = create_entity_extraction_prompt(batch_paragraphs, start_idx)
        response = call_openrouter(prompt, "выделение сущностей", doc_id, batch_idx)

        if not response:
            print(f"   ⚠️ Пропускаем батч {batch_idx} (нет ответа от API)")
            continue

        # Извлекаем текст ответа
        try:
            if "choices" not in response or not response["choices"]:
                print(f"   ⚠️ Нет choices в ответе")
                continue

            message = response["choices"][0].get("message", {})
            if "content" not in message:
                print(f"   ⚠️ Нет content в message")
                continue

            result_text = message["content"]

        except Exception as e:
            print(f"   ❌ Ошибка извлечения текста ответа: {e}")
            continue

        # Парсим ответ
        parsed = parse_llm_response(result_text)

        if not parsed:
            print(f"   ⚠️ Не удалось распарсить ответ для батча {batch_idx}")
            continue

        # Сохраняем словарь
        if "dictionary" in parsed and isinstance(parsed["dictionary"], dict):
            all_dictionaries.append(parsed["dictionary"])
            print(f"   ✅ Найдено сущностей: {len(parsed['dictionary'])}")

        # Сохраняем связи абзац-сущность
        if "paragraph_entities" in parsed and isinstance(parsed["paragraph_entities"], list):
            all_paragraph_entities.extend(parsed["paragraph_entities"])
            print(f"   ✅ Обработано абзацев: {len(parsed['paragraph_entities'])}")

        time.sleep(config.DELAY_BETWEEN_REQUESTS)

    # Объединяем все словари
    final_dictionary = {}
    for d in all_dictionaries:
        if isinstance(d, dict):
            final_dictionary.update(d)

    # Сортируем связи по номеру абзаца
    try:
        all_paragraph_entities.sort(key=lambda x: x.get("num", 0))
    except Exception as e:
        print(f"   ⚠️ Ошибка сортировки абзацев: {e}")

    print(f"\n   📚 Всего уникальных сущностей: {len(final_dictionary)}")
    print(f"   📚 Всего абзацев с сущностями: {len(all_paragraph_entities)}")

    if not final_dictionary:
        print("   ❌ Не удалось выделить сущности")
        return None

    # Формируем финальный результат
    result = {
        "doc_id": doc_id,
        "source_file": doc.get("source_file", ""),
        "language": doc.get("language", ""),
        "dictionary": final_dictionary,
        "paragraph_entities": all_paragraph_entities
    }

    return result
