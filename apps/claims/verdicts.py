"""Plain verdict text from status + reasons. Pre-written templates.

English is reviewed; pcm, ha, yo and ig are drafts awaiting native-speaker review.

Never free-form AI text. Never names a party or a winner.
"""

from __future__ import annotations

from .models import ClaimAssessment

HEADLINE = {
    "unconfirmed": {
        "en": "Not confirmed",
        "pcm": "We never confirm am",
        "ha": "Ba a tabbatar ba",
        "yo": "A ko ti jerisi re",
        "ig": "Akwadobeghi ya",
    },
    "corroborated": {
        "en": "Corroborated by independent sources",
        "pcm": "Different people wey no know each other confirm am",
        "ha": "Majiyoyi daban-daban masu zaman kansu sun tabbatar",
        "yo": "Awon orisun otooto ti jerisi re",
        "ig": "Ndi isi mmalite di iche iche akwadoola ya",
    },
    "confirmed_by_source": {
        "en": "Confirmed by {authority}",
        "pcm": "{authority} confirm am",
        "ha": "{authority} ta tabbatar",
        "yo": "{authority} ti jerisi re",
        "ig": "{authority} akwadoola ya",
    },
    "refuted_by_source": {
        "en": "Denied by {authority}",
        "pcm": "{authority} talk say e no true",
        "ha": "{authority} ta ce ba gaskiya ba ne",
        "yo": "{authority} so pe ko je otito",
        "ig": "{authority} kwuru na o bughi eziokwu",
    },
}
REASON = {
    "no_supporting_evidence": {
        "en": "No one has supported this claim with evidence yet.",
        "pcm": "Nobody don bring evidence for am yet.",
        "ha": "Babu wanda ya kawo shaida kan wannan magana tukuna.",
        "yo": "Ko si eni to ti mu eri wa fun oro yii sibesibe.",
        "ig": "O nweghi onye wetara ihe akaebe maka okwu a ugbu a.",
    },
    "single_origin": {
        "en": "Only one source has reported it.",
        "pcm": "Na only one person report am.",
        "ha": "Mutum daya ne kadai ya ruwaito shi.",
        "yo": "Eniyan kan soso lo royin re.",
        "ig": "O bu naani otu onye koro ya.",
    },
    "forwards_only": {
        "en": "It has been forwarded {forwards} times, but forwards are not confirmation.",
        "pcm": "People don forward am {forwards} times, but forward no be confirmation.",
        "ha": "An tura shi sau {forwards}, amma turawa ba tabbaci ba ne.",
        "yo": "Won ti fi ranse ni igba {forwards}, sugbon fifi ranse ki i se ijerisi.",
        "ig": "Ezigharila ya ugboro {forwards}, mana izigharia abughi nkwado.",
    },
    "forwards_only_one": {
        "en": "It was forwarded to you, and forwards are not confirmation.",
        "pcm": "Na forward dem send you, and forward no be confirmation.",
        "ha": "An tura maka shi ne, kuma turawa ba tabbaci ba ne.",
        "yo": "Won fi ranse si o ni, fifi ranse ki i se ijerisi.",
        "ig": "O bu ozi e zigharitere gi, izigharia abughi nkwado.",
    },
    "conflicting_evidence": {
        "en": "Other reports say the opposite.",
        "pcm": "Some other reports talk the opposite.",
        "ha": "Wasu rahotanni sun fadi akasin haka.",
        "yo": "Awon iroyin miiran so idakeji.",
        "ig": "Akuko ndi ozo na-ekwu ihe di iche.",
    },
    "missing_observation_time": {
        "en": "We don't know when it was seen.",
        "pcm": "We no know when dem see am.",
        "ha": "Ba mu san lokacin da aka gan shi ba.",
        "yo": "A ko mo igba ti won ri i.",
        "ig": "Anyi amaghi mgbe ahuru ya.",
    },
    "outside_time_window": {
        "en": "The reports were seen too far apart in time to confirm each other.",
        "pcm": "The reports far from each other for time, so dem no fit confirm each other.",
        "ha": "Lokutan rahotannin sun yi nisa da juna, don haka ba za su tabbatar da juna ba.",
        "yo": "Akoko awon iroyin naa jinna sira won ju, nitori naa won ko le jerisi ara won.",
        "ig": "Oge akuko ndi a di anya n'etiti onwe ha, ya mere ha enweghi ike ikwado ibe ha.",
    },
    "independent_sources_agree": {
        "en": "{origins} independent sources agree, seen at about the same time.",
        "pcm": "{origins} different sources talk the same thing around the same time.",
        "ha": "Majiyoyi {origins} masu zaman kansu sun fadi abu daya a kusan lokaci guda.",
        "yo": "Awon orisun {origins} ti ko mo ara won so ohun kan naa ni nnkan bi akoko kan naa.",
        "ig": "Isi mmalite {origins} na-adabereghi onwe ha kwuru otu ihe n'ihe dika otu oge.",
    },
    "authority_statement": {
        "en": "Official statement from {source}.",
        "pcm": "Official talk from {source}.",
        "ha": "Sanarwa a hukumance daga {source}.",
        "yo": "Atejade osise lati odo {source}.",
        "ig": "Nkwuputa ndi isi si na {source}.",
    },
    "authorities_conflict": {
        "en": "Official sources disagree.",
        "pcm": "Official sources no agree.",
        "ha": "Majiyoyin hukuma ba su yi daidai ba.",
        "yo": "Awon orisun ijoba ko fohun sokan.",
        "ig": "Ndi isi mmalite ochichi ekwekoritaghi.",
    },
}
UNKNOWN = {
    "en": "What we don't know: who saw it first and whether it is still happening.",
    "pcm": "Wetin we no know: who first see am and whether e still dey happen.",
    "ha": "Abin da ba mu sani ba: wanda ya fara ganinsa, da ko har yanzu yana faruwa.",
    "yo": "Ohun ti a ko mo: eni ti o koko ri i, ati boya o si n sele.",
    "ig": "Ihe anyi amaghi: onye buru uzo hu ya, na ma o ka na-eme.",
}


def render(assessment: ClaimAssessment | None, language: str = "en") -> dict[str, object]:
    lang = language if language in ("en", "pcm", "ha", "yo", "ig") else "en"
    if assessment is None:
        return {
            "status": "checking",
            "headline": {
                "en": "Checking sources…",
                "pcm": "We dey check am…",
                "ha": "Muna dubawa…",
                "yo": "A n se ayewo…",
                "ig": "Anyi na-enyocha…",
            }[lang],
            "reasons": [],
            "unknown": UNKNOWN[lang],
            "language": lang,
        }
    head = HEADLINE[assessment.status][lang].format(authority=assessment.authority or "")
    lines = []
    for r in assessment.reasons[:2]:
        code = r["code"]
        if code == "forwards_only" and assessment.forward_count <= 1:
            code = "forwards_only_one"
        tmpl = REASON.get(code)
        if tmpl:
            detail = {
                "forwards": assessment.forward_count,
                "origins": assessment.origin_count,
                "source": assessment.authority,
                **r.get("detail", {}),
            }
            lines.append(tmpl[lang].format(**detail))
    return {
        "status": assessment.status,
        "headline": head,
        "reasons": lines,
        "unknown": UNKNOWN[lang],
        "language": lang,
    }


def sms_text(assessment: ClaimAssessment | None, language: str = "en") -> str:
    v = render(assessment, language)
    return " ".join([str(v["headline"]) + ".", *v["reasons"]])[:300]
