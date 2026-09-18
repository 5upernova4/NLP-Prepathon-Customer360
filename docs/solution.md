# Agentic Customer 360 — Proactive Intervention Desk

Akshat Agrawal · IIT (BHU) Varanasi · Inter IIT Tech Meet 15.0 Prepathon (NLP)

## The problem, and what the data says about it

A bank has one customer's live event stream — cards, transfers, ledger, KYC,
app sessions, support tickets — arriving asynchronously and sometimes out of
order. The system has to keep an up-to-date view of what the customer is going
through and commit to one action from a bounded set, or explicitly decide not
to act, with both decisions equally traceable.

I spent the first days reading the three practice scenarios rather than drawing
boxes, and it changed the design. Three findings did most of the work.

**Transaction size is close to useless as a prior.** Ranking scenario 1's live
events by amount puts the $12,000 tuition wire first and the $2,500 resort
refund seventh. Both are labelled red herrings. The real signals are a $500 ER
visit, a $125 pharmacy run and an $85 purchase at Mothercare. Any design that
scores events by magnitude scores this dataset backwards.

**Churn announces itself by absence, and absence emits no event.** In scenario
3 the customer's last card transaction or app session is 9 March; the window
runs to 15 April. That is 36 days of nothing against a historical maximum gap
of 2 days. In those 36 days exactly four events arrive: salary in at 08:00 and
$4,900 straight back out at 09:15, twice. The account has become a pipe. No
reactive agent can fire on this, because there is nothing to fire on.

**Decisions have to be revisable.** A $600 electronics purchase looks like card
fraud until a support message the next day says it was a baby monitor. A
ground-truth signal event arrives 48 hours after it happened, after a checkpoint
covering that window has already been emitted.

Only about 9% of live events carry any signal at all (26 of 27 ground-truth
signals sit in 28 of 297 events that trip a detector).

## Architecture

The full picture is in `architecture.svg`. The spine is deliberately plain:
ingest, cheap deterministic tests, wake specialists only if something fired,
write evidence to a shared ledger, decide, gate, hand to a human.

**Two tiers.** A deterministic tier touches every event: it orders by event
time rather than arrival, collapses duplicates, swaps names for surrogates, and
runs the cheap tests — is this merchant category new for this customer, is the
salary short or late, did money land and leave again, is savings sliding away
from its own peak. No model runs here. Only when a test fires does the
expensive tier wake. At a 9% wake rate that is roughly an order of magnitude
less model traffic, and 92% fewer opportunities to hallucinate about a coffee
purchase.

**The evidence ledger** is the shared state board the problem statement
recommends, with one change: it is append-only and a finding is a row with a
number on it rather than a sentence. Each row carries a hypothesis, a weight, the
time the evidence was observed, a half-life, the event ids backing it, and a
nullable revocation. Confidence is those rows summed and faded by age.

That shape was chosen because four separate requirements collapse into it.
Explaining a decision is ranking rows by contribution, and they already cite
their sources — the explanation is the computation, not a story told afterwards.
Decaying old memory is the half-life term, which answers whether an 18-month-old
churn flag should still count: it should not, and it does not, because its weight
has decayed rather than because a cleanup job deleted it. Absorbing a late event
is appending a row with its true observation time and recomputing the posterior
for that moment. Retracting a red herring is setting the revocation flag. One
structure, four problems, and every one of them auditable afterwards.

One correction the data forced. Summing rows at face value assumes the evidence
is conditionally independent, and it is not — a pharmacy charge and a hospital
bill are one fact observed twice. Counted naively, scenario 1 reached high
confidence two weeks before ground truth says the picture was clear. Repeats
within a detector group are now discounted (strongest in full, second at half,
third at a third) while corroboration across *different* detectors counts fully.
That is the behaviour worth having: independent sources agreeing should move a
belief, one source repeating itself should not.

**Absence as a first-class event.** A scheduled tick runs daily, compares an
expected-arrival table fitted from history against what actually landed, and
when something is overdue it writes a synthetic breach event into the same log.
Everything downstream then treats absence exactly like presence.

The detail that matters, and which I got wrong first: this tick runs on the
calendar, not on watermark advance. The instinctive streaming design arms a
timer and fires it when the watermark passes, which is how Flink and Beam work.
That deadlocks here — watermarks only advance when events arrive, and this
customer emits nothing for 36 days. The mechanism built to catch the silence
would itself have been silent. An absence detector cannot depend on the arrival
of events.

**Coordination, chosen per stage rather than uniformly.** Four specialists run
in parallel over their own sources, because usage, transactions, support text
and KYC genuinely do not depend on each other. Correlation is agent-dependent:
it fires only when two or more specialists point the same way inside a window,
and this is the one place where having several agents does real work rather than
being organisational theatre. In scenario 2 an income dip, a first-ever baby
purchase and a new daycare instruction are each unremarkable; together they are
the answer. Synthesis receives the assertion set and nothing else — not other
agents' reasoning, because passing full context is how one agent's speculation
becomes another's premise. Debate is gated: it wakes only when the top two
hypotheses are within a margin, resolves by a written rule (a declared fact
beats an inferred one, then more independent agents wins), and where the rule
cannot separate them, caps confidence and routes to a human on ambiguity alone.

I used fewer agents than the suggested roster. The multi-agent literature is
fairly unkind about assuming coordination helps, and three of the four
specialists here are doing arithmetic against a baseline, where a model adds
latency and a failure mode without adding accuracy. The model earns its place
in two spots: reading free-text support messages, and drafting and critiquing
the note a human will read.

## Non-negotiables

**Guardrails are code, not prompts.** A table of (state, action) pairs is
checked before an action can be constructed. `medical_hardship` combined with
`personalized_offer` is denied outright — a customer drawing down savings to
pay hospital bills must never be sold to, and that is a table lookup no prompt
can argue past. Spend ceilings by value tier force escalation rather than
quietly shrinking an offer. Tools are split draft/send; no agent holds a send
tool or a credit tool.

**Access is structural.** Each agent is handed a scoped view built from its
declared capabilities, with no method reaching anything else. This stopped
being theoretical during development: the support agent, on reading "just
confirming it's me, I bought a baby monitor", tried to revoke every recent card
assertion and destroyed a genuine signal. The right fix was to let the support
agent report the claim and have the orchestrator — which can see both sides —
match it to the merchant actually named. The access model had been telling me
the agent could not do that job.

**Human-in-the-loop is a real interrupt.** The run parks. The reviewer sees the
evidence rows ranked by how much each moved the number, each citing its source
events, and can ask why. Every approve, reject or edit is recorded with the
evidence snapshot that was on screen.

**Traceability** is OTel-style spans over every agent run, tool call and model
call, with each ledger row carrying the span that produced it.

## Results, and what is weak

Against the three practice scenarios: state 8/8, confidence band 8/8, action
7/8, subtype 3/3, HITL routing 3/3, lead time 2/3, and no forbidden action
inside any red-herring window (4/4).

The band cutoffs are fitted to three scenarios and the window satisfying every
checkpoint simultaneously is narrow — `HIGH` must sit between 5.80 and 6.66.
That is fitted, not learned, and it is the first thing I would expect to break
on an unseen customer. The band cutoff and the lead time are also driven by the
same number and pull in opposite directions; raising it fixed a band check and
cost two lead-time checks.

Churn escalation fires two days before the ground-truth checkpoint against an
ideal of three. I could pass that check by treating a standing-instruction
cancellation as decisive on its own, and chose not to: a system that escalates
every time someone reorganises their direct debits is one that gets switched
off. Waiting a day for the money to actually move is the trade I would make
again, but it is a genuine miss.

Without an API key the system runs end to end with keyword fallbacks for the two
model-dependent agents; the trace records which path each call took. All reported
numbers are from that offline path. Three synthetic scenarios, one customer
each, is not evidence this works on real customers.

Full detail, including the failures I hit on the way, is in `evaluation.md`; the
reading behind the design decisions is in `../research/research-log.md`.
