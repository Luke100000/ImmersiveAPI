from functools import cache

import PIL.Image
from optimum.intel.openvino.modeling_diffusion import OVStableDiffusionXLPipeline


@cache
def get_model() -> OVStableDiffusionXLPipeline:
    return OVStableDiffusionXLPipeline.from_pretrained(
        "rupeshs/sdxl-turbo-openvino-int8"
    )


def generate_image(prompt: str, num_inference_steps: int = 2) -> PIL.Image:
    pipeline = get_model()

    # pipeline.load_textual_inversion("embedding.pt", "<keyword>")

    return pipeline(
        prompt=prompt,
        width=512,
        height=512,
        num_inference_steps=num_inference_steps,
        guidance_scale=0.0,
    ).images[0]