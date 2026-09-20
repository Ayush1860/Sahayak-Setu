"""The profile vocabulary. One source of truth for extractor and matcher.

PROFILE_FIELDS must stay identical to the profile_field enum in
schema/scheme.schema.json. test_fields.py fails if they drift, because a
field name that exists on one side and not the other produces schemes that
silently never match - a failure that looks like working software.
"""

from __future__ import annotations

PROFILE_FIELDS: tuple[str, ...] = (
    "age",
    "caste_category",
    "gender",
    "area_type",
    "has_existing_unit",
    "has_udyam_registration",
    "annual_income_inr",
    "state",
    "district",
    "sector",
    "investment_planned_inr",
)

# Python type each field must hold once extracted. Anything else is dropped.
FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "age": int,
    "caste_category": str,
    "gender": str,
    "area_type": str,
    "has_existing_unit": bool,
    "has_udyam_registration": bool,
    "annual_income_inr": (int, float),
    "state": str,
    "district": str,
    "sector": str,
    "investment_planned_inr": (int, float),
}

# Closed value sets. A field listed here only accepts these values.
#
# YOU OWN THESE LISTS. Whatever appears here must also be what appears in the
# "values" array of the matching criteria in /schemes/*.json. If a scheme says
# "SC" and the extractor emits "sc", the criterion never passes and nobody is
# told why. Keep them lowercase on both sides.
VOCABULARIES: dict[str, tuple[str, ...]] = {
    "area_type": ("rural", "urban"),
    "gender": ("female", "male", "other"),
    "caste_category": ("general", "obc", "sc", "st"),
    # Broad activity class, not a description of the trade. Schemes are
    # written against classes like "manufacturing", so the extractor has to
    # emit one of these or nothing. "Leaf plate making" is manufacturing;
    # if the model cannot tell, it omits the field and the criterion goes
    # UNKNOWN, which is recoverable.
    "sector": ("manufacturing", "services", "trading", "agriculture", "other"),
}

# Free-text fields that schemes reference by a stable slug. "Madhya Pradesh"
# and "madhya pradesh" must both match a criterion written as
# "madhya_pradesh", or the scheme silently never fires.
SLUG_FIELDS: tuple[str, ...] = ("state", "district")

# Sane bounds. A value outside these is treated as a misread, not a fact.
NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "age": (14, 100),
    "annual_income_inr": (0, 100_000_000),
    "investment_planned_inr": (0, 1_000_000_000),
}


# --------------------------------------------------------------- choices
#
# What the interview offers instead of a text box. Someone answering on a
# borrowed phone should not have to type, and a tap cannot be misread.
#
# Buckets, not numbers. "26 to 35" is what the person actually knows; a
# midpoint would be a precision they never gave. matcher.py evaluates a
# bucket against a criterion as an interval, so a bucket that straddles a
# scheme's boundary comes back UNKNOWN rather than guessing either way.

RANGES: dict[str, tuple[dict, ...]] = {
    "age": (
        {"min": 18, "max": 25, "label_en": "18 to 25", "label_hi": "18 से 25"},
        {"min": 26, "max": 35, "label_en": "26 to 35", "label_hi": "26 से 35"},
        {"min": 36, "max": 45, "label_en": "36 to 45", "label_hi": "36 से 45"},
        {"min": 46, "max": 60, "label_en": "46 to 60", "label_hi": "46 से 60"},
        {"min": 61, "max": 100, "label_en": "Over 60", "label_hi": "60 से ऊपर"},
    ),
    "investment_planned_inr": (
        {"min": 0, "max": 100000,
         "label_en": "Under 1 lakh", "label_hi": "1 लाख से कम"},
        {"min": 100000, "max": 1000000,
         "label_en": "1 to 10 lakh", "label_hi": "1 से 10 लाख"},
        {"min": 1000000, "max": 10000000,
         "label_en": "10 lakh to 1 crore", "label_hi": "10 लाख से 1 करोड़"},
        {"min": 10000000, "max": 100000000,
         "label_en": "1 to 10 crore", "label_hi": "1 से 10 करोड़"},
        {"min": 100000000, "max": 1000000000,
         "label_en": "Over 10 crore", "label_hi": "10 करोड़ से ऊपर"},
    ),
    "annual_income_inr": (
        {"min": 0, "max": 100000,
         "label_en": "Under 1 lakh a year", "label_hi": "साल में 1 लाख से कम"},
        {"min": 100000, "max": 300000,
         "label_en": "1 to 3 lakh", "label_hi": "1 से 3 लाख"},
        {"min": 300000, "max": 800000,
         "label_en": "3 to 8 lakh", "label_hi": "3 से 8 लाख"},
        {"min": 800000, "max": 100000000,
         "label_en": "Over 8 lakh", "label_hi": "8 लाख से ऊपर"},
    ),
}

# Labels for the closed vocabularies, so a button can say "I make things"
# rather than "manufacturing".
CHOICE_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "area_type": {
        "rural": {"en": "A village", "hi": "गाँव"},
        "urban": {"en": "A town or city", "hi": "शहर"},
    },
    "gender": {
        "female": {"en": "Woman", "hi": "महिला"},
        "male": {"en": "Man", "hi": "पुरुष"},
        "other": {"en": "Other", "hi": "अन्य"},
    },
    "caste_category": {
        "general": {"en": "General", "hi": "सामान्य"},
        "obc": {"en": "OBC", "hi": "ओबीसी"},
        "sc": {"en": "SC", "hi": "अनुसूचित जाति"},
        "st": {"en": "ST", "hi": "अनुसूचित जनजाति"},
    },
    "sector": {
        "manufacturing": {"en": "I make things", "hi": "मैं कुछ बनाता/बनाती हूँ"},
        "services": {"en": "I provide a service", "hi": "मैं सेवा देता/देती हूँ"},
        "trading": {"en": "I buy and sell", "hi": "मैं खरीद-बिक्री करता/करती हूँ"},
        "agriculture": {"en": "Farming or livestock", "hi": "खेती या पशुपालन"},
        "other": {"en": "Something else", "hi": "कुछ और"},
    },
}

# Yes/no fields become two buttons.
BOOLEAN_LABELS: dict[str, dict[bool, dict[str, str]]] = {
    "has_existing_unit": {
        True: {"en": "Yes, I already run one", "hi": "हाँ, पहले से चल रही है"},
        False: {"en": "No, not yet", "hi": "नहीं, अभी नहीं"},
    },
    "has_udyam_registration": {
        True: {"en": "Yes", "hi": "हाँ"},
        False: {"en": "No", "hi": "नहीं"},
    },
}

# Reference data, not scheme content. A person outside the states a scheme
# covers must be able to say so and be told plainly.
STATES: tuple[tuple[str, str, str], ...] = (
    ("andhra_pradesh", "Andhra Pradesh", "आंध्र प्रदेश"),
    ("arunachal_pradesh", "Arunachal Pradesh", "अरुणाचल प्रदेश"),
    ("assam", "Assam", "असम"),
    ("bihar", "Bihar", "बिहार"),
    ("chhattisgarh", "Chhattisgarh", "छत्तीसगढ़"),
    ("delhi", "Delhi", "दिल्ली"),
    ("goa", "Goa", "गोवा"),
    ("gujarat", "Gujarat", "गुजरात"),
    ("haryana", "Haryana", "हरियाणा"),
    ("himachal_pradesh", "Himachal Pradesh", "हिमाचल प्रदेश"),
    ("jammu_and_kashmir", "Jammu and Kashmir", "जम्मू और कश्मीर"),
    ("jharkhand", "Jharkhand", "झारखंड"),
    ("karnataka", "Karnataka", "कर्नाटक"),
    ("kerala", "Kerala", "केरल"),
    ("madhya_pradesh", "Madhya Pradesh", "मध्य प्रदेश"),
    ("maharashtra", "Maharashtra", "महाराष्ट्र"),
    ("manipur", "Manipur", "मणिपुर"),
    ("meghalaya", "Meghalaya", "मेघालय"),
    ("mizoram", "Mizoram", "मिज़ोरम"),
    ("nagaland", "Nagaland", "नागालैंड"),
    ("odisha", "Odisha", "ओडिशा"),
    ("punjab", "Punjab", "पंजाब"),
    ("rajasthan", "Rajasthan", "राजस्थान"),
    ("sikkim", "Sikkim", "सिक्किम"),
    ("tamil_nadu", "Tamil Nadu", "तमिलनाडु"),
    ("telangana", "Telangana", "तेलंगाना"),
    ("tripura", "Tripura", "त्रिपुरा"),
    ("uttar_pradesh", "Uttar Pradesh", "उत्तर प्रदेश"),
    ("uttarakhand", "Uttarakhand", "उत्तराखंड"),
    ("west_bengal", "West Bengal", "पश्चिम बंगाल"),
)
