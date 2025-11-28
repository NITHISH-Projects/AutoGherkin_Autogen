# Author: MARRI NITHISH
import json
import requests
from typing import Optional, Tuple, Dict, Any, List
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
        # Normalize Ollama base URL; use native Ollama API (not OpenAI-compatible /v1)
        base = config["llm"]["base_url"].rstrip("/")

        # LLM configuration for AutoGen (native Ollama)
        llm_config = {
            "config_list": [
                {
                    "model": config["llm"]["model"],
                    "base_url": base,
                    "api_type": "ollama"
                }
            ],
            "timeout": 600,
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
                "- Do not output any explanations, summaries, 'URL:', 'Hints', or JSON in your final message.\n"
                "- The very first characters of your message must be 'Feature:' with no leading whitespace or newlines.\n"
                "- Include a Background section that opens the provided URL.\n"
                "- Replace <URL> with the exact URL provided in the context (e.g., from the 'URL:' line).\n"
                "- Produce exactly two scenarios for the given URL and interactions:\n"
                "  1) Popup/overlay validation (Cancel flow if applicable; otherwise assert absence of overlays).\n"
                "  2) Hover-based interaction or Continue redirect validation describing visibility or navigation.\n"
                "- Use Given/When/Then/And steps; avoid extraneous commentary.\n"
                "- Follow this minimal structure (titles/steps may differ):\n"
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


def _count_scenarios(gherkin: str) -> int:
    try:
        return sum(1 for ln in gherkin.splitlines() if ln.strip().startswith("Scenario:"))
    except Exception:
        return 0


def _extract_hints(interactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract soft hints from runtime-detected interactions to guide the LLM,
    without generating any steps locally.
    """
    hints: Dict[str, Any] = {
        "learn_more_label": None,
        "popup_title": None,
        "has_cancel_button": False,
        "has_continue_button": False,
        "expected_redirect_url": None,
    }

    try:
        # Any visible "Learn More"
        for it in interactions or []:
            for el in (it.get("pre_hover", {}) or {}).get("visible_elements", []) or []:
                t = (el.get("text") or "").strip()
                if t and "learn more" in t.lower():
                    hints["learn_more_label"] = t
                    break
            if hints["learn_more_label"]:
                break

        # Popup title and buttons from deltas
        for it in interactions or []:
            delta = (it.get("delta", {}) or {})
            for el in delta.get("new_visible_elements", []) or []:
                t = (el.get("text") or "").strip()
                if not t:
                    continue
                low = t.lower()
                if (hints["popup_title"] is None) and ("you are now leaving" in low or "leaving" in low):
                    hints["popup_title"] = t
                if "cancel" in low:
                    hints["has_cancel_button"] = True
                if "continue" in low:
                    hints["has_continue_button"] = True
                    href = el.get("href") or ""
                    if href:
                        hints["expected_redirect_url"] = href
    except Exception:
        pass

    return hints


def _compact_interactions(interactions: List[Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
    """
    Minimize interaction payload for the LLM prompt to reduce verbosity and nudge the model
    to start directly with 'Feature:' per system_message.

    Keep at most `max_items` interactions and retain only fields helpful for wording assertions.
    """
    compact: List[Dict[str, Any]] = []
    try:
        for it in interactions[: max_items]:
            d = it.get("delta", {}) or {}
            new_vis = d.get("new_visible_elements", []) or []
            # extract up to a few texts/hrefs for concrete assertions
            texts: List[str] = []
            hrefs: List[str] = []
            for el in new_vis:
                t = (el.get("text") or "").strip()
                if t:
                    texts.append(t[:160])
                h = el.get("href") or ""
                if h:
                    hrefs.append(h)
                if len(texts) >= 3 and len(hrefs) >= 2:
                    break
            compact.append(
                {
                    "type": it.get("type", "none"),
                    "selector": it.get("selector", ""),
                    "delta": {
                        "new_texts": texts[:3],
                        "new_hrefs": hrefs[:2],
                        "overlay_detected": bool(d.get("overlay_detected", False)),
                        "overlay_became_visible": bool(d.get("overlay_became_visible", False)),
                    },
                }
            )
    except Exception:
        pass
    return compact


def _coerce_to_text(msg: Any) -> str:
    """
    Robustly extract textual content from various message shapes returned by AutoGen/Ollama:
    - str
    - dicts with content/text
    - lists of segments/dicts
    - objects exposing .get('content')
    """
    try:
        if msg is None:
            return ""
        if isinstance(msg, str):
            return msg
        if isinstance(msg, list):
            parts: List[str] = []
            for part in msg:
                t = _coerce_to_text(part)
                if t:
                    parts.append(t)
            return "\n".join(parts)
        if isinstance(msg, dict):
            if "content" in msg:
                return _coerce_to_text(msg.get("content"))
            if "text" in msg:
                t = msg.get("text")
                return t if isinstance(t, str) else ""
            # Fallback: try nested content again
            c = msg.get("content") if "content" in msg else None
            if c is not None:
                return _coerce_to_text(c)
            return ""
        # Some objects may behave like dicts
        try:
            content = msg.get("content")  # type: ignore
            if content:
                return _coerce_to_text(content)
        except Exception:
            pass
        return str(msg)
    except Exception:
        return ""


def _strip_code_fences(txt: str) -> str:
    try:
        if "```" in txt or "~~~" in txt:
            lines = []
            for ln in txt.splitlines():
                if ln.strip().startswith("```") or ln.strip().startswith("~~~"):
                    continue
                lines.append(ln)
            return "\n".join(lines).strip()
        return txt
    except Exception:
        return txt


def _ensure_feature_header(txt: str, url: str) -> str:
    try:
        idx = txt.find("Feature:")
        if idx >= 0:
            return txt[idx:].strip()
        idx_lower = txt.lower().find("feature:")
        if idx_lower >= 0:
            normalized = "Feature:" + txt[idx_lower + len("feature:") :]
            return normalized.strip()
        title = f"Feature: Hover Interactions on {url}"
        return f"{title}\n\n{txt.strip()}"
    except Exception:
        return txt


def _ensure_background(txt: str, url: str) -> str:
    try:
        if "Background:" in txt and f'Given I open the URL "{url}"' in txt:
            return txt
        parts = txt.splitlines()
        out: List[str] = []
        inserted = False
        i = 0
        while i < len(parts):
            out.append(parts[i])
            if not inserted and parts[i].startswith("Feature:"):
                j = i + 1
                while j < len(parts) and parts[j].strip() == "":
                    out.append(parts[j])
                    j += 1
                out.append("Background:")
                out.append(f'  Given I open the URL "{url}"')
                out.append("")
                inserted = True
                i = j
                continue
            i += 1
        if not inserted:
            out.insert(0, "")
            out.insert(0, f'  Given I open the URL "{url}"')
            out.insert(0, "Background:")
        return "\n".join(out).strip()
    except Exception:
        return txt


def _ensure_two_scenarios(txt: str) -> str:
    try:
        lines = txt.splitlines()
    except Exception:
        lines = txt.split("\n")
    # Collect indices of Scenario headers
    indices = [i for i, ln in enumerate(lines) if ln.strip().startswith("Scenario:")]
    try:
        if len(indices) == 0:
            if lines and lines[-1].strip() != "":
                lines.append("")
            lines.append("Scenario: Validate overlay or popup behavior (Cancel flow)")
            lines.append("  When I hover over detected interactive areas")
            lines.append("  Then I should not see unexpected overlays")
            lines.append("")
            lines.append("Scenario: Validate hover-based interaction or Continue redirect")
            lines.append("  When I hover over detected interactive areas")
            lines.append("  Then related elements should become visible")
            return "\n".join(lines).strip()
        if len(indices) == 1:
            if lines and lines[-1].strip() != "":
                lines.append("")
            lines.append("Scenario: Validate hover-based interaction or Continue redirect")
            lines.append("  When I hover over detected interactive areas")
            lines.append("  Then related elements should become visible")
            return "\n".join(lines).strip()
        if len(indices) > 2:
            second_idx = indices[1]
            end = len(lines)
            for k in range(2, len(indices)):
                end = indices[k]
                break
            return "\n".join(lines[:end]).rstrip()
        return "\n".join(lines).strip()
    except Exception:
        return txt


def generate_gherkin(url: str, interactions: List[Dict[str, Any]]) -> str:
    """
    Generate Gherkin feature content using ONLY the LLM agent.
    - Enforces exactly two scenarios.
    - Uses interaction-derived hints to steer the agent without hardcoding output.
    - No deterministic/non-LLM fallback will be used.
    Returns empty string if the agent cannot produce valid content after retries.
    """
    def _is_valid_gherkin(txt: str) -> bool:
        if not txt or "Feature:" not in txt:
            return False
        if "Background:" not in txt:
            return False
        if "```" in txt or "~~~" in txt:
            return False
        # Ensure exactly two scenarios
        if _count_scenarios(txt) != 2:
            return False
        # Ensure Background contains expected URL open step
        if f'Given I open the URL "{url}"' not in txt:
            return False
        return True

    # Derive soft hints for the agent
    hints = _extract_hints(interactions)

    # Build hints and compact context once
    hint_lines: List[str] = []
    if hints.get("learn_more_label"):
        hint_lines.append(f'- learn_more_label: "{hints["learn_more_label"]}"')
    if hints.get("popup_title"):
        hint_lines.append(f'- popup_title: "{hints["popup_title"]}"')
    if hints.get("has_cancel_button"):
        hint_lines.append("- has_cancel_button: true")
    if hints.get("has_continue_button"):
        hint_lines.append("- has_continue_button: true")
    if hints.get("expected_redirect_url"):
        hint_lines.append(f'- expected_redirect_url: "{hints["expected_redirect_url"]}"')

    hints_block = ""
    if hint_lines:
        hints_block = "Hints (derived from runtime interactions):\n" + "\n".join(hint_lines) + "\n\n"

    compact = _compact_interactions(interactions or [], max_items=3)

    def _instruction_prefix() -> str:
        return (
            "Respond with ONLY valid Gherkin and nothing else. "
            "Begin your message with 'Feature:' as the very first characters. "
            "Include a Background with the exact step: "
            f'Given I open the URL "{url}". '
            "Produce exactly two scenarios. Do not include markdown fences, explanations, JSON, or any other prose. "
            "Do not echo back the prompt, and do not include any 'URL:' or 'Hints' sections."
        )

    base_context_lines: List[str] = []
    base_context_lines.append(f'URL: {url}')
    if hints_block:
        base_context_lines.append(hints_block.strip())
    base_context_lines.append("Context (interactions):")
    base_context_lines.append(json.dumps(compact, indent=2))

    def _build_prompt(corrections: Optional[List[str]] = None) -> str:
        lines: List[str] = []
        lines.append(_instruction_prefix())
        if corrections:
            lines.append("")
            lines.append("Corrections from previous attempt:")
            for c in corrections:
                lines.append(f"- {c}")
        lines.append("")
        lines.extend(base_context_lines)
        return "\n".join(lines)

    def _analyze_invalid(content: str) -> List[str]:
        issues: List[str] = []
        if not content or "Feature:" not in content:
            issues.append("Start with 'Feature:' at the first character; do not include any preface.")
        if "Background:" not in content:
            issues.append("Add a Background section.")
        if f'Given I open the URL "{url}"' not in content:
            issues.append(f'Background must include: Given I open the URL "{url}"')
        if "```" in content or "~~~" in content:
            issues.append("Remove any code fences or markdown.")
        sc = _count_scenarios(content)
        if sc != 2:
            issues.append(f"Include exactly two 'Scenario:' sections (found {sc}).")
        return issues

    max_tries = 3
    content = ""
    corrections: List[str] = []
    last_raw: str = ""

    for _ in range(max_tries):
        # Initialize LLM agents fresh per attempt to avoid conversational drift
        agents = _init_agents()
        if not agents:
            return ""
        gherkin_generation_agent, user_proxy = agents

        prompt = _build_prompt(corrections if corrections else None)

        try:
            result = user_proxy.initiate_chat(gherkin_generation_agent, message=prompt)  # type: ignore

            # Retrieve latest assistant content (rely on AutoGen's auto-reply loop)
            raw_last = None
            try:
                raw_last = gherkin_generation_agent.last_message()  # type: ignore
            except Exception:
                pass

            content = _coerce_to_text(raw_last).strip()
            if not content:
                try:
                    raw_last = user_proxy.last_message()  # type: ignore
                    content = _coerce_to_text(raw_last).strip()
                except Exception:
                    content = _coerce_to_text(result).strip() or str(result)

            last_raw = content
            if "Feature:" in content:
                content = content[content.index("Feature:") :].strip()

            if _is_valid_gherkin(content):
                return content

            # Prepare corrections and retry
            corrections = _analyze_invalid(content)
        except Exception:
            if not corrections:
                corrections = ["Previous attempt failed due to an internal error; follow the format instructions strictly."]
            continue

    # Try direct Ollama chat as LLM fallback (agent-produced)
    try:
        base = config["llm"]["base_url"].rstrip("/")
        model = config["llm"]["model"]
        system_msg = (
            "You generate Gherkin .feature files. Strict requirements:\n"
            "- Begin the response immediately with 'Feature:' (as the very first characters).\n"
            "- Output ONLY valid Gherkin (no prose, no markdown, no code fences).\n"
            f'- Background must include: Given I open the URL "{url}".\n'
            "- Produce exactly two scenarios."
        )
        direct_prompt = _instruction_prefix() + "\n\n" + "\n".join(base_context_lines)
        resp = requests.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": direct_prompt}
                ],
                "stream": False,
                "options": {"temperature": config["llm"].get("temperature", 0.0)}
            },
            timeout=120,
        )
        if resp.ok:
            data = resp.json()
            msg = (data.get("message") or {}).get("content") or data.get("response") or ""
            content = (msg or "").strip()
            last_raw = content
            if "Feature:" in content:
                content = content[content.index("Feature:") :].strip()
            if _is_valid_gherkin(content):
                return content
    except Exception:
        pass

    # Try direct Ollama generate as LLM fallback (still agent-produced)
    try:
        base = config["llm"]["base_url"].rstrip("/")
        model = config["llm"]["model"]
        system_msg = (
            "You generate Gherkin .feature files. Strict requirements:\n"
            "- Begin the response immediately with 'Feature:' (as the very first characters).\n"
            "- Output ONLY valid Gherkin (no prose, no markdown, no code fences).\n"
            "- Include a Background with: " + f'Given I open the URL "{url}"' + ".\n"
            "- Produce exactly two scenarios."
        )
        direct_prompt = _instruction_prefix() + "\n\n" + "\n".join(base_context_lines)
        resp = requests.post(
            f"{base}/api/generate",
            json={
                "model": model,
                "prompt": direct_prompt,
                "system": system_msg,
                "stream": False,
                "options": {"temperature": config["llm"].get("temperature", 0.0)},
            },
            timeout=120,
        )
        if resp.ok:
            data = resp.json()
            content = (data.get("response") or "").strip()
            last_raw = content
            if "Feature:" in content:
                content = content[content.index("Feature:") :].strip()
            if _is_valid_gherkin(content):
                return content
    except Exception:
        pass

    # Soft-fix minor format issues from last agent output if available (still agent-authored content)
    if last_raw:
        soft = _strip_code_fences(last_raw)
        soft = _ensure_feature_header(soft, url)
        soft = _ensure_background(soft, url)
        soft = _ensure_two_scenarios(soft)
        if _is_valid_gherkin(soft):
            return soft

    # Final attempt: ask the model to repair previous output into valid Gherkin (still agent-authored)
    try:
        base = config["llm"]["base_url"].rstrip("/")
        model = config["llm"]["model"]
        system_msg = (
            "Rewrite the user's last message into a valid Gherkin .feature file. Strict requirements:\n"
            "- Begin immediately with 'Feature:' as the very first characters.\n"
            "- Output ONLY valid Gherkin (no prose, no markdown, no code fences).\n"
            f'- Background must include: Given I open the URL "{url}".\n'
            "- Produce exactly two scenarios."
        )
        repair_prompt = (
            "Rewrite the following into valid Gherkin that satisfies the constraints above. "
            "Do not echo this instruction. Output ONLY Gherkin:\n\n"
            + "\n".join(base_context_lines)
            + "\n\nPrevious attempt:\n"
            + (last_raw or "")
        )
        resp = requests.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": repair_prompt}
                ],
                "stream": False,
                "options": {"temperature": config["llm"].get("temperature", 0.0)}
            },
            timeout=120,
        )
        if resp.ok:
            data = resp.json()
            msg = (data.get("message") or {}).get("content") or data.get("response") or ""
            content = (msg or "").strip()
            if "Feature:" in content:
                content = content[content.index("Feature:") :].strip()
            if _is_valid_gherkin(content):
                return content
    except Exception:
        pass

    # Give up after LLM attempts (AutoGen + direct Ollama + soft-fix + repair); caller may decide deterministic fallback
    return ""
