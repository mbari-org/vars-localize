"""
Helpers for dealing with assets.
"""

from pathlib import Path
from typing import Union


ASSETS_DIR = Path(__file__).parent.resolve()


def get_asset_path(rel_path: Union[str, Path]) -> Path:
    """
    Get the absolute path to an asset.

    Args:
        rel_path (Union[str, Path]): The relative path to the asset.

    Returns:
        Path: The absolute path to the asset.

    Raises:
        ValueError: If rel_path is an absolute path.
    """
    rel_path = Path(rel_path)
    if rel_path.is_absolute():
        raise ValueError("rel_path must be a relative path.")
    return ASSETS_DIR / rel_path
