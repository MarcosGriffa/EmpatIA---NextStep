"""
mock_apis.py — Clientes FALSOS de Cohere y Groq, para probar todo el
circuito de evals sin gastar API ni necesitar el .env.

Se usa el semantic_match.py REAL; lo único que se cambia son los clientes
que devuelven _get_cohere() y _get_client(). Los números que salen en modo
mock NO dicen nada sobre NextStep: sirven para verificar que el runner,
las métricas, el export a Power BI y el reporte HTML funcionan.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from types import SimpleNamespace

import numpy as np

DIM = 512


def _tokens(texto: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2]


def _vec(texto: str) -> list[float]:
    v = np.zeros(DIM, dtype=np.float32)
    for w in _tokens(texto):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 9) % 2 else -1.0
    n = np.linalg.norm(v) or 1.0
    return (v / n).tolist()


class FakeCohere:
    def embed(self, texts, model, input_type, embedding_types):
        return SimpleNamespace(
            embeddings=SimpleNamespace(float_=[_vec(t) for t in texts]),
            meta=SimpleNamespace(billed_units=SimpleNamespace(input_tokens=sum(len(t) // 4 for t in texts))),
        )


class FakeGroq:
    def __init__(self):
        self.chat = self
        self.completions = self
        self._rng = random.Random(11)

    def create(self, model, messages, **kw):
        user = messages[-1]["content"]
        cv, _, oferta = user.partition("OFERTA:")
        a, b = set(_tokens(cv)), set(_tokens(oferta))
        overlap = len(a & b) / (len(b) or 1)
        score = int(max(0, min(100, 15 + overlap * 160 + self._rng.gauss(0, 8))))
        content = json.dumps({
            "score": score, "matches": ["(simulado)"], "gaps": [],
            "explicacion": "Respuesta simulada (modo mock).",
        })
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=len(user) // 4 + 180, completion_tokens=self._rng.randint(90, 220)),
        )


def semantic_match_simulado():
    import semantic_match as sm

    cohere, groq = FakeCohere(), FakeGroq()
    sm._get_cohere = lambda: cohere
    sm._get_client = lambda: groq
    return sm
