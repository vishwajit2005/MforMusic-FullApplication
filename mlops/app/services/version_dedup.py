"""
Song-version de-duplication for recommendation lists.

JioSaavn publishes the same song under many IDs (original album, "From <film>"
compilations, instrumental / lofi / remix cuts...). The models rank by ID, so
one song can fill several slots. This module collapses those versions AFTER the
models have scored candidates — it never changes any model's scoring, it only
drops lower-ranked duplicates and re-numbers ranks.

Two tracks are treated as the same song when their core titles match and they
share at least one artist (or one side has no artist information).
"""

import html
import logging
import re
import unicodedata
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

# Bracketed or trailing segments that describe a release/version, not the song.
_BRACKETS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_DASH_SUFFIX = re.compile(r"\s+[-–—|:]\s+.*$")
_FEAT = re.compile(r"\b(feat\.?|ft\.?|featuring)\b.*$")
_NON_WORD = re.compile(r"[^a-z0-9ऀ-ॿ ]+")
_SPACES = re.compile(r"\s+")
_ARTIST_SPLIT = re.compile(r"\s*(?:,|&|/|;|\bx\b|\band\b|\bfeat\.?|\bft\.?|\bfeaturing\b)\s*")


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(str(text))).lower()
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def core_title(title: str | None) -> str:
    """'Tum Hi Ho (From "Aashiqui 2")' -> 'tum hi ho'; 'Tum Hi Ho - Flute Instrumental' -> 'tum hi ho'."""
    if not title or not isinstance(title, str):
        return ""
    raw = html.unescape(title)
    stripped = _BRACKETS.sub(" ", raw)
    stripped = _DASH_SUFFIX.sub("", stripped)
    stripped = _FEAT.sub("", stripped.lower())
    core = _clean(stripped)
    return core or _clean(raw)


def artist_set(artists: str | None) -> frozenset[str]:
    if not artists or not isinstance(artists, str):
        return frozenset()
    parts = _ARTIST_SPLIT.split(html.unescape(artists).lower())
    return frozenset(p for p in (_clean(part) for part in parts) if p and p != "unknown artist")


class VersionIndex:
    """Remembers which songs are already taken (or blocked) and answers 'is this a version of one?'."""

    def __init__(self):
        self._groups: dict[str, list[frozenset[str]]] = {}

    def add(self, title: str | None, artists: str | None) -> None:
        key = core_title(title)
        if key:
            self._groups.setdefault(key, []).append(artist_set(artists))

    def contains(self, title: str | None, artists: str | None) -> bool:
        key = core_title(title)
        if not key or key not in self._groups:
            return False
        mine = artist_set(artists)
        for theirs in self._groups[key]:
            if not mine or not theirs or (mine & theirs):
                return True
        return False


Metadata = dict[str, tuple[str | None, str | None]]


def collapse_versions(
    recs: list[dict[str, Any]],
    metadata: Metadata,
    n: int,
    blocked_song_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """
    Keep the highest-ranked version of each song, drop versions of blocked songs
    (current song, context, songs already interacted with), trim to n, re-rank.
    Candidates without metadata are kept unchanged (nothing to compare against).
    """
    try:
        taken = VersionIndex()
        for sid in blocked_song_ids:
            title, artist = metadata.get(str(sid), (None, None))
            taken.add(title, artist)

        kept: list[dict[str, Any]] = []
        for rec in recs:
            title, artist = metadata.get(str(rec.get("song_id")), (None, None))
            if title and taken.contains(title, artist):
                continue
            taken.add(title, artist)
            kept.append(dict(rec))
            if len(kept) >= n:
                break
        for rank, rec in enumerate(kept, 1):
            rec["rank"] = rank
        return kept
    except Exception:
        # De-duplication is cosmetic; never let it break serving.
        logger.warning("Version de-duplication failed; returning model order", exc_info=True)
        trimmed = [dict(r) for r in recs[:n]]
        for rank, rec in enumerate(trimmed, 1):
            rec["rank"] = rank
        return trimmed


def build_metadata(
    song_ids: Iterable[str],
    catalog_lookup: Callable[[str], dict[str, Any] | None],
    db_lookup: Callable[[list[str]], Metadata],
) -> Metadata:
    """Title/artist for each ID: content catalog first, then stored song embeddings."""
    out: Metadata = {}
    missing: list[str] = []
    for sid in dict.fromkeys(str(s) for s in song_ids):
        meta = None
        try:
            meta = catalog_lookup(sid)
        except Exception:
            meta = None
        title = meta.get("title") if isinstance(meta, dict) else None
        artist = meta.get("artist") if isinstance(meta, dict) else None
        if isinstance(title, str) and title.strip():
            out[sid] = (title, artist if isinstance(artist, str) else None)
        else:
            missing.append(sid)
    if missing:
        try:
            for sid, pair in (db_lookup(missing) or {}).items():
                if isinstance(pair, tuple) and isinstance(pair[0], str) and pair[0].strip():
                    out[str(sid)] = pair
        except Exception:
            logger.debug("Metadata lookup in song_embeddings failed", exc_info=True)
    return out
