from collections.abc import Mapping
from typing import Any


def deep_update(mapping: dict[Any, Any], *updating_mappings: Mapping[Any, Any]) -> dict[Any, Any]:
    """Update a nested dictionary"""
    updated_mapping = mapping.copy()
    for updating_mapping in updating_mappings:
        for k, v in updating_mapping.items():
            if k in updated_mapping and isinstance(v, Mapping):
                updated_mapping[k] = deep_update(updated_mapping[k], v)  # type: ignore
            else:
                updated_mapping[k] = v
    return updated_mapping
