# Author: MARRI NITHISH
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional


class InteractionType(str, Enum):
    NONE = "none"
    DROPDOWN = "dropdown"
    POPUP = "popup"
    HOVER_REVEAL = "hover_reveal"


@dataclass(frozen=True)
class VisibleElement:
    selector: str
    tag: Optional[str] = None
    role: Optional[str] = None
    tabindex: Optional[str] = None
    text: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OverlayInfo:
    overlay_detected: bool
    overlay_nodes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PageStateMeta:
    overlay_detected: bool = False
    overlay_nodes: List[Dict[str, Any]] = field(default_factory=list)
    new_visible_count: int = 0
    overlay_became_visible: bool = False


@dataclass(frozen=True)
class PageState:
    timestamp: str
    visible_elements: List[VisibleElement] = field(default_factory=list)
    meta: PageStateMeta = field(default_factory=PageStateMeta)


@dataclass(frozen=True)
class Delta:
    new_visible_elements: List[VisibleElement] = field(default_factory=list)
    overlay_became_visible: bool = False
    overlay_detected: bool = False


@dataclass(frozen=True)
class Interaction:
    selector: str
    pre_hover: PageState
    post_hover: PageState
    delta: Delta
    type: InteractionType = InteractionType.NONE


@dataclass(frozen=True)
class GenerationResult:
    url: str
    feature_path: Path
    interactions: List[Interaction] = field(default_factory=list)
