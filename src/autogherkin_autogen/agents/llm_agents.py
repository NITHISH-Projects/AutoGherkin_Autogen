# Author: MARRI NITHISH
import json
from typing import Optional, Tuple, Dict, Any
from autogherkin_autogen.config import config


def _init_agents() -> Optional[Tuple[object, object]]:
    """
    Lazily initialize AutoGen agents. If initialization fails (e.g., missing extras),
    return None so the caller can decide how to proceed.
    """
    try:
        # AutoGen imports
        from autogen import AssistantAgent, UserProxyAgent  # type: ignore
    except Exception:
        return None

    try:
        # Normalize Ollama base URL for OpenAI-compatible endpoint expected by AutoGen
        base = config["llm"]["base_url"].rstrip("/")
        api_base = base if base.endswith("/v1") else base + "/v1"

        # LLM configuration for AutoGen (OpenAI-compatible)
        llm_config = {
            "config_list": [
                {
                    "model": config["llm"]["model"],
                    "base_url": api_base,
                    "api_type": "openai",
                    "api_key": "ollama",  # Dummy key for Ollama's OpenAI-compatible API
                }
            ],
            "timeout": 180,
            "temperature": min(0.2, config["llm"].get("temperature", 0.7)),
            "cache_seed": None,
        }

        # Create agents
        g_agent = AssistantAgent(
            name="Gherkin_Generation_Agent",
            system_message=(
                "You generate Gherkin .feature files. Strict requirements:\n"
                "- Begin the response immediately with 'Feature:' (as the very first characters).\n"
                "- Output ONLY valid Gherkin (no prose, no markdown, no code fences).\n"
                "- Include a Background section that opens the provided URL.\n"
                "- Produce exactly two scenarios for the given URL and interactions:\n"
                "  1) Popup/overlay validation (if applicable; otherwise assert absence of overlays in Then).\n"
                "  2) Hover-based interaction validation (e.g., dropdowns/menus revealed on hover) describing visibility changes.\n"
                "- Use Given/When/Then/And steps; avoid extraneous commentary.\n"
                "- Follow this minimal example of structure (titles/steps may differ):\n"
                "Feature: Title\n"
                "\n"
                "Background:\n"
                "  Given I open the URL \"<URL>\"\n"
                "\n"
                "Scenario: Validate overlay or popup behavior\n"
                "  When I hover over interactive elements on the page\n"
                "  Then [assertions]\n"
                "\n"
                "Scenario: Validate hover-based interaction\n"
                "  When I hover the element(s) under test\n"
                "  Then [assertions]\n"
            ),
            llm_config=llm_config,
        )

        # Enable tool execution on the user proxy
        u_proxy = UserProxyAgent(
            name="User_Proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=8,
            code_execution_config={"work_dir": "."},  # allow executing registered tools
        )


        return g_agent, u_proxy

    except Exception:
        return None


def generate_gherkin(url, interactions):
    """
    Generate Gherkin feature content using AutoGen with a registered validation tool.
    This function expects the LLM to be available; if agents cannot be initialized,
    it returns an empty string, and the caller may raise an error.
    """
    agents = _init_agents()
    if not agents:
        # Signal to caller that LLM path is unavailable
        return ""

    gherkin_generation_agent, user_proxy = agents

    # Compose a strict instruction to call the validation tool before returning
    prompt = (
        "Generate a complete Gherkin .feature file for the following URL and interactions.\n"
        "- Your first characters must be 'Feature:' and output ONLY valid Gherkin (no prose, no code fences).\n"
        f"- Include a Background section that opens the provided URL, e.g., Given I open the URL \"{url}\".\n"
        "- Provide exactly two scenarios:\n"
        "  1) Popup/overlay validation (or assert absence of overlays in Then if none).\n"
        "  2) Hover-based interaction validation describing visibility changes and revealed items.\n"
        "- Use Given/When/Then/And steps only.\n"
        "- Replace placeholders like [assertions] with concrete assertions derived from the interactions JSON. Do not output brackets.\n"
        "- Follow this example format strictly (titles and step wording can differ, structure must match):\n"
        "Feature: Title\n"
        "\n"
        "Background:\n"
        f"  Given I open the URL \"{url}\"\n"
        "\n"
        "Scenario: Validate overlay or popup behavior\n"
        "  When I hover over interactive elements on the page\n"
        "  Then Assertions...\n"
        "\n"
        "Scenario: Validate hover-based interaction\n"
        "  When I hover the element(s) under test\n"
        "  Then Assertions...\n"
        "\n"
        f"URL:\n{url}\n\n"
        f"Detected Interactions (JSON):\n{json.dumps(interactions, indent=2)}\n"
    )

    # Start the chat
    try:
        attempt = 0
        content = ""
        current_prompt = prompt
        while attempt < 3:
            result = user_proxy.initiate_chat(gherkin_generation_agent, message=current_prompt)  # type: ignore

            msg = None
            try:
                msg = gherkin_generation_agent.last_message().get("content")  # type: ignore
            except Exception:
                pass
            if not msg:
                try:
                    msg = user_proxy.last_message().get("content")  # type: ignore
                except Exception:
                    msg = str(result)
            content = (msg or "").strip()
            if "Feature:" in content:
                content = content[content.index("Feature:"):]
                break

            repair_prompt = (
                "Your previous response did not start with 'Feature:'. "
                "Respond again with ONLY valid Gherkin content, starting with 'Feature:'. "
                "Follow this exact structure:\n"
                "Feature: <Title>\n\n"
                "Background:\n"
                f"  Given I open the URL \"{url}\"\n\n"
                "Scenario: Validate overlay or popup behavior\n"
                "  When I hover over interactive elements on the page\n"
                "  Then [assertions]\n\n"
                "Scenario: Validate hover-based interaction\n"
                "  When I hover the element(s) under test\n"
                "  Then [assertions]\n\n"
                "Do not include explanations or code fences."
            )
            current_prompt = repair_prompt
            attempt += 1

        return content if "Feature:" in content else ""
    except Exception:
        # Bubble up as empty content; caller will enforce failure if LLM is required
        return ""
