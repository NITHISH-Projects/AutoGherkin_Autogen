<!-- Author: MARRI NITHISH -->
# AutoGherkin Autogen

AI-powered, dynamic Gherkin (.feature) generator for websites with hover-based interactions and overlays/popups.  
The system runs Playwright to analyze a live page (no hardcoded selectors), detects hover-triggered reveals and modal overlays, and produces clean BDD scenarios. It integrates with AutoGen + Ollama where available, with a deterministic fallback to generate feature files with LLM.

Contents
- Overview
- Key Features
- Architecture (SOLID + Hexagonal)
- Workflow
- Project Structure
- Setup
- Usage (CLI + Streamlit UI)
- Configuration
- Testing
- Implementation Details
- Troubleshooting & Tips
- Extensibility & Next Steps

Overview
- Input: A URL
- Output: Gherkin .feature file containing:
  - Popup/overlay validation scenario (if found; otherwise negative validation)
  - Hover-based interaction validation scenario (dropdowns/hover menus; or generic hover validation)
- Fully dynamic: No reliance on hardcoded selectors or labels. Runtime DOM analysis heuristics discover candidates and classify behaviors.

Key Features
- Dynamic hover detection with JavaScript runtime heuristics (visible/interactive, cursor-pointer, event handlers, hidden descendants)
- Popup/overlay detection (ARIA roles, aria-modal, fixed/large overlay heuristics)
- Delta-based state comparison (pre/post hover visible elements, overlay transitions)
- Gherkin generation via AutoGen + Ollama (OpenAI-compatible) when available; deterministic fallback otherwise
- SOLID & Hexagonal architecture (ports & adapters); testable, maintainable, and easily extensible
- CLI and Streamlit UI entrypoints, centralized logging

Architecture (SOLID + Hexagonal)
The codebase is structured as ports (core contracts) and adapters (implementations), coordinated by an application service. High-level orchestration depends on abstractions, not concrete implementations.

Layers
- Domain (core)
  - core/models.py: Domain entities (InteractionType, VisibleElement, PageState, Delta, Interaction, GenerationResult)
  - core/ports.py: Ports (BrowserPort, InteractionDetectorPort, DOMParserPort, GherkinGeneratorPort, InteractionMapperPort)
- Application (app)
  - app/generator_service.py: GeneratorService orchestrates the use-case: load page → (optional) DOM hints → detect interactions → generate Gherkin → map to domain → return result
  - app/interaction_mapper.py: Maps raw detection dicts to domain entities and back
- Adapters (infrastructure/implementations)
  - automation/browser_driver.py (BrowserPort): Playwright-based driver; returns a page handle for low-level evaluation
  - analysis/interaction_detector.py (InteractionDetectorPort): Runtime heuristics + hover simulation + overlay detection
  - analysis/dom_parser.py (DOMParserPort): Static DOM parsing helpers (optional hints)
  - generation/gherkin_builder.py (GherkinGeneratorPort): Builds .feature files, calls LLM (if available) or fallback template
  - agents/llm_agents.py: AutoGen + Ollama adapter with lazy init & graceful fallback
  - infra/logging_config.py: Centralized logging setup

Entry points (composition roots)
- scripts/generate.py (CLI): Wires adapters to the service, runs generation
- scripts/run_app.py (Streamlit): Provides a simple UI to enter a URL and preview the .feature output

SOLID Principles
- SRP: Each class has a single reason to change. BrowserDriver only handles browser automation; InteractionDetector only detects interactions; GeneratorService only orchestrates flow, etc.
- OCP: Add new detectors/browsers/emitters by implementing the port and injecting; existing high-level code remains closed to modification.
- LSP: Adapters conform to ports; swappable without breaking behavior.
- ISP: Small, focused interfaces (ports) avoid forcing clients to depend on unnecessary methods.
- DIP: High-level policies depend on abstractions (ports), not implementations. Adapters are injected via factories.

Workflow

ASCII Diagram
  [scripts/run_app.py / scripts/generate.py]
                |
          setup_logging()
                |
          GeneratorService
        /        |         \
    Browser   Detector     GherkinBuilder
   (Playwright) (JS eval)      (LLM or fallback)
        \        |         /
         \   InteractionMapper
          \______Result (.feature)

Step-by-step
1) BrowserDriver loads URL (headless/headful configurable).
2) Optionally, DOMParser suggests hints (disabled by default).
3) InteractionDetector:
   - Discovers candidate selectors via JS heuristics:
     - element is visible + interactive (a/button/has role/tabindex) OR
     - has onmouseenter/onmouseover OR
     - contains hidden descendants (dropdowns/overlays) OR
     - cursor: pointer
   - Captures pre-hover state (visible elements, overlay state), hovers each candidate, captures post-hover, computes delta.
   - Classifies 'dropdown', 'popup', or 'hover_reveal'.
4) GherkinBuilder:
   - Calls LLM (AutoGen + Ollama) if available to produce formatted .feature content.
   - If not available, falls back to deterministic template producing the two required scenarios.
5) Writes feature file in outputs/feature_files and returns GenerationResult.

Project Structure

.
├─ configs/
│  └─ config.yaml
├─ docs/
│  └─ plan.md
├─ outputs/
│  ├─ feature_files/
│  └─ cache/                # JSON snapshots of interactions
├─ scripts/
│  ├─ generate.py           # CLI entry
│  └─ run_app.py            # Streamlit UI
├─ src/
│  └─ autogherkin_autogen/
│     ├─ config.py
│     ├─ agents/
│     │  └─ llm_agents.py
│     ├─ analysis/
│     │  ├─ dom_parser.py
│     │  └─ interaction_detector.py
│     ├─ app/
│     │  ├─ generator_service.py
│     │  └─ interaction_mapper.py
│     ├─ automation/
│     │  ├─ __init__.py
│     │  └─ browser_driver.py
│     ├─ core/
│     │  ├─ models.py
│     │  └─ ports.py
│     ├─ generation/
│     │  ├─ __init__.py
│     │  └─ gherkin_builder.py
│     └─ infra/
│        └─ logging_config.py
├─ tests/
│  ├─ unit/
│  │  └─ test_autogherkin.py
│  ├─ integration/
│  └─ tests_data/
├─ requirements.txt
├─ pyproject.toml
├─ .gitignore
└─ README.md

Setup

Prerequisites
- Python 3.9+ (venv recommended)
- Playwright browsers (installed via command below)
- Optional: Ollama running locally (for LLM), and the requested model pulled (e.g. llama3)

Install
- Create venv and install deps
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt

- Install Playwright browsers
  .venv/bin/python -m playwright install chromium
  # Optionally: firefox, webkit

Usage

CLI
- Generate feature for a URL
  .venv/bin/python scripts/generate.py --url https://www.tivdak.com/patient-stories/

- Output path will be printed, e.g.:
  outputs/feature_files/Hover_Interactions_on_www.tivdak.com_patient-stories.feature

Streamlit UI
- Start UI
  .venv/bin/streamlit run scripts/run_app.py --server.port 8501
- Open http://localhost:8501 in a browser
- Enter the URL, click “Generate Gherkin Tests”, and preview the .feature content in the UI

Configuration

configs/config.yaml
- browser:
  type: chromium | firefox | webkit
  headless: true|false
  timeout: 30000          # navigation/interaction timeout (ms)
- llm:
  model: llama3
  base_url: http://localhost:11434   # Ollama
  temperature: 0.7
- analysis:
  max_elements: 20
  hover_delay: 1000        # ms to wait after hover
- output:
  directory: outputs/feature_files
  format: feature
- ui: (reserved for future)

LLM integration
- agents/llm_agents.py lazily initializes AutoGen agents; if any required extras (like openai client for the OpenAI-compatible path) are missing or Ollama isn’t reachable, it returns an empty string so GherkinBuilder’s fallback template is used.
- To enable LLM generation:
  - Install AutoGen extras if desired (per AutoGen’s docs).
  - Run Ollama and pull the model configured in configs/config.yaml.
  - Ensure Ollama’s OpenAI-compatible endpoint base URL (…/v1) is reachable.

Testing

Run unit tests
- PYTHONPATH=src .venv/bin/pytest -q

What’s covered
- tests/unit/test_autogherkin.py:
  - InteractionMapper round-trip mapping
  - GherkinBuilder fallback generation (without LLM)
  - GeneratorService end-to-end orchestration with fakes

Add integration tests
- Place in tests/integration; consider using a local static HTML with known hover menus and overlays in tests/tests_data, and Playwright in headless=false mode for debugging.

Implementation Details

Interaction detection
- Candidate discovery:
  - JS executed in page context finds candidates:
    - visible && (interactive [a/button/role/tabindex] || has mouse event handlers || cursor: pointer)
    - or has hidden descendants (indicative of dropdown/overlay content)
- Hover simulation:
  - Capture pre state (visible elements + overlay info), hover selector, wait hover_delay, capture post state
  - Delta computed: newly visible elements count, overlay transitions
  - Classification: popup if overlay appears; dropdown if many new elements with roles; otherwise hover_reveal
- Overlay detection heuristics:
  - role="dialog" or aria-modal="true"
  - large fixed-position elements covering significant viewport

Gherkin generation
- LLM path: AutoGen + Ollama, prompts the assistant to create exactly two scenarios (popup and hover interaction).
- Fallback path: Deterministic template ensures compliant scenarios when LLM is unavailable.

Outputs
- Feature files written to outputs/feature_files
- Interaction snapshots written to outputs/cache (JSON) for debugging

Troubleshooting & Tips
- Timeout/overlay intercepts:
  - Some pages show cookie/GDPR overlays blocking pointer events. The detector logs timeouts and may classify as popup if overlay is visible. For better coverage, add auto-dismiss logic for common consent dialogs.
- Increase hover_delay or browser timeout:
  - configs/config.yaml → analysis.hover_delay and browser.timeout
- Headful mode for debugging:
  - Set browser.headless: false in config
- Playwright install issues:
  - Ensure .venv/bin/python -m playwright install chromium has been executed
- macOS LibreSSL warning:
  - Harmless warning from urllib3 when Python uses LibreSSL; not a blocker

Extensibility & Next Steps
- Add a consent modal handler adapter before detection to auto-close common overlays
- Add Selenium/WebDriver adapter implementing BrowserPort
- Expand overlay heuristics (z-index scrims, focus-trap checks)
- Add typed config dataclasses and validation
- Capture screenshots around hover events for richer debugging
- Telemetry/metrics (OpenTelemetry/Prometheus) for interaction timings and LLM durations
- CI workflow to run unit tests, linting, and optional integration checks
