# Author: MARRI NITHISH
import sys
from pathlib import Path
import streamlit as st

# Ensure local 'src' is on sys.path for package imports (robust across layout changes)
def _add_src_to_path():
    here = Path(__file__).resolve()
    for p in [here.parent] + list(here.parents):
        src = p / "src"
        if src.exists():
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            return
_add_src_to_path()

from autogherkin_autogen.automation.browser_driver import BrowserDriver
from autogherkin_autogen.analysis.dom_parser import DOMParser
from autogherkin_autogen.analysis.interaction_detector import InteractionDetector
from autogherkin_autogen.generation.gherkin_builder import GherkinBuilder
from autogherkin_autogen.config import config

# SOLID-aligned application service and adapters
from autogherkin_autogen.infra.logging_config import setup_logging
from autogherkin_autogen.app.generator_service import GeneratorService, GeneratorServiceConfig
from autogherkin_autogen.app.interaction_mapper import InteractionMapper

st.title("AutoGherkin Generator for Hover Elements")

url = st.text_input("Enter website URL:", placeholder="https://example.com")

if st.button("Generate Gherkin Tests"):
    if url:
        with st.spinner("Analyzing website..."):
            setup_logging("INFO")

            # Build SOLID/DIP service pipeline
            browser = BrowserDriver()
            detector_factory = lambda page: InteractionDetector(page)
            dom_parser_factory = lambda source: DOMParser(source)  # optional hints (disabled below)
            gherkin = GherkinBuilder()
            mapper = InteractionMapper()

            service = GeneratorService(
                browser=browser,
                detector_factory=detector_factory,
                gherkin_generator=gherkin,
                mapper=mapper,
                dom_parser_factory=dom_parser_factory,
                config=GeneratorServiceConfig(use_dom_hints=False),
            )

            try:
                result = service.generate(url)
                st.success(f"Gherkin file generated: {result.feature_path}")
                with open(result.feature_path, 'r', encoding='utf-8') as f:
                    st.code(f.read(), language='gherkin')
            except Exception as e:
                st.error(f"Failed to generate feature: {e}")
    else:
        st.warning("Please enter a URL.")

# Run with: streamlit run scripts/run_app.py
