"""
Модуль для обработки документов: выделение сущностей и нормализация
"""

import json
import requests
import time
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
        # Разбиваем по маркерам абзацев
        page_paragraphs = content.split("[PARAGRAPH_END]")

        for para in page_paragraphs:
            # Убираем маркеры страниц и лишние пробелы
            clean_para = para.replace("[PAGE_END]", "").strip()
            # Пропускаем пустые абзацы и абзацы только с формулами/изображениями
            if clean_para and not clean_para.startswith("[FORMULA]") and not clean_para.startswith("[ИЗОБРАЖЕНИЕ]"):
                paragraphs.append(clean_para)

    return paragraphs


def create_entity_extraction_prompt(paragraphs: List[str]) -> str:
    """
    Создание промпта для выделения сущностей из абзацев
    """
    paragraphs_text = "\n\n".join([f"[АБЗАЦ {i + 1}]: {p}" for i, p in enumerate(paragraphs)])

    prompt = f"""Ты — система анализа научных статей. Твоя задача — выделить ключевые смысловые сущности из каждого абзаца и создать словарь соответствий.

### 📥 Входные данные:
Текст, разбитый на абзацы:

{paragraphs_text}

### 🎯 Задача:
1. Для каждого абзаца выдели **ключевые смысловые сущности** (термины, понятия, важные для понимания текста).
2. Создай **единый словарь** всех уникальных сущностей, где для каждой сущности указан её онтологический класс (обобщающая категория).
3. Для каждого абзаца укажи, какие сущности из словаря в нём встречаются.

### 📌 Правила выделения сущностей:
- Сущности должны быть значимыми терминами из области информатики, программирования, IT.
- Примеры сущностей: "база данных", "алгоритм", "нейронная сеть", "шифрование", "пользователь", "сервер", "интерфейс".
- Онтологический класс — это обобщающая категория, к которой относится сущность.
- Примеры классов: "технология", "метод", "объект", "процесс", "субъект", "архитектура", "данные", "программное обеспечение".
- Одна и та же сущность может встречаться в разных абзацах — в словаре она должна быть один раз.

### 📤 Формат вывода (строго JSON):
{{
  "dictionary": {{
    "сущность_1": "онтологический_класс_1",
    "сущность_2": "онтологический_класс_2",
    ...
  }},
  "paragraphs_entities": [
    {{
      "index": 1,
      "entities": ["сущность_1", "сущность_2", ...]
    }},
    ...
  ]
}}

Верни ТОЛЬКО JSON, без пояснений и без markdown."""

    return prompt


def create_normalization_prompt(paragraphs: List[str], dictionary: Dict[str, str]) -> str:
    """
    Создание промпта для нормализации текста (замены сущностей на классы)
    """
    paragraphs_text = "\n\n".join([f"[АБЗАЦ {i + 1}]: {p}" for i, p in enumerate(paragraphs)])

    # Формируем словарь для подстановки
    dict_text = "\n".join([f"  {entity} → {cls}" for entity, cls in dictionary.items()])

    prompt = f"""Ты — система нормализации научных статей. Твоя задача — заменить ключевые сущности в тексте на их онтологические классы.

### 📥 Входные данные:
1. **Словарь соответствий:**
{dict_text}

2. **Исходный текст по абзацам:**
{paragraphs_text}

### 🎯 Задача:
Для каждого абзаца замени все вхождения сущностей из словаря на их онтологические классы.
Сохрани структуру текста, грамматику и смысл. Если сущность встречается в разных формах (падежи, число), приведи класс к соответствующей форме.

### 📤 Формат вывода (строго JSON):
{{
  "normalized_paragraphs": [
    {{
      "index": 1,
      "original": "исходный текст абзаца",
      "normalized": "нормализованный текст абзаца"
    }},
    ...
  ]
}}

Верни ТОЛЬКО JSON, без пояснений и без markdown."""

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
        print(
            f"   📤 Отправка {request_type} запроса (документ {doc_id}{f', часть {batch_num}' if batch_num else ''})...")
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

        return response.json()

    except requests.exceptions.Timeout:
        print("   ❌ Таймаут соединения")
        return None
    except requests.exceptions.ConnectionError:
        print("   ❌ Ошибка соединения")
        return None
    except Exception as e:
        print(f"   ❌ Неизвестная ошибка: {e}")
        return None


def process_document(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Полная обработка одного документа (два прогона)
    Возвращает результат или None в случае ошибки
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

    # Разбиваем на батчи (чтобы не превысить лимиты токенов)
    batches = []
    for i in range(0, len(paragraphs), config.MAX_PARAGRAPHS_PER_BATCH):
        batches.append(paragraphs[i:i + config.MAX_PARAGRAPHS_PER_BATCH])

    print(f"   📦 Разбито на {len(batches)} батчей")

    # ПРОГОН 1: Выделение сущностей для каждого батча
    print("\n🔨 ПРОГОН 1: ВЫДЕЛЕНИЕ СУЩНОСТЕЙ")

    all_dictionaries = []
    all_paragraphs_entities = []

    for batch_idx, batch_paragraphs in enumerate(batches, 1):
        print(f"\n   📦 Батч {batch_idx}/{len(batches)}")

        prompt = create_entity_extraction_prompt(batch_paragraphs)
        response = call_openrouter(prompt, "выделение сущностей", doc_id, batch_idx)

        if not response:
            print(f"   ❌ Ошибка в батче {batch_idx}")
            continue

        try:
            result_text = response["choices"][0]["message"]["content"]
            # Очищаем от markdown
            if result_text.startswith("```json"):
                result_text = result_text.replace("```json", "").replace("```", "")
            elif result_text.startswith("```"):
                result_text = result_text.replace("```", "")

            result = json.loads(result_text.strip())

            # Сохраняем словарь (объединяем с предыдущими)
            if "dictionary" in result:
                all_dictionaries.append(result["dictionary"])

            # Сохраняем сущности абзацев (смещаем индексы)
            if "paragraphs_entities" in result:
                for pe in result["paragraphs_entities"]:
                    pe["global_index"] = pe["index"] + (batch_idx - 1) * config.MAX_PARAGRAPHS_PER_BATCH
                    all_paragraphs_entities.append(pe)

            print(f"   ✅ Батч {batch_idx} обработан")

        except Exception as e:
            print(f"   ❌ Ошибка парсинга результата: {e}")

        # Пауза между запросами
        if batch_idx < len(batches):
            time.sleep(config.DELAY_BETWEEN_REQUESTS)

    # Объединяем все словари
    final_dictionary = {}
    for d in all_dictionaries:
        final_dictionary.update(d)

    print(f"\n   📚 Всего уникальных сущностей: {len(final_dictionary)}")

    if not final_dictionary:
        print("   ❌ Не удалось выделить сущности")
        return None

    # Пауза перед вторым прогоном
    print("\n   ⏳ Пауза перед вторым прогоном...")
    time.sleep(config.DELAY_BETWEEN_REQUESTS * 2)

    # ПРОГОН 2: Нормализация текста
    print("\n🔨 ПРОГОН 2: НОРМАЛИЗАЦИЯ ТЕКСТА")

    all_normalized = []

    for batch_idx, batch_paragraphs in enumerate(batches, 1):
        print(f"\n   📦 Батч {batch_idx}/{len(batches)}")

        prompt = create_normalization_prompt(batch_paragraphs, final_dictionary)
        response = call_openrouter(prompt, "нормализация", doc_id, batch_idx)

        if not response:
            print(f"   ❌ Ошибка в батче {batch_idx}")
            continue

        try:
            result_text = response["choices"][0]["message"]["content"]
            # Очищаем от markdown
            if result_text.startswith("```json"):
                result_text = result_text.replace("```json", "").replace("```", "")
            elif result_text.startswith("```"):
                result_text = result_text.replace("```", "")

            result = json.loads(result_text.strip())

            if "normalized_paragraphs" in result:
                for np in result["normalized_paragraphs"]:
                    np["global_index"] = np["index"] + (batch_idx - 1) * config.MAX_PARAGRAPHS_PER_BATCH
                    all_normalized.append(np)

            print(f"   ✅ Батч {batch_idx} нормализован")

        except Exception as e:
            print(f"   ❌ Ошибка парсинга результата: {e}")

        # Пауза между запросами
        if batch_idx < len(batches):
            time.sleep(config.DELAY_BETWEEN_REQUESTS)

    # Формируем финальный результат
    result = {
        "doc_id": doc_id,
        "source_file": doc.get("source_file", ""),
        "language": doc.get("language", ""),
        "total_paragraphs": len(paragraphs),
        "dictionary": final_dictionary,
        "paragraphs": []
    }

    # Собираем информацию по каждому абзацу
    for para_idx, para_text in enumerate(paragraphs):
        para_info = {
            "index": para_idx,
            "original": para_text,
            "normalized": None,
            "entities": []
        }

        # Ищем нормализованный текст
        for np in all_normalized:
            if np.get("global_index", -1) == para_idx:
                para_info["normalized"] = np.get("normalized", "")
                break

        # Ищем сущности в этом абзаце
        for pe in all_paragraphs_entities:
            if pe.get("global_index", -1) == para_idx:
                para_info["entities"] = pe.get("entities", [])
                break

        result["paragraphs"].append(para_info)

    return result