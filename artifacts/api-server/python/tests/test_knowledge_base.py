import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.documents import Document

from app.assistant import GroundedDraft, grounded_answer
from app.knowledge_base import DocumentProcessingError, extract_text, split_text
from app.models import AssistantSession, User
from app.routers.attachments import _safe_filename
from app.security import require_admin
from app.support_assistant import process_current_turn
from app.triage import IssueAnalysis, retrieval_query


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

            def with_structured_output(self, _: object) -> "FakeModel":
                return self

            def invoke(self, _: object) -> SimpleNamespace:
                return GroundedDraft(
                    answer="Select Reconnect in printer settings [S1].",
                    needs_human_support=False,
                )

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


class IssueTriageTests(unittest.TestCase):
    def test_retrieval_query_uses_detected_details(self) -> None:
        analysis = IssueAnalysis(
            problem_summary="VPN fails after a password reset",
            issue_type="remote access authentication",
            category="network",
            department="Network Support",
            priority="high",
            priority_reason="The employee cannot access work systems.",
            symptoms=["VPN connection is rejected"],
            timeline="Since this morning",
            device="Laptop",
            operating_system="Windows",
            error_message="Authentication failed",
            affected_users="One employee",
            business_impact="Blocked from remote work",
            troubleshooting_attempted=["Restarted VPN client"],
            likely_area="VPN credential or MFA sync",
            confidence=0.83,
            needs_more_info=False,
            follow_up_question="",
            ready_for_search=True,
            requires_human=False,
            escalation_reason="",
            recommended_action="Check the approved VPN reset guidance.",
        )
        query = retrieval_query(analysis)
        self.assertIn("VPN fails after a password reset", query)
        self.assertIn("Authentication failed", query)
        self.assertIn("Restarted VPN client", query)

    def test_sensitive_issue_escalates_without_waiting_for_knowledge_search(self) -> None:
        user_id = uuid4()
        user = User(id=user_id, name="Requester", role="employee", email="requester@example.com", department="Finance")
        now = datetime.now(UTC)
        session = AssistantSession(
            id=uuid4(),
            requester_id=user_id,
            ticket_id=None,
            status="triage",
            messages=[{"role": "user", "content": "I think someone accessed my account.", "created_at": now.isoformat()}],
            analysis=None,
            answer=None,
            retrieved_sources=[],
            related_tickets=[],
            created_at=now,
            updated_at=now,
        )
        analysis = IssueAnalysis(
            problem_summary="Suspected unauthorized account access",
            issue_type="account security incident",
            category="security",
            department="Security",
            priority="urgent",
            priority_reason="A possible unauthorized login may put company data at risk.",
            symptoms=["Employee suspects an unknown person used the account"],
            timeline="Not provided",
            device="",
            operating_system="",
            error_message="",
            affected_users="Potentially one account",
            business_impact="Possible account compromise",
            troubleshooting_attempted=[],
            likely_area="Account security",
            confidence=0.91,
            needs_more_info=False,
            follow_up_question="",
            ready_for_search=False,
            requires_human=True,
            escalation_reason="A security engineer should review the suspected unauthorized access.",
            recommended_action="Contact the security team immediately and follow incident-response procedures.",
        )

        with patch("app.support_assistant.analyze_issue", return_value=analysis), patch(
            "app.support_assistant.retrieve_chunks"
        ) as retrieval, patch("app.support_assistant.find_related_tickets") as related:
            result = process_current_turn(SimpleNamespace(commit=lambda: None, refresh=lambda _: None), session, user)

        self.assertEqual(result.status, "escalation_preview")
        self.assertEqual(result.analysis.category, "security")
        self.assertTrue(result.answer.needs_human_support)
        retrieval.assert_not_called()
        related.assert_not_called()


if __name__ == "__main__":
    unittest.main()
