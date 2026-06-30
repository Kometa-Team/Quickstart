"""Data redaction utility extracted from _legacy.py."""

import re


def redact_sensitive_data(yaml_content):
    # Split the YAML content into lines for line-by-line processing
    lines = yaml_content.splitlines()

    # Process each line to redact sensitive data
    redacted_lines = [
        re.sub(
            r"(token|client.*|url|api_*key|secret|error|delete|run_start|run_end|version|changes|username|password): .+",
            r"\1: (redacted)",
            line.strip("\r\n"),
        )
        for line in lines
    ]

    # Join the lines back together to form the redacted YAML content
    redacted_content = "\n".join(redacted_lines)
    return redacted_content
