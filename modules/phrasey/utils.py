import hashlib

import numpy as np


def hash_string(input_str: str):
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


def cosine_dist(A, B):
    A_dot_B = np.dot(A, B)
    A_mag = np.sqrt(np.sum(np.square(A)))
    B_mag = np.sqrt(np.sum(np.square(B)))
    dist = 1.0 - (A_dot_B / (A_mag * B_mag))
    return dist
