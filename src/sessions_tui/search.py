"""Multi-field hybrid search: per-field BM25 + semantic with RRF fusion."""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import SessionSummary


def warm_tqdm_lock() -> None:
    """Pre-initialize tqdm's multiprocessing lock.

    Must be called before Textual modifies file descriptors, otherwise
    tqdm.__new__ -> get_lock() -> mp.RLock() -> resource_tracker.spawnv_passfds
    fails with "bad value(s) in fds_to_keep" inside Textual workers.
    """
    try:
        from tqdm import tqdm
        tqdm.get_lock()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Field weights — higher = more relevant when matched
# ---------------------------------------------------------------------------

# BM25 keyword weights per field
_BM25_WEIGHTS: dict[str, float] = {
    "first_prompt": 3.0,   # session "title" — highest keyword signal
    "prompts":      2.5,   # individual user messages
    "topics":       2.0,   # topic tags
    "project":      1.5,   # project short name
    "branch":       1.5,   # git branch
    "domains":      1.0,   # domain tags
    "tools":        0.5,   # tool names
}

# Semantic weights per field (only fields where meaning matters)
_SEM_WEIGHTS: dict[str, float] = {
    "first_prompt": 3.0,
    "prompts":      2.5,   # max-sim across individual prompts
    "topics":       2.0,
    "domains":      1.0,
}

# RRF constant (standard value, higher = more weight to lower-ranked items)
_RRF_K = 60

# Default top-K limit
DEFAULT_TOP_K = 25

# Minimum gap ratio to trigger score-gap cutoff (fraction of top score)
_GAP_RATIO = 0.10

# Minimum results to keep even if gap cutoff would cut more
_GAP_MIN_RESULTS = 2

# Maximum prompts per session to index semantically
_MAX_PROMPTS_SEMANTIC = 10

# Maximum prompts per session for BM25
_MAX_PROMPTS_BM25 = 20


# ---------------------------------------------------------------------------
# BM25 implementation (pure Python, no deps)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Okapi BM25 ranking over document texts."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[list[str]] = []
        self._doc_len: list[int] = []
        self._avgdl: float = 0.0
        self._df: Counter = Counter()
        self._n: int = 0

    def build(self, texts: list[str]) -> None:
        self._docs = [_tokenize(t) for t in texts]
        self._n = len(self._docs)
        self._doc_len = [len(d) for d in self._docs]
        self._avgdl = sum(self._doc_len) / max(self._n, 1)
        self._df = Counter()
        for doc in self._docs:
            for term in set(doc):
                self._df[term] += 1

    def query(self, text: str) -> list[float]:
        tokens = _tokenize(text)
        if not tokens:
            return [0.0] * self._n

        scores = [0.0] * self._n
        for term in tokens:
            if term not in self._df:
                continue
            df = self._df[term]
            idf = math.log((self._n - df + 0.5) / (df + 0.5) + 1.0)
            for i, doc in enumerate(self._docs):
                tf = doc.count(term)
                if tf == 0:
                    continue
                dl = self._doc_len[i]
                num = tf * (self.k1 + 1)
                den = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                scores[i] += idf * num / den

        return scores


# ---------------------------------------------------------------------------
# Semantic model (optional, lazy-loaded)
# ---------------------------------------------------------------------------

_semantic_model = None
_semantic_available: bool | None = None


def _load_semantic_model():
    """Lazy-load the model2vec embedding model."""
    global _semantic_model, _semantic_available
    if _semantic_available is not None:
        return _semantic_available

    try:
        from model2vec import StaticModel
        _semantic_model = StaticModel.from_pretrained("minishlab/potion-base-8M")
        _semantic_available = True
    except Exception:
        _semantic_available = False

    return _semantic_available


def _encode(texts: list[str]):
    """Encode texts using the semantic model. Returns numpy array."""
    return _semantic_model.encode(texts, show_progress_bar=False, use_multiprocessing=False)


def _cosine_sim(query_emb, doc_embs):
    """Cosine similarity between one query embedding and N doc embeddings."""
    import numpy as np
    d_norm = doc_embs / (np.linalg.norm(doc_embs, axis=1, keepdims=True) + 1e-9)
    q_norm = query_emb / (np.linalg.norm(query_emb) + 1e-9)
    return (d_norm @ q_norm.T).flatten()


# ---------------------------------------------------------------------------
# Multi-field session search index
# ---------------------------------------------------------------------------

class SessionSearchIndex:
    """Per-field BM25 + semantic search with RRF fusion and score-gap cutoff."""

    def __init__(self) -> None:
        self._sessions: list[SessionSummary] = []

        # BM25: one index per field
        self._bm25: dict[str, BM25Index] = {}
        self._field_texts: dict[str, list[str]] = {}

        # Semantic: one embedding matrix per field, except prompts (per-session list)
        self._sem_field_embs: dict[str, object] = {}  # field -> ndarray(n, dim)
        self._sem_prompt_embs: list[object | None] = []  # per-session prompt embeddings
        self._doc_embeddings = None  # backward-compat flag for app.py

    def build(self, sessions: list[SessionSummary]) -> None:
        """Extract per-field texts and build BM25 indexes."""
        self._sessions = sessions
        n = len(sessions)

        # Extract text per field
        self._field_texts = {
            "first_prompt": [s.first_prompt or "" for s in sessions],
            "prompts":      [" ".join(s.human_prompts[:_MAX_PROMPTS_BM25]) for s in sessions],
            "topics":       [" ".join(s.topics) for s in sessions],
            "project":      [s.project_short or "" for s in sessions],
            "branch":       [s.git_branch or "" for s in sessions],
            "domains":      [" ".join(s.domains) for s in sessions],
            "tools":        [" ".join(s.tools_used) for s in sessions],
        }

        # Build BM25 per field
        self._bm25 = {}
        for field in _BM25_WEIGHTS:
            idx = BM25Index()
            idx.build(self._field_texts[field])
            self._bm25[field] = idx

        # Reset semantic state
        self._sem_field_embs = {}
        self._sem_prompt_embs = [None] * n
        self._doc_embeddings = None

    def _ensure_semantic(self) -> bool | str:
        """Load semantic model and compute per-field embeddings.

        Returns True on success, or an error string on failure.
        """
        if self._sem_field_embs:
            return True

        if not _load_semantic_model():
            return f"model load failed: {_semantic_model}"

        try:
            self._build_semantic_embeddings()
            self._doc_embeddings = True  # flag for app.py compat
            return True
        except Exception as exc:
            return f"encode failed: {exc}"

    def _build_semantic_embeddings(self) -> None:
        """Compute embeddings for each semantic field."""
        # Simple fields: one embedding per session
        for field in _SEM_WEIGHTS:
            if field == "prompts":
                continue  # handled separately
            texts = self._field_texts[field]
            self._sem_field_embs[field] = _encode(texts)

        # Prompts: encode all individual prompts, then split per session
        all_prompts: list[str] = []
        boundaries: list[tuple[int, int]] = []
        for s in self._sessions:
            prompts = s.human_prompts[:_MAX_PROMPTS_SEMANTIC]
            start = len(all_prompts)
            if prompts:
                all_prompts.extend(prompts)
            else:
                all_prompts.append("")  # placeholder for empty sessions
            boundaries.append((start, len(all_prompts)))

        if all_prompts:
            all_emb = _encode(all_prompts)
            for i, (start, end) in enumerate(boundaries):
                self._sem_prompt_embs[i] = all_emb[start:end]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: str, *, limit: int = 0, top_k: int = DEFAULT_TOP_K,
    ) -> list[tuple[SessionSummary, float]]:
        """Search sessions using multi-field BM25 + semantic with RRF fusion.

        Returns sessions ranked by relevance, filtered by score-gap cutoff.
        """
        if not query.strip() or not self._sessions:
            return [(s, 0.0) for s in self._sessions]

        n = len(self._sessions)

        # --- Per-field BM25 scoring (weighted sum) ---
        bm25_total = [0.0] * n
        for field, weight in _BM25_WEIGHTS.items():
            raw = self._bm25[field].query(query)
            max_raw = max(raw) if raw else 0
            if max_raw > 0:
                for i in range(n):
                    bm25_total[i] += weight * (raw[i] / max_raw)

        # --- Per-field semantic scoring (weighted sum) ---
        sem_total = [0.0] * n
        has_semantic = bool(self._sem_field_embs)
        if has_semantic:
            q_emb = _encode([query])[0]  # shape (dim,)

            for field, weight in _SEM_WEIGHTS.items():
                if field == "prompts":
                    # Max cosine similarity across individual prompts
                    for i, p_emb in enumerate(self._sem_prompt_embs):
                        if p_emb is not None and len(p_emb) > 0:
                            sims = _cosine_sim(q_emb, p_emb)
                            sem_total[i] += weight * max(0.0, float(sims.max()))
                elif field in self._sem_field_embs:
                    sims = _cosine_sim(q_emb, self._sem_field_embs[field])
                    for i in range(n):
                        sem_total[i] += weight * max(0.0, float(sims[i]))

        # --- Candidate gating ---
        # Must have keyword signal OR strong semantic signal
        # Semantic-only candidates must pass both:
        #   1. Absolute floor (rejects nonsense queries where all scores are low)
        #   2. Relative threshold (top quartile of non-zero scores)
        sem_floor = 0.0
        sem_relative = 0.0
        if has_semantic:
            max_sem = max(sem_total)
            # Absolute floor: at least 15% of max possible weighted score
            # Max possible = sum of all semantic weights (perfect cosine=1.0)
            max_possible = sum(_SEM_WEIGHTS.values())
            sem_floor = max_possible * 0.15
            # Relative: top quartile of non-zero scores
            nonzero_sem = sorted([s for s in sem_total if s > 0], reverse=True)
            if nonzero_sem:
                q1_idx = max(0, len(nonzero_sem) // 4 - 1)
                sem_relative = nonzero_sem[q1_idx]

        candidates: list[int] = []
        for i in range(n):
            if bm25_total[i] > 0:
                candidates.append(i)
            elif has_semantic and sem_total[i] >= sem_floor and sem_total[i] >= sem_relative:
                candidates.append(i)

        if not candidates:
            return []

        # --- RRF fusion over candidates ---
        # Rank candidates by BM25
        by_bm25 = sorted(candidates, key=lambda i: -bm25_total[i])
        bm25_rank = {idx: rank for rank, idx in enumerate(by_bm25)}

        # Rank candidates by semantic (or just BM25 rank if no semantic)
        if has_semantic:
            by_sem = sorted(candidates, key=lambda i: -sem_total[i])
            sem_rank = {idx: rank for rank, idx in enumerate(by_sem)}
        else:
            sem_rank = bm25_rank  # degenerate: same ranking

        rrf = []
        for i in candidates:
            score = 1.0 / (_RRF_K + bm25_rank[i]) + 1.0 / (_RRF_K + sem_rank[i])
            rrf.append((i, score))

        rrf.sort(key=lambda x: -x[1])

        # --- Score-gap cutoff ---
        rrf = _apply_score_gap(rrf, top_k)

        # --- Apply top_k ---
        if limit > 0:
            rrf = rrf[:limit]
        else:
            rrf = rrf[:top_k]

        return [(self._sessions[i], score) for i, score in rrf]


def _apply_score_gap(
    ranked: list[tuple[int, float]], top_k: int,
) -> list[tuple[int, float]]:
    """Find the largest score gap and cut there if significant.

    Preserves at least _GAP_MIN_RESULTS and at most top_k results.
    """
    if len(ranked) <= _GAP_MIN_RESULTS:
        return ranked

    scores = [s for _, s in ranked]
    top_score = scores[0]
    if top_score <= 0:
        return ranked

    # Look for the largest gap in the candidate list (within top_k window)
    best_gap = 0.0
    cut_at = len(ranked)
    search_range = min(len(ranked), top_k)

    for j in range(max(_GAP_MIN_RESULTS, 1), search_range):
        gap = scores[j - 1] - scores[j]
        if gap > best_gap:
            best_gap = gap
            cut_at = j

    # Only cut if the gap is significant relative to the top score
    if best_gap > top_score * _GAP_RATIO:
        return ranked[:cut_at]

    return ranked[:top_k]
