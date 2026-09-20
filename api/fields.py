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
