<!-- Author: MARRI NITHISH -->
# Project Plan: AutoGherkin Generator for Hover Elements

## 1. Folder Structure Plan

The project will use the existing `autogherkin-autogen/` directory as the root. We'll organize it modularly for maintainability, separating concerns like automation, analysis, generation, and configuration. This structure supports Python best practices (e.g., src layout) and allows easy testing and deployment.

```
autogherkin-autogen/
├── README.md                  # Project overview, setup instructions, usage
├── requirements.txt           # Python dependencies
├── setup.py                   # Optional: For packaging as a module
├── .gitignore                 # Git ignore file (already present)
├── configs/                   # Configuration files
│   ├── config.yaml            # Main config (e.g., browser settings, LLM params)
│   └── .env.example           # Environment variables template (already present)
├── src/                       # Source code
│   └── autogherkin_autogen/   # Main package
│       ├── __init__.py
│       ├── main.py            # Entry point for running the application
│       ├── automation/        # Browser automation logic
│       │   ├── __init__.py
│       │   ├── browser_driver.py  # Playwright/Selenium setup, page loading
│       │   └── hover_simulator.py # Hover detection and simulation
│       ├── analysis/          # DOM and interaction analysis
│       │   ├── __init__.py
│       │   ├── dom_parser.py  # BeautifulSoup for static analysis
│       │   └── interaction_detector.py  # Identify hover-triggered elements
│       ├── generation/        # Gherkin scenario generation
│       │   ├── __init__.py
│       │   ├── gherkin_builder.py  # Build .feature files from analysis
│       │   └── llm_reasoner.py     # Ollama/AutoGen for dynamic reasoning
│       └── agents/            # Agentic framework (if using AutoGen)
│           ├── __init__.py
│           └── hover_agent.py # LLM-based agent for complex interactions
├── outputs/                   # Generated outputs
│   └── feature_files/         # .feature files for each URL
├── tests/                     # Test suites (already present)
│   ├── __init__.py
│   ├── unit/                  # Unit tests (e.g., for parsers, generators)
│   ├── integration/           # Integration tests (e.g., end-to-end with mock sites)
│   └── tests_data/            # Test fixtures, sample URLs, expected outputs (already present)
├── scripts/                   # Utility scripts
│   ├── run_app.py             # Script to run Streamlit UI or FastAPI
│   └── generate_tests.py      # CLI script for batch generation
└── docs/                      # Documentation
    └── plan.md                # This file
```

This structure ensures:
- **Modularity**: Each module handles a specific responsibility.
- **Scalability**: Easy to add features like multi-page crawling.
- **Testing**: Isolated components for unit/integration tests.
- **Configs/Outputs**: Centralized for easy management.

Next steps: Create missing directories and files using tools (e.g., write_to_file for __init__.py files).

## 2. Tools Required Plan

### Core Technologies (Python-based)
- **Browser Automation**: Playwright (preferred over Selenium for better async support, headless mode, and cross-browser compatibility). Install via `pip install playwright` and run `playwright install` for browsers.
- **HTML Parsing/DOM Analysis**: BeautifulSoup4 (`pip install beautifulsoup4`) for initial static parsing; combined with Playwright's page evaluation for dynamic states.
- **LLM Reasoning**: Ollama (local LLM runner) with a Python client (`pip install ollama`). Models like Llama 3 for reasoning on interactions. Fallback to OpenAI if needed, but keep local.
- **Agentic Frameworks**: AutoGen (`pip install pyautogen`) for multi-agent workflows (e.g., one agent for analysis, another for generation).
- **Backend API**: FastAPI (`pip install fastapi uvicorn`) for RESTful input/output if API needed; simple for URL submission and feature retrieval.
- **UI**: Streamlit (`pip install streamlit`) for a simple web interface to input URL and view generated tests.
- **Storage**: JSON files (`json` stdlib) for caching DOM snapshots and analysis results in `outputs/`.
- **Output Format**: Plain text .feature files using Gherkin syntax (no extra libs needed).

### Additional Tools/Libraries
- **Requests** (`pip install requests`): For initial page fetch if needed (though Playwright handles most).
- **PyYAML** (`pip install pyyaml`): For config.yaml parsing.
- **Pytest** (`pip install pytest`): For testing.
- **Logging**: Stdlib `logging` for debug/info.
- **CLI**: Click or argparse for script-based execution.

### Installation Plan
1. Create `requirements.txt` with all deps.
2. Run `pip install -r requirements.txt`.
3. For Playwright: `playwright install chromium` (headless by default).
4. For Ollama: Assume user installs Ollama separately; pull model via `ollama pull llama3`.
5. Environment: Use `.env` for sensitive keys (e.g., if API fallbacks).

Total deps minimal to avoid bloat; focus on dynamic, autonomous operation without hardcoding.

## 3. Implementation Plan

High-level steps to build the solution dynamically (no hardcoded selectors):

### Phase 1: Setup (1-2 hours)
- Create folder structure as planned.
- Implement `requirements.txt` and install deps (using execute_command).
- Set up `configs/config.yaml` for defaults (e.g., browser: 'chromium', llm_model: 'llama3').
- Create basic `main.py` with URL input (CLI or Streamlit).

### Phase 2: Browser Automation & Detection (3-4 hours)
- In `automation/browser_driver.py`: Launch Playwright, load URL, wait for page stability.
- In `automation/hover_simulator.py`:
  - Dynamically find potential hoverable elements: Query all interactive elements (e.g., `page.query_selector_all('a, button, [role="menuitem"], img')` – focus on non-nested for starters.
  - For each: Record initial visibility/state.
  - Simulate hover: `element.hover()`.
  - Wait for changes: Monitor DOM mutations (Playwright's `page.wait_for_selector` or evaluate JS for visibility).
  - Detect changes: Compare pre/post-hover (new visible elements, popups via `document.querySelectorAll(':hover ~ *')` or visibility checks).
  - Identify behaviors: Check for modals/popups (e.g., elements with `display: none` to `block`), links (clickable post-hover), redirections (simulate click and check navigation).
  - Cache DOM snapshots as JSON.

### Phase 3: Analysis & Reasoning (2-3 hours)
- In `analysis/dom_parser.py`: Use BeautifulSoup on page content for static structure (e.g., find nested ul/li for menus).
- In `analysis/interaction_detector.py`: Post-hover, parse changes; classify (e.g., dropdown if new links appear, tooltip if text overlay).
- In `generation/llm_reasoner.py`: Use Ollama to reason:
  - Prompt: "Given this DOM snapshot before/after hover on [element desc], describe the interaction."
  - Use AutoGen if complex: Agent1 analyzes DOM, Agent2 generates scenarios.

### Phase 4: Gherkin Generation & Output (2 hours)
- In `generation/gherkin_builder.py`:
  - For each detected interaction, generate 2 scenarios:
    a. Popup/Overlay: Given on [URL], When hover [element], Then [popup] visible and dismisses.
    b. Hover Interaction: Given on [URL], When hover [menu], Then [links] appear and clicking [link] navigates to [URL].
  - Format as .feature: Feature: Hover Validation on [site]; Scenario: [name]; Steps in Gherkin.
- Output: Save to `outputs/feature_files/[url_hash].feature`.
- UI/API: Streamlit app with URL input, generate button, display/download feature file.

### Phase 5: Integration & Testing (2 hours)
- `main.py`: Orchestrate: Input URL -> Automate -> Analyze -> Generate -> Output.
- Tests: Unit (e.g., mock DOM parsing), Integration (test on sample sites like example.com dropdowns).
- Handle dynamics: Retry on timeouts, error on non-hover sites (generate basic "No hovers found").

Run via `streamlit run scripts/run_app.py` or CLI `python src/autogherkin_autogen/main.py --url https://example.com`.

## 4. Improve Plan

Post-implementation enhancements:
- **Robustness**: Add multi-page crawling (follow links), handle JS-heavy sites (wait for network idle), error handling for inaccessible URLs.
- **Advanced Detection**: Use computer vision (e.g., OpenCV via Playwright screenshots) for visual hovers; integrate more LLM prompts for edge cases (e.g., animated transitions).
- **Scalability**: Batch processing for multiple URLs; Dockerize for portability.
- **UI/UX**: Add visualizations (e.g., screenshot before/after hover in Streamlit).
- **Testing**: Expand to e2e with real sites; validate generated Gherkin with Behave/Cucumber parser.
- **Performance**: Cache results in JSON; optimize hover simulation (limit to top 20 elements).
- **Extensibility**: Support other interactions (click, scroll); modular plugins for LLMs.
- **Metrics**: Add coverage report (e.g., % of page interactions tested).

