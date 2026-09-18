# What I found in the data, and the approach it pushed me towards

Akshat Agrawal · IIT (BHU) Varanasi · Mid-term submission · 15 September 2026
Problem statement: Agentic Customer 360 — Proactive Intervention Desk

## The finding that reshaped my design

I spent the first couple of days reading the three practice scenarios instead of drawing boxes. The script is in `notebooks/explore_stream.py`, and it changed what I think this problem is.

**The obvious design is backwards.** Score each event, alert on the high scores — that fails these scenarios specifically. Ranking scenario 1's live events by amount puts the $12,000 tuition wire first and the $2,500 resort refund seventh; both are labelled red herrings. The real signals are a $500 ER visit, a $125 pharmacy run, an $85 purchase at Mothercare. Alerting on the five largest amounts catches three of eight signals in scenario 1 and one of three in scenario 3, dragging in a red herring each time. Amount is close to useless as a prior here, and I assume that is deliberate.

What does separate signal from noise is novelty and cadence. In every life-event scenario the event arrives as a merchant category with zero history: healthcare and pharmacy after 221 historical card transactions containing neither, baby_products and clothing after 214 containing neither. Cheap, deterministic, explainable. But novelty triggers rather than concludes — it runs at roughly 2/3 precision, since the resort refund and the electronics purchase are novel too, and what actually separates them is whether a second source corroborates the same hypothesis. It is also completely blind to scenario 3.

**Churn shows up as absence, and absence emits no event.** David Chen's last card transaction or app session is 9 March; the window runs to 15 April. Thirty-six days of nothing, against a historical maximum gap of 2 days — eighteen times the largest silence he has ever produced. In those 36 days exactly four events arrive: salary in at 08:00, $4,900 back out at 09:15, twice. The account has become a pipe. No reactive agent can fire on this because there is nothing to fire on, and the ground truth explicitly penalises noticing late.

Three smaller traps, each of which would have broken a naive pipeline. A $12,000 wire and a $12,000 ledger withdrawal arrive one second apart: one movement reported twice by two systems, and summing naively invents a crisis. A $10,000 withdrawal from savings and a $10,000 deposit into checking, also a second apart, are one drawdown by a man paying hospital bills; read as two events it looks like exfiltration and trips a fraud hold on someone already having the worst month of his life. And a $600 electronics purchase looks like card fraud until a support call the next day says "it's me, I bought a baby monitor". That last one, plus a signal event that arrives 48 hours late, means a decision has to be retractable.

## The approach

I am building the shared state board the problem statement suggests, but **append-only, with numbers instead of prose**. Agents write rows: a hypothesis from the fourteen state enums, a direction, a weight as a log-likelihood ratio, the event ids it rests on, a half-life, and a nullable `revoked_by`. Confidence at time T is the decayed sum of un-revoked rows observed by T.

I chose this because four requirements collapse into one mechanism. Explaining a decision becomes ranking rows by contribution, citations already attached — explainability computed rather than narrated afterwards. Memory decay becomes the half-life term, which answers the question about the 18-month-old churn flag: it stops counting because its weight decayed, not because a job deleted it. A late event is a row appended with its true event time, after which the posterior for that T is recomputed and a revision emitted. The baby monitor is a revocation.

Around it sits a two-speed loop. A deterministic tier touches every event to dedupe, update features and run cheap detectors; only about 8% trip anything, and only those wake the LLM agents. A daily scheduled tick compares an expected-arrival table against what actually landed and injects a synthetic `expectation_breach` when a salary, login cadence or standing instruction lapses. That is how absence becomes visible to event-driven machinery, and it is the only reason scenario 3 is caught in days rather than in April. The tick runs on the replay clock rather than on watermark advance, which sounds like a detail and is not: watermarks only move when events arrive, so a watermark-driven timer would sit frozen through exactly the silence it exists to detect.

Multiple agents earn their place in exactly one place I am confident about: the correlation step, which wakes only when two or more swarm agents have flagged something in the same window. In scenario 2 that is an income shortfall, a first-ever baby_products purchase and a new daycare instruction — none decisive alone. Elsewhere I am using fewer agents than the suggested roster, because the multi-agent literature is unkind about assuming coordination helps.

## What I expect to get wrong

The weights and half-lives are hand-set from domain reasoning and tuned on three scenarios. They are not learned, three scenarios is not a calibration set, and I expect them to be the weakest part when they meet a scenario I have not seen. The Bayesian framing also assumes evidence is conditionally independent, which it is not — a pharmacy charge and a hospital bill are correlated — so the posterior will run hot when several correlated signals land together. And the output schema has one `inferred_state` field, which quietly assumes a customer is going through one thing at a time; someone can be a new parent and in financial distress at once, and I have not resolved that.

Next: the scoring harness, so I find out my thresholds are wrong from a script rather than from the leaderboard.

Details in [`architecture.md`](architecture.md), [`research-log.md`](research-log.md) and [`diagrams/architecture.svg`](diagrams/architecture.svg).
