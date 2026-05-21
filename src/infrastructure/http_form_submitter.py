import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List

from src.interfaces.ports import IFormSubmitter
from src.domain.models import GoogleForm, FormAnswers
from src.domain.exceptions import FormSubmissionError

import logging

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}


class HttpFormSubmitter(IFormSubmitter):
    def submit(self, form: GoogleForm, answers: FormAnswers) -> bool:
        # Group entry IDs by page_index
        page_map: Dict[int, List[str]] = {}
        for field in form.fields:
            page_map.setdefault(field.page_index, []).append(field.id)

        sorted_pages = sorted(page_map.keys())
        is_single_page = len(sorted_pages) <= 1

        try:
            session = requests.Session()
            # Mutable copy of hidden fields — updated between page submissions
            hidden_fields: Dict[str, str] = dict(form.hidden_fields)
            if "pageHistory" in hidden_fields:
                del hidden_fields["pageHistory"]
            page_history: List[int] = [sorted_pages[0]]

            for i, page_idx in enumerate(sorted_pages):
                is_last = i == len(sorted_pages) - 1
                entry_ids_on_page = page_map[page_idx]

                payload: List[tuple] = []

                # Add hidden fields
                for key, value in hidden_fields.items():
                    payload.append((key, value))

                # pageHistory accumulates visited page indices as comma-separated string
                payload.append(("pageHistory", ",".join(map(str, page_history))))

                # Accumulate answers for all pages visited so far (up to the current page)
                for p_idx in sorted_pages[:i + 1]:
                    for entry_id in page_map[p_idx]:
                        answer = answers.answers.get(entry_id)
                        if answer is None:
                            continue
                        if isinstance(answer, list):
                            for item in answer:
                                payload.append((entry_id, str(item)))
                        else:
                            payload.append((entry_id, str(answer)))

                # For non-last pages, signal Google to advance to the next page
                if not is_last:
                    payload.append(("continue", "1"))

                logger.info(
                    f"Submitting page {page_idx + 1}/{len(sorted_pages)} "
                    f"({len(entry_ids_on_page)} field(s))..."
                )

                response = session.post(
                    form.action_url,
                    data=payload,
                    headers=_HEADERS,
                    timeout=15,
                    allow_redirects=True,
                )
                response.raise_for_status()

                # After a non-final page, parse the response HTML to refresh hidden tokens
                if not is_last:
                    next_page_soup = BeautifulSoup(response.text, "html.parser")
                    for hidden in next_page_soup.find_all("input", type="hidden"):
                        name = hidden.get("name")
                        value = hidden.get("value", "")
                        if name:
                            hidden_fields[name] = value
                    if "pageHistory" in hidden_fields:
                        del hidden_fields["pageHistory"]
                    # Advance page history
                    page_history.append(sorted_pages[i + 1])

            return True

        except requests.RequestException as e:
            raise FormSubmissionError(f"Form submission HTTP error: {str(e)}")
