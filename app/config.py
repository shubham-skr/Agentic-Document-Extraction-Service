import os
from pathlib import Path

class Settings:
    llm_base_url = os.getenv('LLM_BASE_URL', 'https://openrouter.ai/api/v1').rstrip('/')
    llm_api_key = os.getenv('LLM_API_KEY', '')
    fast_model = os.getenv('FAST_MODEL', 'google/gemini-3.8-flash')
    strong_model = os.getenv('STRONG_MODEL', 'google/gemini-3.1-pro-preview')
    vision_model = os.getenv('VISION_MODEL', 'z-ai/glm-5.3-flash')
    max_workers = int(os.getenv('MAX_WORKERS', '4'))
    max_llm_concurrency = int(os.getenv('MAX_LLM_CONCURRENCY', '3'))
    max_upload_mb = int(os.getenv('MAX_UPLOAD_MB', '50'))
    database_path = os.getenv('DATABASE_PATH', './data/jobs.sqlite3')
    upload_dir = os.getenv('UPLOAD_DIR', './data/uploads')
    output_dir = os.getenv('OUTPUT_DIR', './outputs')
    ocr_dpi = int(os.getenv('OCR_DPI', '110'))
    ocr_lang = os.getenv('OCR_LANG', 'eng')
    log_level = os.getenv('LOG_LEVEL', 'INFO')

settings = Settings()
for p in (settings.database_path, settings.upload_dir, settings.output_dir):
    Path(p).parent.mkdir(parents=True, exist_ok=True) if p == settings.database_path else Path(p).mkdir(parents=True, exist_ok=True)
