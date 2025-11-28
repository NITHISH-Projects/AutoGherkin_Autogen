# Author: MARRI NITHISH
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import types

import pytest

from autogherkin_autogen.app.interaction_mapper import InteractionMapper
from autogherkin_autogen.core.models import (
    VisibleElement,
    PageStateMeta,
    PageState,
    Delta,
    Interaction,
    InteractionType,
)
from autogherkin_autogen.app.generator_service import GeneratorService, GeneratorServiceConfig


def _mk_state(
    ts: str = "2025-01-01T00:00:00",
    visibles: List[Dict[str, Any]] | None = None,
    overlay_detected: bool = False,
    new_visible_count: int = 0,
    overlay_became_visible: bool = False,
) -> Dict[str, Any]:
    return {
        "timestamp": ts,
        "visible_elements": visibles or [],
        "meta": {
            "overlay_detected": overlay_detected,
            "overlay_nodes": [],
            "new_visible_count": new_visible_count,
            "overlay_became_visible": overlay_became_visible,
        },
    }


def test_interaction_mapper_roundtrip():
    mapper = InteractionMapper()
    raw = {
        "selector": "nav > ul:nth-of-type(1) > li:nth-of-type(1)",
        "pre_hover": _mk_state(),
        "post_hover": _mk_state(new_visible_count=2, overlay_detected=False),
        "delta": {
            "new_visible_elements": [
                {"selector": "a:nth-of-type(1)", "text": "Shop", "role": "menuitem"},
                {"selector": "a:nth-of-type(2)", "text": "Men", "role": "menuitem"},
            ],
            "overlay_became_visible": False,
            "overlay_detected": False,
        },
        "type": "dropdown",
    }

    domain = mapper.to_domain(raw)
    assert isinstance(domain, Interaction)
    assert domain.selector == raw["selector"]
    assert domain.type == InteractionType.DROPDOWN
    assert domain.post_hover.meta.new_visible_count == 2
    assert len(domain.delta.new_visible_elements) == 2

    roundtrip = mapper.to_raw(domain)
    assert roundtrip["type"] == "dropdown"
    assert roundtrip["selector"] == raw["selector"]


def test_gherkin_builder_requires_llm(monkeypatch, tmp_path: Path):
    # Import module to monkeypatch its module-level config and imported generate_gherkin symbol
    import autogherkin_autogen.generation.gherkin_builder as gb

    # Force LLM path to return empty -> should raise due to missing 'Feature:' content
    monkeypatch.setattr(gb, "generate_gherkin", lambda url, interactions: "", raising=False)

    # Redirect output directory to tmp (won't be used because we expect failure)
    cfg = dict(gb.config)
    out = dict(cfg.get("output", {}))
    out["directory"] = str(tmp_path)
    cfg["output"] = out
    monkeypatch.setattr(gb, "config", cfg, raising=False)

    builder = gb.GherkinBuilder()
    url = "https://example.com"
    interactions = [
        {
            "selector": "nav > ul > li:nth-of-type(1)",
            "pre_hover": _mk_state(),
            "post_hover": _mk_state(new_visible_count=1),
            "delta": {"new_visible_elements": [{"selector": "a", "text": "Menu"}], "overlay_became_visible": False, "overlay_detected": False},
            "type": "hover_reveal",
        }
    ]

    with pytest.raises(RuntimeError):
        _ = builder.generate_full_feature(url, interactions)


def test_generator_service_orchestration_happy_path(monkeypatch, tmp_path: Path):
    # Fakes implementing ports
    class FakeBrowser:
        def load_page(self, url: str) -> bool:
            return True

        def get_page_source(self) -> str:
            return "<html></html>"

        def get_page_handle(self) -> Any:
            return object()

        def close(self) -> None:
            pass

    class FakeDetector:
        def __init__(self, page: Any) -> None:
            self.page = page

        def detect_hover_interactions(self, potential_selectors=None) -> List[Dict]:
            return [
                {
                    "selector": "nav > ul > li:nth-of-type(1)",
                    "pre_hover": _mk_state(),
                    "post_hover": _mk_state(new_visible_count=1),
                    "delta": {"new_visible_elements": [{"selector": "a", "text": "Item"}], "overlay_became_visible": False, "overlay_detected": False},
                    "type": "dropdown",
                }
            ]

    class FakeGherkin:
        def __init__(self, outdir: Path) -> None:
            self.outdir = outdir

        def generate_full_feature(self, url: str, analysis_results: List[Dict]) -> Path:
            self.outdir.mkdir(parents=True, exist_ok=True)
            p = self.outdir / "dummy.feature"
            p.write_text("Feature: Dummy\n\nScenario: S\n Given {}\n".format(url), encoding="utf-8")
            return p

    # Mapper returns a minimal domain object
    class FakeMapper:
        def to_domain(self, raw: Dict) -> Interaction:
            return Interaction(
                selector=raw["selector"],
                pre_hover=PageState(timestamp="t0"),
                post_hover=PageState(timestamp="t1", meta=PageStateMeta(new_visible_count=1)),
                delta=Delta(new_visible_elements=[VisibleElement(selector="a")]),
                type=InteractionType.DROPDOWN,
            )

        def to_raw(self, domain_obj: Any) -> Dict:
            raise NotImplementedError

    # Wire service
    outdir = tmp_path / "features"
    gherkin = FakeGherkin(outdir)

    service = GeneratorService(
        browser=FakeBrowser(),
        detector_factory=lambda page: FakeDetector(page),
        gherkin_generator=gherkin,
        mapper=FakeMapper(),
        dom_parser_factory=None,
        config=GeneratorServiceConfig(use_dom_hints=False),
    )

    result = service.generate("https://example.com")
    assert result.feature_path.exists()
    assert len(result.interactions) == 1
