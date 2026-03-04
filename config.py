"""
Конфигурационный файл для OpenRouter API
"""

# Настройки API
OPENROUTER_API_KEY = ""  # ЗАМЕНИТЕ НА СВОЙ КЛЮЧ
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3-vl-30b-a3b-thinking"  # или другая модель

# Настройки обработки
TEMPERATURE = 0.2
MAX_TOKENS = 12856

# Пути к файлам
INPUT_FILE = "physics_1.json"
RESULTS_DIR = "C:\\Users\Mi\PycharmProjects\PythonProject"
ONTOLOGY_DIR = f"{RESULTS_DIR}/ontology"      # для сохранения созданной онтологии
ENTITIES_DIR = f"{RESULTS_DIR}/entities"      # для выделенных сущностей
NORMALIZED_DIR = f"{RESULTS_DIR}/normalized"  # для нормализованного текста
DEBUG_DIR = f"{RESULTS_DIR}/debug"

# Создаём папки, если их нет
import os
for dir_path in [RESULTS_DIR, ONTOLOGY_DIR, ENTITIES_DIR, NORMALIZED_DIR]:
    os.makedirs(dir_path, exist_ok=True)