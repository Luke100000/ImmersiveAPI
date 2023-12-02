import os
import urllib.request
import urllib.request

import requests
from dotenv import load_dotenv

from modules.phrasey.tts import TTS
from modules.phrasey.utils import convert_to_ogg

load_dotenv()

# Collect all voices
voices = {}
for filename in os.listdir("./mystic_embeddings"):
    if filename.endswith(".pth"):
        name = filename[:-4]
        voices[name] = "./mystic_embeddings/" + filename


class MysticEngine(TTS):
    def __init__(
        self, diffusion_iterations: int = 300, num_autoregressive_samples: int = 300
    ) -> None:
        super().__init__()

        self.diffusion_iterations = diffusion_iterations
        self.num_autoregressive_samples = num_autoregressive_samples

    def get_voices(self):
        return ["my_" + v for v in voices.keys()]

    def upload(self, voice: str):
        with open(voices[voice], "rb") as f:
            return requests.post(
                "https://www.mystic.ai/v3/pipeline_files",
                headers={"Authorization": "Bearer " + os.getenv("MYSTIC_API_KEY")},
                files={"pfile": f},
            ).json()["path"]

    def generate(self, text: str, voice: str, file: str):
        data = {
            "pipeline_id_or_pointer": "Conczin/tortoise-tts:v3",
            "async_run": False,
            "input_data": [
                {"type": "string", "value": text},
                {
                    "type": "file",
                    "value": None,
                    "file_path": self.upload(voice[3:]),
                },
                {
                    "type": "dictionary",
                    "value": {
                        "diffusion_iterations": self.diffusion_iterations,
                        "num_autoregressive_samples": self.num_autoregressive_samples,
                    },
                },
            ],
        }

        headers = {
            "Authorization": "Bearer " + os.getenv("MYSTIC_API_KEY"),
            "Content-Type": "application/json",
        }

        response = requests.post(
            "https://www.mystic.ai/v3/runs", headers=headers, json=data
        )

        urllib.request.urlretrieve(
            response.json()["result"]["outputs"][0]["file"]["url"], file + ".wav"
        )

        convert_to_ogg(file + ".wav", file)

        os.remove(file + ".wav")
