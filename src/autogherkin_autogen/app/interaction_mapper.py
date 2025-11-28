# Author: MARRI NITHISH
from __future__ import annotations
from typing import Any, Dict, List
from dataclasses import asdict

from autogherkin_autogen.core.ports import InteractionMapperPort
from autogherkin_autogen.core.models import (
    VisibleElement,
    PageStateMeta,
    PageState,
    Delta,
    Interaction,
    InteractionType,
)


def _visible_from_raw(raw: Dict) -> VisibleElement:
    return VisibleElement(
        selector=raw.get("selector", ""),
        tag=raw.get("tag"),
        role=raw.get("role"),
        tabindex=raw.get("tabindex"),
        text=raw.get("text"),
        extra={k: v for k, v in raw.items() if k not in {"selector", "tag", "role", "tabindex", "text"}},
    )


def _meta_from_raw(raw_meta: Dict) -> PageStateMeta:
    return PageStateMeta(
        overlay_detected=bool(raw_meta.get("overlay_detected", False)),
        overlay_nodes=list(raw_meta.get("overlay_nodes", [])),
        new_visible_count=int(raw_meta.get("new_visible_count", 0)),
        overlay_became_visible=bool(raw_meta.get("overlay_became_visible", False)),
    )


def _state_from_raw(raw_state: Dict) -> PageState:
    visible_raw: List[Dict] = list(raw_state.get("visible_elements", []))
    return PageState(
        timestamp=str(raw_state.get("timestamp", "")),
        visible_elements=[_visible_from_raw(v) for v in visible_raw],
        meta=_meta_from_raw(dict(raw_state.get("meta", {}))),
    )


def _delta_from_raw(raw_delta: Dict) -> Delta:
    new_raw: List[Dict] = list(raw_delta.get("new_visible_elements", []))
    return Delta(
        new_visible_elements=[_visible_from_raw(v) for v in new_raw],
        overlay_became_visible=bool(raw_delta.get("overlay_became_visible", False)),
        overlay_detected=bool(raw_delta.get("overlay_detected", False)),
    )


def _type_from_raw(value: str) -> InteractionType:
    try:
        return InteractionType(value)
    except Exception:
        return InteractionType.NONE


class InteractionMapper(InteractionMapperPort):
    """Concrete mapper to convert runtime detector dicts into domain entities and back."""

    def to_domain(self, raw: Dict) -> Interaction:
        return Interaction(
            selector=str(raw.get("selector", "")),
            pre_hover=_state_from_raw(dict(raw.get("pre_hover", {}))),
            post_hover=_state_from_raw(dict(raw.get("post_hover", {}))),
            delta=_delta_from_raw(dict(raw.get("delta", {}))),
            type=_type_from_raw(str(raw.get("type", "none"))),
        )

    def to_raw(self, domain_obj: Any) -> Dict:
        if isinstance(domain_obj, Interaction):
            # Dataclasses are nested; asdict handles deep conversion
            d = asdict(domain_obj)
            # Convert enum to string for JSON friendliness
            d["type"] = domain_obj.type.value
            return d
        raise TypeError(f"Unsupported type for to_raw: {type(domain_obj)}")
