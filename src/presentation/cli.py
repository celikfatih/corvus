import logging
import os
from pathlib import Path
from dotenv import load_dotenv

from src.infrastructure.google_form_parser import GoogleFormParser
from src.infrastructure.openai_generator import OpenAIAnswerGenerator
from src.infrastructure.http_form_submitter import HttpFormSubmitter
from src.domain.agent_service import CorvusService
from src.domain.exceptions import CorvusError

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _load_persona(persona_path_str: str) -> str:
    """Reads the persona definition from the specified file path."""
    persona_path = Path(persona_path_str)
    if not persona_path.exists():
        raise FileNotFoundError(
            f"Persona file not found at '{persona_path.resolve()}'. "
            "Please check the PERSONA_FILE environment variable or ensure the file exists."
        )
    persona_text = persona_path.read_text(encoding="utf-8").strip()
    if not persona_text:
        raise ValueError(f"Persona file '{persona_path}' is empty.")
    return persona_text

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    form_url = os.getenv("FORM_URL")
    if not form_url:
        logger.error("FORM_URL is not set in environment variables. Please add it to your .env file.")
        exit(1)
    
    # Dependency Injection Setup
    form_parser = GoogleFormParser()
    
    ai_api_url = os.getenv("AI_API_URL")
    ai_api_token = os.getenv("AI_API_TOKEN")
    ai_api_model = os.getenv("AI_API_MODEL", "meta/llama-3.1-70b-instruct")
    ai_chunk_size = int(os.getenv("AI_CHUNK_SIZE", "30"))
    
    answer_generator = OpenAIAnswerGenerator(
        base_url=ai_api_url,
        api_key=ai_api_token,
        model=ai_api_model,
        chunk_size=ai_chunk_size
    )
    form_submitter = HttpFormSubmitter()
    
    agent_service = CorvusService(
        parser=form_parser,
        generator=answer_generator,
        submitter=form_submitter
    )
    
    try:
        persona_file_path = os.getenv("PERSONA_FILE", "persona/persona.md")
        persona_text = _load_persona(persona_file_path)
        logger.info(f"Loaded persona from '{persona_file_path}'.")
        agent_service.fill_and_submit_form(url=form_url, persona_text=persona_text)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Persona Error: {str(e)}")
        exit(1)
    except CorvusError as e:
        logger.error(f"Application Error: {str(e)}")
        exit(1)
    except Exception as e:
        logger.exception(f"Unexpected Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
