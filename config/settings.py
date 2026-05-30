from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM Provider: "deepseek" | "lmstudio"
    llm_provider: str = "lmstudio"

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_main_model: str = "deepseek-v4-pro"
    deepseek_social_model: str = "deepseek-v4-flash"
    deepseek_main_thinking: bool = True  # v4-pro uses thinking for player-facing quality

    # LM Studio
    lmstudio_base_url: str = "http://192.168.50.223:1234"
    lmstudio_model: str = "qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive"
    lmstudio_social_model: str = "qwen3.5-4b-uncensored-hauhaucs-aggressive"

    # Embedding (for vector memory/RAG)
    # Uses llm_provider's base URL by default; override with EMBEDDING_BASE_URL
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_dim: int = 768

    # Database
    database_path: str = "data/city_town.db"
    chromadb_path: str = "data/chromadb"

    # Game
    game_speed_multiplier: int = 15  # 1 real second = 15 game seconds

    # Logging
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Admin
    admin_enabled: bool = False

    # LLM Gateway
    llm_gateway_max_concurrent: int = 8
    llm_gateway_circuit_threshold: int = 5
    llm_gateway_circuit_recovery: float = 30.0
    llm_gateway_retry_max: int = 3
    llm_gateway_retry_base_delay: float = 1.0
    llm_gateway_request_timeout: float = 60.0  # DeepSeek <5s, but keep headroom

    # TTS Gateway
    tts_enabled: bool = True
    tts_python_path: str = "/Users/lanboo/lanbooassistent/mlx_audio/bin/python"
    tts_model_path: str = "/Users/lanboo/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-Base-bf16/snapshots/a6eb4f68e4b056f1215157bb696209bc82a6db48"
    tts_narrator_model_path: str = "/Users/lanboo/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16/snapshots/7d3824abff87e49756bb0f83fb5411de75d160c4"
    tts_narrator_instruct: str = "标准女声，吐字清晰，语调自然，播音员风格"
    tts_voice_refs_dir: str = "frontend/assets/voices"
    tts_audio_dir: str = "frontend/assets/audio"
    tts_max_concurrent: int = 3
    tts_cleanup_age_hours: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
