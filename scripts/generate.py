# Author: MARRI NITHISH
import sys
import argparse
from pathlib import Path

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

from autogherkin_autogen.infra.logging_config import setup_logging
from autogherkin_autogen.app.generator_service import GeneratorService, GeneratorServiceConfig
from autogherkin_autogen.app.interaction_mapper import InteractionMapper

from autogherkin_autogen.automation.browser_driver import BrowserDriver
from autogherkin_autogen.analysis.dom_parser import DOMParser
from autogherkin_autogen.analysis.interaction_detector import InteractionDetector
from autogherkin_autogen.generation.gherkin_builder import GherkinBuilder


def run(url: str) -> Path:
    setup_logging("INFO")

    # Adapters/factories to satisfy ports and DIP
    browser = BrowserDriver()
    detector_factory = lambda page: InteractionDetector(page)
    dom_parser_factory = lambda page_source: DOMParser(page_source)
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

    result = service.generate(url)
    return result.feature_path


def main():
    parser = argparse.ArgumentParser(description="Generate dynamic Gherkin tests for hover/overlay behavior.")
    parser.add_argument("--url", required=True, help="Target website URL")
    args = parser.parse_args()

    feature_path = run(args.url)
    print(str(feature_path))


if __name__ == "__main__":
    main()
