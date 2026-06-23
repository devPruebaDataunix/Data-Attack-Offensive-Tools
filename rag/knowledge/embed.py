#!/usr/bin/env python3
"""
embed.py — Embeddings LOCALES para la Capa 2 (sentence-transformers). Offline: ningún dato sale de la zona.

Decisión de arquitectura (coherente con CVE RAG + Capa 1, ambos offline): los embeddings se calculan en
local, no en la nube, para que ni el corpus ni las CONSULTAS (que pueden llevar contexto del target)
salgan del entorno aislado. Modelo por defecto pequeño y sólido para retrieval; configurable por entorno.

    export KB_EMBED_MODEL="BAAI/bge-small-en-v1.5"   # 384 dim (def.) — admite all-MiniLM-L6-v2, etc.

La importación de sentence-transformers/torch es PEREZOSA: kb_vec.py y el resto se pueden importar y
testear (store, chunking) sin tener el modelo instalado. La query es lo único que necesita el modelo.
"""
import os

DEFAULT_MODEL = os.environ.get("KB_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
# Los modelos BGE recomiendan anteponer una instrucción SOLO a las consultas (no a los pasajes).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, model_name=DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None  # carga perezosa
        self._dim = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # import perezoso (torch pesa)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dim(self):
        if self._dim is None:
            m = self.model
            fn = (getattr(m, "get_sentence_embedding_dimension", None)
                  or getattr(m, "get_embedding_dimension", None))  # nombre nuevo en ST recientes
            self._dim = int(fn()) if fn else len(self.encode("x"))
        return self._dim

    def _prep(self, texts, is_query):
        if is_query and "bge" in self.model_name.lower():
            return [BGE_QUERY_INSTRUCTION + t for t in texts]
        return texts

    def encode(self, texts, is_query=False, batch_size=64):
        """Devuelve una lista de vectores float32 normalizados (L2). Normalizar hace que la distancia
        L2 de sqlite-vec ordene igual que el coseno."""
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        vecs = self.model.encode(self._prep(items, is_query), batch_size=batch_size,
                                 normalize_embeddings=True, show_progress_bar=False)
        out = [[float(x) for x in v] for v in vecs]
        return out[0] if single else out
