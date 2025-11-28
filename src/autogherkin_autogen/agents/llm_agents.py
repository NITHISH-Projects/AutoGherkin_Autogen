# Author: MARRI NITHISH
from typing import Optional, Tuple, Dict, Any, List
from autogherkin_autogen.config import config
import re
import requests


prompt = (
    "You are a generator of pure Gherkin .feature files. Strict non-negotiable rules:\n"
    "- Begin the response immediately with 'Feature:' as the very first characters (no leading whitespace or newlines).\n"
    "- Output ONLY valid Gherkin (no prose, no markdown, no code fences, no JSON).\n"
    "- Do not output any explanations, summaries, 'URL:', 'Hints', or any meta text.\n"
    "- Include a Background section that opens the provided URL.\n"
    "- Use exactly two scenarios:\n"
    "  1) Popup/overlay validation (Cancel flow if applicable; otherwise assert absence of overlays).\n"
    "  2) Hover-based interaction or Continue redirect validation describing visibility or navigation.\n"
    "- Use Given/When/Then/And steps.\n"
    "- Replace <URL> with the exact URL provided in the user message.\n"
    "Example skeleton:\n"
    "Feature: Title\n"
    "\n"
    "Background:\n"
    "  Given I open the URL \"<URL>\"\n"
    "\n"
    "Scenario: Validate overlay or popup behavior (Cancel flow)\n"
    "  When <action>\n"
    "  Then <assertions>\n"
    "\n"
    "Scenario: Validate hover-based interaction or Continue redirect\n"
    "  When <action>\n"
    "  Then <assertions>\n"
)


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
        # Normalize Ollama base URL; use native Ollama API (not OpenAI-compatible /v1)
        base = config["llm"]["base_url"].rstrip("/")

        # LLM configuration for AutoGen (native Ollama)
        llm_config = {
            "config_list": [
                {
                    "model": config["llm"]["model"],
                    "base_url": base,
                    "api_type": "ollama",
                }
            ],
            "timeout": 600,
            "temperature": min(0.2, config["llm"].get("temperature", 0.7)),
            "cache_seed": None,
        }

        # Create agents
        g_agent = AssistantAgent(
            name="Gherkin_Generation_Agent",
            system_message=prompt,
            llm_config=llm_config,
        )

        # Enable tool execution on the user proxy
        u_proxy = UserProxyAgent(
            name="User_Proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            code_execution_config={"work_dir": "."},  # allow executing registered tools
        )

        return g_agent, u_proxy

    except Exception:
        return None


def _format_user_message(url: str, interactions: List[Dict[str, Any]]) -> str:
    """
    Create a single plain-text message that includes the URL and interactions,
    matching the system prompt's expectations (no JSON in final output).
    """
    lines = [f"URL: {url}", "", "Interactions:"]
    for idx, item in enumerate(interactions, start=1):
        # Keep it readable; interactions can be long strings or dicts
        if isinstance(item, dict):
            # Flatten common keys if present
            action = item.get("action")
            selector = item.get("selector")
            note = item.get("note") or item.get("error") or item.get("message")
            summarized = f"{idx}. action={action!r} selector={selector!r} note={note!r}"
        else:
            summarized = f"{idx}. {str(item)}"
        lines.append(summarized)
    return "\n".join(lines)


def _extract_text(msg: Any) -> str:
    """
    Extract text content from autogen message structures (handles dict/list formats).
    """
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg

    # Message dict from autogen
    if isinstance(msg, dict):
        # Direct text field
        if "text" in msg and isinstance(msg["text"], str):
            return msg["text"]

        content = msg.get("content")
        # content may be a string
        if isinstance(content, str):
            return content
        # content may be a list of segments (each possibly dict with 'text')
        if isinstance(content, list):
            parts: List[str] = []
            for seg in content:
                if isinstance(seg, str):
                    parts.append(seg)
                elif isinstance(seg, dict):
                    if isinstance(seg.get("text"), str):
                        parts.append(seg["text"])
                    elif isinstance(seg.get("content"), str):
                        parts.append(seg["content"])
                    else:
                        # Nested lists/dicts
                        parts.append(_extract_text(seg))
                else:
                    parts.append(str(seg))
            return "".join(parts)
        # Fallback to stringify known fields
        if "tool_calls" in msg:
            return ""
        return str(msg.get("content") or msg)

    # List of messages/segments
    if isinstance(msg, list):
        return "".join(_extract_text(m) for m in msg)

    return str(msg)


def _normalize_feature_header(text: str) -> str:
    """
    Normalize any variant like 'feature -', 'FEATURE:' etc. to 'Feature: ...'
    without inventing new content. If a title exists, keep it; otherwise leave as 'Feature:'.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'^\s*(feature)\s*[:\-]\s*(.*)$', line, flags=re.IGNORECASE)
        if m:
            title = m.group(2).strip()
            lines[i] = f"Feature: {title}" if title else "Feature:"
            text = "\n".join(lines)
            break
    return text


def _salvage_gherkin(raw: str) -> str:
    """
    Try to salvage pure Gherkin from an LLM response that may contain
    prose, code fences, or leading text. Returns best-effort cleaned text.
    """
    if not raw:
        return ""
    text = raw

    # Remove code fences if present
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = "".join(parts[1:-1]).strip()
        else:
            text = text.replace("```", "").strip()

    # Trim anything before the first "Feature:"
    idx = text.find("Feature:")
    if idx >= 0:
        text = text[idx:]

    # Normalize header variants like 'feature:' or 'Feature -'
    text = _normalize_feature_header(text)

    return text.strip()


def _validate_gherkin(content: str, url: str) -> Tuple[bool, List[str]]:
    """
    Validate minimal Gherkin constraints:
    - Starts with 'Feature:' (no leading whitespace/newlines)
    - Contains 'Background:'
    - Contains Given I open the URL "<url>"
    - Contains exactly two 'Scenario:' sections
    - No code fences or meta text like 'URL:' lines
    """
    issues: List[str] = []
    if not content:
        issues.append("Empty content.")
        return False, issues

    if not content.startswith("Feature:"):
        issues.append("Response must start immediately with 'Feature:' (no leading whitespace/newlines).")

    # basic contamination checks
    if "```" in content:
        issues.append("Remove code fences (```); output must be pure Gherkin.")
    if "\nURL:" in content or content.startswith("URL:"):
        issues.append("Do not include 'URL:' lines or any meta text in the output.")

    if "Background:" not in content:
        issues.append("Missing 'Background:' section.")
    if f'Given I open the URL "{url}"' not in content:
        issues.append(f'Missing exact step: Given I open the URL "{url}"')

    scenarios_count = content.count("Scenario:")
    if scenarios_count != 2:
        issues.append(f"Must contain exactly two 'Scenario:' sections (found {scenarios_count}).")

    return (len(issues) == 0), issues


def _ollama_generate(model: str, base_url: str, prompt: str, temperature: float) -> str:
    """
    Call Ollama native API /api/generate synchronously and return the response text.
    """
    try:
        url = base_url.rstrip("/") + "/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": max(0.0, min(1.0, float(temperature)))
            }
        }
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        resp = data.get("response")
        if isinstance(resp, str):
            return resp
        return ""
    except Exception:
        return ""


def generate_gherkin(url: str, interactions: List[Dict[str, Any]]) -> str:
    """
    Generate Gherkin feature content using ONLY the LLM agent.
    - Enforces exactly two scenarios and other constraints via validation + guided retry.
    - No deterministic/non-LLM fallback will be used here. Returns empty string if validation fails.
    """
    # First attempt: call Ollama directly with a constrained prompt and retry loop
    try:
        base = config["llm"]["base_url"].rstrip("/")
        model = config["llm"]["model"]
        temperature = float(config["llm"].get("temperature", 0.0))
    except Exception:
        base = ""
        model = ""
        temperature = 0.0

    base_user_prompt = _format_user_message(url, interactions)
    max_attempts = 6
    last_issues: List[str] = []
    if base and model:
        for attempt in range(max_attempts):
            if attempt == 0:
                message = (
                    "Respond with ONLY pure Gherkin starting immediately with 'Feature:' and no prose/markdown/JSON.\n"
                    "Include a Background with the exact step: Given I open the URL "
                    f"\"{url}\"\n"
                    "Provide exactly two Scenario sections and use Given/When/Then/And steps.\n\n"
                    f"{base_user_prompt}"
                )
            else:
                issues_bulleted = "\n".join(f"- {i}" for i in last_issues) if last_issues else "- Does not satisfy constraints."
                message = (
                    "Regenerate the feature strictly following the rules. Previous output had issues:\n"
                    f"{issues_bulleted}\n\n"
                    "Remember:\n"
                    "- Start immediately with 'Feature:' (no leading whitespace/newlines)\n"
                    "- Output ONLY Gherkin (no prose/markdown/JSON)\n"
                    "- Include Background with exact step: Given I open the URL "
                    f'"{url}"\n'
                    "- Provide exactly two Scenario sections\n"
                    "- Use Given/When/Then/And steps\n\n"
                    f"{base_user_prompt}"
                )
            resp = _ollama_generate(model, base, message, temperature)
            content = _salvage_gherkin(_extract_text(resp)).strip()
            is_valid, issues = _validate_gherkin(content, url)
            if is_valid and "Feature:" in content:
                return content
            last_issues = issues

    # Prepare base prompt and retry count
    base_user_prompt = _format_user_message(url, interactions)
    max_attempts = 6

    last_issues: List[str] = []
    for attempt in range(max_attempts):
        # Reinitialize agents each attempt to avoid history contamination
        agents = _init_agents()
        if not agents:
            return ""
        gherkin_generation_agent, user_proxy = agents

        if attempt == 0:
            message = (
                "Respond with ONLY pure Gherkin starting immediately with 'Feature:' and no prose/markdown/JSON.\n"
                "Include some subject after 'Feature:' descripting short single line summary of Test File"
                "Include a Background with the exact step: Given I open the URL "
                f"\"{url}\"\n"
                "Provide exactly two Scenario sections and use Given/When/Then/And steps.\n\n"
                f"{base_user_prompt}"
            )
        else:
            # Provide precise feedback and restate constraints to steer the LLM deterministically
            issues_bulleted = "\n".join(f"- {i}" for i in last_issues) if last_issues else "- Does not satisfy constraints."
            message = (
                "Regenerate the feature strictly following the rules. Previous output had issues:\n"
                f"{issues_bulleted}\n\n"
                "Remember:\n"
                "- Start immediately with 'Feature:' (no leading whitespace/newlines)\n"
                "- Output ONLY Gherkin (no prose/markdown/JSON)\n"
                "- Include Background with exact step: Given I open the URL "
                f'"{url}"\n'
                "- Provide exactly two Scenario sections\n"
                "- Use Given/When/Then/And steps\n\n"
                f"{base_user_prompt}"
            )

        # Start/continue the chat with the assistant
        try:
            resp = user_proxy.initiate_chat(gherkin_generation_agent, message=message)  # type: ignore
        except Exception:
            return ""

        # Retrieve latest assistant content (prefer direct response, then agent state)
        content_raw: Any = resp
        if not content_raw:
            try:
                content_raw = gherkin_generation_agent.last_message()  # type: ignore
            except Exception:
                content_raw = None

        content = _extract_text(content_raw).strip()
        content = _salvage_gherkin(content)
        is_valid, issues = _validate_gherkin(content, url)

        if is_valid and "Feature:" in content:
            return content

        last_issues = issues

    # If we reach here, all attempts failed validation
    return ""
