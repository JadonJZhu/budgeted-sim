"""Load the scenes and ratings of Lu, Bechlivanidis & Gerstenberg (2026).

Materials at github.com/cicl-stanford/complex_causation_cogsci2026. Point
ORIGINAL at a local copy of that repository (default: ../reference/...).
"""
import glob
import os

import pandas as pd

from sim.models import load_scenes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.environ.get(
    "ORIGINAL", os.path.join(HERE, "..", "reference", "complex_causation_cogsci2026"))


def scenes():
    return load_scenes(os.path.join(
        ORIGINAL, "code", "python", "trialinfo", "multi_ball_trials_combined.json"))


def ratings(question):
    """Long table: person, video, rating. Whether ratings are flipped (100 - x)
    so that high means 'B would have missed without A'."""
    files = glob.glob(os.path.join(ORIGINAL, "data", f"{question}_judgment", "output", "Output_*.csv"))
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.rename(columns={"randomID": "person", "video_id": "video",
                            "continuous_response": "rating"})[["person", "video", "rating"]]
    if question == "whether":
        df["rating"] = 100 - df["rating"]
    return df


def balls(video):
    return int(video.split("ball")[0])
