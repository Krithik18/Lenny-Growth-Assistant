"""Bounded token chunks preserving source text and observed speaker/timestamp labels."""

from dataclasses import dataclass
import re

import tiktoken

TURN = re.compile(r"^(?:(?P<speaker>[^\n()]+?)[ \t]+)?\((?:(?P<h>\d{1,2}):)?(?P<m>\d{2}):(?P<s>\d{2})\):", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    token_count: int
    start_char: int
    end_char: int
    speaker: str | None
    start_seconds: int | None
    end_seconds: int | None


class TranscriptChunker:
    def __init__(self, max_tokens: int = 400, overlap_tokens: int = 60):
        if not 0 <= overlap_tokens < max_tokens or max_tokens < 100:
            raise ValueError("Require max_tokens >= 100 and 0 <= overlap < max_tokens.")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.version = f"turn-char-v2-cl100k-{max_tokens}-{overlap_tokens}"

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text, disallowed_special=()))

    def split(self, text: str) -> list[Chunk]:
        # Character boundaries avoid cutting a Unicode character in half.
        turns = []
        speaker = None
        for match in TURN.finditer(text):
            speaker = match.group("speaker").strip() if match.group("speaker") else speaker
            seconds = int(match.group("h") or 0) * 3600 + int(match.group("m")) * 60 + int(match.group("s"))
            turns.append((match.start(), speaker, seconds))
        chunks = []
        start = 0
        while start < len(text):
            if not text[start:].strip():
                break
            low, high = start + 1, min(len(text), start + self.max_tokens * 12)
            end = low
            while low <= high:
                middle = (low + high) // 2
                if self.count(text[start:middle]) <= self.max_tokens:
                    end, low = middle, middle + 1
                else:
                    high = middle - 1
            if end < len(text):
                # Prefer the last paragraph/speaker boundary in the latter half.
                boundary = text.rfind("\n\n", start + (end - start) // 2, end)
                if boundary != -1:
                    end = boundary + 2
                else:
                    boundary = text.rfind(" ", start + (end - start) // 2, end)
                    if boundary != -1:
                        end = boundary + 1
            content = text[start:end]
            # Token counts are verified at the chosen boundary (BPE counts aren't
            # mathematically monotonic across every possible text prefix).
            while self.count(content) > self.max_tokens:
                end -= 1
                content = text[start:end]
            before = [turn for turn in turns if turn[0] <= start]
            inside = [turn for turn in turns if start < turn[0] < end]
            observed = before[-1:] + inside
            speakers = {turn[1] for turn in observed if turn[1]}
            times = [turn[2] for turn in observed]
            chunks.append(Chunk(
                len(chunks), content, self.count(content), start, end,
                next(iter(speakers)) if len(speakers) == 1 else None,
                min(times) if times else None, max(times) if times else None,
            ))
            if end == len(text):
                break
            # Select an overlapping suffix measured with the same tokenizer.
            next_start = end
            if self.overlap_tokens:
                low, high = start + 1, end
                while low <= high:
                    middle = (low + high) // 2
                    if self.count(text[middle:end]) <= self.overlap_tokens:
                        next_start, high = middle, middle - 1
                    else:
                        low = middle + 1
                while next_start < end and self.count(text[next_start:end]) > self.overlap_tokens:
                    next_start += 1
            start = max(start + 1, next_start)
        return chunks
