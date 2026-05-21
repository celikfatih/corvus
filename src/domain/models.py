from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class FormField(BaseModel):
    id: str = Field(..., description="The entry.XXXXX ID for the field")
    type: str = Field(..., description="Type of the field: Text, Radio, Checkbox, Scale, etc.")
    title: str = Field(..., description="The question title/text")
    options: Optional[List[str]] = Field(None, description="Available choices for Radio/Checkbox")
    scale_labels: Optional[Dict[str, str]] = Field(None, description="Labels for scale constraints, e.g. {'1': 'Worst', '5': 'Best'}")
    required: bool = Field(False, description="Whether the field is required")
    page_index: int = Field(0, description="0-based page/section index this field belongs to")

class GoogleForm(BaseModel):
    action_url: str = Field(..., description="The POST URL for form submission")
    fields: List[FormField] = Field(default_factory=list, description="List of parsed fields")
    hidden_fields: Dict[str, str] = Field(default_factory=dict, description="Hidden fields required for submission (fbzx, partialResponse, etc.)")

class Persona(BaseModel):
    description: str = Field(..., description="The free-text or JSON string describing the persona")

class FormAnswers(BaseModel):
    answers: Dict[str, Any] = Field(..., description="Mapping of entry.XXXXX to the chosen answer(s). Lists are used for checkboxes.")
