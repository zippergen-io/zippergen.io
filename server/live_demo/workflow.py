"""A bounded live companion to the website's mailbox tutorial."""
from zippergen import Lifeline, human, pure, workflow

Mailbox = Lifeline("Mailbox")
Writer = Lifeline("Writer")
REQUEST = "Could we move our project meeting to Thursday at 10?"
DRAFT = "Thursday at 10 works for me. I'll update my calendar once we confirm."


@pure
def example_draft(message: str) -> str:
    if message != REQUEST:
        raise ValueError("This public demo accepts only its fixed example request")
    return DRAFT


@human(
    kind="confirm",
    context="ZipperGen demo. Fixed example draft, no model call:\n\n{draft}",
    instruction="Release this example reply? No email will be sent.",
    outputs=["approved: bool"],
    submit_label="Approve",
    cancel_label="Reject",
)
def approve_reply(draft: str): ...


@pure
def release_reply(draft: str) -> str:
    return "approved"


@pure
def discard_reply(draft: str) -> str:
    return "rejected"


@workflow
def telegram_approval(message: str @ Mailbox) -> str:
    Mailbox(message) >> Writer(message)
    Writer: draft = example_draft(message)
    Writer(draft) >> Mailbox(draft)
    Mailbox: approved = approve_reply(draft)
    if approved @ Mailbox:
        Mailbox: outcome = release_reply(draft)
    else:
        Mailbox: outcome = discard_reply(draft)
    return outcome @ Mailbox
