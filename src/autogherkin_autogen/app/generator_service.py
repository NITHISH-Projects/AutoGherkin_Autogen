# Author: MARRI NITHISH
from __future__ import annotations
from typing import Callable, Optional, Any, List, Dict
from dataclasses import dataclass
import logging

from autogherkin_autogen.core.models import GenerationResult, Interaction
from autogherkin_autogen.core.ports import (
    BrowserPort,
    InteractionDetectorPort,
    DOMParserPort,
    GherkinGeneratorPort,
    InteractionMapperPort,
)


@dataclass
class GeneratorServiceConfig:
    use_dom_hints: bool = False  # if True, pass DOMParser-derived hints to detector; otherwise rely on runtime discovery


class GeneratorService:
    """
    Application service orchestrating the end-to-end flow.

    Dependencies are injected via constructor to satisfy DIP:
    - browser: BrowserPort
    - detector_factory: Callable[[Any], InteractionDetectorPort]  # factory that accepts page handle
    - dom_parser_factory: Optional[Callable[[str], DOMParserPort]]
    - gherkin_generator: GherkinGeneratorPort
    - mapper: InteractionMapperPort
    """

    def __init__(
        self,
        browser: BrowserPort,
        detector_factory: Callable[[Any], InteractionDetectorPort],
        gherkin_generator: GherkinGeneratorPort,
        mapper: InteractionMapperPort,
        dom_parser_factory: Optional[Callable[[str], DOMParserPort]] = None,
        config: Optional[GeneratorServiceConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.browser = browser
        self.detector_factory = detector_factory
        self.dom_parser_factory = dom_parser_factory
        self.gherkin_generator = gherkin_generator
        self.mapper = mapper
        self.cfg = config or GeneratorServiceConfig()
        self.log = logger or logging.getLogger(__name__)

    def generate(self, url: str) -> GenerationResult:
        """
        Orchestrates:
        - Load page
        - Optionally parse DOM hints
        - Detect interactions on live page
        - Generate .feature file
        - Map raw interactions to domain model
        """
        self.log.info("Starting generation for url=%s", url)
        try:
            if not self.browser.load_page(url):
                raise RuntimeError(f"Failed to load URL: {url}")

            page_source = self.browser.get_page_source()
            page_handle = self.browser.get_page_handle()

            # Optional DOM hints
            potential: Optional[List[Dict]] = None
            if self.cfg.use_dom_hints and self.dom_parser_factory:
                try:
                    dom_parser = self.dom_parser_factory(page_source)
                    potential = dom_parser.parse_hoverable_elements()
                    self.log.debug("Parsed %d potential DOM hints", len(potential or []))
                except Exception as e:
                    self.log.warning("DOM parsing failed, proceeding without hints: %s", e)

            # Runtime interaction detection (no hardcoded selectors)
            detector = self.detector_factory(page_handle)
            interactions_raw = detector.detect_hover_interactions(potential)

            # Generate Gherkin using LLM (if available) or fallback
            feature_path = self.gherkin_generator.generate_full_feature(url, interactions_raw)

            # Map to domain models for returns/analytics
            interactions_domain: List[Interaction] = []
            for raw in interactions_raw:
                try:
                    interactions_domain.append(self.mapper.to_domain(raw))
                except Exception as e:
                    self.log.debug("Skipping interaction due to mapping error: %s", e)

            self.log.info("Generated feature at %s with %d interactions", feature_path, len(interactions_domain))
            return GenerationResult(url=url, feature_path=feature_path, interactions=interactions_domain)
        finally:
            try:
                self.browser.close()
            except Exception as e:
                self.log.warning("Failed to close browser: %s", e)
