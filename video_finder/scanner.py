from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass
class VideoFile:
    path: str
    size: int
    mtime: float


@dataclass
class VideoGroup:
    key: str
    title: str
    files: list = field(default_factory=list)

    @property
    def total_size(self):
        return sum(f.size for f in self.files)

    @property
    def is_duplicate(self):
        """Same video stored more than once.

        Two files whose names normalize to the same key are duplicates:
        copies in different folders, or quality variants in the same
        folder (720p + 1080p).  Files in the *same* folder that differ
        only by a disc/part token (CD1/CD2) are one video in segments
        and are never duplicates.
        """
        if len(self.files) < 2:
            return False
        if self.is_segments:
            return False
        return True

    @property
    def is_segments(self):
        """Same folder, multiple disc/part files = one video in segments."""
        if len(self.files) < 2:
            return False
        folders = {os.path.normcase(os.path.dirname(f.path)) for f in self.files}
        if len(folders) != 1:
            return False
        return any(has_part_token(os.path.basename(f.path)) for f in self.files)


# Tokens that mark a disc/part of a multi-disc video.  Files differing only
# by one of these (CD1/CD2, DISC 1, PART 2, 碟1, 第1碟, ...) are one video.
DISC_PATTERNS = [
    re.compile(r"\b(?:cd|disc|part|pt)\.?\s*[-_:]?\s*\d+", re.I),
    re.compile(r"第\s*\d+\s*碟"),
    re.compile(r"\d+\s*碟"),
    re.compile(r"碟\s*\d+"),
]

# Common release/quality/codec markers that should not separate duplicates.
# These are safe for AV catalogue numbers: a bare 番号 (AVOP-123, LF-06,
# 080123-001, 090333_01) has no such tokens, and a year only matches at a
# word boundary, so it is never stripped out of a digit run.
QUALITY_PATTERNS = [
    re.compile(r"\b\d{3,4}[pi]\b", re.I),
    re.compile(r"\b2160p\b", re.I),
    re.compile(r"\b4k\b", re.I),
    re.compile(r"\b(?:uhd|hdr10\+?|hdr|dv)\b", re.I),
    re.compile(r"\b(?:blu-?ray|bd-?rip|br-?rip|dvd-?rip|web-?dl|web-?rip|hdtv|hdrip)\b", re.I),
    re.compile(r"\b(?:x264|x265|h264|h265|hevc|avc|av1)\b", re.I),
    re.compile(r"\b(?:aac|ac3|eac3|ec3|dts|ddp\d*\.?\d*|atmos|truehd|flac|mp3|lpcm)\b", re.I),
    re.compile(r"\b(?:10bit|8bit|hi10p)\b", re.I),
    re.compile(r"\b\d{2,3}\s*fps\b", re.I),
    re.compile(r"\b(?:remux|proper|repack|internal|limited|complete)\b", re.I),
    re.compile(r"\[\s*-?\d{4}\s*\]"),
    re.compile(r"\b19\d{2}\b"),
    re.compile(r"\b20\d{2}\b"),
]


def has_part_token(name: str) -> bool:
    """True when a file name carries a CD/DISC/PART/碟 marker."""
    stem = os.path.splitext(name)[0]
    return any(pat.search(stem) for pat in DISC_PATTERNS)


def strip_disc(stem: str) -> str:
    for pat in DISC_PATTERNS:
        stem = pat.sub(" ", stem)
    return stem


def strip_quality(stem: str) -> str:
    for pat in QUALITY_PATTERNS:
        stem = pat.sub(" ", stem)
    return stem


def normalize_stem(stem: str, do_strip_disc: bool = True, do_strip_quality: bool = True) -> str:
    """Reduce a file name stem to a stable duplicate-detection key."""
    s = stem
    if do_strip_disc:
        s = strip_disc(s)
    if do_strip_quality:
        s = strip_quality(s)
    s = "".join(ch if ch.isalnum() else " " for ch in s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


def display_title(stem: str, do_strip_disc: bool = True, do_strip_quality: bool = True) -> str:
    """A human friendly title: the original name minus disc and quality tokens.

    For AV catalogue numbers this yields the clean 番号, e.g.
    ``AVOP-123.1080p.x264`` -> ``AVOP-123``.
    """
    s = stem
    if do_strip_disc:
        s = strip_disc(s)
    if do_strip_quality:
        s = strip_quality(s)
    s = re.sub(r"\s+", " ", s).strip(" \t-_.")
    return s if s else stem


def group_files(files: list, cfg) -> list:
    """Group video files into videos by their normalized names."""
    groups: dict = {}
    order: list = []
    for vf in files:
        stem = os.path.splitext(os.path.basename(vf.path))[0]
        key = normalize_stem(stem, cfg.strip_disc, cfg.strip_quality)
        if not key:
            key = "raw:" + stem.lower()
        group = groups.get(key)
        if group is None:
            group = VideoGroup(key=key,
                               title=display_title(stem, cfg.strip_disc, cfg.strip_quality),
                               files=[])
            groups[key] = group
            order.append(group)
        group.files.append(vf)
    for group in order:
        group.files.sort(key=lambda f: f.path.lower())
    order.sort(key=lambda g: (g.title.lower(), g.key))
    return order