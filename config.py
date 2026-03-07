"""
Конфигурационный файл для OpenRouter API
"""
import multiprocessing

# Настройки API
OPENROUTER_API_KEY = ""  # ЗАМЕНИТЕ НА СВОЙ КЛЮЧ
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3-vl-30b-a3b-thinking"  # или другая модель

# Настройки обработки
TEMPERATURE = 0.2
MAX_TOKENS_PER_REQUEST = 16000
REQUEST_TIMEOUT = 120
DELAY_BETWEEN_REQUESTS = 2  # секунд между запросами к API

# Многопоточность
CPU_COUNT = multiprocessing.cpu_count()
# Для API лучше ограничить, чтобы не забанили
MAX_WORKERS = min(CPU_COUNT * 2 + 1, 5)  # Не больше 5 потоков для API
print(f"⚙️  CPU: {CPU_COUNT}, MAX_WORKERS: {MAX_WORKERS}")

# Скользящее окно по страницам
PAGES_PER_BATCH = 5  # сколько страниц за раз обрабатываем
CONTEXT_OVERLAP = 2  # сколько предыдущих страниц добавляем как контекст

# Пути к файлам
INPUT_FILE = "physics_1.json"
RESULTS_FILE = "results/processed_documents_physics_1.json"

# Максимальное количество абзацев на один запрос (чтобы не превысить лимиты)
MAX_PARAGRAPHS_PER_BATCH = 1  # Обрабатываем по одному абзацу