"""
Главный скрипт для обработки всех документов
Многопоточная обработка + скользящее окно по страницам + контекст между батчами
"""

import json
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    except json.JSONDecodeError:
        print(f"⚠️ Файл результатов поврежден, создаем новый")
        return []

def save_results(results: List[Dict[str, Any]]):
    """Сохранение результатов"""
    os.makedirs(os.path.dirname(config.RESULTS_FILE), exist_ok=True)

    # Сохраняем во временный файл, затем переименовываем
    temp_file = config.RESULTS_FILE + ".tmp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, config.RESULTS_FILE)
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

def process_single_document(doc: Dict[str, Any]) -> tuple:
    """
    Обработка одного документа (для параллельного выполнения)
    Возвращает (doc_id, результат или None, имя_файла)
    """
    doc_id = doc.get("doc_id", "unknown")
    filename = doc.get("source_file", "unknown")

    try:
        result = document_processor.process_document(doc)
        return (doc_id, result, filename)
    except Exception as e:
        print(f"\n❌ Критическая ошибка в документе {filename}: {e}")
        return (doc_id, None, filename)

def main():
    print("="*60)
    print("🔬 ОБРАБОТКА НАУЧНЫХ СТАТЕЙ")
    print(f"   Многопоточность: {config.MAX_WORKERS} workers")
    print(f"   Скользящее окно: {config.PAGES_PER_BATCH} стр./{config.CONTEXT_OVERLAP} в контексте")
    print(f"   Контекст между батчами: Да (резюмирующий)")
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
        user_input = input("\nСколько документов обработать? (Enter - все): ").strip()
        num = int(user_input) if user_input else len(documents)
    except ValueError:
        print("⚠️ Неверный ввод, обрабатываем все")
        num = len(documents)

    if num <= 0:
        return

    # Берём необработанные
    to_process = []
    for doc in documents:
        if doc.get("doc_id") not in processed_ids:
            to_process.append(doc)
            if len(to_process) >= num:
                break

    print(f"📊 Будет обработано: {len(to_process)}")

    if not to_process:
        print("✅ Все документы уже обработаны")
        return

    # Статистика
    start = time.time()
    processed = 0
    failed = 0
    new_results = []

    # Многопоточная обработка
    print(f"\n🚀 Запуск {config.MAX_WORKERS} потоков...")

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        # Запускаем все задачи
        future_to_doc = {
            executor.submit(process_single_document, doc): doc
            for doc in to_process
        }

        # Собираем результаты по мере завершения
        for i, future in enumerate(as_completed(future_to_doc), 1):
            doc = future_to_doc[future]
            filename = doc.get("source_file", "unknown")

            try:
                doc_id, result, filename = future.result(timeout=300)  # 5 минут таймаут

                if result:
                    new_results.append(result)
                    processed += 1
                    print(f"\n✅ [{i}/{len(to_process)}] {filename} — ГОТОВ")
                else:
                    failed += 1
                    print(f"\n❌ [{i}/{len(to_process)}] {filename} — ОШИБКА")

            except Exception as e:
                failed += 1
                print(f"\n❌ [{i}/{len(to_process)}] {filename} — ОШИБКА: {e}")

    # Сохраняем
    save_results(existing + new_results)

    # Итог
    print_summary(processed, failed, start)

if __name__ == "__main__":
    main()