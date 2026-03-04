"""
Модуль для второго прогона: присвоение сущностям онтологических классов
"""

import json
import requests
import os
import time
from typing import Dict, Any
import config


def load_ontology(filepath: str) -> Dict[str, Any]:
    """Загрузка созданной онтологии"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Файл онтологии не найден: {filepath}")
        return None


def create_entity_assignment_prompt(doc: Dict[str, Any], ontology: Dict[str, Any]) -> str:
    """
    Создание промпта для присвоения сущностям онтологических классов
    """

    # Собираем текст документа
    full_text = ""
    for page in doc["pages"][:3]:  # те же страницы, что в первом прогоне
        full_text += page["content"] + "\n"

    if len(full_text) > 10000:
        full_text = full_text[:10000] + "..."

    prompt = f"""
Ты — система нормализации научных статей по физике. Твоя задача — найти в тексте все сущности и присвоить им онтологические классы.

### 📥 Входные данные:
1. **Исходный документ:**
- ID: {doc['doc_id']}
- Файл: {doc['source_file']}
- Язык: {doc['language']}
- Текст:
{full_text}

2. **Созданная онтология:**
{json.dumps(ontology, ensure_ascii=False, indent=2)}

### 🎯 Задача:
1. Проанализируй текст и найди все вхождения физических сущностей.
2. Для каждой найденной сущности:
   - Определи, какому L0 из онтологии она соответствует
   - Если сущность есть в онтологии (прямо или через синонимы) — присвой L0
   - Если сущности нет в онтологии — создай новую запись (расширь онтологию)
3. Сохрани информацию о позиции в тексте и контексте.

### 📌 Правила:
- Учитывай синонимы (L1), близкие термины (L2), общие категории (L3)
- Указывай точные позиции в тексте (start_char, end_char)
- Контекст: до 50 символов до и после сущности

### 📤 Формат вывода (строго JSON):
{{
  "doc_id": {doc['doc_id']},
  "source_file": "{doc['source_file']}",
  "language": "{doc['language']}",
  "pages": [
    {{
      "page_id": 1,
      "paragraphs": [
        {{
          "paragraph_index": 0,
          "original_text": "текст абзаца",
          "entities": [
            {{
              "text": "найденный термин",
              "normalized": "L0_из_онтологии",
              "start_char": 0,
              "end_char": 10,
              "context": "контекст вокруг термина"
            }}
          ]
        }}
      ]
    }}
  ],
  "updated_ontology": {{
    "categories": [
      // обновлённая онтология с новыми сущностями, если они найдены
    ]
  }}
}}
"""
    return prompt


def call_openrouter(prompt: str) -> Dict[str, Any]:
    """Отправка запроса к OpenRouter API"""

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS
    }

    try:
        response = requests.post(
            config.OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка API: {e}")
        return None


def save_assignment(result: Dict[str, Any], doc_id: int):
    """Сохранение результата присвоения классов"""

    output_file = f"{config.ENTITIES_DIR}/entities_{doc_id}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ Результат сохранён: {output_file}")

    return output_file


def process_document(doc: Dict[str, Any], ontology_file: str) -> bool:
    """Обработка одного документа (второй прогон)"""

    print(f"\n📄 Обработка документа: {doc['source_file']}")
    print(f"   ID: {doc['doc_id']}, язык: {doc['language']}")

    # Загружаем онтологию
    ontology = load_ontology(ontology_file)
    if not ontology:
        print("   ❌ Онтология не загружена")
        return False

    # Создаём промпт
    prompt = create_entity_assignment_prompt(doc, ontology)

    # Отправляем запрос
    print("   ⏳ Отправка запроса к OpenRouter...")
    response = call_openrouter(prompt)

    if not response:
        print("   ❌ Не удалось получить ответ")
        return False

    # Извлекаем результат
    try:
        result_text = response["choices"][0]["message"]["content"]
        # Очищаем от markdown-форматирования
        if result_text.startswith("```json"):
            result_text = result_text.replace("```json", "").replace("```", "")
        elif result_text.startswith("```"):
            result_text = result_text.replace("```", "")

        result_json = json.loads(result_text)

        # Добавляем метаданные
        result_json["doc_id"] = doc["doc_id"]
        result_json["source_file"] = doc["source_file"]
        result_json["processing_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Сохраняем результат
        save_assignment(result_json, doc["doc_id"])
        print(f"   ✅ Сущности обработаны успешно")
        return True

    except (KeyError, json.JSONDecodeError) as e:
        print(f"   ❌ Ошибка парсинга ответа: {e}")
        if 'result_text' in locals():
            print(f"   Полученный ответ: {result_text[:200]}...")
        return False