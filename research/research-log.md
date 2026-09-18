# Research log

What I read while working this out, what I took from each thing, and which
decision it changed. Where something talked me out of an idea I have said so,
because those were the more useful reads.

The entries at the top of each section are the ones that actually shaped a
decision and I have written those up properly. The collapsed list under each is
things I read more quickly or skimmed for one specific point. I have kept those
to a line each rather than pretending to more depth than I have.

A caveat worth stating: a lot of the genuinely useful material here is vendor
engineering writing rather than peer-reviewed work, because the practical
literature on agent memory and coordination is about two years old and the
people building these systems publish on blogs. Where a source has a commercial
interest in its own conclusion I have flagged it.

---

## Agent memory

The problem statement asks three questions about memory it deliberately refuses to answer: when is an old memory relevant, how do you stop customers bleeding into each other, and who decides a flag has expired. These are what I read to answer them. The thing that surprised me is that the working/episodic/semantic split everyone quotes comes from cognitive architecture rather than from any LLM paper, and the recent systems are mostly arguing about retrieval scoring and invalidation.

**[OWASP Top 10 for LLM Applications 2025 — LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/)**  
<sub>OWASP GenAI Security Project · genai.owasp.org · 2025</sub>

Names the failure modes of vector stores used as agent memory: cross-context information leaks in multi-tenant environments (embeddings from one user group retrieved for another group's query), embedding inversion attacks (recovering substantial source text from stored vectors), data/knowledge-sourc...

*Took:* 'Permission-aware vector store with strict logical partitioning' plus 'immutable retrieval logs' as the concrete standard to build and document against.

*Changed:* This is the citable standard behind the role-based-data-access-at-the-data-layer and PII requirements.

*Doesn't apply where:* OWASP is a risk checklist, not a mechanism: it tells you the boundary must exist but not how to enforce it when one agent legitimately spans customers (e.g.

**[Is Mem0 Really SOTA in Agent Memory? (Lies, Damn Lies, and Statistics)](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/)**  
<sub>Daniel Chalef, Preston Rasmussen (Zep AI) · Zep engineering blog · 2025</sub>

A point-by-point rebuttal of Mem0's LoCoMo evaluation. Claims three implementation errors in Mem0's Zep baseline: modelling both conversation participants as a single user, non-standard timestamp handling that broke temporal reasoning, and sequential rather than concurrent search.

*Took:* Two things: memory-system leaderboard numbers are not trustworthy, and on any corpus that fits in context, a memory architecture must justify itself on something other than accurac...

*Changed:* Do not justify the memory layer with 'it beats full context'. For this problem, 300-400 history + 70-120 live events per customer plausibly FITS in a long context window, so a stuff-everything baseline is a real competitor and a judge will ask about it.

*Doesn't apply where:* ARGUES AGAINST THE OBVIOUS APPROACH, and is itself conflicted: Zep is a direct commercial competitor rebutting a competitor's paper, and the corrected numbers are self-reported and unreplicated.

**[Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956)**  
<sub>Preston Rasmussen, Pavlo Paliychuk, Travis Beauvais, Jack Ryan, Daniel Chalef (Zep AI) · arXiv (Graphiti is the open-source engine) · 2025</sub>

Graphiti maintains a three-tier graph: episode subgraph (raw, non-lossy messages/JSON), semantic entity subgraph (extracted entities and relation edges), and community subgraph (clustered higher-level summaries).

*Took:* Bi-temporal edge invalidation with four timestamps, and the non-lossy episode tier sitting underneath the derived tiers.

*Changed:* This is the single most load-bearing borrowing for this system. The deliverable's as_of_time IS a bi-temporal query, and the dataset forces it: a card transaction arriving with ingestion_time 48h after event_time means a checkpoint already emitted covered a period whose facts have since changed.

*Doesn't apply where:* The benchmark numbers are vendor-published and the DMR margin (94.8 vs 93.4) is within plausible noise for a 500-item benchmark.

**[The TSQL2 Temporal Query Language / Bitemporal Conceptual Data Model](https://people.cs.aau.dk/~csj/Thesis/pdf/chapter12.pdf)**  
<sub>Richard T. Snodgrass (ed.), Christian S. Jensen et al. · Springer (Kluwer), Boston; TSQL2 committee · 1995</sub>

Formalises the distinction that everything downstream depends on: VALID TIME is when a fact was true in the modelled reality; TRANSACTION TIME is when the fact was stored in the database. A relation carrying both is bitemporal.

*Took:* Transaction time is append-only by construction. That property, not the query syntax, is the thing to steal.

*Changed:* Gives the formal vocabulary and the correctness rule for the whole memory layer, and pre-dates every LLM memory system by thirty years — worth citing precisely because it shows the 'novel' temporal-KG work is rediscovering a solved model. Map event_time -> valid time, ingestion_time -> transaction time.

*Doesn't apply where:* TSQL2 itself was rejected as an SQL standard (it became SQL:2011 system-versioned tables in reduced form) and its coalescing semantics were criticised;

**[Reflections of the Environment in Memory (and the ACT-R base-level activation equation)](https://doi.org/10.1111/j.1467-9280.1991.tb00174.x)**  
<sub>John R. Anderson, Lael J. Schooler (Carnegie Mellon) · Psychological Science, Vol. 2, pp. 396-408 · 1991</sub>

Rational analysis of memory: the probability that an item will be NEEDED again is a predictable function of how frequently and how recently it has been encountered, and human forgetting curves match the statistics of the environment (they measured New York Times headlines, parental speech to childre...

*Took:* Activation is an estimate of P(needed now) derived from the observed inter-arrival statistics of the item itself.

*Changed:* This is the principled answer to the hardest fact in the dataset: absence emits no event. Fit a per-item arrival model from history and let the DEFICIT in activation be the trigger. Salary_credit with 12 observations at exactly 14-day spacing has a very tight arrival distribution;

*Doesn't apply where:* ACT-R decay is calibrated on human recall latency in laboratory tasks; d=0.5 has no principled meaning for financial event streams and must be refit per signal family.

**[How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior](https://arxiv.org/abs/2505.16067)**  
<sub>Zidi Xiong et al. (8 authors; Harvard and collaborators) · arXiv (May 2025, revised Oct 2025) · 2025</sub>

Identifies and names 'experience-following': when a task input is highly similar to the input of a retrieved memory record, the agent's output is highly similar to that record's output — an agent copies precedent rather than reasoning. This produces two compounding failure modes.

*Took:* The core warning: an unfiltered episodic bank of past decisions actively degrades an agent, and the degradation is proportional to bank size.

*Changed:* This is a hard constraint on how past checkpoint decisions are reused. With ~8% signal density, roughly 9 in 10 stored precedents say inferred_state=no_significant_event, action=no_action.

*Doesn't apply where:* ARGUES AGAINST THE OBVIOUS APPROACH. The instinctive design — 'store every past checkpoint decision and retrieve similar ones' — is shown here to get worse over time.

<details>
<summary>Also read (9)</summary>

- [Memory Injection Attacks on LLM Agents via Query-Only Interaction (MINJA)](https://arxiv.org/abs/2503.03704) (2025) — The threat model: any customer-authored text that the agent reflects on and stores becomes an injection channel, and the poison is authored by the age...
- [Sleep-time Compute: Beyond Inference Scaling at Test-time](https://arxiv.org/abs/2504.13171) (2025) — Move all context-dependent work off the latency path, and amortise it across many queries over the same context.
- [Extending Cognitive Architecture with Episodic Memory](https://web.eecs.umich.edu/~soar/sitemaker/docs/pubs/AAAI2007_NuxollLaird_ver14(final).pdf) (2007) — Automatic, non-selective episode capture plus cue-based partial-match retrieval and forward replay — the agent queries with a partial situation descri...
- [The Power of Noise: Redefining Retrieval for RAG Systems](https://arxiv.org/abs/2401.14887) (2024) — Near-miss retrieval is worse than no retrieval. Optimise the evidence set for discriminativeness, not for similarity.
- [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://arxiv.org/abs/2410.10813) (2024/2025) — The knowledge-updates and abstention categories, and the finding that long-context models fail them badly.
- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) (2023) — The three-term additive retrieval score and the accumulated-importance reflection trigger are the right shape.
- [HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models](https://arxiv.org/abs/2405.14831) (2024) — Single-shot graph-spreading retrieval with IDF-style node specificity, replacing multi-round agentic retrieval.
- [Cognitive Architectures for Language Agents (CoALA)](https://arxiv.org/abs/2309.02427) (2023) — The insistence that memory WRITES are actions in the same action space as tool calls, and therefore are proposable, evaluatable, selectable and loggab...
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) (2025) — Link generation at write time, and the principle that a later event can legitimately change the meaning of an earlier one.

</details>


## Evidence, and changing your mind

This section changed the design. I went looking for how other fields represent a belief that builds over time and can be withdrawn, because that is what a confidence band actually is, and found sequential analysis and truth maintenance had been doing it since the 1940s and 1970s.

**[The Neural Hawkes Process: A Neurally Self-Modulating Multivariate Point Process](https://arxiv.org/abs/1612.09328;)**  
<sub>Hongyuan Mei, Jason Eisner · Advances in Neural Information Processing Systems 30 (NIPS 2017) · 2017</sub>

Models K event types with intensities λ_k(t) = f_k(w_k · h(t)) driven by a continuous-time LSTM whose hidden state decays between events toward a learned steady state and jumps at each event.

*Took:* The −∫λ(s)ds term. Absence is evidence with a computable likelihood, and it accrues continuously without any event arriving.

*Changed:* This is the answer to the hardest measured fact in the brief: 'absence is the strongest signal and emits no event.' Model each customer as a multivariate point process over {card_txn, login, salary_credit, support_ticket, ...}.

*Doesn't apply where:* Training a neural Hawkes needs far more data than one customer's 300-event history — per-customer fitting is hopeless.

**[Use time travel (LangGraph documentation)](https://docs.langchain.com/oss/python/langgraph/use-time-travel)**  
<sub>LangChain / LangGraph · docs.langchain.com · 2026 (accessed)</sub>

Verified by fetching the page. Every super-step writes a checkpoint (a StateSnapshot of values, metadata, and the next nodes) keyed by thread_id; get_state_history(config) returns the thread's checkpoints in reverse chronological order, each carrying config['configurable']['checkpoint_id'].

*Took:* Fork-from-past-checkpoint with the original branch preserved, plus interrupt/Command(resume=...) as the HITL primitive — both already persisted and inspectable.

*Changed:* Concrete implementation of 'recompute the posterior as of any past timestamp'. Run one thread per (customer, hypothesis) and checkpoint at every ingested event.

*Doesn't apply where:* The docs are explicit that replay RE-EXECUTES LLM calls nondeterministically, so a naive re-run will not reproduce the original decision even without the late event — which destroys the audit story.

**[Differential Dataflow](https://www.cidrdb.org/cidr2013/Papers/CIDR13_Paper111.pdf;)**  
<sub>Frank McSherry, Derek G. Murray, Rebecca Isaacs, Michael Isard · CIDR 2013 (6th Biennial Conference on Innovative Data Systems Research) · 2013</sub>

Represents collections as multisets with INTEGER multiplicities (negative multiplicity = retraction) and stores, instead of successive full collections, the DIFFERENCES indexed by multi-dimensional, PARTIALLY ORDERED logical timestamps.

*Took:* Retraction-as-negative-multiplicity over partially-ordered timestamps, and 'current value = sum of differences ≤ t' as the recomputation rule.

*Changed:* This is the formal model for the append-only, retractable ledger — and it is the strongest architectural-novelty claim available in this sub-domain. Use a two-dimensional timestamp (event_time, ingestion_time), which is a partial order, not a sequence.

*Doesn't apply where:* Differential dataflow's incrementality theorems assume the computation is expressible in its operator algebra (map/filter/join/group/iterate) over commutative-group-valued differences.

**[Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback](https://arxiv.org/abs/2305.14975)**  
<sub>Katherine Tian, Eric Mitchell, Allan Zhou, Archit Sharma, Rafael Rafailov, Huaxiu Yao, Chelsea Finn, Christopher D. Manning · EMNLP 2023 · 2023</sub>

Verified by fetching the arXiv abstract page. Evaluates how to extract confidence from RLHF-fine-tuned LLMs.

*Took:* Never read confidence off token logprobs from an RLHF'd model; elicit it verbally, and calibrate the verbal output post hoc.

*Changed:* Decides the LLM's job description in this architecture, which is the key guardrail question. The LLM does NOT produce confidence_band and does NOT produce a posterior.

*Doesn't apply where:* ARGUES AGAINST the convenient design. The result is about factual QA calibration, not about likelihood-ratio elicitation over financial event streams, and coarse verbal LRs are still systematically ov...

**[An assumption-based TMS](https://doi.org/10.1016/0004-3702(86)90080-9;)**  
<sub>Johan de Kleer · Artificial Intelligence, Vol. 28(2), pp. 127–162 · 1986</sub>

Replaces justification manipulation (Doyle's JTMS) with ASSUMPTION-SET manipulation. Every derived node carries a LABEL: the set of minimal, consistent ENVIRONMENTS (sets of primitive assumptions) from which it follows.

*Took:* Label conclusions with their minimal supporting assumption sets, and make retraction a set operation rather than a recomputation.

*Changed:* This is the architecture of the retractable evidence ledger, and it is where the genuine novelty claim lives. Every inferred_state emission is labelled with the minimal set of events that support it.

*Doesn't apply where:* ATMS label computation is worst-case exponential in the number of assumptions — with 70–120 live events treating each as an assumption is tractable, but do not scale this to 400 history events.

**[Developing Time-Oriented Database Applications in SQL](https://www2.cs.arizona.edu/~rts/tdbbook.pdf)**  
<sub>Richard T. Snodgrass · Morgan Kaufmann (Series in Data Management Systems); full text at cs.arizona.edu · 1999</sub>

The standard treatment of bitemporal data. VALID TIME is when a fact was true in the modelled reality; TRANSACTION TIME is when the database believed it, and is strictly append-only — transaction-time rows are never updated or deleted, only logically closed. A bitemporal table carries both.

*Took:* The two independent time axes and the rule that transaction time is immutable — which is what makes 'what did we believe at time X' answerable at all.

*Changed:* This is the storage contract underneath the ledger and it is what the traceability/observability rubric item is actually asking for. Store every event and every ledger delta with (valid_time = event_time, transaction_time = ingestion_time).

*Doesn't apply where:* Bitemporal SQL is notoriously verbose and every sequenced query needs interval-overlap handling by hand; naive implementations get coalescing and period joins wrong.

<details>
<summary>Also read (9)</summary>

- [A logic for default reasoning](https://doi.org/10.1016/0004-3702(80)90014-4;) (1980) — The explicit 'in the absence of information to the contrary' operator, and normal defaults as the well-behaved fragment that is guaranteed to have an...
- [On the logic of theory change: Partial meet contraction and revision functions](https://philpapers.org/rec/ALCOTL-2) (1985) — The distinction between contraction and revision, minimal change as an explicit criterion, and the fact that which beliefs survive a retraction is a m...
- [Royal Statistical Society: Statement regarding statistical issues in the Sally Clark case](https://rss.org.uk/RSS/media/File-library/Membership/Sections/2020/Sally-Clark-RSS-statement-2001.pdf) (2001) — A concrete, catastrophic, real-world instance of the exact failure mode our design risks: independent multiplication of correlated evidence producing...
- [E-values: Calibration, combination, and applications](https://arxiv.org/abs/1912.06116;) (2021) — The dependence-robust merge rule: average, don't multiply, when detectors may be correlated.
- [Event History (Temporal Platform Documentation)](https://docs.temporal.io/encyclopedia/event-history/event-history-go) (2026 (accessed)) — The determinism boundary: deterministic orchestration replayed from an immutable log, with every nondeterministic effect recorded as a replayable acti...
- [Durable Functions: Semantics for Stateful Serverless](https://doi.org/10.1145/3485510;) (2021) — The three-abstraction decomposition, and specifically the ENTITY: a durable, single-threaded-per-key piece of state that is addressed by name and does...
- [A Simple View of the Dempster-Shafer Theory of Evidence and Its Implication for the Rule of Combination](https://doi.org/10.1609/aimag.v7i2.542;) (1986) — That conflict normalisation is not a technicality — under high conflict it produces confidently wrong answers, and the magnitude of the error grows wi...
- [Reasoning with belief functions: An analysis of compatibility](https://doi.org/10.1016/0888-613X(90)90013-R;) (1990) — The provability-vs-truth distinction, and the specific finding that belief functions handle CONDITIONAL, defeasible rules badly.
- [The Cost of Accumulating Evidence in Perceptual Decision Making](https://www.jneurosci.org/content/32/11/3612) (2012) — Time-varying (collapsing) decision boundaries derived from an explicit cost-of-waiting, solved by dynamic programming over the belief state.

</details>


## Streaming and event time

I assumed this was the boring plumbing part. The Dataflow paper is what taught me otherwise, and CEP absence patterns turned out to be the literature for the hardest single fact in the dataset.

**[MillWheel: Fault-Tolerant Stream Processing at Internet Scale](http://www.vldb.org/pvldb/vol6/p1033-akidau.pdf)**  
<sub>Tyler Akidau, Alex Balikov, Kaya Bekiroğlu, Slava Chernyak, Josh Haberman, Reuven Lax, Sam McVeety, Daniel Mills, Paul Nordstrom, Sam Whittle (Google) · Proceedings of the VLDB Endowment (PVLDB) 6(11):1033-1044 · 2013</sub>

I read the PDF. Defines the low watermark of computation A recursively as min(oldest work of A, low watermark of C for all C that output to A), seeded by injectors.

*Took:* Absence is detected by a persistent per-key timer that fires on watermark advance, plus the watermark as the thing that distinguishes 'delayed' from 'never happened'.

*Changed:* This is the single most load-bearing citation for the two hardest dataset facts.

**[The Dataflow Model: A Practical Approach to Balancing Correctness, Latency, and Cost in Massive-Scale, Unbounded, Out-of-Order Data Processing](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf)**  
<sub>Tyler Akidau, Robert Bradshaw, Craig Chambers, Slava Chernyak, Rafael J. Fernández-Moctezuma, Reuven Lax, Sam McVeety, Daniel Mills, Frances Perry, Eric Schmidt, Sam Whittle (Google) · Proceedings of the VLDB Endowment (PVLDB) 8(12):1792-1803 · 2015</sub>

Decomposes stream processing into four orthogonal questions: WHAT is computed, WHERE in event time (windowing), WHEN in processing time results are materialized (triggers), and HOW later refinements relate to earlier ones (accumulation mode). I read the PDF directly.

*Took:* The trigger/accumulation separation, and specifically Accumulating & Retracting: a decision emitted at a checkpoint is a *pane*, not a final answer, and a late arrival legitimately...

*Changed:* This is the backbone of the checkpoint emitter. Each checkpoint emission is a pane keyed by (customer_id, as_of_time) with an explicit revision counter and a supersedes pointer, not an immutable verdict.

**[FlinkCEP — Complex Event Processing for Flink (official documentation)](https://nightlies.apache.org/flink/flink-docs-master/docs/libs/cep/)**  
<sub>Apache Flink project · nightlies.apache.org/flink/flink-docs-master/docs/libs/cep/ · 2026 (master docs)</sub>

I fetched this page. notNext() is strict non-contiguity (the negative event must directly succeed); notFollowedBy() is relaxed non-contiguity (the partial match is discarded even if other events intervene).

*Took:* The absence idiom (notFollowedBy + within) and, more importantly, the explicit admission that FlinkCEP DROPS late events rather than revising completed matches.

*Changed:* Argues against the obvious choice. FlinkCEP is the natural off-the-shelf engine for our patterns, but its late-element policy is fatal for this dataset: the 48-hour-late card transaction would land behind the watermark and be silently discarded, so the decision it should have revised never gets revised.

**[A Large-Scale Comparison of Concept Drift Detectors](https://doi.org/10.1016/j.ins.2018.04.014)**  
<sub>Roberto Souto Maior de Barros, Silas Garrido Teixeira de Carvalho Santos · Information Sciences 451-452:348-370 · 2018</sub>

Empirically compares 14 concept-drift-detector configurations (including DDM, EDDM, Page-Hinkley, ADWIN and variants) across a large set of artificial datasets with two base learners (Naive Bayes and Hoeffding Tree), measuring accuracy, runtime, false-alarm rate, miss rate and distance to the true d...

*Took:* Detector sensitivity is not a virtue; a simple periodic baseline is a real competitor and must be measured against.

*Changed:* The deliberate counter-argument to our own architecture. Before shipping a stack of CUSUM + ADWIN + BOCPD detectors, benchmark them against a dumb baseline: re-evaluate the customer at every checkpoint with a fixed-window feature diff and no detector at all.

<details>
<summary>Also read (9)</summary>

- [Sequential Tests of Statistical Hypotheses (the SPRT)](https://doi.org/10.1214/aoms/1177731118) (1945) — The three-way decision with an explicit CONTINUE region, and boundaries that are functions of the error rates you are willing to accept.
- [Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742) (2007) — A run-length posterior that yields a calibrated probability of 'a change happened k steps ago', plus a Poisson/gamma-conjugate model of event INTER-AR...
- [Esper EPL Reference: Event Patterns (timer:interval with 'and not' for absence detection)](http://esper.espertech.com/release-7.0.0/esper-reference/html/event_patterns.html) (2017 (product ongoing)) — The canonical absence idiom: absence is expressed as a timer firing conjoined with the negation of the expected event — the timer supplies the event t...
- [Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress](https://arxiv.org/abs/2009.13807) (2021 (arXiv 2020)) — Always establish the one-line baseline first, and audit your own evaluation set for triviality, density realism and label quality before believing any...
- [A Survey on Concept Drift Adaptation](https://doi.org/10.1145/2523813) (2014) — The real-vs-virtual drift distinction, the Page-Hinkley forgetting factor, and the insistence on reporting detection delay separately from false-alarm...
- [Learning from Time-Changing Data with Adaptive Windowing (ADWIN / ADWIN2)](https://www.cs.upc.edu/~gavalda/papers/adwin06.pdf) (2007) — The window length itself becomes the detector output — no magic lookback constant — with provable error bounds and O(log W) cost.
- [Sequence Pattern Query Processing over Out-of-Order Event Streams](https://ieeexplore.ieee.org/document/4812454/) (2009) — The aggressive-plus-compensation strategy, and the specific warning that NEGATION patterns are the ones late events corrupt.
- [Efficient Pattern Matching over Event Streams (SASE+)](https://doi.org/10.1145/1376616.1376634) (2008) — The selection-strategy axis — the same pattern means very different things under strict contiguity vs skip-till-any-match — and the separation of nega...
- [Watermarks in Stream Processing Systems: Semantics and Comparative Analysis of Apache Flink and Google Cloud Dataflow](https://doi.org/10.14778/3476311.3476389) (2021) — The input-watermark / output-watermark distinction per stage, and the explicit framing of a watermark as a claim about completeness that each stage mu...

</details>


## Multi-agent coordination

I read the sceptics before the enthusiasts, deliberately. The problem statement hands you a roster of ten agents and it would be easy to build all ten without asking whether any earn their keep. The honest summary is that multi-agent systems have a patchy record and a well-documented set of failure modes, and that the patterns which do work are narrower than the marketing.

**[Constitutional AI: Harmlessness from AI Feedback](https://arxiv.org/abs/2212.08073)**  
<sub>Yuntao Bai, Saurav Kadavath, Sandipan Kundu, Amanda Askell, Jackson Kernion, Jared Kaplan et al. (Anthropic) · arXiv (Anthropic) · 2022</sub>

Two phases. Supervised phase: sample a response from the initial model, prompt the SAME model to critique its response against a randomly sampled written principle from a short 'constitution', then revise; fine-tune on the revised responses.

*Took:* Principle-conditioned critique. The critic is never asked 'is this good?' — it is asked 'does this violate principle P?', with P drawn from an explicit written list.

*Changed:* Write an explicit, versioned Intervention Constitution for the desk and make every guardrail check a principle-conditioned critique with the principle ID logged in the trace.

**[Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)**  
<sub>Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, Bhavya Chopra, Rishabh Tiwari, Kurt Keutzer, Aditya Parameswaran, Dan Klein, Kannan Ramchandran, Matei Zaharia, Joseph E. Gonzalez, Ion Stoica (UC Berkeley) · arXiv; NeurIPS 2025 Datasets & Benchmarks Track · 2025</sub>

MAST taxonomy built from 150 hand-annotated traces (inter-annotator kappa = 0.88) then scaled to MAST-Data, 1600+ annotated traces across 7 MAS frameworks and GPT-4/Claude 3/Qwen2.5/CodeLlama.

*Took:* A ready-made failure-mode checklist to instrument against, and the empirical fact that ~79% of MAS failures are design/communication, not model capability.

*Changed:* Use MAST's 14 modes as named span-level assertions in our trace log — this converts the 15% 'non-negotiables' score into something measurable. Concretely: FM-1.5 (unaware of termination) -> hard round cap of 2 on the critique-refine loop with a deterministic tie-break;

**[When to use multi-agent systems (and when not to)](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)**  
<sub>Cara Phillips, with Paul Chen, Andy Schumeister, Brad Abrams, Theo Chu (Anthropic / Claude blog) · claude.com/blog · 2026</sub>

Names exactly three situations where multiple agents beat one: (1) context protection — isolating information that pollutes a single window; (2) parallelization — covering an information space larger than one context; (3) specialization — focused toolsets improving tool-selection reliability.

*Took:* A three-question admission test for every agent you are tempted to add, and the rule to decompose by CONTEXT BOUNDARY not by problem type.

*Changed:* Justify each agent in the design doc against the three criteria, and decompose by data-source context boundary (card/transaction stream; recurring-commitment registry; channel-activity/absence; support-tickets-and-comms/NLP) rather than by state label.

**[ChatDev: Communicative Agents for Software Development](https://arxiv.org/abs/2307.07924)**  
<sub>Chen Qian, Wei Liu, Hongzhang Liu, Nuo Chen, Yufan Dang, Jiahao Li, Cheng Yang, Weize Chen, Yusheng Su, Xin Cong, Juyuan Xu, Dahai Li, Zhiyuan Liu, Maosong Sun (Tsinghua / OpenBMB) · ACL 2024 · 2023</sub>

Two named mechanisms. CHAT CHAIN: the waterfall (design, coding, testing) is decomposed into a chain of atomic two-agent subtasks, each with exactly one instructor and one assistant, so that at any moment only two agents are talking and the chain — not a manager — determines what gets communicated n...

*Took:* Communicative dehallucination — an agent's legal move set must include 'I need more evidence' — and the chain-of-dyads structure that keeps the active conversation at exactly two p...

*Changed:* 'Insufficient evidence' must be a first-class return value for every specialist, not a forced classification.

**[LLMs Get Lost In Multi-Turn Conversation](https://arxiv.org/abs/2505.06120)**  
<sub>Philippe Laban, Hiroaki Hayashi, Yingbo Zhou, Jennifer Neville (Microsoft Research / Salesforce Research) · arXiv (code: github.com/microsoft/lost_in_conversation) · 2025</sub>

Simulates 200,000+ conversations by sharding fully-specified single-turn instructions into multi-turn drip-feeds, across six generation tasks (code, database, actions, math, data-to-text, summary, translation).

*Took:* Incremental information delivery is itself the failure cause, and early wrong commitments are unrecoverable inside a growing conversation.

*Changed:* This is the decisive argument for STATELESS RE-DERIVATION at every checkpoint. We do NOT maintain one long-running conversation that ingests 70-120 live events turn by turn — that is exactly the sharded setup that loses 39%.

**[MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352)**  
<sub>Sirui Hong, Mingchen Zhuge, Jiaqi Chen, Xiawu Zheng, Yuheng Cheng, Ceyao Zhang, Jinlin Wang, Zili Wang, Steven Ka Shing Yau, Zijuan Lin, Liyang Zhou, Chenyu Ran, Lingfeng Xiao, Chenglin Wu, Jürgen Schmidhuber · arXiv (v7, Nov 2024); widely cited as ICLR 2024 · 2023</sub>

Encodes human Standardised Operating Procedures into prompt sequences so agents with role expertise (Product Manager, Architect, Project Manager, Engineer, QA) run an assembly line over a task.

*Took:* Typed artefacts over free-text messages, plus role-scoped subscription to a shared pool instead of broadcast.

*Changed:* Our evidence ledger IS the shared message pool, and every specialist publishes a typed Finding {finding_type, event_ids[], baseline_stats, effect_size, confidence, agent_id, timestamp} — never prose.

<details>
<summary>Also read (9)</summary>

- [Handoffs (OpenAI Agents SDK documentation)](https://openai.github.io/openai-agents-python/handoffs/) (2025) — The mechanics of the required 'handoff' pattern, and the exact location of the footgun: the convenience filter that strips tool calls is precisely wha...
- [CAMEL: Communicative Agents for "Mind" Exploration of Large Language Model Society](https://arxiv.org/abs/2303.17760) (2023) — The four named conversational pathologies — they are the ones that appear in any free-form two-agent loop, and each maps onto a cheap deterministic de...
- [AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation](https://arxiv.org/abs/2308.08155) (2023) — The human_input_mode taxonomy and the speaker-selection abstraction.
- [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents) (2025) — Writes stay single-threaded; extra agents contribute intelligence, not actions.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (2025) — Orchestrator-worker with parallel, context-isolated, READ-ONLY workers plus one synthesising lead.
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) (2023) — The 80%-equals-human-agreement number that legitimises LLM judging for OFFLINE evaluation, paired with the named biases that disqualify a naive judge...
- [CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing](https://arxiv.org/abs/2305.11738) (2023) — The critique channel must be a tool call that returns a verdict the generator cannot argue with. Verification, not deliberation.
- [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651) (2023) — The three-role decomposition with a hard requirement that feedback be actionable and name a specific deficiency — and the stopping rule (stop when fee...
- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents) (2024) — The evaluator-optimizer precondition — iterative refinement is only justified where evaluation criteria are CLEAR — and the voting flavour of parallel...

</details>


## Retrieval

Most of this talked me out of things. The instinct is to put everything in a vector database; for a stream of near-identical card transactions that is close to the worst available choice, and several of these say so directly.

**[PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models](https://arxiv.org/abs/2402.07867)**  
<sub>Wei Zou, Runpeng Geng, Binghui Wang, Jinyuan Jia (Penn State, Illinois Institute of Technology) · USENIX Security 2025 (arXiv preprint Feb 2024) · 2025</sub>

First systematic knowledge-corruption attack on RAG.

*Took:* The threat model: any text in the retrieval corpus that a non-trusted party can influence is an injection vector, and the attack works precisely because the retriever is doing its...

*Changed:* Forces a trust boundary inside our own corpus, which is easy to miss because the data looks internal. Our event stream contains free-text the CUSTOMER authors or influences: support ticket bodies, chat transcripts, merchant description strings.

*Doesn't apply where:* PoisonedRAG attacks an open-domain QA corpus an adversary can write into at will (e.g. a wiki);

**[Feast documentation: Point-in-time joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins)**  
<sub>Feast (Linux Foundation / Tecton originated) · docs.feast.dev · 2026 (docs, continuously updated)</sub>

Feature values are stored as timestamped time series.

*Took:* The two-clock as-of join, and specifically the created-timestamp filter as the operational mechanism for reproducing past state in the presence of late-arriving corrections.

*Changed:* This is the concrete implementation of bi-temporal correctness at the feature layer, and it is where our evaluation integrity lives.

*Doesn't apply where:* Vendor/OSS documentation rather than a paper, and the exact flag name is version-specific.

**[Hubs in Space: Popular Nearest Neighbors in High-Dimensional Data](https://jmlr.org/papers/v11/radovanovic10a.html)**  
<sub>Miloš Radovanović, Alexandros Nanopoulos, Mirjana Ivanović (University of Novi Sad, University of Hildesheim) · Journal of Machine Learning Research 11:2487-2531 · 2010</sub>

Identifies HUBNESS as a distinct aspect of the curse of dimensionality.

*Took:* In high-dimensional embedding spaces, a few generic, near-mean points hijack top-k results for unrelated queries, and points far from the mean become effectively unretrievable.

*Changed:* Explains the specific failure we would hit if we naively embedded every one of the ~300-400 historical card transactions per customer.

*Doesn't apply where:* From 2010 and studied on classical feature vectors and early text representations, not modern contrastively-trained sentence embeddings, which are explicitly optimised for uniformity/alignment and are...

**[Text2SQL is Not Enough: Unifying AI and Databases with TAG](https://arxiv.org/abs/2408.14717)**  
<sub>Asim Biswal, Liana Patel, Siddarth Jha, Amog Kamsetty, Shu Liu, Joseph E. Gonzalez, Carlos Guestrin, Matei Zaharia (UC Berkeley Sky Computing Lab, Stanford) · arXiv / CIDR 2025; TAG-Bench released by Berkeley Sky Lab · 2024</sub>

Argues that Text2SQL covers only questions expressible in relational algebra and that RAG covers only questions answerable by point lookups of one or a few records — both are strict special cases of a general Table-Augmented Generation model (query synthesis -> database execution -> LM generation ov...

*Took:* The decomposition itself: exact/aggregate/set-shaped subquestions go to the database engine, and only the semantic residue goes to the LM.

*Changed:* Defines the split between our feature store and our vector index, with named owners per query type.

*Doesn't apply where:* TAG-Bench is a static warehouse benchmark over BIRD; it has no notion of streaming, out-of-order arrival, or point-in-time correctness, all of which are central for us.

<details>
<summary>Also read (9)</summary>

- [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://arxiv.org/abs/2409.04701) (2024) — A training-free way to give a short, individually-meaningless span the context of its neighbourhood — the cheaper cousin of Anthropic's Contextual Ret...
- [ACORN: Performant and Predicate-Agnostic Search Over Vector Embeddings and Structured Data](https://arxiv.org/abs/2403.04871) (2024) — The explicit statement that post-filtering is unsafe for selective predicates — you can silently get an empty or unrepresentative result set — and tha...
- [Qdrant documentation: Optimizer (vacuum optimizer, deleted_threshold, vacuum_min_vector_number)](https://qdrant.tech/documentation/concepts/optimizer/) (2026 (docs, continuously updated)) — The universal pattern across vector stores: delete is logical, reclamation is a background rebuild with a threshold, and 'update' is really delete+ins...
- [Weaviate documentation: Vector index configuration (tombstones, cleanupIntervalSeconds, async indexing)](https://docs.weaviate.io/weaviate/config-refs/indexing/vector-index) (2026 (docs, continuously updated)) — Two operational facts: (1) deleted vectors keep participating in graph traversal until a background job runs, so 'deleted' evidence can still be retri...
- [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172) (2024) — Position in the prompt is a real, measurable accuracy lever, and long contexts do not make retrieval quality irrelevant.
- [NevIR: Negation in Neural Information Retrieval](https://arxiv.org/abs/2305.07614) (2024) — Retrieval systems have essentially no representation of 'not' / 'absent' / 'stopped'.
- [FreshDiskANN: A Fast and Accurate Graph-Based ANN Index for Streaming Similarity Search](https://arxiv.org/abs/2105.09613) (2021) — The two-tier hot/cold pattern — a small mutable index in front of a large stable index, with periodic merge — and the specific finding that deletes mu...
- [TempRetriever: Fusion-based Temporal Dense Passage Retrieval for Time-Sensitive Questions](https://arxiv.org/abs/2502.21024) (2025) — Two things: (1) time-aware negatives — training/evaluating against distractors that are topically right but temporally wrong is the discriminative tas...
- [Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) (2024) — The core insight is that a chunk embedded without its surrounding context is unretrievable, and that the cheap fix is to write the context INTO the te...

</details>


## Calibration and human oversight

The evaluation grades timeliness in both directions, so 'low confidence' has to genuinely mean low. That makes calibration a scored property rather than a nicety, and the literature on LLM confidence is not reassuring.

**[LangGraph Human-in-the-Loop / Interrupts (official documentation)](https://docs.langchain.com/oss/python/langgraph/interrupts)**  
<sub>LangChain, Inc. · docs.langchain.com (LangGraph OSS Python docs) · accessed 2026</sub>

interrupt() pauses graph execution mid-node and surfaces any JSON-serializable payload to the caller; execution resumes via Command(resume=value), and that value becomes the return value of the original interrupt() call.

*Took:* Durable pause-on-thread as the HITL mechanism, plus the node-replay idempotency hazard that most implementations get wrong.

*Changed:* Concrete implementation of hitl_status. escalated = an open interrupt on that customer's thread; human_approved / human_rejected / human_modified = the resume payload, recorded with reviewer id and timestamp in the trace log.

*Doesn't apply where:* Vendor documentation, not peer-reviewed, and the API surface has changed across LangGraph versions (interrupt()/Command superseded the older NodeInterrupt and interrupt_before patterns) — pin the vers...

**[Selective Classification Can Magnify Disparities Across Groups](https://openreview.net/pdf?id=_3tRq40EohT)**  
<sub>Erik Jones, Shiori Sagawa, Pang Wei Koh, Ananya Kumar, Percy Liang (Stanford) · ICLR 2021 · 2021</sub>

Across five vision and NLP datasets, abstaining on low-confidence inputs raises average accuracy while simultaneously widening the accuracy gap between groups — and, counter-intuitively, increasing abstention can DECREASE accuracy on the worst-off group in absolute terms.

*Took:* Abstention is not a free safety mechanism. Always report risk–coverage per subgroup, never only in aggregate.

*Changed:* ARGUES AGAINST the comfortable assumption that 'when unsure, escalate' automatically makes the system safer.

*Doesn't apply where:* Demonstrated on vision and NLP classifiers with explicit group annotations and known spurious correlations.

**[The flaws of policies requiring human oversight of government algorithms](https://arxiv.org/abs/2109.05067)**  
<sub>Ben Green (University of Michigan / Harvard) · Computer Law & Security Review, vol. 45 · 2022</sub>

Surveys 41 real policies mandating human oversight of government algorithms and identifies two structural flaws.

*Took:* A HITL checkpoint is not by itself a safety argument. If the reviewer cannot realistically detect the error class, the checkpoint launders risk rather than reducing it.

*Changed:* ARGUES AGAINST the competition's own framing — the rubric asks for 'HITL approval checkpoints', and the tempting response is to sprinkle approve/reject gates everywhere and call the system safe.

*Doesn't apply where:* Argues about government/public-sector algorithms in legally consequential settings (benefits, policing, sentencing) where the asymmetry of power is severe.

**[Calibrated Language Models Must Hallucinate](https://arxiv.org/abs/2311.14648)**  
<sub>Adam Tauman Kalai (OpenAI), Santosh S. Vempala (Georgia Tech) · STOC 2024 (56th Annual ACM Symposium on Theory of Computing) · 2023 (arXiv) / 2024 (STOC)</sub>

Proves a statistical lower bound: a pretrained LM satisfying a calibration condition appropriate for generative models MUST hallucinate 'arbitrary' facts — facts whose veracity is not determined by the training data — at a rate close to the Good–Turing monofact rate, i.e.

*Took:* Calibration is not a free good and is not the same as correctness. A perfectly calibrated generator still emits confident falsehoods about rare one-off facts.

*Changed:* ARGUES AGAINST treating 'make the model calibrated' as the whole uncertainty story.

*Doesn't apply where:* A theoretical result about pretraining-time facts under a specific calibration definition; it does not bound hallucination for a retrieval-grounded system where the facts are in context.

<details>
<summary>Also read (9)</summary>

- [Detecting hallucinations in large language models using semantic entropy](https://doi.org/10.1038/s41586-024-07421-0) (2024) — Cluster-then-entropy: measure disagreement in meaning-space.
- [Consistent Estimators for Learning to Defer to an Expert](https://arxiv.org/abs/2006.01862) (2020) — Deferral should be conditioned on expected human accuracy on that instance, not purely on model uncertainty. Model the expert, not just yourself.
- [Transaction monitoring in anti-money laundering: A qualitative analysis and points of view from industry](https://doi.org/10.1016/j.future.2024.05.027) (2024) — Hard sector-specific evidence that threshold-based rule engines in exactly our domain run at 90–95% false positives, plus the constraint that regulato...
- [The Foundations of Cost-Sensitive Learning](https://dblp.org/rec/conf/ijcai/Elkan01.html) (2001) — One threshold per action, derived from that action's own cost ratio. Costs set the operating point; accuracy does not.
- [Conformal Prediction Sets Improve Human Decision Making](https://arxiv.org/abs/2401.13744) (2024) — Human-subjects RCT evidence that handing a person a variable-size SET beats handing them a ranked top-k, because set size is itself a legible uncertai...
- [To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-assisted Decision-making](https://arxiv.org/abs/2102.09692) (2021) — Concrete UI mechanics that convert a rubber stamp into a real review: commit-first, on-demand disclosure, deliberate friction.
- [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170) (2021) — The online alpha update rule with step size gamma. Coverage is maintained by feedback, not by an i.i.d. assumption nobody in a live stream can honour.
- [Does automation bias decision-making?](https://doi.org/10.1006/ijhc.1999.0252) (1999) — Omission bias is the residual risk training cannot fix: humans stop looking for what the system does not surface.
- [Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners (KnowNo)](https://arxiv.org/abs/2307.01928) (2023) — The exact singleton-versus-set escalation rule for an LLM agent, and the reframing of 'when to ask a human' as coverage-constrained help-rate minimiza...

</details>


## Guardrails and observability

The non-negotiables are 15% of the score and the problem statement is explicit that a prompt instruction does not count as a guardrail. I read for the difference between a control that is enforced and one that is merely requested.

**[Equal Credit Opportunity Act / Regulation B, 12 CFR 1002.2(z) 'prohibited basis' and 1002.4(b) discouragement](https://www.consumerfinance.gov/rules-policy/regulations/1002/2/)**  
<sub>Consumer Financial Protection Bureau · eCFR / consumerfinance.gov · current</sub>

'Prohibited basis' means race, colour, religion, national origin, sex, marital status, or age (where the applicant can contract); the fact that all or part of the applicant's income derives from any public assistance program;

*Took:* That marital status, age and public-assistance income are themselves prohibited bases — so inferring them and then acting on them is the regulated act, not just denying credit on t...

*Changed:* This is the sharpest domain-specific guardrail we can show, and it maps onto the enum one-to-one. marriage_or_relationship_change is marital status. retirement_transition and elder_vulnerability_or_scam_risk are age proxies.

**[Regulation (EU) 2024/1689 (EU AI Act): Article 12 record-keeping, Article 14 human oversight, Article 86 right to explanation, Annex III point 5(b)](https://artificialintelligenceact.eu/article/14/)**  
<sub>European Parliament and Council of the EU · artificialintelligenceact.eu / EUR-Lex · 2024</sub>

Annex III point 5(b) classifies as high-risk 'AI systems intended to be used to evaluate the creditworthiness of natural persons or establish their credit score, with the exception of AI systems used for the purpose of detecting financial fraud'.

*Took:* Three hard design constraints — logging is an obligation not a feature; oversight must be effective and built-in, not nominal;

*Changed:* Note the carve-out precisely: fraud detection is exempt from the credit-scoring high-risk category, so our compliance_fraud_hold path sits outside Annex III 5(b) while the personalized_offer path, if it gates a credit product, sits inside it.

**[Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657)**  
<sub>Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, Bhavya Chopra, Rishabh Tiwari, Kurt Keutzer, Aditya Parameswaran, Dan Klein, Kannan Ramchandran, Matei Zaharia, Joseph E. Gonzalez, Ion Stoica (UC Berkeley) · arXiv (ICML 2025) · 2025</sub>

Builds MAST, a taxonomy of 14 failure modes in three categories, from 150 traces across 7 multi-agent frameworks, validated with inter-annotator agreement kappa = 0.88, then scaled to 1600+ annotated traces.

*Took:* The measured failure distribution as a prior on where to spend instrumentation, especially that 'disobey task specification' is the single largest mode and that verification failur...

*Changed:* The problem statement mandates critique-refiner and debate patterns, and MAST says those patterns' own dominant failure is Incorrect/Incomplete Verification. So: instrument one counter per MAST mode as a first-class metric.

**[The Algorithmic Foundations of Differential Privacy](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf)**  
<sub>Cynthia Dwork and Aaron Roth · Foundations and Trends in Theoretical Computer Science, Now Publishers · 2014</sub>

Defines (epsilon, delta)-differential privacy: a randomized mechanism M is (eps, delta)-DP if for all adjacent datasets differing in one record and all output sets S, Pr[M(D) in S] <= exp(eps) * Pr[M(D') in S] + delta.

*Took:* Composition and a privacy budget: repeated querying is the leak, and the protection applies to aggregate release, not to per-record operational use.

*Changed:* Included deliberately to draw a boundary rather than to add machinery. DP is the wrong tool for the per-customer operational path — we must act on this individual's $500 ER visit, and noising it destroys exactly the small signal the dataset is built around, given that magnitude is anti-correlated with signal value.

<details>
<summary>Also read (9)</summary>

- [NIST SP 800-162: Guide to Attribute Based Access Control (ABAC) Definition and Considerations](https://csrc.nist.gov/pubs/sp/800/162/upd2/final) (2014 (updated 2019)) — The PDP/PEP/PIP split, and environment-condition attributes (time, threat level) as legitimate inputs to an access decision.
- [GDPR Article 22 and CJEU Case C-634/21 (SCHUFA Holding — Scoring)](https://gdpr-info.eu/art-22-gdpr/) (2016 / 2023) — The SCHUFA holding that an upstream inferred score counts as the automated decision when a downstream human leans on it — 'a human clicks approve' is...
- [Consumer Financial Protection Circular 2023-03: Adverse action notification requirements and the proper use of the CFPB's sample forms provided in Regulation B](https://www.consumerfinance.gov/compliance/circulars/circular-2023-03-adverse-action-notification-requirements-and-the-proper-use-of-the-cfpbs-sample-forms-provided-in-regulation-b/) (2023) — The explicit rejection of the 'black-box' excuse, and the warning about reasons derived from behavioural surveillance data that no standard reason cod...
- [Cryptographic Support for Secure Logs on Untrusted Machines](https://www.usenix.org/legacy/publications/library/proceedings/sec98/full_papers/schneier/schneier.pdf) (1998) — The hash-chained, forward-secure append-only log with a remote verifier — tamper-evidence obtained from a cheap primitive rather than from a database...
- [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837) (2025) — Plan-Then-Execute and Action-Selector, because our action space is already a closed enum of six values — the strongest patterns are the ones that are...
- [Defeating Prompt Injections by Design (CaMeL)](https://arxiv.org/abs/2503.18813) (2025) — Capability tags attached to data values and propagated through computation, with the policy check at the tool-call boundary — security that is a prope...
- [Guardrails AI — open-source input/output validation framework for LLMs](https://guardrailsai.com/docs/concepts/validators) (2026) — Per-validator failure policy (reask / filter / refrain / exception) as an explicit design axis, and Pydantic-typed output as the enforcement mechanism...
- [OpenTelemetry Semantic Conventions for Generative AI — Agent and Tool Spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) (2026) — Use the standard attribute names verbatim so traces are portable across Langfuse, Phoenix and any OTLP backend — and note the Development status hones...
- [NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails](https://arxiv.org/abs/2310.10501) (2023) — The five-position rail taxonomy (input / dialog / retrieval / execution / output) as an architectural placement scheme, and the principle that the pol...

</details>


## Banking

I know the agent side better than I know retail banking, so I spent real time here. The most useful thing I read was not technical at all — it was the regulatory material on inferring sensitive circumstances from spending, which is directly why one row of my policy matrix exists.

**[FG21/1: Guidance for firms on the fair treatment of vulnerable customers](https://www.fca.org.uk/publication/finalised-guidance/fg21-1.pdf)**  
<sub>UK Financial Conduct Authority · FCA Finalised Guidance, published 23 February 2021 · 2021</sub>

I read the PDF. Defines a vulnerable customer as someone who, due to their personal circumstances, is especially susceptible to harm, and frames vulnerability as a spectrum of risk driven by 4 key drivers: Health (conditions affecting day-to-day tasks), Life events (bereavement, job loss, relationsh...

*Took:* Three operational rules: the 4-driver taxonomy as a state ontology; the prohibition on labelling the customer;

*Changed:* Maps almost one-to-one onto our state enum and is the regulatory citation behind our hardest guardrail.

*Doesn't apply where:* UK-specific and principles-based rather than prescriptive; it gives no detection thresholds and does not directly regulate automated inference.

**Advisory on Elder Financial Exploitation (FIN-2022-A002)**  
<sub>US FinCEN (Financial Crimes Enforcement Network) · FinCEN Advisory, 15 June 2022 · 2022</sub>

I read the PDF. Reports over 62,000 EFE-related SARs filed in 2020 covering an estimated $3.4 billion in suspicious transactions (up from $2.6bn in 2019), rising to over 72,000 SARs in 2021. Lists 12 behavioural and 12 financial red flags.

*Took:* A ready-made, authoritative, deterministic rule set for elder_vulnerability_or_scam_risk, plus the meta-rule that single flags are not determinative and must be scored against the...

*Changed:* Supplies the concrete feature list for the elder-risk detector and justifies co-occurrence scoring rather than any-single-rule firing. It fits the measured dataset unusually well: 'uncharacteristic nonpayment for services' is our cancelled standing instructions;

*Doesn't apply where:* US AML/BSA framing aimed at SAR filing, not customer-care outreach — acting on these flags means escalation and investigation, NOT contacting the customer with an offer, and in a real bank a SAR carri...

**EU AI Act, Article 5(1)(b) - prohibited exploitation of vulnerabilities**  
<sub>European Parliament and Council; European Commission Guidelines on Prohibited AI Practices (February 2025) · Regulation (EU) 2024/1689, Official Journal of the EU; prohibitions applicable from 2 February 2025 · 2024 (in force 2025)</sub>

Prohibits placing on the market, putting into service or using an AI system that exploits any vulnerability of a person or group due to their AGE, DISABILITY, or a SPECIFIC SOCIAL OR ECONOMIC SITUATION, with the objective or EFFECT of materially distorting their behaviour in a manner that causes or...

*Took:* A statutory, intent-independent prohibition covering exactly this system's worst failure mode: detect financial distress, then offer a credit product.

*Changed:* Turns the central guardrail from a policy preference into a legal boundary and extends it beyond medical hardship.

*Doesn't apply where:* Verified via multiple law-firm and Commission-guidance summaries, not the Official Journal text; the regulation number 2024/1689 is from memory — verify before printing.

**[Feature engineering strategies for credit card fraud detection](https://doi.org/10.1016/j.eswa.2015.12.030)**  
<sub>Alejandro Correa Bahnsen, Djamila Aouada, Aleksandar Stojanovic, Bjorn Ottersten (SnT, University of Luxembourg) · Expert Systems With Applications, 51:134-142 · 2016</sub>

I read the full PDF. States plainly that raw per-transaction features (amount, time, entry mode) give an incomplete profile of the customer, and builds two better families. (1) Transaction aggregation (after Whitrow et al.

*Took:* The exact recipe: multi-window (1h to 168h) counts and sums grouped by merchant category and counterparty, plus circular-statistics time-of-day novelty — and the measured fact that...

*Changed:* This is the concrete feature spec for the swarm's numeric agent and the direct antidote to the dataset's amount-magnitude trap.

*Doesn't apply where:* It is a cost-sensitive FRAUD paper; the savings metric is fraud-specific and does not transfer to life-event inference, and the von Mises time-of-day feature may not vary meaningfully in our data.

**Case C-184/20, OT v Vyriausioji tarnybines etikos komisija**  
<sub>Court of Justice of the European Union (Grand Chamber) · CJEU judgment, 1 August 2022 · 2022</sub>

The Grand Chamber held that publishing the name of a declarant's spouse/cohabitee/partner alongside their own is processing of special categories of personal data under Article 9(1) GDPR, because it is liable INDIRECTLY to reveal sexual orientation.

*Took:* Inference IS processing. Deriving a sensitive category from non-sensitive inputs creates special category data carrying the full Article 9 burden — there is no 'we only used ordina...

*Changed:* The legal reason our medical_hardship guardrail must be architectural rather than advisory, and it reaches past the action layer: the moment the pipeline computes a health-related state from pharmacy/diagnostics categories, it CREATES Article 9 data, which must be (a) access-controlled by role at the data layer (support/care rol...

*Doesn't apply where:* Verified through multiple law-firm analyses of the judgment rather than the judgment text itself, so quote the 'comparison or deduction' formulation as reported.

**[ADBench: Anomaly Detection Benchmark](https://arxiv.org/abs/2206.09426)**  
<sub>Songqiao Han, Xiyang Hu, Hailiang Huang, Minqi Jiang, Yue Zhao (SUFE / CMU) · NeurIPS 2022, Datasets and Benchmarks Track · 2022</sub>

Benchmarks 30 anomaly detection algorithms over 57 datasets along three axes (level of supervision, anomaly type, robustness to noise/corruption).

*Took:* Do not build a generic unsupervised detector and hope. Encode a small number of TYPED detectors matched to named anomaly shapes, and exploit the handful of labels you have.

*Changed:* The second argument against the obvious approach. Our first instinct — throw an isolation forest or autoencoder at the transaction stream — is precisely what ADBench says has no reliable advantage, and on this dataset it would rank the $12,000 tuition wire top because amount is the highest-variance feature.

*Doesn't apply where:* ADBench uses tabular i.i.d. benchmark data, not temporally dependent event streams, so its conclusions about specific algorithms are weaker evidence here than its meta-conclusion about supervision.

<details>
<summary>Also read (9)</summary>

- [Credit Card Fraud Detection: A Realistic Modeling and a Novel Learning Strategy](https://doi.org/10.1109/TNNLS.2017.2736643) (2018) — The architectural admission that information available at decision time is systematically different from information available later, and that the ans...
- [How Companies Learn Your Secrets](https://www.nytimes.com/2012/02/19/magazine/shopping-habits.html) (2012) — Two lessons in one story: (a) a basket of low-value, high-novelty purchases beats any single large transaction as a life-event detector — structurally...
- [Did Target Really Predict a Teen's Pregnancy? The Inside Story](https://www.kdnuggets.com/2014/05/target-predict-teen-pregnancy-inside-story.html) (2014) — Epistemic hygiene about the field's favourite parable: the most-cited evidence for 'transaction data reveals pregnancy with high precision' is an unve...
- [Data Spotlight: Suspicious Activity Reports on Elder Financial Exploitation - Issues and Trends](https://files.consumerfinance.gov/f/documents/cfpb_suspicious-activity-reports-elder-financial-exploitation_report.pdf) (2019) — The magnitude asymmetry (tens of thousands of dollars per incident) and the documented detection-to-intervention gap.
- [Leveraging fine-grained transaction data for customer life event predictions](https://doi.org/10.1016/j.dss.2019.113232) (2020) — The counterparty pseudo-social-network feature — a new recurring counterparty is itself a feature — and their framing of rarity as the central modelli...
- [Scalable and Weakly Supervised Bank Transaction Classification](https://arxiv.org/abs/2305.18430) (2023) — The anchor-then-generalise pattern — deterministic high-precision rules produce labels and a learned model generalises beyond them — and the principle...
- ["Counting Your Customers" the Easy Way: An Alternative to the Pareto/NBD Model](https://doi.org/10.1287/mksc.1040.0098) (2005) — A latent-attrition posterior from recency and frequency alone, personalised by the customer's own baseline rate — silence scored against what THIS cus...
- [A Novel Profit Maximizing Metric for Measuring Classification Performance of Customer Churn Prediction Models](https://doi.org/10.1109/TKDE.2012.50) (2013) — Evaluation must encode asymmetric costs, and the model should output an optimal targeting fraction rather than a tuned probability cutoff.
- [CoLES: Contrastive Learning for Event Sequences with Self-Supervision](https://arxiv.org/abs/2002.08232;) (2022) — A single learned customer-state vector built from raw event sequences and reusable across tasks — and specifically the augmentation premise that two w...

</details>
