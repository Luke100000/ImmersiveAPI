import os
import subprocess

import torch
from tortoise.api import TextToSpeech
from tortoise.utils.audio import load_voice

# Directory paths
input_directory = "data/voices"
output_directory = "data/voices_processed"

# Create output directory if it doesn't exist
os.makedirs(output_directory, exist_ok=True)

# List all audio files in the input directory
audio_files = [f for f in os.listdir(input_directory)]

tts = TextToSpeech()

# Convert and process audio files
for audio_file in audio_files:
    voice_name = os.path.splitext(audio_file)[0]
    input_path = os.path.join(input_directory, audio_file)
    output_path = os.path.join(output_directory, voice_name + ".wav")

    # Convert and process using ffmpeg
    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ar",
        "24000",
        "-af",
        "afftdn=nf=-70,loudnorm=I=-14",
        output_path,
    ]
    subprocess.run(ffmpeg_command)

    # Run shell script to split processed file
    split_output_directory = os.path.join(output_directory, voice_name)

    # Create split output directory if it doesn't exist
    os.makedirs(split_output_directory, exist_ok=True)

    # Run the split script
    split_command = [
        "scripts/split.sh",
        output_path,
        os.path.join(split_output_directory, "%03d.wav"),
    ]
    subprocess.run(split_command)

    # Convert into latent conditioning vectors
    voice_samples, _ = load_voice(voice_name, ["data/voices_processed"])
    conditioning_latents = tts.get_conditioning_latents(voice_samples)
    torch.save(
        conditioning_latents, os.path.join(output_directory, f"{voice_name}.pth")
    )
