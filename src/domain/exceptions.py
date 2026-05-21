class CorvusError(Exception):
    """Base exception for the Corvus application."""
    pass

class FormParsingError(CorvusError):
    """Raised when the form cannot be parsed successfully."""
    pass

class AIProcessingError(CorvusError):
    """Raised when the AI fails to generate valid structured output."""
    pass

class FormSubmissionError(CorvusError):
    """Raised when form submission fails."""
    pass
