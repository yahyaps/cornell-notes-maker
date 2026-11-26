"""Support tickets (support.py): validation, header safety, sending."""

import os
import unittest
from unittest import mock

import support
from support import TicketError

SETTINGS = {"SUPPORT_EMAIL_TO": "owner@example.com", "SMTP_USER": "sender@example.com",
            "SMTP_PASSWORD": "app-password"}


class ValidateTest(unittest.TestCase):
    def test_accepts_valid_ticket(self):
        self.assertEqual(support.validate(" a@b.co ", " message long enough ", "Sara"),
                         ("a@b.co", "message long enough", "Sara"))

    def test_rejects_bad_input(self):
        cases = [
            (("not-an-email", "message long enough"), "invalid_email"),
            (("a@b.co", "short"), "invalid_message"),
            (("a@b.co", "x" * (support.MAX_MESSAGE_CHARS + 1)), "invalid_message"),
            (("a@b.co", "message long enough", "Eve\r\nBcc: x@y.z"), "invalid_name"),
            (("a@b.co\r\nBcc: x@y.z", "message long enough"), "invalid_email"),
        ]
        for args, kind in cases:
            with self.subTest(args=args), self.assertRaises(TicketError) as ctx:
                support.validate(*args)
            self.assertEqual(ctx.exception.kind, kind)


class SendTest(unittest.TestCase):
    def test_unconfigured_is_unavailable(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("streamlit.secrets") as secrets, \
                self.assertRaises(TicketError) as ctx:
            secrets.get.return_value = None
            support.send_ticket("problem", "a@b.co", "message long enough")
        self.assertEqual(ctx.exception.kind, "unavailable")

    def test_sends_to_owner_with_reply_to_visitor(self):
        with mock.patch.dict(os.environ, SETTINGS), \
                mock.patch.object(support.smtplib, "SMTP_SSL") as smtp:
            ticket = support.send_ticket("pdf", "student@uni.edu", "The PDF is blank.",
                                         "Sara", {"Lecture": "Bio.pdf (4 pages)"})
        server = smtp.return_value.__enter__.return_value
        server.login.assert_called_once_with("sender@example.com", "app-password")
        mail = server.send_message.call_args.args[0]
        self.assertEqual(mail["To"], "owner@example.com")
        self.assertIn("student@uni.edu", mail["Reply-To"])
        self.assertIn(ticket, mail["Subject"])
        self.assertIn("The PDF is blank.", mail.get_content())
        self.assertIn("Bio.pdf", mail.get_content())

    def test_unknown_category_becomes_other(self):
        with mock.patch.dict(os.environ, SETTINGS), \
                mock.patch.object(support.smtplib, "SMTP_SSL") as smtp:
            support.send_ticket("<script>", "a@b.co", "message long enough")
        mail = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertIn("other", mail["Subject"])

    def test_smtp_failure_is_reported(self):
        with mock.patch.dict(os.environ, SETTINGS), \
                mock.patch.object(support.smtplib, "SMTP_SSL",
                                  side_effect=support.smtplib.SMTPAuthenticationError(535, b"x")), \
                self.assertRaises(TicketError) as ctx:
            support.send_ticket("problem", "a@b.co", "message long enough")
        self.assertEqual(ctx.exception.kind, "send_failed")


if __name__ == "__main__":
    unittest.main()
