"""Keyword check for self-harm messages, used ONLY when Claude can't answer (API error, no usable reply).
Normally the model recognizes these on its own (prompt Rule 2); this list is the safety net for when it
can't. Keep it in this one file so it can be reviewed. Matching is deliberately broad: a false match only
adds a 988 line and a log flag, a miss means a person in crisis gets a plain error message.

Each entry is (language of the reply, regular expression). Matching is case-insensitive, and apostrophes
and accents are folded for the Latin-script languages, so write those patterns without accents/apostrophes
where the letter varies. Punjabi patterns are Gurmukhi and match word stems (ਚਾਹ covers ਚਾਹੁੰਦਾ/ਚਾਹੁੰਦੀ).
Add phrases freely; tests/test_crisis.py checks the examples.
"""

import re
import unicodedata

CRISIS_PHRASES: list[tuple[str, str]] = [
    # English
    ("en", r"\bkill(ing)?\s+(my\s*self|myself)\b"),
    ("en", r"\b(want|wanna|wish)\s*(to|2)?\s*die\b"),
    ("en", r"\bwant\s+to\s+be\s+dead\b"),
    ("en", r"\b(hurt|harm|cut)(ting)?\s+(my\s*self|myself)\b"),
    ("en", r"\bsuicid(e|al)\b"),
    ("en", r"\b(end|take)\s+(my\s+own|my)\s+life\b"),
    ("en", r"\bend\s+it\s+all\b"),
    ("en", r"\b(dont|do not)\s+want\s+to\s+(live|be\s+alive|be\s+here)\b"),
    ("en", r"\bbetter\s+off\s+dead\b"),
    # Spanish (accents are folded away before matching)
    ("es", r"\bmatarme\b"),
    ("es", r"\bquiero\s+morir(me)?\b"),
    ("es", r"\bquisiera\s+morir(me)?\b"),
    ("es", r"\bsuicid\w*"),
    ("es", r"\bquitarme\s+la\s+vida\b"),
    ("es", r"\b(acabar|terminar)\s+con\s+(mi\s+vida|todo)\b"),
    ("es", r"\bno\s+quiero\s+(vivir|seguir\s+viviendo|estar\s+vivo|estar\s+viva)\b"),
    ("es", r"\bhacerme\s+(dano|mal)\b|\blastimarme\b|\bcortarme\b"),
    ("es", r"\bmejor\s+muerto\b|\bmejor\s+muerta\b"),
    # Punjabi, Gurmukhi script (the message is NFC-normalized first, as are these patterns)
    ("pa", r"ਖ\u0a3c?ੁਦਕੁਸ\u0a3c?ੀ"),  # ਖੁਦਕੁਸ਼ੀ (suicide); \u0a3c is the optional nukta dot
    ("pa", r"ਮਰਨਾ\s+ਚਾਹ|ਮਰ\s+ਜਾਣਾ\s+ਚਾਹ|ਮਰਨ\s+ਨੂੰ\s+ਦਿਲ"),
    ("pa", r"ਜੀ(ਉ|ਣ|ਵ)\S*\s+ਨਹੀਂ\s+ਚਾਹ|ਜਿ(ਉ|ਣ)\S*\s+ਨਹੀਂ\s+ਚਾਹ"),
    ("pa", r"ਆਪਣੀ\s+ਜਾਨ\s+(ਲੈ|ਦੇ)"),
    ("pa", r"ਆਪਣੇ\s+ਆਪ\s+ਨੂੰ\s+(ਮਾਰ|ਖ\u0a3c?ਤਮ|ਨੁਕਸਾਨ|ਸੱਟ)"),
    ("pa", r"ਆਪਣੀ\s+ਜ਼ਿੰਦਗੀ\s+(ਖ\u0a3c?ਤਮ)"),
    # Punjabi written in Latin letters (replied to in English, which the customer can read)
    ("en", r"\bkhud\s*kushi\b|\bkhudkhushi\b"),
    ("en", r"\bmarna\s+chah(unda|undi|nda|ndi)\b"),
    ("en", r"\bjeena\s+nahi\s+chah|\bjeeva\s+nahi\s+chah"),
    ("en", r"\bapni\s+jaan\s+(le|de)"),
]


def _fold(text: str) -> str:
    """Lowercase, drop Latin accent marks and apostrophes, and NFC-normalize (so Gurmukhi letters with a
    dot, like ਸ਼, compare equal however they were typed)."""
    out = [
        ch for ch in unicodedata.normalize("NFD", text.lower())
        if not ("\u0300" <= ch <= "\u036f") and ch not in "'\u2019\u2018`"
    ]
    return unicodedata.normalize("NFC", "".join(out))


_COMPILED = [(lang, re.compile(unicodedata.normalize("NFC", pattern), re.IGNORECASE)) for lang, pattern in CRISIS_PHRASES]


def detect_crisis(message: str) -> str | None:
    """Returns the language to answer in ('en', 'es' or 'pa') if the message looks like a self-harm
    message, otherwise None."""
    folded = _fold(message)
    for lang, pattern in _COMPILED:
        if pattern.search(folded):
            return lang
    return None
