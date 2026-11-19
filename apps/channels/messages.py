"""Pre-written message templates. Alerts never use free-form AI text.

English is the reviewed source. Pidgin (pcm), Hausa (ha), Yoruba (yo) and Igbo (ig) drafts need
native-speaker review before real use. They are written in plain letters (no tone marks, dots or
hooks) so they stay in the GSM-7 SMS alphabet, as SMS in these languages commonly is.
"""

from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    "result.matches": {
        "en": "{app}: PU {code} result matches IReV ({n} independent uploads). {url}",
        "pcm": "{app}: PU {code} result don match IReV ({n} different people upload am). {url}",
        "ha": "{app}: Sakamakon PU {code} ya yi daidai da IReV (mutane {n} daban-daban sun "
        "dora). {url}",
        "yo": "{app}: Esi PU {code} ba ti IReV mu ({n} eniyan otooto lo fi ranse). {url}",
        "ig": "{app}: Nsonaazu PU {code} kwekoritara IReV (mmadu {n} di iche iche zitere ya). "
        "{url}",
    },
    "result.mismatch": {
        "en": "{app}: PU {code} wall result does NOT match IReV ({n} independent uploads). "
        "Observers have been alerted. {url}",
        "pcm": "{app}: PU {code} result wey dem paste for wall no match IReV ({n} different "
        "people confirm am). Observers don hear. {url}",
        "ha": "{app}: Sakamakon da aka lika a bango a PU {code} BAI yi daidai da IReV ba "
        "(mutane {n} daban-daban sun tabbatar). An sanar da masu sa ido. {url}",
        "yo": "{app}: Esi ti won le mo ogiri ni PU {code} KO ba ti IReV mu ({n} eniyan otooto "
        "lo jerisi). A ti so fun awon oluwoye. {url}",
        "ig": "{app}: Nsonaazu a mara na mgbidi na PU {code} EKWEKORITAGHI IReV (mmadu {n} di "
        "iche iche kwadoro ya). Agwala ndi na-ele anya. {url}",
    },
    "result.cancelled": {
        "en": "{app}: PU {code} result sheet is marked Result Cancelled. {url}",
        "pcm": "{app}: Dem don cancel PU {code} result for the sheet. {url}",
        "ha": "{app}: An soke sakamakon PU {code} a takardar sakamako. {url}",
        "yo": "{app}: Won ti fagile esi PU {code} lori iwe esi. {url}",
        "ig": "{app}: Akagbuola nsonaazu PU {code} na mpempe akwukwo nsonaazu. {url}",
    },
    "pu.relocated": {
        "en": "{app}: Your polling unit {old} has moved. Vote at {new_name} ({new}). "
        "{landmark}. Source: {source}",
        "pcm": "{app}: Your polling unit {old} don move. Go vote for {new_name} ({new}). "
        "{landmark}. Source: {source}",
        "ha": "{app}: An mayar da rumfar zabenku {old}. Ku je ku yi zabe a {new_name} ({new}). "
        "{landmark}. Majiya: {source}",
        "yo": "{app}: Won ti gbe ibudo idibo yin {old} kuro. E lo dibo ni {new_name} ({new}). "
        "{landmark}. Orisun: {source}",
        "ig": "{app}: Ebugharila ebe ntuli aka unu {old}. Gaa tuo vootu na {new_name} "
        "({new}). {landmark}. Isi mmalite: {source}",
    },
    "otp.code": {
        "en": "{app} code: {code}. It expires in 5 minutes. Don't share it.",
        "pcm": "{app} code: {code}. E go expire for 5 minutes. No give anybody.",
        "ha": "Lambar {app}: {code}. Za ta kare cikin minti 5. Kada ku ba kowa ita.",
        "yo": "Koodu {app}: {code}. Yoo pari ni iseju 5. E ma fi han enikeni.",
        "ig": "Koodu {app}: {code}. O ga-agwu n'ime nkeji 5. Egosila onye obula.",
    },
}

SUPPORTED = {"en", "pcm", "ha", "yo", "ig"}


def render(key: str, language: str, **values: object) -> tuple[str, str]:
    """Return (text, language_used). Unreviewed languages fall back to English."""
    lang = language if language in SUPPORTED else "en"
    template = MESSAGES[key].get(lang) or MESSAGES[key]["en"]
    return template.format(**values).strip(), lang
