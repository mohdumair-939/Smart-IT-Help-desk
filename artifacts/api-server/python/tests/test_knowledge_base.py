import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.documents import Document

from app.assistant import grounded_answer
from app.knowledge_base import DocumentProcessingError, extract_text, split_text
from app.models import User
from app.routers.attachments import _safe_filename
from app.security import require_admin


class KnowledgeExtractionTests(unittest.TestCase):
    def test_plain_text_is_normalized(self) -> None:
        source = b"Printer setup\n\n\nRestart the print spooler before retrying the job."
        self.assertEqual(
            extract_text("printer-guide.txt", source),
            "Printer setup\n\nRestart the print spooler before retrying the job.",
        )

    def test_short_or_unsupported_documents_are_rejected(self) -> None:
        with self.assertRaises(DocumentProcessingError):
            extract_text("notes.txt", b"too short")
        with self.assertRaises(DocumentProcessingError):
            extract_text("program.exe", b"some longer content that is not an approved document")

    def test_chunks_observe_size_limit_and_overlap(self) -> None:
        text = ("network troubleshooting steps and diagnostics. " * 130)
        chunks = split_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1200 for chunk in chunks))
        self.assertTrue(set(chunks[0][-80:].split()) & set(chunks[1][:80].split()))


class GroundedAnswerTests(unittest.TestCase):
    def test_no_matching_source_escalates_without_calling_the_model(self) -> None:
        with patch("app.assistant.retrieve_chunks", return_value=[]), patch(
            "app.assistant.ChatOpenAI", side_effect=AssertionError("must not call the model")
        ):
            result = grounded_answer(None, "How do I reconnect the printer?")
        self.assertTrue(result.needs_human_support)
        self.assertEqual(result.citations, [])
        self.assertIn("couldn't find", result.answer)

    def test_matching_passage_is_returned_as_a_citation(self) -> None:
        source = Document(
            page_content="Open system settings, choose Printers, and select Reconnect.",
            metadata={
                "document_id": "a2f27a48-6c44-4cc5-9d71-9ae7a2b15533",
                "title": "Printer setup",
                "filename": "printer-guide.pdf",
                "chunk_index": 2,
            },
        )

        class FakeModel:
            def __init__(self, **_: object) -> None:
                pass

            def invoke(self, _: object) -> SimpleNamespace:
                return SimpleNamespace(content="Select Reconnect in printer settings [S1].")

        with patch("app.assistant.retrieve_chunks", return_value=[(source, 0.84)]), patch(
            "app.assistant.ChatOpenAI", FakeModel
        ):
            result = grounded_answer(None, "The printer is disconnected.")

        self.assertFalse(result.needs_human_support)
        self.assertEqual(result.citations[0].title, "Printer setup")
        self.assertEqual(result.citations[0].chunk_index, 2)
        self.assertIn("[S1]", result.answer)


class RoleGuardTests(unittest.TestCase):
    def test_only_admin_can_manage_knowledge_documents(self) -> None:
        admin = User(role="admin")
        self.assertIs(require_admin(admin), admin)
        with self.assertRaises(HTTPException) as raised:
            require_admin(User(role="employee"))
        self.assertEqual(raised.exception.status_code, 403)


class AttachmentValidationTests(unittest.TestCase):
    def test_attachment_names_are_reduced_to_safe_supported_filenames(self) -> None:
        self.assertEqual(_safe_filename("../../network trace.LOG"), "network-trace.log")
        with self.assertRaises(HTTPException):
            _safe_filename("run-me.exe")


if __name__ == "__main__":
    unittest.main()
