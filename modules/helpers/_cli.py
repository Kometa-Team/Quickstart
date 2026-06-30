"""CLI argument normalization utilities extracted from _legacy.py."""


def _unwrap_doublewrap(s: str) -> str:
    """Turn ""Foo Bar"" -> "Foo Bar" (leave normal "Foo Bar" alone)."""
    if len(s) >= 2 and s[0] == s[-1] == '"':
        inner = s[1:-1]
        if len(inner) >= 2 and inner[0] == inner[-1] == '"':
            return inner
    return s


def normalize_cli_args_inplace(argv: list[str]) -> None:
    """
    Fix double-wrapped quoted values produced on Frozen-Windows.
    Works generically, and also ensures flags that take a single value
    (like --run-libraries and --times) have their next arg cleaned.
    """
    if not argv:
        return

    # 1) generic pass: unwrap any fully-double-wrapped token
    for i, tok in enumerate(argv):
        argv[i] = _unwrap_doublewrap(tok)

    # 2) flags with exactly one following value we care about
    single_value_flags = {
        "--run-libraries",
        "--times",
        "--divider",
        "--config",
        "--timeout",
        "--width",
    }
    i = 0
    while i < len(argv):
        if argv[i] in single_value_flags and i + 1 < len(argv):
            argv[i + 1] = _unwrap_doublewrap(argv[i + 1])
            i += 2
        else:
            i += 1


def strip_outer_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def normalize_flag_values(argv: list[str]) -> None:
    """
    Remove one layer of surrounding quotes from *values* that follow flags which
    take a single argument (no shell; quotes are literal).
    Works for both --run-libraries and --times, and is harmless elsewhere.
    """
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            # flags that take exactly one value next
            if a in {"--run-libraries", "--times", "--divider", "--config", "--width", "--timeout"}:
                if i + 1 < len(argv):
                    argv[i + 1] = strip_outer_quotes(argv[i + 1])
                    i += 2
                    continue
        # also do a generic dequote of any standalone arg that is fully quoted
        argv[i] = strip_outer_quotes(argv[i])
        i += 1
