# Author: MARRI NITHISH
from __future__ import annotations
from pathlib import Path
from typing import Any, List, Optional, Protocol, runtime_checkable, Dict


@runtime_checkable
class BrowserPort(Protocol):
    """Abstraction over a browser/page automation driver (e.g., Playwright)."""

    def load_page(self, url: str) -> bool:
        ...

    def get_page_source(self) -> str:
        ...

    def get_page_handle(self) -> Any:
        """Return the underlying page/driver handle for low-level operations when needed."""
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class InteractionDetectorPort(Protocol):
    """Abstraction for detecting hover/popup interactions on a live page handle."""

    def detect_hover_interactions(self, potential_selectors: Optional[List[Any]] = None) -> List[Dict]:
        """
        Detect and classify hover interactions.
        Returned items are implementation-agnostic dicts that a mapper can convert to domain models.
        """
        ...


@runtime_checkable
class DOMParserPort(Protocol):
    """Abstraction for static DOM parsing helpers (optional for runtime-first systems)."""

    def parse_hoverable_elements(self) -> List[Dict]:
        ...

    def extract_interactive_elements(self) -> List[Dict]:
        ...


@runtime_checkable
class GherkinGeneratorPort(Protocol):
    """Abstraction for producing a .feature file from interactions."""

    def generate_full_feature(self, url: str, analysis_results: List[Dict]) -> Path:
        ...


@runtime_checkable
class InteractionMapperPort(Protocol):
    """Abstraction to convert raw detector dicts to domain entities and back."""

    def to_domain(self, raw: Dict) -> Any:
        ...

    def to_raw(self, domain_obj: Any) -> Dict:
        ...
