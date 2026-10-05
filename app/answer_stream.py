"""Finish streamed prose at sentence boundaries without pretending to count model tokens."""
import re

CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
CITATION_LINE = re.compile(r"(?:\s*\[\d+(?:\s*,\s*\d+)*\]\s*)+")
ABBREVIATIONS = frozenset("dr prof kab prov kec kel no rp dsb dll dst hlm hal vol s.d a.n u.p pt cv jl dkk e.g i.e".split())
CLOSERS = "\"'\u201d\u2019)*_"


def sentence_ends(text, final=False):
    """Offsets include trailing citations. Wait for lookahead across split stream chunks."""
    ends = []
    for mark in re.finditer(r"[.!?]+", text):
        start, end = mark.span()
        if ".." in mark.group():
            continue
        segment_start = ends[-1] if ends else 0
        if not any(c.isalpha() for c in text[segment_start:start]):
            continue  # A list number or a citation alone is not a sentence.
        if mark.group() == ".":
            line_prefix = text[:start].rsplit("\n", 1)[-1]
            if re.fullmatch(r"\s*(?:[-*]\s*)?(?:\d+|[A-Za-z])", line_prefix):
                continue  # Numbered/list-letter markers, including after a heading.
            if start and text[start-1].isdigit() and end < len(text) and text[end].isdigit():
                continue
            word = re.search(r"([^\W\d_]+(?:\.[^\W\d_]+)*)$", text[:start])
            if word and word.group(1).casefold() in ABBREVIATIONS:
                continue
        if end < len(text) and not (text[end].isspace() or text[end] in CLOSERS + "["):
            continue  # Decimal fragments, URL components and dotted abbreviations.
        while end < len(text) and text[end] in CLOSERS:
            end += 1
        complete = True
        while True:
            cursor = end
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            citation = CITATION.match(text, cursor)
            if citation:
                end = citation.end()
                while end < len(text) and text[end] in CLOSERS:
                    end += 1
                continue
            if cursor == len(text) and not final:
                complete = False
            elif not final and re.fullmatch(r"\[[\d,\s]*", text[cursor:]):
                complete = False
            break
        if complete:
            ends.append(end)
    return ends


def remove_duplicate_citation_lines(text):
    seen, lines = set(), []
    for line in text.strip().splitlines():
        refs = {n for group in CITATION.findall(line) for n in re.findall(r"\d+", group)}
        if CITATION_LINE.fullmatch(line) and refs and refs <= seen:
            continue
        lines.append(line)
        seen.update(refs)
    return "\n".join(lines).strip()


class AnswerStream:
    def __init__(self, max_tokens):
        # A character-based soft budget, NOT an exact token count or NDJSON chunk count.
        self.soft_characters = max(80, int(max_tokens * 2.4))
        self.text = ""
        self.stopped = False

    def push(self, fragment):
        previous = len(self.text)
        self.text += fragment
        if len(self.text) >= self.soft_characters:
            boundary = next((end for end in sentence_ends(self.text) if end >= self.soft_characters), None)
            if boundary is not None:
                self.text = self.text[:boundary]
                self.stopped = True
        return self.text[previous:]

    def finish(self, provider_reason=None):
        text = self.text
        reason = "sentence_boundary" if self.stopped else "model_stop"
        trimmed = False
        if not self.stopped and provider_reason == "length":
            ends = sentence_ends(text, final=True)
            complete = text[:ends[-1]] if ends else ""
            trimmed = complete.strip() != text.strip()
            text = complete
            reason = "token_limit_trimmed" if trimmed else "token_limit_complete"
            if not text.strip():
                reason = "token_limit_no_sentence"
        self.text = remove_duplicate_citation_lines(text)
        return self.text, {
            "output_finish_reason": reason,
            "stopped_early": self.stopped,
            "trimmed_incomplete_sentence": trimmed,
            "soft_character_limit": self.soft_characters,
        }
