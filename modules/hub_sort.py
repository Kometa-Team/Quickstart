"""Shared optional auto_sort_hubs values for forms, validation and export."""

SETTINGS_AUTO_SORT_HUBS_VALUES = frozenset(
    {
        "sort_title",
        "sort_title.desc",
        "alpha",
        "alpha.desc",
        "configured",
        "configured.desc",
        "random",
    }
)


def normalize_auto_sort_hubs(value):
    """Recover the legacy form's literal None without hiding invalid values.

    Kometa accepts YAML null. QuickStart's form cleaner has historically
    represented blank and case-insensitive "None" inputs as Python None.
    Keep this field's pre-save validation and rendering consistent with it.
    """
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() == "none":
            return None
    return value
