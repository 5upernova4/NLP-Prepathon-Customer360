# What I found in the domain, and how I plan to solve it

Akshat Agrawal · IIT (BHU) Varanasi · Mid-term submission · 15 September 2026
Problem statement: Agentic Customer 360 — Proactive Intervention Desk

## Starting with the data, not the architecture

I spent the first couple of days reading the three practice scenarios rather than drawing boxes, and that changed what I think the problem is. The script I used is in `notebooks/explore_stream.py`; everything below comes out of it.

The headline is that **the obvious design is backwards.** If you build the thing that first comes to mind — score each incoming event, alert when the score is high — you fail these scenarios specifically. Ranking scenario 1's live events by transaction size puts the $12,000 tuition wire first and the $2,500 resort refund seventh. Both are labelled red herrings. The actual signals are a $500 ER visit, a $125 pharmacy run, and an $85 purchase at Mothercare. Alerting on the five largest amounts catches three of eight signals in scenario 1 and one of three in scenario 3, while dragging in a red herring each time. Amount is close to useless as a prior here, and I suspect that is deliberate on the organisers' part.

What does separate signal from noise is **novelty and cadence, not magnitude.** In every life-event scenario the event announces itself as a merchant category with literally zero history: healthcare and pharmacy appear after 221 historical card transactions containing neither; baby_products and clothing appear after 214 containing neither. That test is cheap, deterministic, and explainable. It is also blind to scenario 3, which brings me to the finding I care most about.

**Churn shows up as absence, and absence emits no event.** David Chen's last card transaction or app session is on 9 March. The simulated window runs to 15 April. That is 36 days of nothing, against a historical maximum gap of 2 days — eighteen times the largest silence the customer has ever produced. During those 36 days exactly four events arrive: salary in at 08:00, and $4,900 of it back out at 09:15, twice. The account has quietly become a pipe. No event-driven agent can ever fire on this, because there is nothing to fire on. Any architecture that is purely reactive fails scenario 3 by construction, and the ground truth explicitly penalises noticing late.

Three smaller things I only found by reading the raw records, each of which would have broken a naive pipeline:

A $12,000 `ach_wire` transfer and a $12,000 `core_banking_ledger` withdrawal arrive one second apart. It is one money movement reported twice by two source systems. Sum the outflows naively and you have invented a crisis. Separately, a $10,000 withdrawal from savings and a $10,000 deposit into checking, also one second apart, are one savings drawdown by a man paying hospital bills; read as two events it looks like exfiltration and trips a fraud hold on someone who is already having the worst month of his life. And the $600 electronics purchase in scenario 2 looks like card fraud until a support call the next day says "it's me, I bought a baby monitor."

That last one is the important one, because it means **a decision has to be retractable.** Add the signal event that arrives 48 hours after it happened, and it is clear the system cannot treat a checkpoint as final.

## The approach

I am building the shared state board the problem statement suggests, but as an **append-only evidence ledger** rather than a document agents overwrite. Each agent writes rows, not prose: a hypothesis (one of the fourteen state enums), a direction, a weight expressed as a log-likelihood ratio, the event ids it rests on, a half-life, and a nullable `revoked_by`. Confidence at time T is the decayed sum of the un-revoked rows observed by T.

I picked this because four separate requirements collapse into one mechanism. Explaining a decision becomes ranking the rows by contribution, with citations already attached, which is what the problem statement means by explainability that is not reconstructed afterwards. Memory decay becomes the half-life term, which answers the question about whether an 18-month-old churn flag should still count: it does not, because its weight has decayed, not because a cleanup job deleted it. A late event is just a row appended with its true event time, after which the posterior for that T is recomputed and a revision emitted. And the baby monitor is a revocation. One data structure, four problems.

The cost of this choice is real and I want to state it now rather than be caught by it: **the weights are hand-set from domain reasoning and tuned against three scenarios.** They are not learned, three scenarios is not a calibration set, and I expect the thresholds to be the weakest part of the system when it meets a scenario I have not seen.

Around the ledger sits a two-speed loop. A deterministic tier touches every event to dedupe, update features and run the cheap detectors; only about 8% of events trip anything, and only those wake the LLM agents. A daily scheduled tick compares an expected-arrival table against what actually landed and injects a synthetic `expectation_breach` event when a salary, a login cadence or a standing instruction lapses. That is how absence becomes something the event-driven machinery can see, and it is the only reason scenario 3 gets caught in days rather than in April.

The architecture diagram and the reading that got me here are in `diagrams/architecture.svg` and `research-log.md`.
