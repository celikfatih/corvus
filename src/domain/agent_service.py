import logging
import json
from datetime import datetime
from pathlib import Path

from src.interfaces.ports import IFormParser, IAnswerGenerator, IFormSubmitter
from src.domain.models import Persona, FormAnswers

logger = logging.getLogger(__name__)

SUBMISSION_LOG_FILE = Path("submission_history.log")

class CorvusService:
    def __init__(
        self,
        parser: IFormParser,
        generator: IAnswerGenerator,
        submitter: IFormSubmitter
    ):
        self.parser = parser
        self.generator = generator
        self.submitter = submitter

    def fill_and_submit_form(self, url: str, persona_text: str) -> bool:
        logger.info(f"Starting process for URL: {url}")
        
        persona = Persona(description=persona_text)
        
        logger.info("Parsing form...")
        form = self.parser.parse(url)
        logger.info(f"Successfully parsed form with {len(form.fields)} fields.")
        
        logger.info("Generating answers using AI...")
        answers = self.generator.generate_answers(form, persona)
        logger.info(f"Successfully generated answers for {len(answers.answers)} fields.")
        
        logger.info("Submitting form...")
        success = self.submitter.submit(form, answers)
        
        if success:
            logger.info("Form submitted successfully!")
            self._log_submission(url, persona_text, answers)
        else:
            logger.warning("Form submission might not have been successful.")
            
        return success

    def _log_submission(self, url: str, persona_text: str, answers: FormAnswers) -> None:
        """Appends a structured record of the completed submission to a persistent log file."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "form_url": url,
            "persona": persona_text,
            "answers": answers.answers,
        }
        log_line = json.dumps(record, ensure_ascii=False)

        logger.info(f"Submission record: {log_line}")

        try:
            with open(SUBMISSION_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
            logger.info(f"Submission written to {SUBMISSION_LOG_FILE}")
        except OSError as e:
            logger.error(f"Failed to write to {SUBMISSION_LOG_FILE}: {str(e)}")
