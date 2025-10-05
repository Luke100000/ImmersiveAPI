import io
import os
import os.path
from functools import cache
from random import randint
from typing import Union

import numpy as np
import torch
from pydub import AudioSegment

xtts_num_threads = 2

os.environ["COQUI_TOS_AGREED"] = "1"


@cache
def get_model():
    from TTS.api import TTS

    return TTS("tts_models/multilingual/multi-dataset/xtts_v2")


@cache
def get_embedding(audio_path: str):
    tts = get_model()
    return tts.synthesizer.tts_model.get_conditioning_latents(audio_path=audio_path)


def get_speakers():
    return list(get_model().synthesizer.tts_model.speaker_manager.speaker_names)


def get_languages():
    return get_model().synthesizer.tts_model.language_manager.language_names


def generate_speech(
    text: str,
    language: str = "en",
    speaker: str = None,
    speaker_wav: str = None,
    file_format: str = "wav",
    file_path: str = None,
    overwrite: bytes = True,
) -> Union[str, bytes]:
    # Load from file
    if file_path is not None and not overwrite and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return f.read()

    # We use fewer cores because we go for model-level parallelism
    num_threads = torch.get_num_threads()
    torch.set_num_threads(xtts_num_threads)
    tts = get_model()

    # Fetch embeddings
    if speaker_wav is not None:
        gpt_cond_latent, speaker_embedding = get_embedding(speaker_wav)
    else:
        speakers = tts.synthesizer.tts_model.speaker_manager.speakers
        if speaker is None:
            speaker = list(speakers.keys())[randint(0, len(speakers) - 1)]
        gpt_cond_latent, speaker_embedding = speakers[speaker].values()

    # Generate speech
    wav = tts.synthesizer.tts_model.inference(
        text, language, gpt_cond_latent, speaker_embedding
    )["wav"]

    torch.set_num_threads(num_threads)

    # Convert to 16 bit PCM
    pcm_data = (np.array(wav) * 32767).astype(np.int16)

    # Encode
    buffer = io.BytesIO()
    audio = AudioSegment(
        pcm_data.tobytes(),
        sample_width=2,
        frame_rate=tts.synthesizer.output_sample_rate,
        channels=1,
    )
    audio.export(buffer, format=file_format)

    audio = buffer.getvalue()

    # Write to file
    if file_path is not None:
        with open(file_path, "wb") as f:
            f.write(audio)
        return file_path

    return audio


# noinspection SpellCheckingInspection
"""
Not included because of low quality
Gitta Nikolina, Viktor Eka

Not included because children
Daisy Studious, Andrew Chipper

Not included to match number of male voices
Badr Odhiambo, Chandra MacFarland, Szofi Granger, Brenda Stern
"""


# noinspection SpellCheckingInspection
def get_base_speakers():
    return {
        "female_0": "Claribel Dervla",
        "female_1": "Gracie Wise",
        "female_2": "Tammie Ema",
        "female_3": "Alison Dietlinde",
        "female_4": "Ana Florence",
        "female_5": "Annmarie Nele",
        "female_6": "Asya Anara",
        "female_7": "Rosemary Okafor",
        "female_8": "Henriette Usha",
        "female_9": "Sofia Hellen",
        "female_10": "Tammy Grit",
        "female_11": "Tanja Adelina",
        "female_12": "Vjollca Johnnie",
        "female_13": "Suad Qasim",
        "female_14": "Nova Hogarth",
        "female_15": "Maja Ruoho",
        "female_16": "Uta Obando",
        "female_17": "Lidiya Szekeres",
        "female_18": "Alma María",
        "female_19": "Alexandra Hisakawa",
        "female_20": "Camilla Holmström",
        "female_21": "Lilya Stainthorpe",
        "female_22": "Zofija Kendrick",
        "female_23": "Narelle Moon",
        "female_24": "Barbora MacLean",
        "male_0": "Dionisio Schuyler",
        "male_1": "Royston Min",
        "male_2": "Abrahan Mack",
        "male_3": "Adde Michal",
        "male_4": "Baldur Sanjin",
        "male_5": "Craig Gutsy",
        "male_6": "Damien Black",
        "male_7": "Gilberto Mathias",
        "male_8": "Ilkin Urbano",
        "male_9": "Kazuhiko Atallah",
        "male_10": "Ludvig Milivoj",
        "male_11": "Torcull Diarmuid",
        "male_12": "Viktor Menelaos",
        "male_13": "Zacharie Aimilios",
        "male_14": "Ige Behringer",
        "male_15": "Filip Traverse",
        "male_16": "Damjan Chapman",
        "male_17": "Wulf Carlevaro",
        "male_18": "Aaron Dreschner",
        "male_19": "Kumar Dahl",
        "male_20": "Eugenio Mataracı",
        "male_21": "Ferran Simen",
        "male_22": "Xavier Hayasaka",
        "male_23": "Luis Moray",
        "male_24": "Marcos Rudaski",
    }
