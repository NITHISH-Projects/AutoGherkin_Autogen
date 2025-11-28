# Author: MARRI NITHISH
from pathlib import Path
from typing import List, Dict, Any
from autogherkin_autogen.config import config
from autogherkin_autogen.agents.llm_agents import generate_gherkin


def _sanitize_filename(url: str) -> str:
    name = url.replace("https://", "").replace("http://", "")
    for ch in ["/", ":", "?", "&", "=", "#", "%"]:
        name = name.replace(ch, "_")
    return name.strip("_")


class GherkinBuilder:
    def __init__(self):
        self.output_dir = Path(config["output"]["directory"])

    def generate_full_feature(self, url: str, analysis_results: List[Dict[str, Any]]) -> Path:
        """Generate Gherkin feature using the LLM (required)."""
        feature_content = (generate_gherkin(url, analysis_results) or "").strip()
        if not feature_content or "Feature:" not in feature_content:
            raise RuntimeError("LLM did not produce valid Gherkin content (missing 'Feature:').")

        feature_name = f"Hover_Interactions_on_{_sanitize_filename(url)}"
        file_path = self.output_dir / f"{feature_name}.feature"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(feature_content)
        return file_path
