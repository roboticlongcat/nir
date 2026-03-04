"""
Основной скрипт для двухпрогонной обработки документов
Поддерживает обработку нескольких документов
"""

import json
import time
import os
from typing import List, Dict, Any
import config
import ontology_builder
import entity_assigner  # импортируем второй модуль

def check_api_key():
    """Проверка наличия API ключа"""
    if config.OPENROUTER_API_KEY == "your-openrouter-api-key":
        print("\n❌ ОШИБКА: Не указан OPENROUTER_API_KEY в config.py")
        print("   Пожалуйста, замените 'your-openrouter-api-key' на ваш реальный ключ")
        return False

    if len(config.OPENROUTER_API_KEY) < 20:
        print("\n⚠️  Предупреждение: API ключ короткий")

    return True

def test_api_connection():
    """Тест подключения к API"""
    print("\n🔍 Тестирование подключения к OpenRouter...")

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    test_payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": "Say 'API is working'"}
        ],
        "max_tokens": 50
    }

    try:
        import requests
        response = requests.post(
            config.OPENROUTER_URL,
            headers=headers,
            json=test_payload,
            timeout=10
        )

        print(f"   Статус: {response.status_code}")

        if response.status_code == 200:
            print("   ✅ Подключение работает!")
            return True
        elif response.status_code == 401:
            print("   ❌ Ошибка авторизации: неверный API ключ")
        elif response.status_code == 429:
            print("   ❌ Превышен лимит запросов")
        else:
            print(f"   ❌ Ошибка: {response.text[:200]}")

        return False

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

def print_stats(stats: Dict[str, Any], start_time: float):
    """Вывод статистики обработки"""
    elapsed = time.time() - start_time

    print("\n" + "="*60)
    print("📊 СТАТИСТИКА ОБРАБОТКИ")
    print("="*60)
    print(f"📑 Всего документов: {stats['total']}")
    print(f"✅ Прогон 1 (онтология): {stats['ontology_success']}/{stats['total']}")
    print(f"✅ Прогон 2 (присвоение): {stats['assignment_success']}/{stats['total']}")
    print(f"❌ Ошибок: {stats['failed']}")
    print(f"⏱️  Время выполнения: {elapsed:.1f} секунд")
    print("="*60)

    if stats['failed_docs']:
        print("\n❌ Документы с ошибками:")
        for i, doc in enumerate(stats['failed_docs'], 1):
            print(f"   {i}. {doc}")

def main():
    """Основная функция"""

    print("="*60)
    print("🔬 ДВУХПРОГОННАЯ ОБРАБОТКА НАУЧНЫХ СТАТЕЙ ПО ФИЗИКЕ")
    print("="*60)

    # Проверка API ключа
    if not check_api_key():
        return

    # Тестируем подключение
    if not test_api_connection():
        print("\n❌ Не удалось подключиться к API")
        return

    # Загрузка входных данных
    print(f"\n📂 Загрузка данных из {config.INPUT_FILE}...")
    data = ontology_builder.load_input_data(config.INPUT_FILE)
    documents = data.get("documents", [])

    # Сколько документов обрабатывать (можно изменить)
    DOCS_TO_PROCESS = 3  # обработаем первые 3 документа
    documents_to_process = documents[:DOCS_TO_PROCESS]

    print(f"📊 Всего документов в файле: {len(documents)}")
    print(f"📊 Будет обработано: {len(documents_to_process)} документов")

    # Статистика
    stats = {
        "total": len(documents_to_process),
        "ontology_success": 0,
        "assignment_success": 0,
        "failed": 0,
        "failed_docs": []
    }

    start_time = time.time()

    # Обрабатываем каждый документ
    for idx, doc in enumerate(documents_to_process, 1):
        print(f"\n{'='*60}")
        print(f"📄 ДОКУМЕНТ {idx}/{len(documents_to_process)}")
        print(f"   ID: {doc['doc_id']}")
        print(f"   Файл: {doc['source_file']}")
        print(f"   Язык: {doc['language']}")
        print(f"   Страниц: {len(doc['pages'])}")
        print(f"{'='*60}")

        doc_success = True

        # ПРОГОН 1: Создание онтологии
        print("\n🔨 ПРОГОН 1: СОЗДАНИЕ ОНТОЛОГИИ")
        success1 = ontology_builder.process_document(doc)

        if success1:
            stats['ontology_success'] += 1
            print(f"   ✅ Онтология создана")

            # Путь к файлу созданной онтологии
            ontology_file = f"{config.ONTOLOGY_DIR}/ontology_{doc['doc_id']}.json"

            # Пауза между запросами
            print("   ⏳ Пауза 3 секунды...")
            time.sleep(3)

            # ПРОГОН 2: Присвоение классов
            print("\n🔨 ПРОГОН 2: ПРИСВОЕНИЕ ОНТОЛОГИЧЕСКИХ КЛАССОВ")
            success2 = entity_assigner.process_document(doc, ontology_file)

            if success2:
                stats['assignment_success'] += 1
                print(f"   ✅ Классы присвоены")
            else:
                doc_success = False
                print(f"   ❌ Ошибка во втором прогоне")
        else:
            doc_success = False
            print(f"   ❌ Ошибка в первом прогоне")

        if not doc_success:
            stats['failed'] += 1
            stats['failed_docs'].append(doc['source_file'])

        # Пауза между документами
        if idx < len(documents_to_process):
            print(f"\n⏳ Пауза 5 секунд перед следующим документом...")
            time.sleep(5)

    # Вывод статистики
    print_stats(stats, start_time)

    print(f"\n📁 Результаты сохранены в папках:")
    print(f"   - Онтологии: {config.ONTOLOGY_DIR}")
    print(f"   - Сущности: {config.ENTITIES_DIR}")
    print(f"   - Отладка: {config.DEBUG_DIR}")

if __name__ == "__main__":
    main()