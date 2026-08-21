# HR Policy Assistant

> **Status:** Draft customer brief

## 1. Executive summary

The company receives a growing number of employee questions about HR policies.
Employees currently send these questions to HR by email and wait for a member of the team to respond.

Many questions are repetitive and already answered in approved company documents.
HR staff spend a large part of their time finding the same information and writing similar replies.
The team must remain available to keep up with demand, but the current process is becoming expensive and difficult to scale.

Employees are frustrated by slow responses.
HR staff have less time for sensitive cases and work that needs human judgement.

The company wants an AI policy assistant in Slack.
Employees will ask general HR policy questions in a dedicated channel and receive a clear answer in a Slack thread.
The assistant will answer only from approved company policies and will direct the employee to HR when it cannot answer safely.

## 2. Customer

The customer is a growing company with an internal HR team and a shared set of employee policies.

The company already uses Slack for daily communication.
Employees are comfortable asking questions there, but HR support still relies heavily on email.

The main users are:

- Employees who need quick answers about company policies.
- HR staff who currently answer repeated questions by hand.
- Policy owners who maintain the approved source documents.
- Company leaders who need HR support to remain useful as the company grows.

## 3. Business problem

The current HR support process does not scale with the number of employees.

Employees email HR with questions about annual leave, working arrangements, pay and benefits, expenses, parental leave, onboarding, and other internal policies.
HR staff read each message, find the relevant policy, interpret it, and write a response.

This causes several problems:

- Employees wait too long for answers to routine questions.
- HR staff repeat work that could be handled consistently from existing documents.
- The company must pay for enough support capacity to cover a growing volume of requests.
- Email backlogs make it difficult to distinguish simple policy questions from sensitive cases.
- Answers may vary depending on who responds and which document they use.
- HR staff have less time for work that genuinely requires empathy, judgement, or access to private employee information.

The company does not want to replace the HR team.
It wants to remove repetitive work and make human support easier to reach when it is actually needed.

## 4. Desired outcome

Employees should be able to ask a general HR policy question in Slack and receive a useful answer without waiting for an email response.

The assistant should:

- Respond from approved and current HR policy documents.
- Name the policy used so the employee can check the source.
- Keep answers short, clear, and suitable for Slack.
- Refuse off-topic requests without attempting to answer them.
- Refer personal, sensitive, unclear, or unsupported questions to HR.
- Continue to accept questions when several employees ask at the same time.
- Record enough information for the company to understand how each answer was produced.

HR should spend less time answering repeated questions and more time handling complex employee needs.

## 5. Intended experience

The first version will operate in one dedicated public Slack channel, such as `#ask-hr`.

An employee mentions the assistant in a new top-level message:

> How many days of annual leave can I carry into next year?

The assistant accepts the question and processes it in the background.
It adds an `:eyes:` reaction to the employee's message before starting the policy workflow, so the employee can see that work has begun.
It then posts a reply in the message thread:

> You can carry up to five unused days into the next holiday year with manager approval.
>
> Source: Annual Leave Policy, “Carrying leave forward”

If the employee asks an off-topic question, the assistant gives a short standard response explaining that it only answers HR policy questions.

If the question is personal, sensitive, or not supported by an approved policy, the assistant does not invent an answer.
It replies:

> I couldn’t find a reliable answer in the policy documents. Please ask a member of the HR team.

The reply does not tag a Slack user or user group.

Examples that require HR include:

- Why was my salary payment lower this month?
- Can you approve my parental leave request?
- I want to report a problem with my manager.
- What should I do if the policies appear to conflict?

## 6. Scope

The first version covers general questions about approved internal HR policies.

Initial topics include:

- Annual leave and public holidays.
- Sickness, bereavement, parental, and family leave.
- Pay, benefits, and employee records.
- Expenses and travel policies.
- Remote and flexible working.
- Employee onboarding, probation, learning, and development.
- Working hours, workplace adjustments, conduct, and grievances.

The system will use Slack as its employee interface.
It will process questions asynchronously so that receiving a request is separate from generating and delivering an answer.
It must be able to buffer a burst of questions and process them safely without losing work or producing duplicate replies.

The policy collection will remain curated and use short, focused documents, but it must be broad enough to represent the routine questions received by a typical HR team.
Policy owners will provide the approved source documents that the assistant is allowed to use.

## 7. Business requirements

1. The assistant must answer only general HR policy questions.
2. Every factual answer must be supported by an active, approved company policy.
3. The assistant must identify the policy used for an answer.
4. The assistant must not answer from general model knowledge when company evidence is missing.
5. Off-topic questions must not receive a generated answer.
6. Personal, sensitive, or employee-specific questions must be referred to HR.
7. The assistant must not approve requests, change employee records, or make employment decisions.
8. Repeated delivery of the same Slack event must not create repeated work or duplicate intended replies.
9. A temporary system or provider failure must not silently lose an accepted question.
10. HR and system operators must be able to inspect the outcome and supporting evidence for each processed question.
11. The assistant should add one visible acknowledgement reaction before starting the policy workflow, without making the final reply depend on that reaction succeeding.

## 8. Success measures

The company will judge the project using:

- Reduction in routine HR questions received by email.
- Time employees wait for answers to covered questions.
- Percentage of supported questions answered without HR intervention.
- Percentage of answers that cite the correct approved policy.
- Percentage of off-topic, sensitive, and unsupported questions correctly referred or declined.
- Employee feedback on whether answers are clear and useful.
- HR feedback on whether the system reduces repetitive work.
- Number of lost questions, duplicate replies, and unresolved processing failures.

Targets will be agreed after the company measures the current email volume and response time.
The course project will also use a fixed evaluation set to prove that supported questions are answered and unsafe questions are not.

## 9. Constraints and assumptions

- The first release supports one company and one Slack workspace.
- The assistant operates in one configured public HR questions channel.
- Version one handles text `app_mention` events in the configured channel.
- A mention can start a new thread or appear inside an existing thread, and each mention creates an independent request.
- Each question receives one assistant response.
- Employees should not post private employee information in the public channel.
- The assistant has access only to approved policy content, not employee records.
- HR remains responsible for sensitive cases, exceptions, disputes, and final decisions.
- The company is responsible for keeping policy documents current.
- The system must be testable on a developer's computer without requiring the complete cloud environment.

## 10. Risks

The assistant could give a confident answer from the wrong policy.
The system must therefore preserve the evidence used and reject answers that are not grounded in approved content.

An employee could post a sensitive question in a public channel.
The channel guidance must warn against sharing private information, and the assistant must avoid repeating sensitive details.

Employees may treat the assistant as an authority even when a policy is incomplete.
Answers must identify their source and make the human referral path clear.

Policies can become outdated or conflict with one another.
Only active versions may be used, and conflicting evidence must result in an HR referral.

Automation could hide failures while reducing visible email volume.
Accepted questions, retries, final outcomes, and unresolved failures must remain observable.

## 11. Out of scope

The first version will not:

- Read or change private employee records.
- Calculate individual pay, benefits, leave balances, or entitlement.
- Approve leave, expenses, travel, or other employee requests.
- Replace formal HR case management.
- Handle direct messages, attachments, or multi-turn conversations.
- Answer questions outside the approved HR policy domain.
- Serve several companies or support public Slack Marketplace installation.
- Provide a custom HR administration dashboard.
- Replace HR staff or make final employment decisions.

## 12. Course project

This customer brief is the starting point for the AI Systems course project.

Throughout the course, students will turn the brief into a working professional AI system.
They will design the workflow, build the Slack interface, store and retrieve trusted policy documents, process work asynchronously, add guardrails and evaluations, observe failures, and deploy the finished application.

The finished project must solve the customer problem as one complete system.
A successful model call or chatbot demo is not enough.
The system is complete when a real Slack question is accepted, processed safely, answered or referred correctly, and recorded in a way that can be inspected.

## 13. Open questions

- Which additional HR policy topics would justify a later release?
- What is the approved human referral route?
- How quickly does the company expect routine questions to be answered?
- How long may question text and generated answers be retained?
- Who owns approval and publication of policy updates?
- What reduction in email volume would make the project commercially successful?
