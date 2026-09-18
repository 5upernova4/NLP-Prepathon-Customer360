# Preliminary system architecture

Akshat Agrawal · IIT (BHU) Varanasi · Mid-term submission · 15 September 2026

The drawn diagram is [`diagrams/architecture.svg`](diagrams/architecture.svg). This document is the written version of it: what each component is, where its data comes from, what it hands to whom, and why it is shaped that way. Everything here is provisional and I expect the weights and thresholds in particular to change once I am running against more than three scenarios.

---

## 1. The one decision everything else follows from

The problem statement recommends a shared per-customer state board that agents write findings to and read from. I am building that, with one change: **the board is append-only, and a finding is a row with a number on it rather than a sentence.**

Each row is an assertion:

```
assertion_id
customer_id
hypothesis          one of the 14 inferred_state values
direction           supports | opposes
weight              a log-likelihood ratio
observed_at         the event_time of the evidence
asserted_at         when the agent wrote the row
half_life_days      how quickly this evidence stops counting
source_event_ids    the citation
agent               who wrote it
rationale           one line, for a human
revoked_by          null, or the assertion that withdraws this one
```

and the belief in a hypothesis at any moment is

```
posterior(h, T) = prior(h) + Σᵢ wᵢ · 2^(−Δtᵢ / half_lifeᵢ)
                  over rows where observed_at ≤ T and revoked_by is null
```

`confidence_band` is this posterior put into three buckets.

I did not start here. My first sketch had a Synthesis agent re-reading a state document and reporting a confidence, which is the obvious design and is what most of the roster in the problem statement implies. I moved off it for a specific reason: four of the requirements turn out to be the same requirement.

| Requirement | How the ledger answers it |
|---|---|
| Explain a decision, with citations, generated as part of deciding rather than reconstructed afterwards | Sort the rows by their contribution to the posterior. Each already carries `source_event_ids`. The explanation *is* the computation. |
| Decide whether an 18-month-old churn flag should still influence today | It should not, and it does not, because `2^(−Δt/half_life)` has taken its weight to nearly nothing. No expiry job, no deletion, and the row is still there for the audit. |
| Absorb an event that arrives 48 hours late, after a checkpoint covering that window was already emitted | Append the row with its true `observed_at`, recompute `posterior(h, T)` for the affected T, emit a revision. Nothing is mutated. |
| Withdraw a conclusion when a later event explains the earlier one away | Set `revoked_by`. The posterior drops. The trace still shows the system believed it, and why, which is what an audit of a fraud hold needs. |

One structure, four problems. That is the whole argument. The reading behind it is in the research log under *Evidence accumulation* (Wald's sequential analysis for the accumulate-until-threshold shape, de Kleer's truth maintenance for retraction) and under *Agent memory* (Zep/Graphiti's bi-temporal edge invalidation, which is the closest existing thing to what I am describing).

**What this costs me.** The weights are hand-set from domain reasoning and tuned against three scenarios. They are not learned, and three scenarios is not a calibration set. The Bayesian framing also assumes the evidence is conditionally independent, which it plainly is not — a pharmacy purchase and a hospital billing charge are correlated — so the posterior will be overconfident when several correlated signals land together. I plan to handle this by grouping correlated evidence into a single assertion at the detector level rather than pretending the independence holds, but I have not built that yet.

---

## 2. Two speeds

About 8% of live events carry any signal (10 ground-truth signal events out of 116 in scenario 1). Sending all of them to an LLM would be twelve times the cost and twelve times the surface on which to hallucinate, for no gain on the 92% that are a coffee purchase.

**Tier 0** is deterministic and touches every event. No model in this path.

- *Normalise and tokenise.* Schema check; name and account number replaced by surrogates from a PII vault. Merchant and counterparty names are mapped to a semantic class rather than redacted, because the class is exactly what carries the signal: `State University → education_institution` is what makes a $12,000 wire benign, and `David Chen - Chase Bank → competitor_institution` is what makes a $22,500 self-transfer alarming. Redacting the name would destroy the discriminator; keeping it raw sends PII to a model. The class is the compromise.
- *Cross-source de-duplication.* Fingerprint on (account, amount, ±5s). This exists because scenario 1 reports one $12,000 movement twice, once as `ach_wire/outbound_transfer` and once as `core_banking_ledger/withdrawal`, one second apart.
- *Event-time buffer and watermark.* Ordered by `event_time`, never by arrival. Allowed lateness 72 hours, chosen because the worst observed lateness is 48. Late arrivals produce revisions.
- *Incremental feature store.* Rolling login frequency, balance per account, MCC histogram, counterparty set, standing-instruction set, and an expected-arrival table holding (amount, period, tolerance) per recurring stream.
- *Cheap detectors.* Novel category, cadence break, income shortfall, sweep pair, balance drawdown, standing-instruction set diff. Each emits a Signal only when it actually fires.
- *Hard-stop scanner.* Legal threat, self-harm, fraud pattern, sanctions match. Routes straight to the human desk, bypassing every agent.

**Tier 1** is the LLM agents, and only wakes when Tier 0 raises something.

The detectors are worth being concrete about, because the obvious one is wrong. Ranking scenario 1's live events by amount puts both red herrings in the top seven and scatters the real signals from rank 3 to rank 27. What separates them is that healthcare and pharmacy have *zero* occurrences in 221 historical card transactions.

Two honest qualifications on that, both of which I only got to by testing it rather than asserting it. First, **novelty triggers, it does not conclude.** Across the three scenarios the first-in-category test fires on three categories per scenario and two of the three are genuine, so bare novelty runs at about 2/3 precision; the resort refund and the electronics purchase are both novel and both red herrings. I briefly thought repetition was the fix, since healthcare recurs three times while lodging appears once, but scenario 2 kills that idea outright: no novel category repeats at all there, and both baby_products and clothing are singletons that are genuinely signal. Repetition buys precision and costs almost all the recall on the scenario where the life event is clearest. What actually separates them is corroboration under a shared hypothesis. baby_products, a Mothercare purchase, a new daycare instruction, a 40% income dip and a `dependents_change` all point at one state; the TechWorld purchase points at nothing and is explained away by the customer the next day. That is precisely the job of the agent-dependent correlation step below, so novelty belongs in the reflex tier as a wake condition and nowhere near the final verdict.

Second, I should be accurate about what "not amount" means. Sweep-pair detection compares $5,000 in against $4,900 out, compound collapse matches $10,000 against $10,000, and the income shortfall detector is built on $3,800 falling to $1,400. All of those read amounts. The claim I am actually making is narrower and I want it stated correctly: **no detector uses an absolute amount threshold.** Amounts are used relationally, against this customer's own baseline or against another amount in the same window, never as "large means interesting" — which is the assumption that ranks a tuition wire above an ER visit.

---

## 3. Absence as a first-class event

This is the part I think most submissions will miss, and it is the reason scenario 3 exists.

David Chen's last card transaction or app session is 9 March. The window runs to 15 April. That is 36 days of no engagement against a historical maximum gap of 2 days, which is eighteen times the largest silence he has ever produced. In those 36 days exactly four events arrive: salary in at 08:00 and $4,900 straight back out at 09:15, twice over.

No event-driven trigger can fire on this, because there is no event. So a scheduled job does it instead. A **daily tick** compares the expected-arrival table against what actually landed, and when an expectation lapses it writes a synthetic `expectation_breach` event into the same immutable log. From that point on the ordinary machinery handles it: detectors run, agents wake, assertions get written. Absence becomes something the event-driven system can see.

One detail here matters more than it looks, and I nearly got it wrong. **The tick must be driven by wall-clock (or replay-clock) time, not by watermark advance.** The natural streaming instinct is to arm a timer and fire it when the watermark passes it, which is how Flink and Beam do it and how I first sketched it. That design deadlocks on exactly this case: watermarks only advance when events arrive, the stream is partitioned per customer, and this customer emits nothing for 36 days and then the scenario ends. The watermark stalls at the last activity, the timer never fires, and the mechanism built specifically to catch the silence is silent too. The absence detector cannot depend on the arrival of events, because absence of events is the thing it detects. So the scheduler reads the replay clock, and the watermark is used only for deciding when a window is safe to close.

The same mechanism catches the income story in scenario 1. Salary arrived at $3,800 every 14 days, twelve times running. Then one more at $3,800, then $1,400 of `benefits_credit` at the next two slots, then nothing at all on 20 March and 3 April. Two of those five observations are non-arrivals. A system built to react to deposits sees three events; a system that knows what it expected sees five, and the two silent ones are the ones that matter.

Scenario 3 also shows the other half of the pattern. The `manage_standing_instructions_cancel` web event on 4 March is the early warning; the *absence* of rent, gym and utilities on 1 April is the confirmation. One is an event, the other is a non-event, and the case is much stronger with both.

---

## 4. Which coordination pattern, and where

The problem statement lists five patterns. I do not think all five earn their place, and the multi-agent literature is fairly unkind about assuming they do, so here is the per-stage justification.

**Swarm, for signal gathering.** Usage, Transaction, Support/Sentiment and KYC/Compliance run in parallel over the woken window. They genuinely do not depend on each other and they read different sources, so there is nothing to serialise. Each writes assertions.

**Agent-dependent trigger, for correlation.** The Life-Event Inference agent does not watch the raw stream. It wakes only when two or more swarm agents have posted correlated assertions inside the same window. In scenario 2 that is the income shortfall, the first-ever `baby_products` purchase, and the new daycare standing instruction — none decisive alone, decisive together. This is the one place where having multiple agents is doing real work rather than being organisational theatre.

**Handoff, into synthesis.** The package is the assertion set. Not the swarm's reasoning traces. Scoping it this way is deliberate: passing full context is how one agent's speculation becomes another's premise.

**Debate, gated.** Only when the top two hypotheses sit within a margin of each other. The tax refund in scenario 3 is exactly this — a reasonable agent reads $5,200 arriving as `wealth_growth_or_windfall` and proposes an investment offer, which is the labelled false positive, while another reads the engagement collapse around it as `churn_risk`. Resolution is a written rule. If the rule cannot settle it, confidence is capped and the case goes to a human on ambiguity alone, which is the escalation-for-ambiguity requirement rather than escalation-for-cost.

**Round robin, inside the critique refiner only.** Grounding, then tone, then policy, one concern per pass. I am least convinced by this one and I am using it narrowly, for customer-facing text, because that is the only place where a sequence of single-concern passes clearly beats one combined pass.

**Critique-refiner, last.** It sends a draft back exactly once. A second failure escalates instead of looping, so a bad draft cannot burn latency indefinitely.

---

## 5. Guardrails that are enforced rather than requested

The problem statement is blunt that a prompt-level instruction is not a guardrail, so:

**A policy matrix over `inferred_state × action`,** evaluated in code before an action can be constructed. The entry I care about most is that `medical_hardship → personalized_offer` is denied outright. Marcus Vance is drawing down savings to pay hospital bills; a system that reads a large balance movement and pitches him a product has failed in a way no amount of good intent fixes. This is not a threshold the model can argue past, it is a table lookup.

**Blast radius.** Tools are split into draft and send. No agent holds a send tool or a credit tool. Spend ceilings are set per customer value tier, and exceeding one forces escalation rather than reducing the offer.

**Role-based access at the data layer.** Each agent is handed a scoped view object built from its declared capability set. The Support agent has no method that reaches brokerage data. This is the difference between a control and a request, and it also caps the blast radius of a poisoned retrieval to one customer.

**PII.** Identifiers are tokenised on ingest and the mapping lives outside the prompt path. Embeddings are treated as PII-equivalent, since the vector of "ER visit, pharmacy, diagnostics" is health-adjacent data in its own right.

---

## 6. Human-in-the-loop

The interrupt is real: the run parks until a person acts. What the reviewer sees is the evidence rows ranked by how much each moved the posterior, each citing its source events, and they can ask "why this and not that" — answered by querying the ledger, not by re-prompting the model to explain itself after the fact. The approval log stores the decision together with the exact evidence snapshot that was on screen at the time, so the decision can be reconstructed later. Every approve, reject or modify is written back into episodic memory.

Two triggers for escalation, not one. Cost, obviously. But also ambiguity: low posterior, or an unresolved debate, escalates regardless of the amount involved.

---

## 7. Output

`inferred_events.json` in the required schema. Because the evaluator picks its own checkpoint times, I write densely: one checkpoint daily, another whenever the confidence band changes or an action fires, and a revision row whenever a late event moves a past belief. Since the posterior is a function of `T`, any `as_of_time` can be answered exactly rather than approximated from the nearest row.

Alongside it, a scoring harness that takes my output and a `ground_truth.json` and reports state accuracy, band timing, action match, lead time against `ideal_action_lead_time_days`, and whether any forbidden action fired inside the red-herring windows. Not built yet; it is the first thing I am writing after this submission, because I would rather find out my thresholds are wrong from a script than from the leaderboard.

---

## 8. What I am least sure about

- The weights and half-lives are hand-set. Three scenarios is not enough to calibrate them and I know it.
- Conditional independence does not hold between correlated signals, so the posterior will run hot when several land together.
- I have not decided how the life-phase slot handles two life events overlapping. A customer can be both a new parent and in financial distress, and right now the design implicitly assumes one dominant state because the output schema has one `inferred_state` field.
- The debate stage is the part most likely to be cut if it turns out to add latency without changing outcomes. I will keep it only if the harness shows it moving results.
- Cold start. Every mechanism here leans on a historical baseline. A customer with two months of history produces unstable expectations, and I have not designed the shrinkage toward a population prior that this needs.
- The correlation step is now carrying a lot of weight, since novelty alone is only ~2/3 precise and I am relying on corroboration to do the discriminating. If the correlation window is tuned too tightly it will miss the new-child case, where the supporting evidence is spread over five weeks.
