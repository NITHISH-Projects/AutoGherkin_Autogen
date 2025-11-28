# Author: MARRI NITHISH
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any
from autogherkin_autogen.config import config


class InteractionDetector:
    """
    Dynamically detects hover-based interactions without relying on hardcoded selectors.

    Strategy:
    - Discover candidate hoverable elements in the live page via JS heuristics:
      * visible + interactive (a/button/role/tabindex) OR
      * has onmouseenter/over handlers OR
      * has hidden descendants (common for dropdowns and overlays) OR
      * cursor: pointer and has descendants that are initially hidden
    - For each candidate, capture pre-hover visible snapshot, simulate hover, then capture post-hover snapshot.
    - Compute delta: newly visible elements, presence of overlays/popups, and classify interaction type.
    - Return structured interaction records to feed into the LLM Gherkin generator.
    """

    def __init__(self, page):
        self.page = page
        self.hover_delay = config["analysis"]["hover_delay"]
        self.max_elements = config["analysis"]["max_elements"]

    # ------------------------------
    # Public API
    # ------------------------------
    def detect_hover_interactions(self, potential_selectors: Optional[List[Any]] = None) -> List[dict]:
        """
        Detect interactions for potential hoverable elements. If potential_selectors are not valid CSS selectors,
        this method will auto-discover candidates from the live page.
        """
        selectors = self._normalize_or_discover_candidates(potential_selectors)
        interactions = []

        for selector in selectors[: self.max_elements]:
            try:
                pre = self._get_current_state()
                post = self.simulate_hover(selector)
                if not post:
                    continue

                delta = self._compute_delta(pre, post)
                interaction_type = self._classify_interaction(pre, post, delta)

                if interaction_type != "none":
                    record = {
                        "selector": selector,
                        "pre_hover": pre,
                        "post_hover": post,
                        "delta": delta,
                        "type": interaction_type,
                    }
                    interactions.append(record)
                    self._cache_snapshot(record)

            except Exception as e:
                print(f"Error detecting interaction for {selector}: {e}")
        return interactions

    # ------------------------------
    # Hover Simulation
    # ------------------------------
    def simulate_hover(self, selector: str) -> Optional[dict]:
        """Simulate hover on an element and return the post-hover state."""
        try:
            # Ensure the element exists and is visible
            if not self._element_exists(selector):
                return None

            # Attempt to dismiss cookie/consent overlays (e.g., OneTrust) that intercept pointer events
            if config.get("consent", {}).get("auto_dismiss", True):
                self._dismiss_blocking_banners()

            # Capture overlay state before hover for delta calculation
            pre_overlay = self._detect_overlay_like()

            # Prefer locator-based hover with scroll into view; then fallback strategies
            loc = self.page.locator(selector).first
            try:
                loc.scroll_into_view_if_needed(timeout=self.hover_delay)
            except Exception:
                pass

            hovered = False
            try:
                # Try locator.hover with a slightly larger timeout
                loc.hover(timeout=self.hover_delay * 2)
                hovered = True
            except Exception:
                # Fallback 1: move real mouse to the element center
                try:
                    box = loc.bounding_box()
                    if box:
                        cx = box["x"] + box["width"] / 2
                        cy = box["y"] + box["height"] / 2
                        self.page.mouse.move(cx, cy, steps=10)
                        hovered = True
                except Exception:
                    pass

            if not hovered:
                # Fallback 2: dispatch a mouseover event or try page.hover with force
                try:
                    self.page.dispatch_event(selector, "mouseover")
                    hovered = True
                except Exception:
                    try:
                        # Some Playwright bindings support 'force' on page.hover
                        self.page.hover(selector, timeout=self.hover_delay * 2, force=True)  # type: ignore
                        hovered = True
                    except Exception:
                        # Last resort: hard-hide known blocking banners and continue
                        self._force_hide_known_banners()

            self.page.wait_for_timeout(self.hover_delay)

            # Return the post state; delta computation happens at a higher level
            post = self._get_current_state(pre_overlay=pre_overlay)
            return post
        except Exception as e:
            print(f"Error simulating hover on {selector}: {e}")
        return None

    def _dismiss_blocking_banners(self) -> None:
        """
        Dismiss common cookie/consent overlays that intercept pointer events.
        Currently includes OneTrust and a generic site banner close button if present.
        """
        try:
            # OneTrust consent (common IDs/selectors)
            ot_root = self.page.locator("#onetrust-consent-sdk")
            ot_visible = False
            try:
                ot_visible = ot_root.first.is_visible()
            except Exception:
                ot_visible = False

            if ot_visible:
                # Try reject first, then accept, then close
                candidates = [
                    "#onetrust-reject-all-handler",
                    "#onetrust-accept-btn-handler",
                    "#onetrust-close-btn-container",
                    "button:has-text(\"Reject All\")",
                    "button:has-text(\"Reject\")",
                    "button:has-text(\"Accept All\")",
                    "button:has-text(\"Accept\")",
                ]
                for sel in candidates:
                    try:
                        btn = self.page.locator(sel).first
                        if btn.is_visible():
                            btn.click(timeout=1500)
                            break
                    except Exception:
                        continue
                try:
                    ot_root.first.wait_for(state="hidden", timeout=3000)
                except Exception:
                    # If still present, try to hide via CSS as a last resort
                    self._force_hide_known_banners()

            # Site-specific "indication" banner close if present (from error logs)
            try:
                indi = self.page.locator("button#indication-close").first
                if indi.is_visible():
                    indi.click(timeout=1000)
            except Exception:
                pass
        except Exception:
            # Best-effort; ignore failures
            pass

    def _force_hide_known_banners(self) -> None:
        """Force-hide known blocking banners if graceful dismissal failed."""
        try:
            self.page.evaluate(
                """() => {
                    const el = document.querySelector('#onetrust-consent-sdk');
                    if (el) { el.style.display = 'none'; el.setAttribute('aria-hidden', 'true'); }
                }"""
            )
        except Exception:
            pass

    # ------------------------------
    # Candidate Discovery & Utilities
    # ------------------------------
    def _normalize_or_discover_candidates(self, potential_selectors: Optional[List[Any]]) -> List[str]:
        """Normalize input into a list of CSS selectors or auto-discover candidates if needed."""
        if not potential_selectors:
            return self._discover_candidates()

        # If strings, assume CSS selectors
        if all(isinstance(s, str) for s in potential_selectors):
            return potential_selectors

        # Otherwise, attempt discovery to avoid tight coupling with static parser structures
        return self._discover_candidates()

    def _discover_candidates(self) -> List[str]:
        """Discover potential hoverable elements using generic, runtime heuristics."""
        script = f"""
        () => {{
            const MAX = {self.max_elements * 3}; // discover a bit more, we'll cut later

            const isVisible = (el) => {{
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
            }};

            const hasHiddenDescendant = (el) => {{
                // Hidden or zero-sized descendant - common in dropdowns/menus/overlays that reveal on hover
                for (const c of el.querySelectorAll('*')) {{
                    const sc = getComputedStyle(c);
                    const rc = c.getBoundingClientRect();
                    if (sc.display === 'none' || sc.visibility === 'hidden' || (rc.width === 0 && rc.height === 0)) {{
                        return true;
                    }}
                }}
                return false;
            }};

            const isInteractive = (el) => {{
                const s = getComputedStyle(el);
                return (
                    el.tagName === 'A' ||
                    el.tagName === 'BUTTON' ||
                    el.hasAttribute('role') ||
                    el.hasAttribute('tabindex') ||
                    typeof el.onmouseenter === 'function' ||
                    typeof el.onmouseover === 'function' ||
                    s.cursor === 'pointer'
                );
            }};

            const cssPath = (el) => {{
                if (!(el instanceof Element)) return '';
                const path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {{
                    let selector = el.nodeName.toLowerCase();
                    if (el.id) {{
                        selector += '#' + CSS.escape(el.id);
                        path.unshift(selector);
                        break;
                    }} else {{
                        let sib = el, nth = 1;
                        while ((sib = sib.previousElementSibling) != null) {{
                            if (sib.nodeName === el.nodeName) nth++;
                        }}
                        selector += `:nth-of-type(${{nth}})`;
                    }}
                    path.unshift(selector);
                    el = el.parentElement;
                }}
                return path.join(' > ');
            }};

            const candidates = new Set();
            const all = document.querySelectorAll('*');
            for (const el of all) {{
                if (!isVisible(el)) continue;
                if (isInteractive(el) || hasHiddenDescendant(el)) {{
                    const sel = cssPath(el);
                    if (sel) candidates.add(sel);
                    if (candidates.size >= MAX) break;
                }}
            }}
            return Array.from(candidates);
        }}
        """
        try:
            selectors = self.page.evaluate(script)
            # De-duplicate and cap
            uniq = []
            seen = set()
            for s in selectors:
                if s not in seen:
                    seen.add(s)
                    uniq.append(s)
                if len(uniq) >= self.max_elements:
                    break
            return uniq
        except Exception as e:
            print(f"Candidate discovery failed: {e}")
            return []

    def _element_exists(self, selector: str) -> bool:
        try:
            return self.page.query_selector(selector) is not None
        except Exception:
            return False

    # ------------------------------
    # State, Delta, Classification
    # ------------------------------
    def _get_current_state(self, pre_overlay: Optional[dict] = None) -> dict:
        """Get current DOM state summary: visible interactive elements and overlay presence."""
        visible = self._get_visible_elements()
        overlay = self._detect_overlay_like()
        delta_overlay = False
        if pre_overlay is not None:
            delta_overlay = overlay.get("overlay_detected", False) and not pre_overlay.get("overlay_detected", False)

        state = {
            "timestamp": datetime.now().isoformat(),
            "visible_elements": visible,
            "meta": {
                "overlay_detected": overlay.get("overlay_detected", False),
                "overlay_nodes": overlay.get("overlay_nodes", []),
                "new_visible_count": 0,  # will be populated by _compute_delta
                "overlay_became_visible": delta_overlay,
            },
        }
        return state

    def _get_visible_elements(self) -> List[dict]:
        """
        Capture visible elements in a generic way (not depending on specific classes).
        We prioritize interactives and elements with roles/tabindex.
        """
        script = """
        () => {
            const isVisible = (el) => {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
            };
            const cssPath = (el) => {
                if (!(el instanceof Element)) return '';
                const path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    if (el.id) {
                        selector += '#' + CSS.escape(el.id);
                        path.unshift(selector);
                        break;
                    } else {
                        let sib = el, nth = 1;
                        while ((sib = sib.previousElementSibling) != null) {
                            if (sib.nodeName === el.nodeName) nth++;
                        }
                        selector += `:nth-of-type(${{nth}})`;
                    }
                    path.unshift(selector);
                    el = el.parentElement;
                }
                return path.join(' > ');
            };
            const result = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (!isVisible(el)) continue;
                const role = el.getAttribute('role') || '';
                const tabindex = el.getAttribute('tabindex') || '';
                const tag = el.tagName;
                const text = (el.textContent || '').trim().slice(0, 80);
                const selector = cssPath(el);
                const href = el.tagName === 'A' ? (el.href || el.getAttribute('href') || '') : (el.getAttribute('href') || '');
                const ariaLabel = el.getAttribute('aria-label') || '';
                const titleAttr = el.getAttribute('title') || '';
                result.push({ selector, tag, role, tabindex, text, href, ariaLabel, title: titleAttr });
            }
            return result;
        }
        """
        try:
            items = self.page.evaluate(script)
            # cap output
            return items[: self.max_elements * 10]
        except Exception as e:
            print(f"Visible elements snapshot failed: {e}")
            return []

    def _detect_overlay_like(self) -> dict:
        """
        Detect overlay/modal-like behavior heuristically:
        - elements with role='dialog' or aria-modal='true'
        - large fixed-position elements covering significant viewport area
        """
        script = """
        () => {
            const overlays = [];
            const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
            const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);

            const isOverlayCandidate = (el) => {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                const large = r.width >= vw * 0.6 && r.height >= vh * 0.4;
                const fixed = s.position === 'fixed';
                const dialogLike = el.getAttribute('role') === 'dialog' || el.getAttribute('aria-modal') === 'true';
                return (dialogLike || (fixed && large));
            };

            const cssPath = (el) => {
                if (!(el instanceof Element)) return '';
                const path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    if (el.id) {
                        selector += '#' + CSS.escape(el.id);
                        path.unshift(selector);
                        break;
                    } else {
                        let sib = el, nth = 1;
                        while ((sib = sib.previousElementSibling) != null) {
                            if (sib.nodeName === el.nodeName) nth++;
                        }
                        selector += `:nth-of-type(${{nth}})`;
                    }
                    path.unshift(selector);
                    el = el.parentElement;
                }
                return path.join(' > ');
            };

            for (const el of document.querySelectorAll('*')) {
                try {
                    if (!el.isConnected) continue;
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    if (s.visibility === 'hidden' || s.display === 'none' || r.width === 0 || r.height === 0) continue;
                    if (isOverlayCandidate(el)) {
                        overlays.push({ selector: cssPath(el), tag: el.tagName, role: el.getAttribute('role') || '' });
                    }
                } catch (_) {}
            }
            return {
                overlay_detected: overlays.length > 0,
                overlay_nodes: overlays.slice(0, 10)
            };
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception as e:
            print(f"Overlay detection failed: {e}")
            return {"overlay_detected": False, "overlay_nodes": []}

    def _compute_delta(self, pre: dict, post: dict) -> dict:
        """Compute newly visible elements and summarize changes."""
        pre_set = {item["selector"] for item in pre.get("visible_elements", [])}
        post_items = post.get("visible_elements", [])
        new_items = [item for item in post_items if item["selector"] not in pre_set]

        # update post meta for convenience
        post["meta"]["new_visible_count"] = len(new_items)

        return {
            "new_visible_elements": new_items[: self.max_elements],
            "overlay_became_visible": post.get("meta", {}).get("overlay_became_visible", False),
            "overlay_detected": post.get("meta", {}).get("overlay_detected", False),
        }

    def _classify_interaction(self, pre: dict, post: dict, delta: dict) -> str:
        """Classify the type of interaction (dropdown, popup, hover_reveal, none)."""
        if delta.get("overlay_became_visible") or (delta.get("overlay_detected") and (pre.get("meta", {}).get("overlay_detected") is False)):
            return "popup"

        new_count = len(delta.get("new_visible_elements", []))
        if new_count == 0:
            return "none"

        # Heuristic: if most new elements are descendants of the hovered element area, call it dropdown
        # We can't easily compute ancestry without storing the hovered selector; approximate via text/role density.
        role_count = sum(1 for el in delta["new_visible_elements"] if el.get("role"))
        if role_count >= max(1, new_count // 2):
            return "dropdown"

        return "hover_reveal"

    def _cache_snapshot(self, interaction: dict):
        """Cache interaction snapshot as JSON."""
        cache_dir = Path("outputs/cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        timestamp = interaction["post_hover"]["timestamp"].replace(":", "-")
        with open(cache_dir / f"interaction_{timestamp}.json", "w") as f:
            json.dump(interaction, f, indent=2)
