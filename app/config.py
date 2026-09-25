from dynaconf import Dynaconf
from loguru import logger

from app.utils import get_data_path

# Load config
settings = Dynaconf(
    settings_files=[
        "default_config.toml",
        get_data_path("config.toml"),
    ]
)

logger.debug("Config {}", settings.as_dict())
