"""
Модуль для первого прогона: выделение сущностей и создание онтологии
"""

import json
import requests
import os
import time
from typing import Dict, Any, List, Optional
import config

def load_input_data(filepath: str) -> Dict[str, Any]:
    """Загрузка входного JSON-файла"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Файл не найден: {filepath}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        exit(1)

def create_ontology_prompt(doc: Dict[str, Any]) -> str:
    """
    Создание промпта для выделения сущностей и построения онтологии
    """

    # Собираем текст документа (первые 2 страницы для теста)
    full_text = ""
    pages_used = 0
    for page in doc["pages"][:2]:  # ограничиваем 2 страницами
        full_text += page["content"] + "\n"
        pages_used += 1

    # Обрезаем, если слишком длинно
    if len(full_text) > 3000:
        full_text = full_text[:3000] + "..."

    prompt = f"""Ты — система анализа научных статей по физике. Твоя задача — выделить ключевые физические сущности и создать для них онтологию.

### 📥 Входные данные:
Документ:
- ID: {doc['doc_id']}
- Файл: {doc['source_file']}
- Язык: {doc['language']}
- Текст (первые {pages_used} страниц):
{full_text}

### 🎯 Задача:
1. Проанализируй текст и выдели **все ключевые физические сущности** (термины).
2. Для каждой уникальной сущности создай онтологическую запись:
   - L0: каноническая форма (основной термин)
   - L1: синонимы (2-3 варианта)
   - L2: близкие по смыслу термины (2-3 варианта)
   - L3: более общие категории (1-2 варианта)
   - L4: атрибуты, свойства, связанные понятия (1-2 варианта)

### 📌 Правила:
- Сущности должны быть физическими терминами:
  * физические величины (скорость, масса, энергия)
  * физические объекты (атом, электрон, кристалл)
  * физические явления (дифракция, резонанс)
  * физические процессы (испарение, диффузия)
  * материалы и среды (диэлектрик, плазма)
  * приборы и оборудование (лазер, спектрометр)
  * законы и принципы (закон Ньютона)
  * единицы измерения (герц, джоуль)

### 📤 Формат вывода (строго JSON, без markdown-разметки):
{{
  "doc_id": {doc['doc_id']},
  "source_file": "{doc['source_file']}",
  "language": "{doc['language']}",
  "ontology": {{
    "entities": [
      {{
        "L0": "каноническая форма",
        "L1": ["синоним1", "синоним2"],
        "L2": ["близкий1", "близкий2"],
        "L3": ["общая_категория"],
        "L4": ["атрибут1", "атрибут2"]
      }}
    ]
  }}
}}

Верни ТОЛЬКО JSON, без пояснений и без markdown."""

    return prompt

def call_openrouter(prompt: str, doc_id: int) -> Optional[Dict[str, Any]]:
    """Отправка запроса к OpenRouter API с диагностикой"""

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Physics Ontology Builder"
    }

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS
    }

    # Сохраняем запрос для отладки
    debug_file = f"{config.DEBUG_DIR}/request_{doc_id}.json"
    try:
        with open(debug_file, 'w', encoding='utf-8') as f:
            json.dump({
                "headers": {k: v for k, v in headers.items() if k != "Authorization"},
                "payload": payload
            }, f, ensure_ascii=False, indent=2)
    except:
        pass

    try:
        print(f"   📤 Отправка запроса к {config.OPENROUTER_MODEL}...")
        response = requests.post(
            config.OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=60
        )

        # Сохраняем сырой ответ для отладки
        raw_response_file = f"{config.DEBUG_DIR}/raw_response_{doc_id}.html"
        try:
            with open(raw_response_file, 'w', encoding='utf-8') as f:
                f.write(response.text[:2000])
        except:
            pass

        print(f"   📥 Статус ответа: {response.status_code}")

        if response.status_code != 200:
            print(f"   ❌ Ошибка HTTP {response.status_code}")
            print(f"   Ответ: {response.text[:200]}")
            return None

        # Пробуем распарсить JSON
        try:
            return response.json()
        except json.JSONDecodeError as e:
            print(f"   ❌ Ошибка парсинга JSON: {e}")
            print(f"   Первые 200 символов ответа: {response.text[:200]}")
            return None

    except requests.exceptions.Timeout:
        print("   ❌ Таймаут соединения")
        return None
    except requests.exceptions.ConnectionError:
        print("   ❌ Ошибка соединения")
        return None
    except Exception as e:
        print(f"   ❌ Неизвестная ошибка: {e}")
        return None

def save_ontology(result: Dict[str, Any], doc_id: int) -> str:
    """Сохранение созданной онтологии в файл"""

    output_file = f"{config.ONTOLOGY_DIR}/ontology_{doc_id}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Онтология сохранена: {output_file}")

    return output_file

def process_document(doc: Dict[str, Any]) -> bool:
    """
    Обработка одного документа (первый прогон)
    Это основная функция, которую вызывает main.py
    """

    print(f"\n📄 Обработка документа: {doc['source_file']}")
    print(f"   ID: {doc['doc_id']}, язык: {doc['language']}")
    print(f"   Всего страниц: {len(doc['pages'])}")

    # Создаём промпт
    prompt = create_ontology_prompt(doc)

    # Отправляем запрос
    response = call_openrouter(prompt, doc["doc_id"])

    if not response:
        print("   ❌ Не удалось получить ответ от API")
        return False

    # Проверяем структуру ответа
    try:
        if "choices" not in response:
            print(f"   ❌ Некорректный ответ API: нет поля 'choices'")
            print(f"   Структура ответа: {list(response.keys())}")
            return False

        if not response["choices"]:
            print(f"   ❌ Пустой массив choices")
            return False

        message = response["choices"][0].get("message", {})
        if "content" not in message:
            print(f"   ❌ Нет поля content в message")
            return False

        result_text = message["content"]

        # Сохраняем сырой ответ для отладки
        raw_file = f"{config.DEBUG_DIR}/raw_result_{doc['doc_id']}.txt"
        try:
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(result_text)
        except:
            pass

        # Очищаем от markdown-форматирования
        if result_text.startswith("```json"):
            result_text = result_text.replace("```json", "").replace("```", "")
        elif result_text.startswith("```"):
            result_text = result_text.replace("```", "")

        result_text = result_text.strip()

        # Пробуем распарсить JSON
        try:
            result_json = json.loads(result_text)
        except json.JSONDecodeError as e:
            print(f"   ❌ Ошибка парсинга JSON результата: {e}")
            print(f"   Первые 200 символов: {result_text[:200]}")
            return False

        # Добавляем метаданные
        result_json["doc_id"] = doc["doc_id"]
        result_json["source_file"] = doc["source_file"]
        result_json["processing_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Сохраняем результат
        save_ontology(result_json, doc["doc_id"])
        print(f"   ✅ Онтология создана успешно")
        return True

    except Exception as e:
        print(f"   ❌ Ошибка обработки ответа: {e}")
        import traceback
        traceback.print_exc()
        return False