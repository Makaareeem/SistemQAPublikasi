"""Lightweight checks catch unsupported numbers/citations, not semantic truth."""
import re

ABSTENTION = "Informasi yang diminta belum ditemukan dalam sumber yang terambil. Coba perjelas indikator, wilayah, atau periode."
UNVERIFIED = "Jawaban model belum dapat diverifikasi terhadap sumber yang terambil. Silakan periksa cuplikan sumber di bawah."
CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def normalized(text):
    return " ".join(text.split()).casefold()


def numbers(text):
    return set(NUMBER.findall(CITE.sub("", text)))


def citation_ids(text):
    return [int(number) for group in CITE.findall(text) for number in re.findall(r"\d+", group)]


def _basic_answer_checks(answer, docs, question=None):
    if not isinstance(answer, str) or not answer.strip():
        return ["Jawaban kosong."]
    refs = citation_ids(answer)
    if any(i < 1 or i > len(docs) for i in refs):
        return ["Nomor sitasi tidak tersedia."]
    if not refs:
        # Only accept an explicit abstention without numbers; factual uncited output is unverified.
        if not numbers(answer) and re.search(r"tidak (?:tersedia|ditemukan|memuat|memiliki)|belum (?:ditemukan|tersedia)|tidak cukup", answer, re.I):
            return []
        return ["Jawaban tidak memiliki sitasi."]
    for clause in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", answer):
        if not numbers(clause):
            continue
        ids = citation_ids(clause)
        if not ids:
            return ["Klaim angka tidak memiliki sitasi pada kalimatnya."]
        evidence = " ".join(docs[i-1].page_content for i in ids)
        if not numbers(clause).issubset(numbers(evidence)):
            return ["Ada angka yang tidak terdapat pada sumber yang disitasi."]
        # Deliberately conservative: target/projection cannot support an unqualified numeric claim.
        claim_numbers = {n for n in numbers(clause) if not re.fullmatch(r"(19|20)\d{2}", n)}
        passages = [p for p in re.split(r"(?<=[.!?])\s+|\n+", evidence)
                    if claim_numbers and claim_numbers.issubset(numbers(p))]
        if passages and all(re.search(r"\b(target|sasaran|proyeksi|rencana)\b", p, re.I) for p in passages) and not re.search(r"\b(target|sasaran|proyeksi|rencana|belum|tidak)\b", clause, re.I):
            return ["Sumber memuat target/proyeksi; jenis angka belum jelas dalam jawaban."]
    return population_warnings(answer, docs, question)

 
def check_answer(answer, docs, question=None):
    issues = _basic_answer_checks(answer, docs, question)
    if isinstance(answer, str) and answer.strip():
        issues += population_warnings(answer, docs, question)
    return list(dict.fromkeys(issues))


_POPULATIONS = (
    (r"\b(?:anak|usia dini)\b", "anak"),
    (r"\b(?:pemuda|remaja)\b", "pemuda/remaja"),
    (r"\b(?:lansia|lanjut usia)\b", "lansia"),
)


def population_warnings(answer, docs, question=None):
    """Flag only explicit subgroup titles. This does not establish semantic entailment."""
    refs = citation_ids(answer)
    if not refs:
        return []
    cited = [docs[i-1] for i in refs if 1 <= i <= len(docs)]
    if not cited:
        return []
    for pattern, label in _POPULATIONS:
        if question and re.search(pattern, question, re.I):
            continue
        if all(re.search(pattern, str(d.metadata.get("document_title", "")), re.I) for d in cited):
            if numbers(answer) and not re.search(pattern, answer, re.I):
                return [f"Sumber yang disitasi membahas kelompok {label}, tetapi jawaban belum menyebut batas kelompok tersebut. Angkanya belum tentu mewakili seluruh penduduk."]
    return []


_STOPWORDS = set("apa apakah bagaimana berapa yang dan di ke dari pada untuk dengan menurut tahun adalah itu ini tersebut saya ingin tentang publikasi bps".split())


def source_excerpt(question, text):
    """Select a literal passage around the most relevant sentence, never fabricate punctuation."""
    if not text.strip():
        return ""
    bounds = [0] + [m.end() for m in re.finditer(r"(?<=[.!?])\s+|\n+", text)] + [len(text)]
    spans = [(a,b) for a,b in zip(bounds,bounds[1:]) if text[a:b].strip()]
    terms = set(re.findall(r"\w+", question.casefold())) - _STOPWORDS
    def score(span):
        words = set(re.findall(r"\w+", text[span[0]:span[1]].casefold()))
        return sum(3 if word.isdigit() else 1 for word in terms & words)
    index = max(range(len(spans)), key=lambda i: score(spans[i]))
    start,end = spans[index]
    # Adjacent text preserves qualifiers (e.g. targets) and explanatory context.
    if index > 0 and end-spans[index-1][0] <= 1300:
        start = spans[index-1][0]
    if index+1 < len(spans) and spans[index+1][1]-start <= 1800:
        end = spans[index+1][1]
    return text[start:end].strip()
