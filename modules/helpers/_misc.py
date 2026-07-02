"""Miscellaneous utility functions extracted from the original helpers.py monolith."""

import re


def normalize_id(name, existing_ids):
    """Convert library names to safe and unique HTML IDs while preserving Unicode."""

    # Step 1: Remove unwanted characters (only keep letters, numbers, - and _)
    safe_id = re.sub(r"[^\w\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7A3-]", "", name)

    # Step 2: Replace spaces with dashes
    safe_id = safe_id.replace(" ", "-").lower()

    # Step 3: Ensure ID is unique by appending a counter if needed
    base_id = safe_id
    counter = 1
    while safe_id in existing_ids:
        safe_id = f"{base_id}-{counter}"
        counter += 1

    existing_ids.add(safe_id)  # Store it to prevent future duplicates
    return safe_id


def is_valid_aspect_ratio(image, target_ratio="2:3", tolerance=0.01):
    """Check if the image has an acceptable aspect ratio within a given tolerance."""
    width, height = image.size
    actual_ratio = width / height

    # Map aspect ratio strings to numeric values
    ratio_map = {
        "2:3": 2 / 3,
        "1:1.5": 2 / 3,  # alias
        "16:9": 16 / 9,
    }

    if target_ratio not in ratio_map:
        raise ValueError(f"Unsupported target_ratio: {target_ratio}")

    expected_ratio = ratio_map[target_ratio]
    return abs(actual_ratio - expected_ratio) < tolerance


def extract_library_name(key):
    """Extracts the actual library name from the key format."""
    if not isinstance(key, str):
        return None
    # Capture only the library-id segment between `-library_` and the next
    # known section marker. This avoids greedy matches when template variable
    # keys themselves contain hyphens (e.g. `use_South-Eastern Asia`).
    match = re.match(
        r"^(?:mov|sho)-library_(.+?)-(?:library$|collection_|template_|attribute_|overlay_|top_level_|metadata_files$)",
        key,
    )
    return match.group(1) if match else None
