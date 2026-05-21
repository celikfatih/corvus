from abc import ABC, abstractmethod
from src.domain.models import GoogleForm, Persona, FormAnswers

class IFormParser(ABC):
    @abstractmethod
    def parse(self, url: str) -> GoogleForm:
        """Fetches and parses a Google Form from the given URL."""
        pass

class IAnswerGenerator(ABC):
    @abstractmethod
    def generate_answers(self, form: GoogleForm, persona: Persona) -> FormAnswers:
        """Generates answers based on the given form and persona."""
        pass

class IFormSubmitter(ABC):
    @abstractmethod
    def submit(self, form: GoogleForm, answers: FormAnswers) -> bool:
        """Submits the answers to the form action URL."""
        pass
