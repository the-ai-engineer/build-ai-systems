---
name: product-evals
description: Build and run product-specific evals for an AI application. Use when creating test cases, choosing evaluators, checking real model behavior, comparing prompts or models, or making a release decision.
---

# Product Evals

Turn product requirements into a small eval set, run it against the real application, and report evidence for a release decision.

## Read the product before writing cases

Read the repository instructions, product brief, application contract, existing tests, model entry point, and current evals.
Identify:

- what the application must do;
- what it must never do;
- which behavior depends on a model; and
- which failures must block a release.

Do not use the current model output as the expected answer.
The current model may be wrong.

## Create a small, varied case set

Start with 8 to 15 cases covering common requests, paraphrases, boundary cases, unsupported requests, sensitive requests, adversarial requests, and past failures.

Write the expected behavior before running the model.
For each case, record:

- a stable identifier;
- the input;
- the expected decision or outcome;
- expected sources or tool results when relevant;
- forbidden behavior; and
- whether the case must pass.

Use fictional or approved test data.
Never copy private production messages, credentials, identifiers, or documents into an eval fixture.

## Use the simplest reliable check

Use ordinary code for schemas, exact decisions, source identifiers, citation verification, required fields, forbidden output, and tool or turn limits.

Use a person or an LLM judge only when the criterion requires judgment.
Each judge checks one criterion with explicit pass and fail definitions.
Keep judge prompts in separate text files so they can be reviewed and versioned.

Treat an unvalidated judge as an experiment, not as a release gate.
Compare its verdicts with human labels and inspect every disagreement before trusting it.

## Run the real application

Use the same workflow entry point, model provider, tools, and approved data source as the application.
Run each case once and reuse the result across all checks.

Record safe metadata such as the model identifier, prompt revision, document revision, latency, tokens, tool calls, model turns, and estimated cost.
Do not print or store sensitive inputs, answers, or retrieved text unless the repository explicitly permits it.

Do not change application behavior while evaluating it unless the user separately asks for a fix.

## Report what happened

Report:

- every failed case and the exact failed check;
- results by category;
- any must-pass failure;
- latency, token use, and cost when available;
- the configuration that ran; and
- a clear release recommendation.

Never hide a must-pass failure inside an average score.
If credentials are unavailable, finish the cases and deterministic checks, then give the exact command needed to run the live evals.
