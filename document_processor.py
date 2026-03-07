"""
Модуль для обработки документов: выделение сущностей
Со скользящим окном по страницам и контекстом между батчами
"""

import json
import requests
import time
import re
import os
from typing import Dict, List, Any, Optional, Tuple
import config

# Создаём папку для отладки
DEBUG_DIR = "debug_responses"
os.makedirs(DEBUG_DIR, exist_ok=True)

class BatchContextManager:
    """Управляет контекстом между батчами с резюмированием"""

    def __init__(self, max_summaries=3, max_entities_per_summary=15):
        self.max_summaries = max_summaries
        self.max_entities_per_summary = max_entities_per_summary
        self.summaries = []  # Список резюме по батчам
        self.all_entities = {}  # Все сущности из документа
        self.entity_frequency = {}  # Частота встречаемости

    def update(self, batch_result: Dict[str, Any], batch_pages: str, batch_idx: int):
        """Обновляет контекст на основе результатов батча"""
        if not batch_result:
            return

        # Обновляем частоту и словарь сущностей
        if "dictionary" in batch_result:
            for entity, entity_class in batch_result["dictionary"].items():
                self.entity_frequency[entity] = self.entity_frequency.get(entity, 0) + 1
                self.all_entities[entity] = entity_class  # Перезаписываем класс (может уточняться)

        # Создаём резюме батча
        summary = self._create_batch_summary(batch_result, batch_pages, batch_idx)
        self.summaries.append(summary)

        # Оставляем только последние N резюме
        if len(self.summaries) > self.max_summaries:
            self.summaries = self.summaries[-self.max_summaries:]

    def _create_batch_summary(self, batch_result: Dict[str, Any], batch_pages: str, batch_idx: int) -> str:
        """Создает краткое резюме результатов батча"""
        summary_lines = [f"--- БАТЧ {batch_idx}: Страницы {batch_pages} ---"]

        # Самые частотные/важные сущности в этом батче
        if "dictionary" in batch_result and batch_result["dictionary"]:
            # Сортируем по частоте (если есть данные) или просто берем первые
            entities = list(batch_result["dictionary"].items())

            # Если есть информация о частоте из параграфов, используем её
            entity_in_paragraphs = {}
            if "paragraph_entities" in batch_result:
                for para in batch_result["paragraph_entities"]:
                    for entity in para.get("entities", []):
                        entity_in_paragraphs[entity] = entity_in_paragraphs.get(entity, 0) + 1

            # Сортируем по частоте встречаемости в параграфах
            if entity_in_paragraphs:
                entities.sort(key=lambda x: entity_in_paragraphs.get(x[0], 0), reverse=True)

            # Берём топ-N
            top_entities = entities[:self.max_entities_per_summary]
            entities_str = ", ".join([f"'{e}' ({c})" for e, c in top_entities])
            summary_lines.append(f"Ключевые сущности: {entities_str}")

            if len(entities) > self.max_entities_per_summary:
                summary_lines.append(f"И ещё {len(entities) - self.max_entities_per_summary} сущностей")

        # Количество обработанных абзацев
        if "paragraph_entities" in batch_result:
            summary_lines.append(f"Абзацев в батче: {len(batch_result['paragraph_entities'])}")

        return "\n".join(summary_lines)

    def get_context_prompt(self) -> str:
        """Формирует промпт с контекстом из предыдущих батчей"""
        if not self.summaries:
            return ""

        context_parts = ["### 📋 КОНТЕКСТ ПРЕДЫДУЩИХ БАТЧЕЙ:"]

        # Добавляем резюме батчей
        for summary in self.summaries[:-1]:  # Все кроме текущего (он ещё не обработан)
            context_parts.append(summary)

        # Добавляем общую статистику для справки
        if self.all_entities:
            context_parts.append(f"\n--- ОБЩАЯ СТАТИСТИКА ---")
            context_parts.append(f"Всего уникальных сущностей в документе: {len(self.all_entities)}")

            # Топ-5 самых частотных сущностей
            top_freq = sorted(self.entity_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_freq:
                freq_str = ", ".join([f"'{e}' ({f} раз)" for e, f in top_freq])
                context_parts.append(f"Наиболее частотные: {freq_str}")

        return "\n".join(context_parts)

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

def extract_page_text(page: Dict[str, Any]) -> str:
    """Извлечение текста из одной страницы"""
    content = page.get("content", "")
    if not isinstance(content, str):
        return ""

    # Убираем маркеры, но сохраняем текст
    clean_text = content.replace("[PARAGRAPH_END]", "\n\n").replace("[PAGE_END]", "\n\n")
    clean_text = re.sub(r'\[FORMULA\]', '', clean_text)
    clean_text = re.sub(r'\[ИЗОБРАЖЕНИЕ\]', '', clean_text)

    return clean_text.strip()

def estimate_tokens(text: str) -> int:
    """Грубая оценка количества токенов (для русского языка 3 символа = 1 токен)"""
    return len(text) // 3

def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """Обрезает текст до примерного лимита токенов"""
    if not text:
        return text

    chars_per_token = 3
    max_chars = max_tokens * chars_per_token

    if len(text) <= max_chars:
        return text

    # Оставляем конец текста (более релевантный для контекста)
    return "..." + text[-(max_chars-3):]

def create_batches_with_context(doc: Dict[str, Any]) -> List[Tuple[int, int, str, str]]:
    """
    Создание батчей со скользящим окном
    Возвращает список кортежей (start_page, end_page, контекст_страниц, текст_для_обработки)
    """
    pages = doc.get("pages", [])
    if not pages:
        return []

    batches = []
    total_pages = len(pages)

    for start_idx in range(0, total_pages, config.PAGES_PER_BATCH):
        end_idx = min(start_idx + config.PAGES_PER_BATCH, total_pages)

        # Контекст — предыдущие страницы (для локального понимания)
        context_start = max(0, start_idx - config.CONTEXT_OVERLAP)
        context_text = ""
        for i in range(context_start, start_idx):
            page_text = extract_page_text(pages[i])
            if page_text:  # Добавляем только непустые страницы
                context_text += f"[КОНТЕКСТ: СТРАНИЦА {i+1}]\n{page_text}\n\n"

        # Текст для обработки — текущие страницы
        main_text = ""
        for i in range(start_idx, end_idx):
            page_text = extract_page_text(pages[i])
            if page_text:  # Добавляем только непустые страницы
                main_text += f"[СТРАНИЦА {i+1}]\n{page_text}\n\n"

        # Проверяем размер
        estimated_tokens = estimate_tokens(context_text + main_text)
        if estimated_tokens > config.MAX_TOKENS_PER_REQUEST * 0.8:
            print(f"   ⚠️ Батч {start_idx+1}-{end_idx} может быть большим: ~{estimated_tokens} токенов")

        batches.append((start_idx, end_idx, context_text, main_text))

    return batches

def get_entity_extraction_instructions() -> str:
    """Возвращает инструкции по выделению сущностей"""
    return """
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
- Параметры и формулы ("(3)", "γ", "x_i") — это не слова

### 📌 ПРАВИЛА ВЫДЕЛЕНИЯ КАНОНИЧЕСКОЙ ФОРМЫ:

1. **Если удаление слова не меняет объект — слово не включается.**
   ✅ "компания Метаграф" → сущность "Метаграф"
   ✅ "корпорация Microsoft" → сущность "Microsoft"

2. **Если оба компонента обязательны — сохраняем полностью.**
   ✅ "интеграл Ито" — полное название
   ✅ "метод конечных элементов" — полное название

3. **Полные официальные названия — единая сущность.**
   ✅ "Московский Государственный Технический Университет"

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
"""

def create_entity_extraction_prompt(context: str, main_text: str,
                                   batch_context: str,
                                   start_page: int, end_page: int) -> str:
    """
    Создание промпта для выделения сущностей с контекстом
    """
    prompt = f"""Ты — система анализа научных статей. Твоя задача — выделить ключевые смысловые сущности из указанных страниц, используя контекст.

### 📥 КОНТЕКСТ ПРЕДЫДУЩИХ СТРАНИЦ:
{context if context else "(нет контекста страниц)"}

{batch_context}

### 📥 ТЕКСТ ДЛЯ ОБРАБОТКИ (страницы {start_page+1}-{end_page}):
{main_text}

### 🎯 Задача:
1. Проанализируй текст на страницах {start_page+1}-{end_page} и выдели **все ключевые смысловые сущности**.
2. Для каждой уникальной сущности определи её **онтологический класс**.
3. Верни **словарь всех сущностей** с их классами.
4. Для каждого абзаца укажи список сущностей, которые в нём встречаются.

ВАЖНО: 
- Используй контекст для понимания терминов, но выделяй сущности ТОЛЬКО из основного текста
- Сохраняй согласованность с ранее выделенными сущностями
- Не дублируй сущности (используй единую форму)

{get_entity_extraction_instructions()}

### 📤 Формат вывода (строго JSON):
{{
  "dictionary": {{
    "сущность_1": "класс_1",
    "сущность_2": "класс_2"
  }},
  "paragraph_entities": [
    {{
      "num": 0,  // Глобальный номер абзаца
      "entities": ["сущность_1", "сущность_2"]
    }},
    ...
  ]
}}

ВАЖНО: Верни ТОЛЬКО JSON, без пояснений, без markdown. Номера страниц будут добавлены автоматически пост-обработкой."""

    return prompt

def call_openrouter(prompt: str, doc_id: int, batch_info: str) -> Optional[Dict[str, Any]]:
    """Запрос к OpenRouter API"""

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

    # Сохраняем промпт для отладки
    debug_file = os.path.join(DEBUG_DIR, f"prompt_doc{doc_id}_{batch_info.replace(' ', '_')}.txt")
    with open(debug_file, 'w', encoding='utf-8') as f:
        f.write(prompt[:2000])  # Сохраняем начало промпта

    try:
        print(f"   📤 {batch_info}")
        response = requests.post(
            config.OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=config.REQUEST_TIMEOUT
        )

        print(f"   📥 Статус: {response.status_code}")

        if response.status_code != 200:
            if response.text:
                print(f"   Ответ: {response.text[:500]}")
            return None

        return response.json()

    except requests.exceptions.Timeout:
        print(f"   ❌ Таймаут запроса")
        return None
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

def clean_json_response(text: Any) -> str:
    """Очистка ответа от LLM"""
    if not isinstance(text, str):
        return "{}"

    # Убираем markdown
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)

    # Ищем JSON
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace+1]

    return text.strip()

def validate_llm_response(parsed: Dict[str, Any]) -> bool:
    """Проверяет корректность структуры ответа от LLM"""
    if not isinstance(parsed, dict):
        return False

    # Проверяем наличие обязательных полей
    if "dictionary" not in parsed or not isinstance(parsed["dictionary"], dict):
        return False

    if "paragraph_entities" not in parsed or not isinstance(parsed["paragraph_entities"], list):
        return False

    # Проверяем структуру paragraph_entities
    for item in parsed["paragraph_entities"]:
        if not isinstance(item, dict):
            return False
        if "num" not in item or not isinstance(item["num"], int):
            return False
        if "entities" not in item or not isinstance(item["entities"], list):
            return False

    return True

def parse_llm_response(response_text: Any) -> Optional[Dict[str, Any]]:
    """Парсинг ответа от LLM"""
    if not isinstance(response_text, str):
        return None

    cleaned = clean_json_response(response_text)

    try:
        parsed = json.loads(cleaned)
        if validate_llm_response(parsed):
            return parsed
        else:
            print(f"   ⚠️ Неверная структура ответа")
            return None
    except json.JSONDecodeError:
        return None

def process_document_batch(doc_id: int, start_page: int, end_page: int,
                          context: str, main_text: str,
                          batch_context: str,
                          global_paragraph_offset: int) -> Optional[Dict[str, Any]]:
    """
    Обработка одного батча страниц
    """
    prompt = create_entity_extraction_prompt(context, main_text, batch_context, start_page, end_page)
    batch_info = f"страницы {start_page+1}-{end_page}"

    response = call_openrouter(prompt, doc_id, batch_info)

    if not response:
        return None

    try:
        result_text = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print(f"   ❌ Неверный формат ответа API: {e}")
        return None

    parsed = parse_llm_response(result_text)

    if not parsed:
        return None

    # Сдвигаем номера абзацев с учётом глобального смещения
    if "paragraph_entities" in parsed:
        for item in parsed["paragraph_entities"]:
            if "num" in item:
                item["num"] += global_paragraph_offset

    return parsed

def count_paragraphs_in_pages(doc: Dict[str, Any], page_indices: List[int]) -> int:
    """Подсчёт количества абзацев в указанных страницах"""
    count = 0
    pages = doc.get("pages", [])

    for idx in page_indices:
        if idx < len(pages):
            content = pages[idx].get("content", "")
            if isinstance(content, str) and content.strip():
                # Считаем абзацы, только если есть контент
                count += content.count("[PARAGRAPH_END]") + 1

    return count


def add_page_info(result: Dict[str, Any], original_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Добавляет информацию о страницах с привязкой сущностей к страницам
    """
    pages = original_doc.get("pages", [])
    paragraphs = result.get("paragraph_entities", [])

    # Создаем маппинг абзац -> страница
    paragraph_to_page = {}
    global_para_idx = 0

    for page_idx, page in enumerate(pages):
        content = page.get("content", "")
        if not isinstance(content, str) or not content.strip():
            num_paragraphs = 0
        else:
            num_paragraphs = content.count("[PARAGRAPH_END]") + 1

        # Запоминаем, какой странице принадлежат абзацы
        for i in range(num_paragraphs):
            paragraph_to_page[global_para_idx + i] = page_idx + 1  # +1 для читаемости

        global_para_idx += num_paragraphs

    # Добавляем номер страницы к каждому абзацу
    enhanced_paragraphs = []
    for para in paragraphs:
        para_num = para.get("num")
        enhanced_para = para.copy()
        enhanced_para["page"] = paragraph_to_page.get(para_num, 0)
        enhanced_paragraphs.append(enhanced_para)

    # Заменяем в результате
    result["paragraph_entities"] = enhanced_paragraphs

    # Добавляем сводку по страницам (как было)
    pages_info = []
    global_para_idx = 0

    for page_idx, page in enumerate(pages):
        content = page.get("content", "")
        if not isinstance(content, str) or not content.strip():
            num_paragraphs = 0
        else:
            num_paragraphs = content.count("[PARAGRAPH_END]") + 1

        if num_paragraphs > 0:
            page_paragraphs = enhanced_paragraphs[global_para_idx:global_para_idx + num_paragraphs]

            # Сущности на этой странице
            page_entities = set()
            for para in page_paragraphs:
                page_entities.update(para.get("entities", []))

            page_dict = {}
            for entity in page_entities:
                if entity in result["dictionary"]:
                    page_dict[entity] = result["dictionary"][entity]

            pages_info.append({
                "page_num": page_idx + 1,
                "page_dictionary": page_dict,
                "entities_count": len(page_dict)  # Добавляем для удобства
            })

            global_para_idx += num_paragraphs
        else:
            pages_info.append({
                "page_num": page_idx + 1,
                "page_dictionary": {},
                "entities_count": 0
            })

    result["pages"] = pages_info
    result["total_pages"] = len(pages)  # Добавляем общее количество страниц

    return result

def process_document(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Обработка одного документа со скользящим окном по страницам и контекстом между батчами
    """

    doc_id = doc.get("doc_id", "unknown")
    print(f"\n📄 Обработка: {doc.get('source_file', 'unknown')}")
    print(f"   ID: {doc_id}")

    pages = doc.get("pages", [])
    if not pages:
        print("   ⚠️ Нет страниц")
        return None

    print(f"   📊 Всего страниц: {len(pages)}")

    # Создаём батчи со скользящим окном
    batches = create_batches_with_context(doc)
    print(f"   📦 Батчей: {len(batches)}")

    # Инициализируем менеджер контекста
    context_manager = BatchContextManager()

    # Результаты
    all_dictionaries = []
    all_paragraph_entities = []
    global_paragraph_num = 0

    # Обрабатываем батчи последовательно
    for batch_idx, (start_page, end_page, context, main_text) in enumerate(batches, 1):
        print(f"\n   🔨 Батч {batch_idx}/{len(batches)} (страницы {start_page+1}-{end_page})")

        # Получаем контекст из предыдущих батчей
        batch_context = context_manager.get_context_prompt()

        result = process_document_batch(
            doc_id, start_page, end_page,
            context, main_text,
            batch_context,
            global_paragraph_num
        )

        # Подсчитываем абзацы в текущем батче (даже если результат None, для корректного смещения)
        page_indices = list(range(start_page, end_page))
        paragraphs_in_batch = count_paragraphs_in_pages(doc, page_indices)

        if result:
            if "dictionary" in result:
                all_dictionaries.append(result["dictionary"])
                print(f"   ✅ Найдено сущностей: {len(result['dictionary'])}")

            if "paragraph_entities" in result:
                all_paragraph_entities.extend(result["paragraph_entities"])
                print(f"   ✅ Обработано абзацев: {len(result['paragraph_entities'])}")

            # Обновляем контекст менеджер с результатами
            batch_pages_str = f"{start_page+1}-{end_page}"
            context_manager.update(result, batch_pages_str, batch_idx)
        else:
            print(f"   ⚠️ Батч не обработан, пропускаем")

        # Обновляем глобальный счётчик абзацев (всегда, даже если батч не обработан)
        global_paragraph_num += paragraphs_in_batch

        # Пауза между батчами
        if batch_idx < len(batches):
            time.sleep(config.DELAY_BETWEEN_REQUESTS)

    # Объединяем словари (приоритет у более поздних батчей)
    final_dictionary = {}
    for d in all_dictionaries:
        final_dictionary.update(d)

    print(f"\n   📚 Всего уникальных сущностей: {len(final_dictionary)}")
    print(f"   📚 Всего абзацев с сущностями: {len(all_paragraph_entities)}")

    if not final_dictionary:
        print("   ❌ Нет сущностей")
        return None

    # Формируем базовый результат
    result = {
        "doc_id": doc_id,
        "source_file": doc.get("source_file", ""),
        "language": doc.get("language", ""),
        "dictionary": final_dictionary,
        "paragraph_entities": all_paragraph_entities
    }

    # Добавляем информацию о страницах
    result = add_page_info(result, doc)

    return result