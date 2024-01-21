import torch
from pipeline import Pipeline, Variable, entity, pipe

from tortoise.api import TextToSpeech

import torch
import torchaudio
from pipeline import File, Pipeline, Variable, entity, pipe
from pipeline.cloud import environments, pipelines
from pipeline.cloud.compute_requirements import Accelerator
from pipeline.objects.graph import InputField, InputSchema


class ModelKwargs(InputSchema):
    num_autoregressive_samples: int | None = InputField(default=300)
    diffusion_iterations: int | None = InputField(default=300)


@entity
class TTSModel:
    @pipe(run_once=True, on_startup=True)
    def load(self) -> None:
        self.tts = TextToSpeech(use_deepspeed=True, kv_cache=True, half=True)

    @pipe
    def predict(self, prompt: str, voice: File, params: ModelKwargs) -> str:
        conditioning_latents = torch.load(voice.path.open("rb"))

        gen = self.tts.tts(
            prompt,
            conditioning_latents=conditioning_latents,
            num_autoregressive_samples=params.num_autoregressive_samples,
            diffusion_iterations=params.diffusion_iterations,
        )

        # noinspection PyUnresolvedReferences
        torchaudio.save("/tmp/output.wav", gen.squeeze(0).cpu(), 24000)
        return File(path="/tmp/output.wav", allow_out_of_context_creation=True)


with Pipeline() as builder:
    input_var = Variable(
        int,
        description="A basic input number to do things with",
        title="Input number",
    )

    prompt = Variable(
        str, description="The prompt to generate audio for", title="Prompt"
    )
    voice_file = Variable(
        File, description="The voice latents to use.", title="Voice latents file"
    )
    kwargs = Variable(ModelKwargs)
    model = TTSModel()
    model.load()
    output = model.predict(prompt, voice_file, kwargs)
    builder.output(output)

pipeline = builder.get_pipeline()
