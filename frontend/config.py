"""Frontend configuration shared by page renderers."""

import os


def demo_user_id() -> int:
    """Return the configured demo profile ID, with a safe positive fallback."""
    try:
        value = int(os.getenv("MOVIEVERSE_DEMO_USER_ID", "1"))
    except ValueError:
        return 1
    return value if value > 0 else 1
