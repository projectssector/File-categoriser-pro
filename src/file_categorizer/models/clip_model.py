"""CLIP-based local classifier (zero-shot)."""
from __future__ import annotations

import numpy as np
import torch
import open_clip
from PIL import Image

from .base import Prediction


class CLIPClassifier:
    name = "clip"

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)

    @torch.no_grad()
    def predict(self, image: np.ndarray, categories: list[str]) -> Prediction:
        pil = Image.fromarray(image[:, :, ::-1])  # BGR → RGB
        img_t = self.preprocess(pil).unsqueeze(0).to(self.device)
        text_t = self.tokenizer(categories).to(self.device)

        img_f = self.model.encode_image(img_t)
        txt_f = self.model.encode_text(text_t)
        img_f /= img_f.norm(dim=-1, keepdim=True)
        txt_f /= txt_f.norm(dim=-1, keepdim=True)

        probs = (100.0 * img_f @ txt_f.T).softmax(dim=-1).squeeze(0).cpu().numpy()
        scores = {c: float(p) for c, p in zip(categories, probs)}
        best = max(scores, key=scores.get)
        return Prediction(tag=best, confidence=scores[best], model=self.name, all_scores=scores)