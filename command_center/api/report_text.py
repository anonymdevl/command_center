"""A written report or answer made to read like a document, not a chat reply.

The analyst writes markdown. Whatever its instructions say (api/reports.py BRIEF), a
model will sometimes open a report with a heading that repeats the report's own title
("Executive Summary" printed, then "Executive Summary: Gigmann Medical Supplies Ltd"),
decorate with emoji, open with "Here is the report", or list its recommendations as
"**Recommendation:** ..." bullets. This puts those right, the same way for the screen,
the PDF, the email and the copy:

    tidy(md, title, business, report=True)

  - a heading (or a bold line) at the top that repeats the title or the business's name
    is dropped, and so is any later heading that is the title again;
  - emoji are removed;
  - a chatty first or last line ("Here is ...", "Let me know ...") is dropped;
  - bullets are "-" and numbered items "1.", whatever the model used;
  - in a report, headings are in Title Case, and the items under "Recommendations" are
    a numbered list without a "Recommendation:" label (the heading says what they are).

It only removes and reformats; it never adds a word or a figure.
"""

from __future__ import annotations

import re

SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor",
               "of", "on", "or", "per", "the", "to", "via", "vs", "with"}
# Pictographs, symbols and their joiners. The ticks and crosses (U+2713, U+2717) a table
# may use as values are kept.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U00002712\U00002714-\U00002716"
                   "\U00002718-\U000027BF\U00002B00-\U00002BFF\U0000FE0F\U0000200D\U000020E3]")
CHATTY = re.compile(r"^\s*(?:here(?:'s| is| are)|below is|below are|i have|i've|i hope|let me|"
                    r"let's|great|sure|certainly|of course|feel free|happy to|hope this)\b",
                    re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BOLD_LINE = re.compile(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*:?\s*$")
BULLET = re.compile(r"^(\s*)(?:[*•●▪◦‣–—]|-)\s+")
NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+")
REC_LABEL = re.compile(r"^(?:\*\*|__)?\s*recommendation\s*\d*\s*[:.\-–—]\s*(?:\*\*|__)?\s*"
                       r"|^(?:\*\*|__)\s*recommendation\s*\d*\s*(?:\*\*|__)\s*[:.\-–—]\s*", re.I)
FILLER = {"for", "the", "of", "at", "as", "on", "report", "ltd", "limited", "plc", "inc",
          "and", "to", "date", "period", "week", "month", "year", "ending", "ended"}
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun",
          "jul", "aug", "sep", "sept", "oct", "nov", "dec"}


def _norm(text: str) -> str:
    text = re.sub(r"[*_`#]", "", str(text or "")).lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def repeats_title(heading: str, title: str, business: str = "") -> bool:
    """A heading that only says the report's title (and perhaps the business, a date or
    "report") again -- the document's own title block already says it."""
    h, t, b = _norm(heading), _norm(title), _norm(business)
    if not h:
        return False
    if h == t or (b and h == b):
        return True
    if t and t in h:
        rest = (" " + h + " ").replace(" " + t + " ", " ").split()
        allowed = set(b.split()) | FILLER | MONTHS
        return all(w in allowed or w.isdigit() for w in rest)
    return False


def title_case(text: str) -> str:
    """Title Case for a heading: each word capitalised except short joining words;
    acronyms, figures and words with capitals of their own (GHS, KPIs, ERPNext, Q3) as
    written."""
    words = text.split(" ")
    out = []
    last = len(words) - 1
    for i, w in enumerate(words):
        if not w:
            out.append(w)
            continue
        letters = [c for c in w if c.isalpha()]
        if not letters or any(c.isdigit() for c in w) or sum(c.isupper() for c in w[1:]) > 0:
            out.append(w)
            continue
        bare = re.sub(r"[^A-Za-z]", "", w).lower()
        after_colon = i > 0 and words[i - 1].endswith((":", "—", "–"))
        if 0 < i < last and bare in SMALL_WORDS and not after_colon:
            out.append(w.lower())
            continue
        out.append("-".join(_cap(p) for p in w.split("-")))
    return " ".join(out)


def _cap(word: str) -> str:
    for j, c in enumerate(word):
        if c.isalpha():
            return word[:j] + c.upper() + word[j + 1:]
    return word


def _blocks(lines: list) -> list:
    """Paragraph boundaries: (start, end) line indexes of each run of non-blank lines,
    fenced blocks kept whole."""
    out, i, n = [], 0, len(lines)
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        start = i
        if lines[i].lstrip().startswith("```"):
            i += 1
            while i < n and not lines[i].lstrip().startswith("```"):
                i += 1
            i += 1
        else:
            while i < n and lines[i].strip() and not lines[i].lstrip().startswith("```"):
                i += 1
        out.append((start, min(i, n)))
    return out


def tidy(md: str, title: str = "", business: str = "", report: bool = True) -> str:
    if not md:
        return md or ""
    lines = str(md).replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # Emoji out, everywhere but inside fenced blocks (figures and charts are data).
    fenced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            if EMOJI.search(line):
                line = re.sub(r"[ \t]{2,}", " ", EMOJI.sub("", line))
                lines[i] = re.sub(r"(?<=\S) +([,.;:!?)])", r"\1", line).rstrip()

    # A heading or bold line at the top that says the title again.
    for _ in range(3):
        top = next((j for j, l in enumerate(lines) if l.strip()), None)
        if top is None:
            break
        m = HEADING.match(lines[top].strip()) or BOLD_LINE.match(lines[top])
        if m and repeats_title(m.groups()[-1], title, business):
            del lines[top]
            continue
        break

    # A chatty opening or closing line.
    blocks = _blocks(lines)
    drop = set()
    for start, end in (blocks[:1] + blocks[-1:]) if blocks else []:
        text = " ".join(lines[start:end]).strip()
        if (end - start <= 2 and len(text) < 220 and CHATTY.match(text)
                and not lines[start].lstrip().startswith(("```", "|", "#"))):
            drop.update(range(start, end))
    lines = [l for j, l in enumerate(lines) if j not in drop]

    out, fenced, in_recs, n = [], False, False, 0
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        if fenced:
            out.append(line)
            continue
        h = HEADING.match(line.strip())
        if h:
            text = re.sub(r"^(?:\*\*|__)(.*)(?:\*\*|__)$", r"\1", h.group(2).strip()).strip()
            if title and _norm(text) == _norm(title):
                continue  # the title again, further down
            if report:
                text = title_case(text)
            in_recs = report and _norm(text).startswith(("recommendation", "recommended action",
                                                         "next steps", "actions"))
            n = 0
            out.append(f"{h.group(1)} {text}")
            continue
        b = BULLET.match(line)
        num = NUMBERED.match(line)
        if b or num:
            indent = (b or num).group(1)
            body = line[(b or num).end():]
            if in_recs and not indent:
                n += 1
                body = REC_LABEL.sub("", body, count=1).lstrip()
                body = body[:1].upper() + body[1:]
                out.append(f"{n}. {body}")
            elif num:
                out.append(f"{indent}{num.group(2)}. {body}")
            else:
                out.append(f"{indent}- {body}")
            continue
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
