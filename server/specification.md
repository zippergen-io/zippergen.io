# Live Telegram approval

This is the live companion to the simulated mailbox tutorial. Each visitor
starts a separate, bounded workflow on the demo server. It uses the same
example request and reply, with deterministic draft generation and one human
decision. It does not watch a mailbox, call a model, or send email.

Mailbox owns the example request, sends it to Writer, and receives the fixed
draft. Mailbox asks a human to approve or reject it. Approval releases the
example reply and rejection discards it. Both branches finish the workflow.
The server reports completion only after the ZipperGen workflow has returned
and persisted its result. Telegram delivery reports that saved outcome.

The browser creates a temporary session and receives separate capabilities for
reading its status and connecting a private Telegram chat. A Start link can
bind to one Telegram user only. Only that user in that private chat can answer
its durable human task. Browser requests cannot approve a live workflow.

The server retains the run for 30 minutes from creation, including completed
results. Closing the browser has no effect on execution. Reloading the saved
URL recovers its status. Restarting the backend resumes unexpired executions
from their ZipperGen stores. Duplicate Telegram updates cannot change a saved
decision. Expired sessions reject further answers and are removed along with
their workflow files and chat identifiers.

Telegram notifications can repeat if the server dies between sending and
recording delivery. This does not repeat the human decision or change its
outcome. The demo makes no exactly-once notification claim.

The browser-only path remains available when the backend is disabled or
unreachable. Its approvals and state are separate from live sessions.
