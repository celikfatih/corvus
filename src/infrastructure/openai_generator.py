import json
import logging
from typing import List

from openai import OpenAI

from src.interfaces.ports import IAnswerGenerator
from src.domain.models import GoogleForm, FormField, Persona, FormAnswers
from src.domain.exceptions import AIProcessingError

logger = logging.getLogger(__name__)


def _build_question_payload(fields: List[FormField]) -> str:
    """Serialise a list of fields into a JSON string for the AI prompt."""
    return json.dumps(
        [
            {
                "id": f.id,
                "title": f.title,
                "type": f.type,
                "options": f.options,
                "scale_labels": f.scale_labels,
                "required": f.required,
            }
            for f in fields
        ],
        indent=2,
        ensure_ascii=False,
    )


def _parse_ai_response(content: str, chunk_index: int) -> dict:
    """Parse the AI's JSON response and validate the expected schema."""
    if not content:
        raise AIProcessingError(f"Received empty response from AI for chunk {chunk_index}.")
    try:
        parsed = json.loads(content)
        return parsed.get("answers", {})
    except json.JSONDecodeError as e:
        raise AIProcessingError(
            f"AI returned invalid JSON for chunk {chunk_index}: {e}"
        )


def find_closest_option(value: str, options: List[str]) -> str:
    """Finds the closest matching option in a list of options using robust matching."""
    if not options:
        return value

    # 1. Exact match
    if value in options:
        return value

    # 2. Case-insensitive / strip whitespace match
    val_norm = value.strip().lower()
    for opt in options:
        if opt.strip().lower() == val_norm:
            return opt

    # 3. Handle Turkish characters or common variations
    def normalize(s: str) -> str:
        s = s.lower().replace(" ", "").replace("\xa0", "")
        replacements = {
            "ç": "c",
            "ğ": "g",
            "ı": "i",
            "ö": "o",
            "ş": "s",
            "ü": "u",
            "i̇": "i",
        }
        for tr_char, eng_char in replacements.items():
            s = s.replace(tr_char, eng_char)
        return s.replace("\u0307", "")

    val_norm_tr = normalize(value)
    for opt in options:
        if normalize(opt) == val_norm_tr:
            return opt

    # 4. Partial substring match
    for opt in options:
        if val_norm_tr in normalize(opt) or normalize(opt) in val_norm_tr:
            return opt

    # 5. Default fallback to first option if no match is found
    logger.warning(f"Could not match AI response '{value}' to any option in {options}. Falling back to '{options[0]}'.")
    return options[0]


class OpenAIAnswerGenerator(IAnswerGenerator):
    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model: str = "gpt-4o",
        chunk_size: int = 30,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.chunk_size = chunk_size

    def generate_answers(self, form: GoogleForm, persona: Persona) -> FormAnswers:
        """
        Splits the form fields into chunks of `chunk_size`, calls the AI for
        each chunk, and merges all answers into a single FormAnswers object.
        """
        fields = form.fields
        chunks = [
            fields[i: i + self.chunk_size]
            for i in range(0, len(fields), self.chunk_size)
        ]

        total_chunks = len(chunks)
        logger.info(
            f"Splitting {len(fields)} fields into {total_chunks} chunk(s) "
            f"of up to {self.chunk_size} fields each."
        )

        merged_answers: dict = {}
        for idx, chunk in enumerate(chunks, start=1):
            logger.info(f"Processing chunk {idx}/{total_chunks} ({len(chunk)} fields)...")
            chunk_answers = self._generate_for_chunk(chunk, persona, chunk_index=idx)
            merged_answers.update(chunk_answers)
            logger.info(f"Chunk {idx}/{total_chunks} complete — {len(chunk_answers)} answers received.")

        # Post-process answers for maximum robustness (exact matching, scale cleaning, etc.)
        final_answers: dict = {}
        fields_by_id = {f.id: f for f in fields}
        import re

        for field_id, answer in merged_answers.items():
            field = fields_by_id.get(field_id)
            if not field:
                final_answers[field_id] = answer
                continue

            if field.type == "Scale":
                digits = re.findall(r"\d+", str(answer))
                if digits:
                    final_answers[field_id] = digits[0]
                else:
                    final_answers[field_id] = str(answer)
                continue

            if not field.options:
                final_answers[field_id] = answer
                continue

            if isinstance(answer, list):
                mapped_list = []
                for item in answer:
                    mapped_list.append(find_closest_option(str(item), field.options))
                final_answers[field_id] = mapped_list
            else:
                final_answers[field_id] = find_closest_option(str(answer), field.options)

        return FormAnswers(answers=final_answers)

    def _generate_for_chunk(
        self, fields: List[FormField], persona: Persona, chunk_index: int
    ) -> dict:
        system_prompt = (
            "You are an automated agent answering a survey form on behalf of the following persona:\n"
            f"{persona.description}\n\n"
            "Answer every question truthfully from the persona's perspective.\n"
            "Rules:\n"
            "- Radio / Dropdown: return exactly ONE string from the provided options.\n"
            "- Checkbox: return a LIST of strings from the provided options.\n"
            "- Text / Paragraph: return a concise, realistic string that fits the persona.\n"
            "- Scale: return the STRING representation of the chosen number.\n"
            "- Date (type Date): return a date string like '2004-03-15'.\n"
            "- Time (type Time): return a time string like '09:00'.\n"
            "IMPORTANT: only pick values from the options list when options are provided."
        )

        user_message = f"Form questions (answer all):\n{_build_question_payload(fields)}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "form_answers",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answers": {
                                    "type": "object",
                                    "description": (
                                        "Mapping of entry.XXXXX keys to the answer value. "
                                        "A list of strings for checkboxes, a plain string otherwise."
                                    ),
                                    "additionalProperties": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        ]
                                    },
                                }
                            },
                            "required": ["answers"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    },
                },
            )
        except Exception as e:
            raise AIProcessingError(
                f"AI API call failed for chunk {chunk_index}: {str(e)}"
            )

        return _parse_ai_response(response.choices[0].message.content, chunk_index)
