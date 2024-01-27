import hashlib
import subprocess

import numpy as np


def hash_string(input_str: str):
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


def cosine_dist(A, B):
    A_dot_B = np.dot(A, B)
    A_mag = np.sqrt(np.sum(np.square(A)))
    B_mag = np.sqrt(np.sum(np.square(B)))
    dist = 1.0 - (A_dot_B / (A_mag * B_mag))
    return dist


def convert_to_ogg(input_file: str, output_file: str, sample_rate: int = 48000):
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_file,
                "-ar",
                str(sample_rate),
                "-filter:a",
                "" "loudnorm=i=-14" "",
                output_file,
            ]
        )
        print(f"Conversion successful: {input_file} -> {output_file}")
    except Exception as e:
        print(f"Error during conversion: {e}")
