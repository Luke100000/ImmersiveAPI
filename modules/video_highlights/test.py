import os
import time

from modules.video_highlights.labels import positive_labels, negative_labels
from modules.video_highlights.processor import predict, MODELS


def main():
    url = "https://www.youtube.com/watch?v=RSEpjfNNuv4"

    similarity, times, frames = predict(
        url,
        positive_labels,
        negative_labels,
        enhance=True,
        resolution=1.0,
        report_progress=print,
        model=MODELS[0],
    )
    os.makedirs("output_2", exist_ok=True)
    for frame_index, frame in enumerate(frames):
        frame.save(f"output_2/{frame_index}.png")


if __name__ == "__main__":
    t = time.time()
    main()
    print(f"Time: {time.time() - t}")
