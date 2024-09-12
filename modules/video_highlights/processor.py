import hashlib
import os
import os.path
import subprocess
from functools import lru_cache
from typing import Callable

import cv2
import numpy as np
import torch
from PIL import Image
from scipy.ndimage import gaussian_filter1d
from scipy.signal import argrelextrema
from transformers import AutoProcessor, CLIPModel

CACHE_DIR = "cache/video_highlights"

MODELS = [
    "openai/clip-vit-base-patch32",
    "openai/clip-vit-base-patch16",
    "openai/clip-vit-large-patch14",
    "openai/clip-vit-large-patch14-336",
]


def str_to_hash(s: str):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def download_video(url: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = CACHE_DIR + "/" + str_to_hash(url)
    if not os.path.exists(path):
        subprocess.run(
            ['yt-dlp -o - -S "res:480" --max-filesize 256M \'' + url + "' > " + path],
            shell=True,
        )
    return path


def video_as_frames(cap: cv2.VideoCapture, resolution: float | None = None):
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = 0

    if resolution is None:
        resolution = fps

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if int(frame_count / fps * resolution) != int(
            (frame_count - 1) / fps * resolution
        ):
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            yield frame_count / fps, pil_image
        frame_count += 1


@lru_cache(1)
def get_model(model: str):
    processor = AutoProcessor.from_pretrained(model)
    clip_model = CLIPModel.from_pretrained(model)
    return clip_model, processor


@lru_cache(64)
def get_features(labels: tuple, model: str):
    clip_model, processor = get_model(model)
    label_inputs = processor(text=labels, return_tensors="pt", padding=True)
    with torch.no_grad():
        text_features = clip_model.get_text_features(**label_inputs)
    prompt_vectors = text_features.cpu().numpy()
    # return np.mean(prompt_vectors, axis=0)
    return prompt_vectors


def cosine_similarity(vec: np.ndarray, mat: np.ndarray):
    if len(vec.shape) == 1:
        p1 = vec.dot(mat)
        p2 = np.linalg.norm(mat, axis=0) * np.linalg.norm(vec)
        return p1 / p2
    else:
        similarities = np.asarray([cosine_similarity(v, mat) for v in vec])
        return np.percentile(similarities, axis=0, q=90)


def embedd_frames(images: list[Image.Image], model: str):
    clip_model, processor = get_model(model)
    with torch.no_grad():
        inputs = processor(images=images, return_tensors="pt")
        image_features = clip_model.get_image_features(**inputs)
    return image_features.cpu().numpy().T


def embedd_video(
    url: str,
    resolution: float = 1.0,
    model: str = MODELS[-1],
    report_progress: Callable = lambda x: None,
):
    model_identifier = model.replace("/", "_")
    path = f"{CACHE_DIR}/{str_to_hash(url)}_{resolution}_{model_identifier}.npz"
    if not os.path.exists(path):
        report_progress("Downloading video...")
        video_path = download_video(url)

        report_progress("Processing video...")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(
                "Unable to open video, either unknown website or too large"
            )

        # Skip very long videos
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = frame_count / fps
        if duration * resolution > 10000:
            raise ValueError("Video is too long, reduce resolution or video length")

        # Process the video
        features = []
        batch = []
        batch_size = 8
        for second, frame in video_as_frames(cap, resolution=resolution):
            batch.append(frame)
            if len(batch) == batch_size:
                report_progress(f"Processing video ({int(second / duration * 100)}%)")
                features.append(embedd_frames(batch, model))
                batch = []

        if len(batch) > 0:
            features.append(embedd_frames(batch, model))

        # Save the features
        features = np.concatenate(features, axis=1)
        np.savez(
            path,
            features=features,
        )
        return features

    return np.load(path)["features"]


def extract_frames(url: str, times: np.ndarray) -> list[Image.Image]:
    video_path = download_video(url)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    for time in times:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(time * fps) - 1))
        ret, frame = cap.read()
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        frames.append(pil_image)
    return frames


def adjust_local_maxima(similarity: np.ndarray, best: np.ndarray):
    """
    Given the approximate local maxima, find the true maxima
    """
    sorted_best = best[np.argsort(best)]

    new_best = []
    for index, frame in enumerate(sorted_best):
        r = np.array(
            range(
                0 if index == 0 else (sorted_best[index - 1] + frame) // 2,
                (
                    len(similarity)
                    if index == len(sorted_best) - 1
                    else (sorted_best[index + 1] + frame) // 2
                ),
            )
        )
        best_index = r[np.argmax(similarity[r])]

        new_best.append(best_index)

    return np.array(new_best)[np.argsort(-similarity[new_best])]


def extract_maxima(
    similarity: np.ndarray, resolution: float, maxima_count: int
) -> np.ndarray:
    """
    Returns a sorted list of local maxima, in seconds
    """
    best = []
    high_blur = len(similarity)
    low_blur = 0
    blur = (high_blur + low_blur) / 2
    for _ in range(16):
        blurred = gaussian_filter1d(similarity, blur)
        local_maxima = argrelextrema(blurred, np.greater)[0]
        capped_local_maxima = local_maxima[
            np.argsort(-similarity[local_maxima])[:maxima_count]
        ]

        if abs(len(local_maxima) - maxima_count) <= abs(len(best) - maxima_count):
            best = np.asarray(capped_local_maxima)

        if len(local_maxima) < maxima_count:
            high_blur = blur
        elif len(local_maxima) > maxima_count:
            low_blur = blur
        else:
            break

        blur = (high_blur + low_blur) / 2

    return adjust_local_maxima(similarity, np.asarray(best)) / resolution


def enhance_local_maxima(
    times: np.ndarray,
    cap: cv2.VideoCapture,
    resolution: float,
    model: str,
    positive_vector: np.ndarray,
    negative_vector: np.ndarray,
    report_progress: Callable = lambda x: None,
):
    """
    Given time estimates with low resolution, enhance the estimates to a per-frame resolution
    """
    # Collect batches of frames
    batches = [[] for _ in range(len(times))]
    seconds = [[] for _ in range(len(times))]
    fps = cap.get(cv2.CAP_PROP_FPS)
    for second, frame in video_as_frames(cap):
        for batch_index, time in enumerate(times):
            if abs((time + 0.5 / resolution) - (second + 0.5 / fps)) < 1.0 / resolution:
                batches[batch_index].append(frame)
                seconds[batch_index].append(second)

    # Find the maxima of each batch
    enhanced = []
    for batch_index, batch in enumerate(batches):
        report_progress(
            f"Enhancing highlight ({int(batch_index / len(batches) * 100)}%)"
        )
        video_features = embedd_frames(batch, model)
        positive_similarity = cosine_similarity(positive_vector, video_features)
        negative_similarity = cosine_similarity(negative_vector, video_features)
        similarity = positive_similarity - negative_similarity
        enhanced.append(seconds[batch_index][np.argmax(similarity)])

    return np.array(enhanced)


def predict(
    url: str,
    positive_labels: list,
    negative_labels: list,
    resolution: float = 2,
    maxima_count: int = 5,
    quality_threshold: float = 0.8,
    model: str = MODELS[0],
    enhance: bool = True,
    report_progress: Callable = lambda x: None,
):
    # Process the labels
    report_progress("Processing labels...")
    positive_vector = get_features(tuple(positive_labels), model)
    negative_vector = get_features(tuple(negative_labels), model)

    # Calculate the embedding
    video_features = embedd_video(url, resolution, model, report_progress)

    # Calculate the similarity
    report_progress("Searching for highlights...")
    positive_similarity = cosine_similarity(positive_vector, video_features)
    negative_similarity = cosine_similarity(negative_vector, video_features)
    similarity = positive_similarity - negative_similarity

    # Postprocess the similarity
    similarity -= np.min(similarity)
    similarity /= np.max(similarity)

    # Find local maxima, favoring unique frames
    times = extract_maxima(
        similarity, resolution, int(maxima_count / (1.0 - quality_threshold))
    )[:maxima_count]

    # Enhance the local maxima by scanning on full resolution
    if enhance:
        cap = cv2.VideoCapture(download_video(url))
        times = enhance_local_maxima(
            times,
            cap,
            resolution,
            model,
            positive_vector,
            negative_vector,
            report_progress,
        )

    report_progress("Extracting frames...")
    frames = extract_frames(url, times)

    return similarity, times, frames
