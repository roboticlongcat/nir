"""
Главный скрипт для обработки всех документов из входного файла
Результаты сохраняются в единый JSON-файл
"""

import json
import time
import os
from typing import Dict, Any, List
import config
import document_processor


def check_api_key():
    """Проверка наличия API ключа"""
    if config.OPENROUTER_API_KEY == "your-openrouter-api-key":
        print("\n❌ ОШИБКА: Не указан OPENROUTER_API_KEY в config.py")
        print("   Пожалуйста, замените 'your-openrouter-api-key' на ваш реальный ключ")
        print("   Получить ключ можно на https://openrouter.ai/")
        return False
    return True


def load_results() -> Dict[str, Any]:
    """Загрузка существующих результатов (если есть)"""
    try:
        if os.path.exists(config.RESULTS_FILE):
            with open(config.RESULTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass

    return {
        "metadata": {
            "total_documents": 0,
            "processed_documents": 0,
            "failed_documents": 0,
            "processing_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_run": None
        },
        "documents": []
    }


def save_results(results: Dict[str, Any]):
    """Сохранение результатов в файл"""
    # Создаём папку results, если её нет
    os.makedirs(os.path.dirname(config.RESULTS_FILE), exist_ok=True)

    results["metadata"]["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")

    with open(config.RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Результаты сохранены в {config.RESULTS_FILE}")


def print_summary(results: Dict[str, Any], start_time: float):
    """Вывод сводки по обработке"""
    elapsed = time.time() - start_time
    meta = results["metadata"]

    print("\n" + "=" * 60)
    print("📊 СВОДКА ПО ОБРАБОТКЕ")
    print("=" * 60)
    print(f"📑 Всего документов в файле: {meta['total_documents']}")
    print(f"✅ Успешно обработано: {meta['processed_documents']}")
    print(f"❌ Ошибок: {meta['failed_documents']}")
    print(f"⏱️  Время выполнения: {elapsed:.1f} секунд")
    if meta['processed_documents'] > 0:
        print(f"   Среднее время на документ: {elapsed / meta['processed_documents']:.1f} сек")
    print("=" * 60)


def main():
    """Основная функция"""

    print("=" * 60)
    print("🔬 ОБРАБОТКА НАУЧНЫХ СТАТЕЙ (IT-ТЕМАТИКА)")
    print("=" * 60)

    # Проверка API ключа
    if not check_api_key():
        return

    # Загрузка входных данных
    print(f"\n📂 Загрузка данных из {config.INPUT_FILE}...")
    data = document_processor.load_input_data(config.INPUT_FILE)

    if not data:
        print("❌ Не удалось загрузить входные данные")
        return

    documents = data.get("documents", [])
    print(f"📊 Всего документов в файле: {len(documents)}")

    # Загрузка существующих результатов
    results = load_results()
    results["metadata"]["total_documents"] = len(documents)

    # Определяем, какие документы уже обработаны
    processed_ids = {doc.get("doc_id") for doc in results["documents"]}

    print(f"📊 Уже обработано: {len(processed_ids)} документов")
    print(f"📊 Осталось обработать: {len(documents) - len(processed_ids)} документов")

    # Спросить, сколько документов обработать
    print("\n⚙️ Настройки обработки:")
    print(f"   Модель: {config.OPENROUTER_MODEL}")
    print(f"   Абзацев за запрос: {config.MAX_PARAGRAPHS_PER_BATCH}")

    try:
        num_to_process = int(
            input("\nСколько документов обработать? (0 - пропустить, Enter - все): ") or len(documents))
    except ValueError:
        num_to_process = len(documents)

    if num_to_process <= 0:
        print("❌ Обработка отменена")
        return

    # Берем только необработанные документы
    docs_to_process = []
    for doc in documents[:num_to_process]:
        if doc.get("doc_id") not in processed_ids:
            docs_to_process.append(doc)

    print(f"📊 Будет обработано: {len(docs_to_process)} новых документов")

    if not docs_to_process:
        print("✅ Все выбранные документы уже обработаны")
        print_summary(results, time.time())
        save_results(results)
        return

    # Статистика
    start_time = time.time()
    processed = 0
    failed = 0

    # Обрабатываем документы
    for idx, doc in enumerate(docs_to_process, 1):
        print(f"\n{'=' * 60}")
        print(f"📄 ДОКУМЕНТ {idx}/{len(docs_to_process)}")
        print(f"   ID: {doc.get('doc_id', 'unknown')}")
        print(f"   Файл: {doc.get('source_file', 'unknown')}")
        print(f"   Язык: {doc.get('language', 'unknown')}")
        print(f"{'=' * 60}")

        # Обработка документа
        result = document_processor.process_document(doc)

        if result:
            results["documents"].append(result)
            processed += 1
            print(f"\n✅ Документ {idx} обработан успешно")
        else:
            failed += 1
            print(f"\n❌ Ошибка обработки документа {idx}")

        # Пауза между документами
        if idx < len(docs_to_process):
            wait_time = config.DELAY_BETWEEN_REQUESTS * 3
            print(f"\n⏳ Пауза {wait_time} секунд перед следующим документом...")
            time.sleep(wait_time)

    # Обновляем метаданные
    results["metadata"]["processed_documents"] = len(results["documents"])
    results["metadata"]["failed_documents"] = failed

    # Сохраняем результаты
    save_results(results)

    # Вывод сводки
    print_summary(results, start_time)


if __name__ == "__main__":
    main()