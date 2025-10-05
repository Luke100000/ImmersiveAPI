import hashlib
import json
import logging
import os.path
import shutil
from functools import cache
from pathlib import Path
from typing import Any, Dict, Iterable, Set, Union
from urllib.request import urlopen

from piper import PiperVoice, SynthesisConfig

URL_FORMAT = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{file}"

_DIR = Path(__file__).parent
_LOGGER = logging.getLogger(__name__)

_SKIP_FILES = {"MODEL_CARD"}


class VoiceNotFoundError(Exception):
    pass


def get_file_hash(path: Union[str, Path], bytes_per_chunk: int = 8192) -> str:
    """Hash a file in chunks using md5."""
    path_hash = hashlib.md5()
    with open(path, "rb") as path_file:
        chunk = path_file.read(bytes_per_chunk)
        while chunk:
            path_hash.update(chunk)
            chunk = path_file.read(bytes_per_chunk)

    return path_hash.hexdigest()


def get_voices(
    download_dir: Union[str, Path], update_voices: bool = False
) -> Dict[str, Any]:
    """Loads available voices from downloaded or embedded JSON file."""
    download_dir = Path(download_dir)
    voices_download = download_dir / "voices.json"

    if update_voices:
        # Download latest voices.json
        voices_url = URL_FORMAT.format(file="voices.json")
        _LOGGER.debug("Downloading %s to %s", voices_url, voices_download)
        with (
            urlopen(voices_url) as response,
            open(voices_download, "wb") as download_file,
        ):
            shutil.copyfileobj(response, download_file)

    # Prefer downloaded file to embedded
    voices_embedded = _DIR / "voices.json"
    voices_path = voices_download if voices_download.exists() else voices_embedded

    _LOGGER.debug("Loading %s", voices_path)
    with open(voices_path, "r", encoding="utf-8") as voices_file:
        return json.load(voices_file)


def ensure_voice_exists(
    name: str,
    data_dirs: Iterable[Union[str, Path]],
    download_dir: Union[str, Path],
    voices_info: Dict[str, Any],
):
    assert data_dirs, "No data dirs"
    if name not in voices_info:
        raise VoiceNotFoundError(name)

    voice_info = voices_info[name]
    voice_files = voice_info["files"]
    files_to_download: Set[str] = set()

    for data_dir in data_dirs:
        data_dir = Path(data_dir)

        # Check sizes/hashes
        for file_path, file_info in voice_files.items():
            if file_path in files_to_download:
                # Already planning to download
                continue

            file_name = Path(file_path).name
            if file_name in _SKIP_FILES:
                continue

            data_file_path = data_dir / file_name
            _LOGGER.debug("Checking %s", data_file_path)
            if not data_file_path.exists():
                _LOGGER.debug("Missing %s", data_file_path)
                files_to_download.add(file_path)
                continue

            expected_size = file_info["size_bytes"]
            actual_size = data_file_path.stat().st_size
            if expected_size != actual_size:
                _LOGGER.warning(
                    "Wrong size (expected=%s, actual=%s) for %s",
                    expected_size,
                    actual_size,
                    data_file_path,
                )
                files_to_download.add(file_path)
                continue

            expected_hash = file_info["md5_digest"]
            actual_hash = get_file_hash(data_file_path)
            if expected_hash != actual_hash:
                _LOGGER.warning(
                    "Wrong hash (expected=%s, actual=%s) for %s",
                    expected_hash,
                    actual_hash,
                    data_file_path,
                )
                files_to_download.add(file_path)
                continue

    if (not voice_files) and (not files_to_download):
        raise ValueError(f"Unable to find or download voice: {name}")

    # Download missing files
    download_dir = Path(download_dir)

    for file_path in files_to_download:
        file_name = Path(file_path).name
        if file_name in _SKIP_FILES:
            continue

        file_url = URL_FORMAT.format(file=file_path)
        download_file_path = download_dir / file_name
        download_file_path.parent.mkdir(parents=True, exist_ok=True)

        _LOGGER.debug("Downloading %s to %s", file_url, download_file_path)
        with (
            urlopen(file_url) as response,
            open(download_file_path, "wb") as download_file,
        ):
            shutil.copyfileobj(response, download_file)

        _LOGGER.info("Downloaded %s (%s)", download_file_path, file_url)


data_dir = Path("cache/piper")

# Voices that are either too specific or of low quality
blacklist = {"thorsten_emotional"}


@cache
def get_gender_lookup():
    if os.path.exists("data/piper_gender.json"):
        with open("data/piper_gender.json", "r") as f:
            return json.load(f)
    return {}


# Do not support low since those are 16 kHz and would need extra logic
quality = {"medium": 2, "high": 3}


@cache
def get_best_voices():
    data_dir.mkdir(parents=True, exist_ok=True)
    voices = get_voices(data_dir, True)
    best_voices = {}
    for info in voices.values():
        if info["quality"] in quality and (
            info["name"] not in best_voices
            or quality[info["quality"]] > quality[best_voices[info["name"]]["quality"]]
        ):
            best_voices[info["name"]] = info
    return best_voices


def speak(text: str, speaker: str) -> Iterable[bytes]:
    name, speaker_id = speaker.split(":", 1)
    voices = get_best_voices()

    # Download voice
    ensure_voice_exists(name, [data_dir], data_dir, voices)

    # Load voice
    voice = PiperVoice.load(
        data_dir / f"{voices[name]['key']}.onnx",
        data_dir / f"{voices[name]['key']}.onnx.json",
    )

    # Generate audio
    audio_stream = voice.synthesize(
        text,
        syn_config=SynthesisConfig(
            speaker_id=None if speaker_id == "-1" else int(speaker_id)
        ),
    )
    for audio_bytes in audio_stream:
        yield audio_bytes.audio_int16_bytes
