import abc
from enum import Enum


class JsonFormat(Enum):
    PHRASES = "phrases"
    DIALOGUE = "dialogue"


class Environment(abc.ABC):
    """
    An environment maps query and event parameters to translations, checks for validity, and provides context.
    """

    @abc.abstractmethod
    def get_prompt(self, params: dict[str, str]) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def get_filter(self, params: dict[str, str]) -> set[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_valid_voices(self, params: dict[str, str]) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_json_format(self, params: dict[str, str]) -> JsonFormat:
        raise NotImplementedError
