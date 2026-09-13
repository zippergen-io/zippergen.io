# Try an approval workflow

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
python -m pip install "zippergen @ git+https://github.com/zippergen-io/zippergen.git@0346b490d72699228031eee8349528a77ac389ba"
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.
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

Framework revision: `0346b490d72699228031eee8349528a77ac389ba`.
Source: `examples/email_approval.py`, copied without changes.
The downloaded protocol matches the code shown in the browser.

- Framework: https://github.com/zippergen-io/zippergen
- Tutorial: https://github.com/zippergen-io/zippergen/blob/main/docs/first-workflow.pdf
- Deployment checks: https://github.com/zippergen-io/zippergen/blob/main/docs/reviews/2026-09-12-deployment-walkthrough.md

The browser session is an illustration of these operations, not a live
ZipperGen runtime or a recording of an actual coding-agent session.
