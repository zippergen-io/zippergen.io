"""Refresh the demo's real code views and downloadable tutorial project.

Run with the framework's Python environment:
  ../zippergen/.venv/bin/python scripts/prepare-demo.py --framework ../zippergen

This validates and inspects code. It does not deploy or contact a provider.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", type=Path, required=True)
    args = parser.parse_args()
    framework = args.framework.resolve()
    site = Path(__file__).resolve().parents[1]
    demo = site / "public" / "demo"
    project = demo / "example"
    project.mkdir(parents=True, exist_ok=True)
    source = (framework / "examples/email_approval.py").read_text()
    spec = "examples/email_approval.py:email_approval"

    def zg(*arguments):
        result = subprocess.run(
            [sys.executable, "-m", "zippergen.serve", *arguments],
            cwd=framework, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    validation = zg("validate", spec)
    communications = zg("show", spec, "--communications")
    full = zg("show", spec, "--detail", "full")
    writer = zg("show", spec, "--agent", "Writer")
    mailbox = zg("show", spec, "--agent", "Mailbox")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=framework, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--", "examples/email_approval.py", "examples/email_approval.specification.md", "src"], cwd=framework, text=True).strip():
        raise SystemExit("Commit framework changes before creating a revision-pinned download.")

    prompt = (
        "Watch .txt files in mailbox/. Have an LLM draft a reply, then ask me "
        "to approve it. Send only if I approve. Keep waiting for new requests, "
        "and let me stop and resume at an approval.\n\n"
        "Use ZipperGen. Simulate sending for now, and validate the workflow "
        "and participant views."
    )
    request = "Could we move our project meeting to Thursday at 10?"
    reply = "Thursday at 10 works for me. I'll update my calendar once we confirm."
    workflow = source.split("@workflow\n", 1)[1].split("\n\n\n# A foreground", 1)[0]
    actions = source[source.index("@llm("):source.index("\n\n@effect\ndef send_reply")]
    content = {
        "prompt": prompt, "request": request, "reply": reply,
        "workflow": "@workflow\n" + workflow,
        "writer": writer, "mailbox": mailbox, "communications": communications,
        "full": full, "actions": actions,
        "provenance": {
            "revision": revision,
            "source": "examples/email_approval.py",
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "validation": validation,
        },
    }
    (demo / "content.json").write_text(json.dumps(content, indent=2) + "\n")
    (project / "workflow.py").write_text(source)
    (project / "LICENSE").write_text((framework / "LICENSE").read_text())
    (project / "specification.md").write_text((framework / "examples/email_approval.specification.md").read_text())
    (project / "prompt.txt").write_text(prompt + "\n")
    (project / "answers.json").write_text(json.dumps({"Writer.draft_reply": {"draft": reply}}, indent=2) + "\n")
    (project / "mailbox").mkdir(exist_ok=True)
    (project / "mailbox/01.txt").write_text(request + "\n")
    (project / "zippergen.toml").write_text('''schema_version = 2
name = "approval-example"
specification_file = "specification.md"
workflow_entry = "workflow.py:email_approval"

[models.assignments]
default = "mock"
''')
    (project / "AGENTS.md").write_text(
        "Read `zg skill` and its authoring reference before changing this workflow.\n"
        "Keep specification.md current. Validate and inspect the global workflow\n"
        "and both local views. Use a snapshot and semantic diff for changes.\n"
        "The send action is simulated. Do not add real message delivery without\n"
        "the user's instruction. Keep credentials out of project files.\n"
    )
    (project / "CLAUDE.md").write_text("Follow AGENTS.md in this directory.\n")
    (project / ".gitignore").write_text(".venv/\n__pycache__/\n*.pyc\nmailbox/*.done\n")
    (project / "README.md").write_text(f'''# Try an approval workflow

This is the runnable example from https://zippergen.io/demo/.
It reads a text file, drafts a reply, asks for human approval, and either
prints a simulated send or discards the reply. Both outcomes mark the input
`.done`. No email is sent. No API key is needed for the scripted first run.

## Install

Python 3.11 or later and Git are required. From this unzipped directory, create
a virtual environment and install the exact framework revision used for this
example. Installation needs internet access. Some features may be newer than
the current PyPI release.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "zippergen @ git+https://github.com/zippergen-io/zippergen.git@{revision}"
```

On Windows, activate with `.venv\\Scripts\\Activate.ps1` in PowerShell.
Managed service deployment currently supports macOS and Linux.

## Run one request

```bash
zg validate
zg show
zg run --durable --llm scripted:answers.json --option max_messages=1
```

Answer yes or no at the approval prompt. The result is the approved count,
either 1 or 0. The input `mailbox/01.txt` becomes `mailbox/01.done`.
The scripted provider returns a fixed reply. It does not call an LLM.

## Try a restart while waiting

During the approval prompt, press Ctrl-C before answering. Then run:

```bash
zg run status
zg run tasks
zg run --resume
```

The same saved draft is waiting for approval. Answer yes or no to finish.
This tests a stop after the draft has committed. External calls may repeat
if the process dies after the call succeeds but before its result is saved.
The simulated send is a print and can repeat in that window. A real sending
service needs its own idempotency mechanism.

To try another fresh run, add a new uniquely named `.txt` file to `mailbox/`
and repeat the durable run command. That command replaces the selected
development run, so finish the previous request first. Keep input files
unchanged while they await approval. Use only one consumer for this folder.

## Inspect the participants

```bash
zg show --communications
zg show --detail full
zg show --agent Writer
zg show --agent Mailbox
```

The workflow and source actions are in `workflow.py`. The Writer view is an
exact generated projection, not a second program you maintain.

## Use your coding agent

Open Codex, Claude Code, or another coding agent in this directory. `prompt.txt`
contains the request used in the browser walkthrough. `AGENTS.md` points the
agent to the ZipperGen skill. The existing workflow can be your starting point.

## Connect a model and deploy

First finish the foreground run. For a local OpenAI-compatible model server:

```bash
zg provider configure local-model local --base-url http://127.0.0.1:11434/v1
zg model configure writer local-model YOUR_MODEL
zg model assign Writer writer
zg check --strict
```

Replace `YOUR_MODEL` with a model available on your server. For hosted models,
follow the configuration guide in the framework README and enter credentials
in your own terminal. This project never needs a credential in source code.

```bash
zg deploy
```

Guided deployment asks for the live mailbox directory. Use its absolute path.
Add a fresh `.txt` file there. The service runs independently of your terminal.
These commands inspect and control that same deployment:

```bash
zg deploy status
zg deploy tasks
zg deploy approve --task TASK_ID --yes
zg deploy stop
zg deploy start
```

Replace `TASK_ID` with the ID from `tasks`. Use `--no` to reject.
The example still simulates sending locally, even with a real model.
Managed deployment uses launchd on macOS and systemd user services on Linux.
See the deployment guide for Linux logout and boot requirements.

## Source and evidence

Framework revision: `{revision}`.
Source: `examples/email_approval.py`, copied without changes.
The downloaded protocol matches the code shown in the browser.

- Framework: https://github.com/zippergen-io/zippergen
- Tutorial: https://github.com/zippergen-io/zippergen/blob/main/docs/first-workflow.pdf
- Deployment checks: https://github.com/zippergen-io/zippergen/blob/main/docs/reviews/2026-09-12-deployment-walkthrough.md

The browser session is an illustration of these operations, not a live
ZipperGen runtime or a recording of an actual coding-agent session.
''')
    (project / "validation.txt").write_text(validation + "\n\n" + communications + "\n\n" + full + "\n\n" + writer + "\n\n" + mailbox + "\n")
    # Fixed metadata keeps the ZIP reproducible. Only include project sources.
    with zipfile.ZipFile(demo / "approval-example.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(project.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and ".venv" not in path.parts:
                relative = path.relative_to(project)
                info = zipfile.ZipInfo("approval-example/" + relative.as_posix(), (2026, 9, 13, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                bundle.writestr(info, path.read_bytes())
    print(validation)
    print(f"Prepared content and download from {revision[:7]}.")


if __name__ == "__main__":
    main()
