# Product Eval Resources

These resources turn the eval ideas from Lesson 11 into files you can run and reuse.

## Run the real policy assistant

Set up Google Cloud Application Default Credentials and provide the project and location used by Gemini.
Run one case first so you can inspect the output and control the cost:

```bash
GOOGLE_CLOUD_PROJECT=your-project \
GOOGLE_CLOUD_LOCATION=global \
uv run python -m tests.evals.run_evals --case hotel_limit
```

Run the complete set when you are ready to compare a prompt or model:

```bash
GOOGLE_CLOUD_PROJECT=your-project \
GOOGLE_CLOUD_LOCATION=global \
uv run python -m tests.evals.run_evals
```

Pass `--model` to evaluate another compatible Gemini model without changing application code:

```bash
GOOGLE_CLOUD_PROJECT=your-project \
GOOGLE_CLOUD_LOCATION=global \
uv run python -m tests.evals.run_evals --model gemini-model-id
```

The command uses the real `run_support_workflow` entry point and the approved fictional policy set.
It prints case identifiers, decisions, source filenames, tokens, latency, tool use, and estimated cost.
It never prints questions, answers, or policy text.

The cases live in [`tests/evals/cases.py`](../../../tests/evals/cases.py).
Each case states its expected decision and source documents before the model runs.
Cases marked `must_pass` are safety boundaries that cannot be hidden inside an average score.

## Try the judge prompt

[`faithfulness-judge.txt`](faithfulness-judge.txt) checks one subjective property: whether every factual policy claim in an answer follows from the supplied evidence.
The application already checks source names and exact excerpts in code.
The judge handles the separate question of whether the answer represents that evidence faithfully.

The file uses `string.Template` placeholders, so you can render it without adding a template library:

```python
from pathlib import Path
from string import Template

template = Template(Path("docs/resources/evals/faithfulness-judge.txt").read_text(encoding="utf-8"))
prompt = template.substitute(
    question="Can I carry unused leave into next year?",
    answer="You may carry up to five unused days with manager approval.",
    evidence=(
        "annual-leave-policy.md: Employees may carry up to five unused days "
        "into the next holiday year with manager approval."
    ),
)
```

A judge is another model, so its verdict is not ground truth.
Compare its verdicts with human decisions before using it to block a release.

## Give the workflow to a coding agent

[`product-evals/SKILL.md`](product-evals/SKILL.md) is a reusable skill for creating cases, choosing checks, running the real application, and reporting a release decision.
Copy the `product-evals` directory into the skills directory used by your coding agent.

The skill is deliberately small.
It helps an agent apply the eval process without replacing the product decisions a person must make.

## Keep eval data safe

Use fictional questions and approved policy documents in committed eval cases.
Do not copy production Slack messages, employee identifiers, complete event payloads, credentials, or private policy text into the repository.
