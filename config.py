"""
Конфигурационный файл для OpenRouter API
"""

# Настройки API
OPENROUTER_API_KEY = ""  # ЗАМЕНИТЕ НА СВОЙ КЛЮЧ
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3-vl-30b-a3b-thinking"  # или другая модель

# Настройки обработки
TEMPERATURE = 0.2
MAX_TOKENS_PER_REQUEST = 12856
REQUEST_TIMEOUT = 60
DELAY_BETWEEN_REQUESTS = 2  # секунд между запросами к API

# Пути к файлам
INPUT_FILE = "it_1.json"
RESULTS_FILE = "results/processed_documents.json"

# Максимальное количество абзацев на один запрос (чтобы не превысить лимиты)
MAX_PARAGRAPHS_PER_BATCH = 5
