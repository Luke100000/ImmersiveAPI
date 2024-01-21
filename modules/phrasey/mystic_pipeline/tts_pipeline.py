import torch
import torchaudio
from pipeline import entity, pipe, Pipeline
from pipeline.objects.graph import InputSchema, InputField, File, Variable
from tortoise.api import TextToSpeech


class ModelKwargs(InputSchema):
    num_autoregressive_samples: int | None = InputField(default=300)
    diffusion_iterations: int | None = InputField(default=300)


@entity
class TTSModel:
    def __init__(self):
        self.tts = TextToSpeech(use_deepspeed=True, kv_cache=True, half=True)

    @pipe(run_once=True, on_startup=True)
    def load(self) -> None:
        pass

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


def get_pipeline():
    with Pipeline() as builder:
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

        return builder.get_pipeline()


pipeline = get_pipeline()
