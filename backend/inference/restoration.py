"""Retained for explicit future restoration + IQA reassessment, never automatic."""
from models.restoration.predict import restore_image


def restore(path, model, output_dir):
    return restore_image(path, model=model, output_dir=output_dir)
