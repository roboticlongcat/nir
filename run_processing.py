"""
Главный скрипт для обработки всех документов
Один запрос на документ — максимальная скорость
"""

import json
import time
import os
from typing import Dict, Any, List
import config
import document_processor

def check_api_key():
    if config.OPENROUTER_API_KEY == "your-openrouter-api-key":
        print("\n❌ ОШИБКА: Не указан OPENROUTER_API_KEY в config.py")
        return False
    return True

def load_results() -> List[Dict[str, Any]]:
    """Загрузка существующих результатов"""
    if not os.path.exists(config.RESULTS_FILE):
        return []

    try:
        with open(config.RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except:
        return []

def save_results(results: List[Dict[str, Any]]):
    """Сохранение результатов"""
    os.makedirs(os.path.dirname(config.RESULTS_FILE), exist_ok=True)
    with open(config.RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Результаты сохранены в {config.RESULTS_FILE}")

def print_summary(processed: int, failed: int, start_time: float):
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print("📊 СВОДКА")
    print("="*60)
    print(f"✅ Успешно: {processed}")
    print(f"❌ Ошибок: {failed}")
    print(f"⏱️  Время: {elapsed:.1f} сек ({elapsed/60:.1f} мин)")
    if processed > 0:
        print(f"   Среднее на документ: {elapsed/processed:.1f} сек")
    print("="*60)

def main():
    print("="*60)
    print("🔬 ОБРАБОТКА НАУЧНЫХ СТАТЕЙ (ОДИН ЗАПРОС НА ДОКУМЕНТ)")
    print("="*60)

    if not check_api_key():
        return

    # Загрузка данных
    print(f"\n📂 Загрузка из {config.INPUT_FILE}...")
    data = document_processor.load_input_data(config.INPUT_FILE)

    if not data:
        return

    documents = data.get("documents", [])
    print(f"📊 Всего документов: {len(documents)}")

    # Загрузка результатов
    existing = load_results()
    processed_ids = {doc.get("doc_id") for doc in existing if doc.get("doc_id")}

    print(f"📊 Уже обработано: {len(processed_ids)}")
    print(f"📊 Осталось: {len(documents) - len(processed_ids)}")

    # Сколько обработать
    try:
        num = int(input("\nСколько документов обработать? (Enter - все): ") or len(documents))
    except:
        num = len(documents)

    if num <= 0:
        return

    # Берём необработанные
    to_process = []
    for doc in documents[:num]:
        if doc.get("doc_id") not in processed_ids:
            to_process.append(doc)

    print(f"📊 Будет обработано: {len(to_process)}")

    if not to_process:
        print("✅ Все уже обработаны")
        return

    # Статистика
    start = time.time()
    processed = 0
    failed = 0
    new_results = []

    # Обрабатываем
    for idx, doc in enumerate(to_process, 1):
        print(f"\n{'='*60}")
        print(f"📄 ДОКУМЕНТ {idx}/{len(to_process)}")
        print(f"   ID: {doc.get('doc_id')}")
        print(f"   Файл: {doc.get('source_file')}")
        print(f"{'='*60}")

        result = document_processor.process_document(doc)

        if result:
            new_results.append(result)
            processed += 1
            print(f"\n✅ Документ {idx} обработан")
        else:
            failed += 1
            print(f"\n❌ Ошибка документа {idx}")

        # Пауза между документами
        if idx < len(to_process):
            print(f"\n⏳ Пауза {config.DELAY_BETWEEN_REQUESTS} сек...")
            time.sleep(config.DELAY_BETWEEN_REQUESTS)

    # Сохраняем
    save_results(existing + new_results)

    # Итог
    print_summary(processed, failed, start)

if __name__ == "__main__":
    main()
