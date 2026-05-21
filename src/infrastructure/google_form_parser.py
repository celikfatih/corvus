import requests
from bs4 import BeautifulSoup
import json
import re
from typing import Dict, List, Any, Optional

from src.interfaces.ports import IFormParser
from src.domain.models import GoogleForm, FormField
from src.domain.exceptions import FormParsingError


# Google Forms internal type constants
_TYPE_TEXT = 0
_TYPE_PARAGRAPH = 1
_TYPE_RADIO = 2
_TYPE_DROPDOWN = 3
_TYPE_CHECKBOX = 4
_TYPE_SCALE = 5
_TYPE_GRID = 7
_TYPE_PAGE_BREAK = 8
_TYPE_DATE = 9
_TYPE_TIME = 10

_TYPE_MAP = {
    _TYPE_TEXT: "Text",
    _TYPE_PARAGRAPH: "Text",
    _TYPE_RADIO: "Radio",
    _TYPE_DROPDOWN: "Dropdown",
    _TYPE_CHECKBOX: "Checkbox",
    _TYPE_SCALE: "Scale",
    _TYPE_DATE: "Date",
    _TYPE_TIME: "Time",
}


def _extract_option_label(option_item: Any) -> Optional[str]:
    """Safely extract the display label from a Google Forms option tuple."""
    if isinstance(option_item, list) and len(option_item) > 0:
        return str(option_item[0]) if option_item[0] is not None else None
    return None


class GoogleFormParser(IFormParser):
    def parse(self, url: str) -> GoogleForm:
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            raise FormParsingError(f"Failed to fetch the form: {str(e)}")

        soup = BeautifulSoup(response.text, "html.parser")
        form_element = soup.find("form")
        if not form_element:
            raise FormParsingError("No <form> element found in the provided URL.")

        action_url = form_element.get("action")
        if not action_url:
            raise FormParsingError("Form action URL not found.")

        # Extract hidden fields required for submission
        hidden_fields: Dict[str, str] = {}
        for hidden in form_element.find_all("input", type="hidden"):
            name = hidden.get("name")
            value = hidden.get("value")
            if name and value is not None:
                hidden_fields[name] = value

        fields = self._extract_fields_from_script(soup)
        if not fields:
            fields = self._extract_fields_fallback(form_element)

        return GoogleForm(
            action_url=action_url,
            fields=fields,
            hidden_fields=hidden_fields,
        )

    def _parse_fb_data(self, soup: BeautifulSoup) -> Optional[Any]:
        """Extract and parse the FB_PUBLIC_LOAD_DATA_ JavaScript variable."""
        for script in soup.find_all("script"):
            raw = script.string or ""
            if "FB_PUBLIC_LOAD_DATA_" not in raw:
                continue
            # Greedy match: capture from the opening bracket to last bracket
            match = re.search(
                r"var FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*\])\s*;", raw, re.DOTALL
            )
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        return None

    def _extract_fields_from_script(self, soup: BeautifulSoup) -> List[FormField]:
        fb_data = self._parse_fb_data(soup)
        if not fb_data or len(fb_data) < 2 or not isinstance(fb_data[1], list):
            return []

        raw_questions = fb_data[1][1] if len(fb_data[1]) > 1 else []
        if not raw_questions:
            return []

        fields: List[FormField] = []
        current_page = 0
        # Section context: type-8 items often carry a descriptive title for the
        # grid questions that follow, so we propagate that as fallback title context.
        section_context: str = ""

        for q in raw_questions:
            if not isinstance(q, list) or len(q) < 4:
                continue

            q_type: int = q[3]
            q_title: Optional[str] = q[1] if len(q) > 1 else None

            # ── Page break ────────────────────────────────────────────────────
            if q_type == _TYPE_PAGE_BREAK:
                current_page += 1
                # The page-break title is a section description — save as context
                if q_title:
                    section_context = q_title.strip()
                continue

            if len(q) < 5 or not q[4]:
                continue

            inputs = q[4]  # list of input sub-items

            # ── Grid (multiple rows, shared column options) ───────────────────
            if q_type == _TYPE_GRID:
                # Grid title may be None — fall back to the section context
                grid_title = (q_title or "").strip() or section_context
                for row in inputs:
                    if not isinstance(row, list) or len(row) < 1:
                        continue
                    row_id = row[0]
                    raw_opts = row[1] if len(row) > 1 else None
                    options = self._parse_options(raw_opts)
                    # Row-specific label sits at index 3
                    row_label = (
                        str(row[3][0]).strip()
                        if len(row) > 3 and isinstance(row[3], list) and row[3]
                        else None
                    )
                    row_title = row_label or grid_title
                    required = row[2] == 1 if len(row) > 2 else False
                    fields.append(
                        FormField(
                            id=f"entry.{row_id}",
                            type="Radio",
                            title=row_title,
                            options=options,
                            required=required,
                            page_index=current_page,
                        )
                    )
                continue

            # ── Standard single-input question ────────────────────────────────
            input_data = inputs[0]
            if not isinstance(input_data, list) or len(input_data) < 1:
                continue

            entry_id = f"entry.{input_data[0]}"
            required = input_data[2] == 1 if len(input_data) > 2 else False
            title = (q_title or "").strip() or section_context

            options: Optional[List[str]] = None
            scale_labels: Optional[Dict[str, str]] = None
            type_str = _TYPE_MAP.get(q_type, "Unknown")

            if q_type in (_TYPE_RADIO, _TYPE_DROPDOWN, _TYPE_CHECKBOX):
                raw_opts = input_data[1] if len(input_data) > 1 else None
                options = self._parse_options(raw_opts)

            elif q_type == _TYPE_SCALE:
                try:
                    raw_opts = input_data[1] if len(input_data) > 1 else None
                    if raw_opts:
                        min_val = str(raw_opts[0][0])
                        max_val = str(raw_opts[-1][0])
                    else:
                        min_val, max_val = "1", "5"
                    min_label = (
                        str(input_data[3][0])
                        if len(input_data) > 3 and input_data[3]
                        else ""
                    )
                    max_label = (
                        str(input_data[4][0])
                        if len(input_data) > 4 and input_data[4]
                        else ""
                    )
                    scale_labels = {min_val: min_label, max_val: max_label}
                except Exception:
                    pass

            fields.append(
                FormField(
                    id=entry_id,
                    type=type_str,
                    title=title,
                    options=options,
                    scale_labels=scale_labels,
                    required=required,
                    page_index=current_page,
                )
            )

        return fields

    def _parse_options(self, raw_opts: Any) -> Optional[List[str]]:
        """Extract display labels from a raw Google Forms options list."""
        if not raw_opts or not isinstance(raw_opts, list):
            return None
        labels = [_extract_option_label(o) for o in raw_opts]
        labels = [lbl for lbl in labels if lbl is not None]
        return labels if labels else None

    def _extract_fields_fallback(self, form_element) -> List[FormField]:
        """DOM-based fallback when FB_PUBLIC_LOAD_DATA_ is unavailable."""
        fields: List[FormField] = []
        for tag in form_element.find_all(["input", "textarea"]):
            name = tag.get("name", "")
            if name.startswith("entry."):
                fields.append(
                    FormField(
                        id=name,
                        type="Text",
                        title=name,
                        required=bool(tag.get("required")),
                    )
                )
        return fields
