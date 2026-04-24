"""
Default configuration values for DeepTutor.
"""

from pathlib import Path

# Get project root
_project_root = Path(__file__).parent.parent.parent

DEFAULT_LLM_PROVIDER = "deepseek"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"

# Default configuration
DEFAULTS = {
    "llm": {"model": DEFAULT_LLM_MODEL, "provider": DEFAULT_LLM_PROVIDER},
    "paths": {
        "user_data_dir": str(_project_root / "data" / "user"),
        "knowledge_bases_dir": str(_project_root / "data" / "knowledge_bases"),
        "user_log_dir": str(_project_root / "data" / "user" / "logs"),
    },
}
