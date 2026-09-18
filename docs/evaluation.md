# Testing and evaluation

Everything here comes from the two scripts in `eval/`, run against the three
practice scenarios. Reproduce with:

```bash
python3 run.py --all
python3 eval/score.py --all runs/ --dataset customer_360_dataset
python3 eval/coverage.py
```

All numbers below are from the offline path, with no `ANTHROPIC_API_KEY` set.
That matters and I say more about it at the end.

## Does Tier 0 catch the signal, and what does it cost?

`eval/coverage.py` asks two questions that pull against each other: of the
events ground truth marks as signal, how many trip a detector, and what
fraction of all live events trip anything — because every one of those wakes an
agent.

| scenario | live events | firing | wake rate | signals caught |
|---|---|---|---|---|
| medical hardship | 115 | 10 | 8.7% | 9 / 10 |
| new child | 110 | 12 | 10.9% | 11 / 11 |
| churn risk | 72 | 6 | 8.3% | 6 / 6 |
| **total** | **297** | **28** | **9.4%** | **26 / 27** |

The 9.4% is the number the whole two-tier design rests on. If it were 60% the
architecture would be pointless overhead.

The one miss is worth being precise about rather than hiding. `EVT_000444` is
the $10,000 withdrawal out of savings on 15 March; its partner `EVT_000445`,
the matching deposit into checking one second later, does fire. The sweep-pair
detector collapses the two into one movement and attributes it to the second
event id, so the money movement is caught and the ledger row cites the wrong
half of the pair. It costs nothing in scoring and it is a labelling bug, not a
detection failure, but it is a miss and it belongs in this table.

## Does it get the answer right?

`eval/score.py` scores the emitted `inferred_events.json` against
`ground_truth.json` at each checkpoint the ground truth defines.

| | result | |
|---|---|---|
| inferred_state | 8 / 8 | 100% |
| confidence_band | 8 / 8 | 100% |
| action | 7 / 8 | 88% |
| action_subtype | 3 / 3 | 100% |
| hitl_status | 3 / 3 | 100% |
| lead time | 2 / 3 | 67% |
| no false positive on red herrings | 4 / 4 | 100% |

Actions first fire on 20 March (medical), 20 March (new child) and 6 March
(churn), against ground-truth checkpoints of 26 March, 27 March and 8 March.

## The two things it gets wrong

**Churn lead time is two days, not three.** Ground truth wants the churn
escalation three days before the 8 March checkpoint, meaning 5 March. We fire
on 6 March. The evidence available beforehand is a rejected fee complaint on
6 February, a collapsing engagement curve through late February, and a
standing-instruction cancellation on 4 March. The thing that tips us over is
the $22,500 transfer to the customer's own account at another bank on 6 March.

I could pass this check by weighting the cancellation heavily enough to fire on
its own. I decided not to. A customer reorganising their direct debits is not a
customer leaving, and a system that escalates to a relationship manager every
time someone cancels a standing order would be unusable in production — the
false-positive burden is the thing that gets these systems switched off. Waiting
one extra day for the money to actually move costs a day of lead and buys a
large reduction in spurious escalations. That is the trade I would make again,
but it is a real failure against the stated ideal and I am not going to dress it
up as a design win.

**The 10 April churn checkpoint scores as a miss.** Ground truth expects
`proactive_retention_outreach` there; we are still holding
`relationship_manager_escalation` from 6 March. The ground-truth note for that
checkpoint says that a system only arriving at the answer by 10 April "has
failed the early lead time test" — so it reads as a don't-be-late check rather
than a target. We got there five weeks earlier with a stronger action. The
harness counts it against us because it compares strings, and I have left it
counted against us rather than special-casing it.

## Where the thresholds are fragile

This is the part I would want a reviewer to push on, so here it is first.

The band cutoffs are fitted to three scenarios. The window that satisfies every
ground-truth checkpoint simultaneously is narrow: `HIGH` has to sit in
(5.80, 6.66] and `MEDIUM` in (2.66, 5.80]. Scenario 1 must still read medium at
5.80 on 12 March while scenario 3 must read high at 6.66 on 8 March. Those two
constraints nearly collide.

A window that tight is fitted, not learned. With three scenarios there is no
way to tell a well-calibrated threshold from one that happens to land between
six data points, and I would expect this to be the first thing that breaks on a
customer I have not seen. The honest fix is more scenarios, not more tuning.

Two knock-on effects I hit while tuning, both real:

The band cutoff and the lead time are driven by the same number, and they pull
in opposite directions. Raising `HIGH` from 6.0 to 6.2 fixed a band check and
cost two lead-time checks, because the action fires later. There is no setting
that maximises both.

Confidence is sensitive to how correlated evidence is counted. The first
version summed every ledger row at face value, which treats a pharmacy charge
and a hospital bill as two independent facts when they are one fact observed
twice. That pushed scenario 1 to high confidence on 12 March, two weeks before
ground truth says the picture is clear. Discounting repeats within a detector
group — strongest row in full, second at half, third at a third — fixed it and
is the single change that most improved the scores.

## Things that broke on the way, and what fixed them

Recording these because the failure modes were more informative than the
successes.

**Scenario 1 came out as job loss.** A benefits credit replacing a salary was
scored as income disruption, which outran the medical evidence. Reading income
shortfall by *instrument* rather than just amount fixed it: a salary that
shrank is ambiguous, a salary replaced by a disability payment is a medical
story. State accuracy went from 1/3 to 3/3 on that scenario.

**The $8,500 hospital bill produced nothing.** Novel-category fires once and
then goes quiet, so by 10 March healthcare was no longer new and the largest
medical charge in the dataset was invisible. Added a detector for heavy health
spend sized against the customer's own median card transaction, rather than a
fixed threshold.

**Every decision read a day late.** Checkpoints were stamped at the following
midnight rather than at the close of the day they described, costing a full day
of lead time on every scenario. A one-line fix worth about two checkpoints.

**Retraction nearly destroyed a real signal.** The support agent, on reading
"just confirming it's me, I bought a baby monitor", revoked every card
assertion from the previous fortnight — including the genuine BuyBuyBaby
purchase from a week earlier, because the word "baby" appeared in both. The fix
was to match on the merchant actually named in the message, and to move that
matching out of the support agent entirely: the support agent is scoped to
support logs and structurally cannot see card transactions, so it reports the
claim and the orchestrator resolves it. The access model prevented the agent
from doing the thing it was doing wrong, once I stopped working around it.

**Support ticket resolutions were never read.** The detector only fired on
`ticket_created`. Both of the interesting support events in this dataset — the
baby-monitor explanation and our own rejection of a fee complaint — arrive as
`ticket_resolved`, so the system was ignoring them entirely.

## What is not tested

The retraction path does not fire on any of the three scenarios. The electronics
purchase that the baby-monitor message explains maps to no hypothesis, so there
is no ledger row to withdraw, and the correct behaviour is to do nothing. The
mechanism is exercised by the orchestrator's merchant matching, and I have
watched it revoke the right row when pointed at one, but no practice scenario
demands it. It is untested in the sense that matters.

All numbers here are from the offline path. Without an API key the support
agent's text reading falls back to keyword rules and the drafting agent falls
back to a template. The structural claims — deduplication, absence detection,
decay, retraction, the policy matrix, the posterior — hold identically either
way, because none of them involve a model. What changes with a key is the
quality of the sentiment reading and the prose of the note a human sees. I have
not run a full scored comparison of the two paths, so I cannot claim the model
path scores better; I can only say it is the path the design intends and that
the trace records which was used for every call.

Three scenarios, one customer each, all synthetic. Nothing here should be read
as evidence the system works on real customers.
