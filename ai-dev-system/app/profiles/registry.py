from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.profiles.base_profile import BaseProfile


class ProfileRegistry:
    """Registry of all available app profiles. Supports decorator-style registration."""

    _profiles: dict[str, type["BaseProfile"]] = {}

    @classmethod
    def register(cls, name: str):
        """Class decorator to register a profile under a given name."""

        def decorator(profile_cls: type["BaseProfile"]) -> type["BaseProfile"]:
            cls._profiles[name] = profile_cls
            return profile_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> "BaseProfile":
        """Instantiate and return a profile by name. Raises ValueError if unknown."""
        if name not in cls._profiles:
            known = ", ".join(sorted(cls._profiles))
            raise ValueError(f"Unknown profile '{name}'. Known profiles: {known or '(none registered)'}")
        return cls._profiles[name]()

    @classmethod
    def names(cls) -> list[str]:
        """Return sorted list of all registered profile names."""
        return sorted(cls._profiles)

    @classmethod
    def reset(cls) -> None:
        """Clear registry — for use in tests only."""
        cls._profiles.clear()
