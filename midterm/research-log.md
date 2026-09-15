# Research log

Akshat Agrawal · IIT (BHU) Varanasi · Mid-term submission · 15 September 2026
Problem statement: Agentic Customer 360 — Proactive Intervention Desk

This is a running list of what I have read while working out how to build this, with a note on each about what I actually took from it and which decision it changed. It is not a bibliography. Where something talked me out of an idea I have said so, because those were the more useful reads.

Two things about how this is organised. The five entries at the top of each section are the ones that genuinely shaped a decision, and I have written those up properly. Everything under the collapsible heading is material I have skimmed, or have queued to read properly before the end term, and I have kept those notes to one line so the list does not pretend to more depth than it has. Total is 179 items, of which roughly 40 are load-bearing.

One caveat I want to be upfront about. A fair amount of the genuinely useful material here is vendor engineering writing (Zep, Anthropic, LangChain, Chroma) rather than peer-reviewed work, because the practical literature on agent memory and coordination is about two years old and the people building these systems are publishing on blogs. I have tried to flag where a source has a commercial interest in its own conclusion, particularly the benchmark numbers.

---

## Agent memory

The problem statement asks three questions about memory it refuses to answer for you: when is an old memory relevant, how do you stop customers bleeding into each other, and who decides a flag has expired. These are the papers I used to answer them. The short version of what I concluded: the taxonomy everyone quotes (working / episodic / semantic) comes from cognitive architecture, not from LLM work, and the LLM-era systems are mostly arguing about retrieval scoring and invalidation.

**[OWASP Top 10 for LLM Applications 2025 — LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/)**  
<sub>OWASP GenAI Security Project · genai.owasp.org · 2025</sub>

Names the failure modes of vector stores used as agent memory: cross-context information leaks in multi-tenant environments (embeddings from one user group retrieved for another group's query), embedding inversion attacks (recovering substantial source text from stored vectors), data/knowledge-source poisoning (intentional or accidental),…

*What I took:* 'Permission-aware vector store with strict logical partitioning' plus 'immutable retrieval logs' as the concrete standard to build and document against.

*Where it lands in my design:* This is the citable standard behind the role-based-data-access-at-the-data-layer and PII requirements. Design consequences: (1) one namespace/collection per customer with tenant_id also embedded in metadata and enforced as a pre-filter, so a similarity search can never physically range across customers — do not rely on post-retrieval filtering, which is where cross-tenant leaks occur;

*Where I think it doesn't apply:* OWASP is a risk checklist, not a mechanism: it tells you the boundary must exist but not how to enforce it when one agent legitimately spans customers (e.g. a fraud-ring detector), which is a real tension in this system.

**[Is Mem0 Really SOTA in Agent Memory? (Lies, Damn Lies, and Statistics)](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/)**  
<sub>Daniel Chalef, Preston Rasmussen (Zep AI) · Zep engineering blog · 2025</sub>

A point-by-point rebuttal of Mem0's LoCoMo evaluation. Claims three implementation errors in Mem0's Zep baseline: modelling both conversation participants as a single user, non-standard timestamp handling that broke temporal reasoning, and sequential rather than concurrent search.

*What I took:* Two things: memory-system leaderboard numbers are not trustworthy, and on any corpus that fits in context, a memory architecture must justify itself on something other than accuracy.

*Where it lands in my design:* Do not justify the memory layer with 'it beats full context'. For this problem, 300-400 history + 70-120 live events per customer plausibly FITS in a long context window, so a stuff-everything baseline is a real competitor and a judge will ask about it.

*Where I think it doesn't apply:* ARGUES AGAINST THE OBVIOUS APPROACH, and is itself conflicted: Zep is a direct commercial competitor rebutting a competitor's paper, and the corrected numbers are self-reported and unreplicated.

**[Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956)**  
<sub>Preston Rasmussen, Pavlo Paliychuk, Travis Beauvais, Jack Ryan, Daniel Chalef (Zep AI) · arXiv (Graphiti is the open-source engine) · 2025</sub>

Graphiti maintains a three-tier graph: episode subgraph (raw, non-lossy messages/JSON), semantic entity subgraph (extracted entities and relation edges), and community subgraph (clustered higher-level summaries).

*What I took:* Bi-temporal edge invalidation with four timestamps, and the non-lossy episode tier sitting underneath the derived tiers.

*Where it lands in my design:* This is the single most load-bearing borrowing for this system. The deliverable's as_of_time IS a bi-temporal query, and the dataset forces it: a card transaction arriving with ingestion_time 48h after event_time means a checkpoint already emitted covered a period whose facts have since changed. Store event_time as valid-time and ingestion_time as transaction-time;

*Where I think it doesn't apply:* The benchmark numbers are vendor-published and the DMR margin (94.8 vs 93.4) is within plausible noise for a 500-item benchmark.

**[How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior](https://arxiv.org/abs/2505.16067)**  
<sub>Zidi Xiong et al. (8 authors; Harvard and collaborators) · arXiv (May 2025, revised Oct 2025) · 2025</sub>

Identifies and names 'experience-following': when a task input is highly similar to the input of a retrieved memory record, the agent's output is highly similar to that record's output — an agent copies precedent rather than reasoning. This produces two compounding failure modes.

*What I took:* The core warning: an unfiltered episodic bank of past decisions actively degrades an agent, and the degradation is proportional to bank size.

*Where it lands in my design:* This is a hard constraint on how past checkpoint decisions are reused. With ~8% signal density, roughly 9 in 10 stored precedents say inferred_state=no_significant_event, action=no_action.

*Where I think it doesn't apply:* ARGUES AGAINST THE OBVIOUS APPROACH. The instinctive design — 'store every past checkpoint decision and retrieve similar ones' — is shown here to get worse over time.

**[Reflections of the Environment in Memory (and the ACT-R base-level activation equation)](https://doi.org/10.1111/j.1467-9280.1991.tb00174.x)**  
<sub>John R. Anderson, Lael J. Schooler (Carnegie Mellon) · Psychological Science, Vol. 2, pp. 396-408 · 1991</sub>

Rational analysis of memory: the probability that an item will be NEEDED again is a predictable function of how frequently and how recently it has been encountered, and human forgetting curves match the statistics of the environment (they measured New York Times headlines, parental speech to children, and email sender patterns — all show…

*What I took:* Activation is an estimate of P(needed now) derived from the observed inter-arrival statistics of the item itself.

*Where it lands in my design:* This is the principled answer to the hardest fact in the dataset: absence emits no event. Fit a per-item arrival model from history and let the DEFICIT in activation be the trigger. Salary_credit with 12 observations at exactly 14-day spacing has a very tight arrival distribution;

*Where I think it doesn't apply:* ACT-R decay is calibrated on human recall latency in laboratory tasks; d=0.5 has no principled meaning for financial event streams and must be refit per signal family.

<details>
<summary>Skimmed or queued for the end term (14 more)</summary>

- [The TSQL2 Temporal Query Language / Bitemporal Conceptual Data Model](https://people.cs.aau.dk/~csj/Thesis/pdf/chapter12.pdf) — <sub>Richard T. Snodgrass (ed.), Christian S. Jensen et al. · 1995</sub>  
  Transaction time is append-only by construction. That property, not the query syntax, is the thing to steal.
- [Memory Injection Attacks on LLM Agents via Query-Only Interaction (MINJA)](https://arxiv.org/abs/2503.03704) — <sub>Shen Dong, Shaochen Xu, Pengfei He, Yige Li, Jiliang Tang, T · 2025</sub>  
  The threat model: any customer-authored text that the agent reflects on and stores becomes an injection channel, and the poison is authored by the agent itself, so content filters on the inp…
- [Sleep-time Compute: Beyond Inference Scaling at Test-time](https://arxiv.org/abs/2504.13171) — <sub>Kevin Lin, Charlie Snell, Yu Wang, Charles Packer, Sarah Woo · 2025</sub>  
  Move all context-dependent work off the latency path, and amortise it across many queries over the same context.
- [Extending Cognitive Architecture with Episodic Memory](https://web.eecs.umich.edu/~soar/sitemaker/docs/pubs/AAAI2007_NuxollLaird_ver14(final).pdf) — <sub>Andrew M. Nuxoll, John E. Laird (University of Michigan, Soa · 2007</sub>  
  Automatic, non-selective episode capture plus cue-based partial-match retrieval and forward replay — the agent queries with a partial situation description, not a text string.
- [The Power of Noise: Redefining Retrieval for RAG Systems](https://arxiv.org/abs/2401.14887) — <sub>Florin Cuconasu, Giovanni Trappolini, Federico Siciliano, Si · 2024</sub>  
  Near-miss retrieval is worse than no retrieval. Optimise the evidence set for discriminativeness, not for similarity.
- [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://arxiv.org/abs/2410.10813) — <sub>Di Wu, Hongwei Wang, Wenhao Yu, Yuwei Zhang, Kai-Wei Chang,  · 2024/2025</sub>  
  The knowledge-updates and abstention categories, and the finding that long-context models fail them badly.
- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) — <sub>Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith R · 2023</sub>  
  The three-term additive retrieval score and the accumulated-importance reflection trigger are the right shape. But the *definitions* of both terms must be replaced for this domain.
- [HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models](https://arxiv.org/abs/2405.14831) — <sub>Bernal Jiménez Gutiérrez, Yiheng Shu, Yu Gu, Michihiro Yasun · 2024</sub>  
  Single-shot graph-spreading retrieval with IDF-style node specificity, replacing multi-round agentic retrieval.
- [Cognitive Architectures for Language Agents (CoALA)](https://arxiv.org/abs/2309.02427) — <sub>Theodore R. Sumers, Shunyu Yao, Karthik Narasimhan, Thomas L · 2023</sub>  
  The insistence that memory WRITES are actions in the same action space as tool calls, and therefore are proposable, evaluatable, selectable and loggable.
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — <sub>Wujiang Xu, Zujie Liang, Kai Mei, Hang Gao, Juntao Tan, Yong · 2025</sub>  
  Link generation at write time, and the principle that a later event can legitimately change the meaning of an earlier one.
- [MemoryBank: Enhancing Large Language Models with Long-Term Memory](https://arxiv.org/abs/2305.10250) — <sub>Wanjun Zhong, Lianghong Guo, Qiqi Gao, He Ye, Yanlin Wang (S · 2024</sub>  
  The use-strengthens-retention counter: S += 1 on recall is a cheap, deterministic, fully explainable consolidation rule that needs no LLM call and produces a number you can put in the trace…
- [A Survey on the Memory Mechanism of Large Language Model based Agents](https://arxiv.org/abs/2404.13501) — <sub>Zeyu Zhang, Xiaohe Bo, Chen Ma, Rui Li, Xu Chen, Quanyu Dai, · 2024</sub>  
  The write / manage / read decomposition, and the observation that memory is almost never evaluated directly.
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413) — <sub>Prateek Chhikara, Dev Khant, Saket Aryan, Taranjeet Singh, D · 2025</sub>  
  The explicit four-way ADD/UPDATE/DELETE/NOOP reconciliation step against retrieved neighbours — memory writes are a decision, not an append.
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) — <sub>Charles Packer, Sarah Wooders, Kevin Lin, Vivian Fang, Shish · 2023</sub>  
  Two ideas: (1) a small, agent-writable core-memory block that holds the live hypothesis, and (2) the memory-pressure interrupt — a deterministic runtime signal, not an LLM decision, that for…

</details>


## Evidence accumulation and belief revision

This is the section that changed the design. I went looking for how other fields represent a belief that accumulates over time and can be withdrawn, because that is what a confidence_band actually is, and found that sequential analysis and truth maintenance have been solving it since the 1940s and 1970s respectively.

**[Use time travel (LangGraph documentation)](https://docs.langchain.com/oss/python/langgraph/use-time-travel)**  
<sub>LangChain / LangGraph · docs.langchain.com · 2026 (accessed)</sub>

Verified by fetching the page. Every super-step writes a checkpoint (a StateSnapshot of values, metadata, and the next nodes) keyed by thread_id; get_state_history(config) returns the thread's checkpoints in reverse chronological order, each carrying config['configurable']['checkpoint_id'].

*What I took:* Fork-from-past-checkpoint with the original branch preserved, plus interrupt/Command(resume=...) as the HITL primitive — both already persisted and inspectable.

*Where it lands in my design:* Concrete implementation of 'recompute the posterior as of any past timestamp'. Run one thread per (customer, hypothesis) and checkpoint at every ingested event.

*Where I think it doesn't apply:* The docs are explicit that replay RE-EXECUTES LLM calls nondeterministically, so a naive re-run will not reproduce the original decision even without the late event — which destroys the audit story.

**[The Neural Hawkes Process: A Neurally Self-Modulating Multivariate Point Process](https://arxiv.org/abs/1612.09328;)**  
<sub>Hongyuan Mei, Jason Eisner · Advances in Neural Information Processing Systems 30 (NIPS 2017) · 2017</sub>

Models K event types with intensities λ_k(t) = f_k(w_k · h(t)) driven by a continuous-time LSTM whose hidden state decays between events toward a learned steady state and jumps at each event.

*What I took:* The −∫λ(s)ds term. Absence is evidence with a computable likelihood, and it accrues continuously without any event arriving.

*Where it lands in my design:* This is the answer to the hardest measured fact in the brief: 'absence is the strongest signal and emits no event.' Model each customer as a multivariate point process over {card_txn, login, salary_credit, support_ticket, ...}.

*Where I think it doesn't apply:* Training a neural Hawkes needs far more data than one customer's 300-event history — per-customer fitting is hopeless.

**[Differential Dataflow](https://www.cidrdb.org/cidr2013/Papers/CIDR13_Paper111.pdf;)**  
<sub>Frank McSherry, Derek G. Murray, Rebecca Isaacs, Michael Isard · CIDR 2013 (6th Biennial Conference on Innovative Data Systems Research) · 2013</sub>

Represents collections as multisets with INTEGER multiplicities (negative multiplicity = retraction) and stores, instead of successive full collections, the DIFFERENCES indexed by multi-dimensional, PARTIALLY ORDERED logical timestamps. The value of a collection at time t is the sum of all differences at times ≤ t.

*What I took:* Retraction-as-negative-multiplicity over partially-ordered timestamps, and 'current value = sum of differences ≤ t' as the recomputation rule.

*Where it lands in my design:* This is the formal model for the append-only, retractable ledger — and it is the strongest architectural-novelty claim available in this sub-domain. Use a two-dimensional timestamp (event_time, ingestion_time), which is a partial order, not a sequence.

*Where I think it doesn't apply:* Differential dataflow's incrementality theorems assume the computation is expressible in its operator algebra (map/filter/join/group/iterate) over commutative-group-valued differences. LLM-produced evidence is not;

**[An assumption-based TMS](https://doi.org/10.1016/0004-3702(86)90080-9;)**  
<sub>Johan de Kleer · Artificial Intelligence, Vol. 28(2), pp. 127–162 · 1986</sub>

Replaces justification manipulation (Doyle's JTMS) with ASSUMPTION-SET manipulation. Every derived node carries a LABEL: the set of minimal, consistent ENVIRONMENTS (sets of primitive assumptions) from which it follows.

*What I took:* Label conclusions with their minimal supporting assumption sets, and make retraction a set operation rather than a recomputation.

*Where it lands in my design:* This is the architecture of the retractable evidence ledger, and it is where the genuine novelty claim lives. Every inferred_state emission is labelled with the minimal set of events that support it.

*Where I think it doesn't apply:* ATMS label computation is worst-case exponential in the number of assumptions — with 70–120 live events treating each as an assumption is tractable, but do not scale this to 400 history events.

**[Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback](https://arxiv.org/abs/2305.14975)**  
<sub>Katherine Tian, Eric Mitchell, Allan Zhou, Archit Sharma, Rafael Rafailov, Huaxiu Yao, Chelsea Finn, Christopher D. Manning · EMNLP 2023 · 2023</sub>

Verified by fetching the arXiv abstract page. Evaluates how to extract confidence from RLHF-fine-tuned LLMs.

*What I took:* Never read confidence off token logprobs from an RLHF'd model; elicit it verbally, and calibrate the verbal output post hoc.

*Where it lands in my design:* Decides the LLM's job description in this architecture, which is the key guardrail question. The LLM does NOT produce confidence_band and does NOT produce a posterior.

*Where I think it doesn't apply:* ARGUES AGAINST the convenient design. The result is about factual QA calibration, not about likelihood-ratio elicitation over financial event streams, and coarse verbal LRs are still systematically overconfident at the extremes.

<details>
<summary>Skimmed or queued for the end term (17 more)</summary>

- [Developing Time-Oriented Database Applications in SQL](https://www2.cs.arizona.edu/~rts/tdbbook.pdf) — <sub>Richard T. Snodgrass · 1999</sub>  
  The two independent time axes and the rule that transaction time is immutable — which is what makes 'what did we believe at time X' answerable at all.
- [A logic for default reasoning](https://doi.org/10.1016/0004-3702(80)90014-4;) — <sub>Raymond Reiter · 1980</sub>  
  The explicit 'in the absence of information to the contrary' operator, and normal defaults as the well-behaved fragment that is guaranteed to have an extension.
- [Royal Statistical Society: Statement regarding statistical issues in the Sally Clark case](https://rss.org.uk/RSS/media/File-library/Membership/Sections/2020/Sally-Clark-RSS-statement-2001.pdf) — <sub>Royal Statistical Society (news release, 23 October 2001) · 2001</sub>  
  A concrete, catastrophic, real-world instance of the exact failure mode our design risks: independent multiplication of correlated evidence producing confidence that is wrong by orders of ma…
- [On the logic of theory change: Partial meet contraction and revision functions](https://philpapers.org/rec/ALCOTL-2) — <sub>Carlos E. Alchourrón, Peter Gärdenfors, David Makinson · 1985</sub>  
  The distinction between contraction and revision, minimal change as an explicit criterion, and the fact that which beliefs survive a retraction is a matter of a declared PREFERENCE ORDER — i…
- [Event History (Temporal Platform Documentation)](https://docs.temporal.io/encyclopedia/event-history/event-history-go) — <sub>Temporal Technologies · 2026 (accessed)</sub>  
  The determinism boundary: deterministic orchestration replayed from an immutable log, with every nondeterministic effect recorded as a replayable activity result.
- [E-values: Calibration, combination, and applications](https://arxiv.org/abs/1912.06116;) — <sub>Vladimir Vovk, Ruodu Wang · 2021</sub>  
  The dependence-robust merge rule: average, don't multiply, when detectors may be correlated. And the calibrator, for folding in legacy p-value-shaped detectors.
- [Durable Functions: Semantics for Stateful Serverless](https://doi.org/10.1145/3485510;) — <sub>Sebastian Burckhardt, Chris Gillum, David Justo, Konstantino · 2021</sub>  
  The three-abstraction decomposition, and specifically the ENTITY: a durable, single-threaded-per-key piece of state that is addressed by name and does not need to be explicitly created or su…
- [A Simple View of the Dempster-Shafer Theory of Evidence and Its Implication for the Rule of Combination](https://doi.org/10.1609/aimag.v7i2.542;) — <sub>Lotfi A. Zadeh · 1986</sub>  
  That conflict normalisation is not a technicality — under high conflict it produces confidently wrong answers, and the magnitude of the error grows with disagreement.
- [Reasoning with belief functions: An analysis of compatibility](https://doi.org/10.1016/0888-613X(90)90013-R;) — <sub>Judea Pearl · 1990</sub>  
  The provability-vs-truth distinction, and the specific finding that belief functions handle CONDITIONAL, defeasible rules badly.
- [The Cost of Accumulating Evidence in Perceptual Decision Making](https://www.jneurosci.org/content/32/11/3612) — <sub>Jan Drugowitsch, Rubén Moreno-Bote, Anne K. Churchland, Mich · 2012</sub>  
  Time-varying (collapsing) decision boundaries derived from an explicit cost-of-waiting, solved by dynamic programming over the belief state.
- [Weight of Evidence: A Brief Survey](https://www.cs.tufts.edu/~nr/cs257/archive/jack-good/weight-of-evidence.pdf) — <sub>I. J. Good · 1985</sub>  
  The additive log-odds ledger and its human-facing unit. A decision is a sum of signed, individually-attributable contributions, each of which can be displayed next to the event that produced…
- [Sequential Tests of Statistical Hypotheses](https://doi.org/10.1214/aoms/1177731118) — <sub>Abraham Wald · 1945</sub>  
  The three-way outcome and the fact that the two thresholds are derived from declared error budgets rather than tuned. 'Keep watching' is a first-class decision, not a fallback.
- A Mathematical Theory of Evidence — <sub>Glenn Shafer · 1976</sub>  
  The Bel/Pl interval and m(Θ): a representation in which 'I have no information' is not the same as 'the evidence is balanced'.
- [The physics of optimal decision making: A formal analysis of models of performance in two-alternative forced-choice tasks](https://www.mrcbndu.ox.ac.uk/sites/default/files/pdf_files/PsychRev06.pdf) — <sub>Rafal Bogacz, Eric Brown, Jeff Moehlis, Philip Holmes, Jonat · 2006</sub>  
  That the speed/accuracy trade-off has a computable optimum given a reward function — and that leaky (forgetting) accumulators are a principled family, not a hack.
- [Game-Theoretic Statistics and Safe Anytime-Valid Inference](https://arxiv.org/abs/2210.01948;) — <sub>Aaditya Ramdas, Peter Grünwald, Vladimir Vovk, Glenn Shafer · 2023</sub>  
  The betting/wealth framing: each incoming event is a bet against 'nothing is happening to this customer', and the accumulated wealth IS the evidence. Continuous monitoring is free.
- [Time-uniform, nonparametric, nonasymptotic confidence sequences](https://arxiv.org/abs/1810.08240;) — <sub>Steven R. Howard, Aaditya Ramdas, Jon McAuliffe, Jasjeet Sek · 2021</sub>  
  Nonparametric, nonasymptotic time-uniform boundaries — usable when you only have an empirical baseline, not a likelihood.
- [Safe Testing](https://arxiv.org/abs/1906.07801;) — <sub>Peter Grünwald, Rianne de Heide, Wouter M. Koolen · 2024 (arXiv 2019)</sub>  
  E-values as the ledger's unit of account, and GROW/Kelly as the principled way to set how aggressively each detector bets.

</details>


## Streaming, event time, and detecting change

I came in assuming streaming was the boring plumbing part. It is not. The Dataflow paper in particular reframed the whole late-event problem for me, and CEP absence patterns turned out to be the literature for the single hardest fact in the dataset.

**[MillWheel: Fault-Tolerant Stream Processing at Internet Scale](http://www.vldb.org/pvldb/vol6/p1033-akidau.pdf)**  
<sub>Tyler Akidau, Alex Balikov, Kaya Bekiroğlu, Slava Chernyak, Josh Haberman, Reuven Lax, Sam McVeety, Daniel Mills, Paul Nordstrom, Sam Whittle (Google) · Proceedings of the VLDB Endowment (PVLDB) 6(11):1033-1044 · 2013</sub>

I read the PDF. Defines the low watermark of computation A recursively as min(oldest work of A, low watermark of C for all C that output to A), seeded by injectors.

*What I took:* Absence is detected by a persistent per-key timer that fires on watermark advance, plus the watermark as the thing that distinguishes 'delayed' from 'never happened'.

*Where it lands in my design:* This is the single most load-bearing citation for the two hardest dataset facts.

**[The Dataflow Model: A Practical Approach to Balancing Correctness, Latency, and Cost in Massive-Scale, Unbounded, Out-of-Order Data Processing](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf)**  
<sub>Tyler Akidau, Robert Bradshaw, Craig Chambers, Slava Chernyak, Rafael J. Fernández-Moctezuma, Reuven Lax, Sam McVeety, Daniel Mills, Frances Perry, Eric Schmidt, Sam Whittle (Google) · Proceedings of the VLDB Endowment (PVLDB) 8(12):1792-1803 · 2015</sub>

Decomposes stream processing into four orthogonal questions: WHAT is computed, WHERE in event time (windowing), WHEN in processing time results are materialized (triggers), and HOW later refinements relate to earlier ones (accumulation mode). I read the PDF directly.

*What I took:* The trigger/accumulation separation, and specifically Accumulating & Retracting: a decision emitted at a checkpoint is a *pane*, not a final answer, and a late arrival legitimately retracts and supers…

*Where it lands in my design:* This is the backbone of the checkpoint emitter. Each checkpoint emission is a pane keyed by (customer_id, as_of_time) with an explicit revision counter and a supersedes pointer, not an immutable verdict.

**[FlinkCEP — Complex Event Processing for Flink (official documentation)](https://nightlies.apache.org/flink/flink-docs-master/docs/libs/cep/)**  
<sub>Apache Flink project · nightlies.apache.org/flink/flink-docs-master/docs/libs/cep/ · 2026 (master docs)</sub>

I fetched this page. notNext() is strict non-contiguity (the negative event must directly succeed); notFollowedBy() is relaxed non-contiguity (the partial match is discarded even if other events intervene).

*What I took:* The absence idiom (notFollowedBy + within) and, more importantly, the explicit admission that FlinkCEP DROPS late events rather than revising completed matches.

*Where it lands in my design:* Argues against the obvious choice. FlinkCEP is the natural off-the-shelf engine for our patterns, but its late-element policy is fatal for this dataset: the 48-hour-late card transaction would land behind the watermark and be silently discarded, so the decision it should have revised never gets revised.

**[A Large-Scale Comparison of Concept Drift Detectors](https://doi.org/10.1016/j.ins.2018.04.014)**  
<sub>Roberto Souto Maior de Barros, Silas Garrido Teixeira de Carvalho Santos · Information Sciences 451-452:348-370 · 2018</sub>

Empirically compares 14 concept-drift-detector configurations (including DDM, EDDM, Page-Hinkley, ADWIN and variants) across a large set of artificial datasets with two base learners (Naive Bayes and Hoeffding Tree), measuring accuracy, runtime, false-alarm rate, miss rate and distance to the true drift point.

*What I took:* Detector sensitivity is not a virtue; a simple periodic baseline is a real competitor and must be measured against.

*Where it lands in my design:* The deliberate counter-argument to our own architecture. Before shipping a stack of CUSUM + ADWIN + BOCPD detectors, benchmark them against a dumb baseline: re-evaluate the customer at every checkpoint with a fixed-window feature diff and no detector at all.

**[Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)**  
<sub>Ryan Prescott Adams, David J. C. MacKay · arXiv (stat.ML), 19 Oct 2007 · 2007</sub>

Maintains a posterior over the run length r_t (time since the last changepoint) via a message-passing recursion with the transition prior P(r_t | r_{t-1}) = H(r_{t-1}+1) if r_t = 0, else 1 - H(r_{t-1}+1), where H is the hazard function (a constant hazard gives a geometric prior over run lengths).

*What I took:* A run-length posterior that yields a calibrated probability of 'a change happened k steps ago', plus a Poisson/gamma-conjugate model of event INTER-ARRIVAL times.

*Where it lands in my design:* Two uses, both central. (1) The coal-mine-disaster setup — changepoint detection on Poisson inter-arrival times — is structurally identical to our churn scenario: model inter-activity gaps whose historical p90 is 0-1 days, and the run-length posterior gives a principled, continuously updating probability that the arrival rate changed, which maps directly to the confidence_band, without needing an…

<details>
<summary>Skimmed or queued for the end term (20 more)</summary>

- [Sequential Tests of Statistical Hypotheses (the SPRT)](https://doi.org/10.1214/aoms/1177731118) — <sub>Abraham Wald · 1945</sub>  
  The three-way decision with an explicit CONTINUE region, and boundaries that are functions of the error rates you are willing to accept.
- [Esper EPL Reference: Event Patterns (timer:interval with 'and not' for absence detection)](http://esper.espertech.com/release-7.0.0/esper-reference/html/event_patterns.html) — <sub>EsperTech · 2017 (product ongoing)</sub>  
  The canonical absence idiom: absence is expressed as a timer firing conjoined with the negation of the expected event — the timer supplies the event that the absence itself cannot.
- [Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress](https://arxiv.org/abs/2009.13807) — <sub>Renjie Wu, Eamonn J. Keogh · 2021 (arXiv 2020)</sub>  
  Always establish the one-line baseline first, and audit your own evaluation set for triviality, density realism and label quality before believing any result.
- [A Survey on Concept Drift Adaptation](https://doi.org/10.1145/2523813) — <sub>João Gama, Indrė Žliobaitė, Albert Bifet, Mykola Pechenizkiy · 2014</sub>  
  The real-vs-virtual drift distinction, the Page-Hinkley forgetting factor, and the insistence on reporting detection delay separately from false-alarm rate.
- [Sequence Pattern Query Processing over Out-of-Order Event Streams](https://ieeexplore.ieee.org/document/4812454/) — <sub>Mo Liu, Ming Li, Denis Golovnya, Elke A. Rundensteiner, Kaja · 2009</sub>  
  The aggressive-plus-compensation strategy, and the specific warning that NEGATION patterns are the ones late events corrupt.
- [Learning from Time-Changing Data with Adaptive Windowing (ADWIN / ADWIN2)](https://www.cs.upc.edu/~gavalda/papers/adwin06.pdf) — <sub>Albert Bifet, Ricard Gavaldà · 2007</sub>  
  The window length itself becomes the detector output — no magic lookback constant — with provable error bounds and O(log W) cost.
- [Watermarks in Stream Processing Systems: Semantics and Comparative Analysis of Apache Flink and Google Cloud Dataflow](https://doi.org/10.14778/3476311.3476389) — <sub>Tyler Akidau, Edmon Begoli, Slava Chernyak, Fabian Hueske, K · 2021</sub>  
  The input-watermark / output-watermark distinction per stage, and the explicit framing of a watermark as a claim about completeness that each stage must independently justify.
- [Efficient Pattern Matching over Event Streams (SASE+)](https://doi.org/10.1145/1376616.1376634) — <sub>Jagrati Agrawal, Yanlei Diao, Daniel Gyllstrom, Neil Immerma · 2008</sub>  
  The selection-strategy axis — the same pattern means very different things under strict contiguity vs skip-till-any-match — and the separation of negation and windowing from the core automat…
- [An Evaluation of Change Point Detection Algorithms (Turing Change Point Benchmark)](https://arxiv.org/abs/2003.06222) — <sub>Gerrit J. J. van den Burg, Christopher K. I. Williams (The A · 2020</sub>  
  Ground truth for changepoints is inherently fuzzy in time, so evaluate with a tolerance margin and treat annotator disagreement as signal, not noise.
- [Exploiting Punctuation Semantics in Continuous Data Streams](https://doi.org/10.1109/TKDE.2003.1198390) — <sub>Peter A. Tucker, David Maier, Tim Sheard, Leonidas Fegaras · 2003</sub>  
  Punctuations are the general form of which watermarks are a special case (a punctuation on the timestamp attribute), and the keep invariant is the formal licence to garbage-collect state.
- [Consistency and Completeness: Rethinking Distributed Stream Processing in Apache Kafka](https://doi.org/10.1145/3448016.3457556) — <sub>Guozhang Wang, Lei Chen, Ayusman Dikshit, Jason Gustafson, B · 2021</sub>  
  Consistency and completeness are orthogonal dials, and exactly-once transactions buy you the first and nothing at all of the second.
- [You Cannot Have Exactly-Once Delivery (and the Redux follow-up)](https://bravenewgeek.com/you-cannot-have-exactly-once-delivery/) — <sub>Tyler Treat · 2015 (Redux 2017)</sub>  
  Push correctness into idempotent, keyed side effects instead of buying a delivery guarantee that does not extend past the engine boundary.
- [Lightweight Asynchronous Snapshots for Distributed Dataflows](https://arxiv.org/abs/1506.08603) — <sub>Paris Carbone, Gyula Fóra, Stephan Ewen, Seif Haridi, Kostas · 2015</sub>  
  State-only snapshots with barrier alignment: the recoverable unit is the operator's state, and replay from a durable log reconstructs everything else.
- [Out-of-Order Processing: A New Architecture for High-Performance Stream Systems](http://www.vldb.org/pvldb/vol1/1453890.pdf) — <sub>Jin Li, Kristin Tufte, Vladislav Shkapenyuk, Vassilis Papadi · 2008</sub>  
  Never sort the stream to make it look ordered; propagate progress indicators and let each operator decide independently when it has seen enough.
- [Continuous Inspection Schemes (the CUSUM chart)](https://doi.org/10.1093/biomet/41.1-2.100) — <sub>E. S. Page · 1954</sub>  
  Accumulate small deviations over time with a slack parameter, rather than thresholding any single observation.
- [Complex Event Recognition in the Big Data Era: A Survey](https://doi.org/10.1007/s00778-019-00557-w) — <sub>Nikos Giatrakos, Elias Alevizos, Alexander Artikis, Antonios · 2020</sub>  
  The taxonomy as a selection framework, and the observation that logic-based CER handles negation and uncertain input more naturally than automata do.
- [Streams and Tables: Two Sides of the Same Coin (the Dual Streaming Model)](https://doi.org/10.1145/3242153.3242155) — <sub>Matthias J. Sax, Guozhang Wang, Matthias Weidlich, Johann-Ch · 2018</sub>  
  Model derived customer state as a table that is the fold of the event stream, with results defined by logical (event-time) order, so out-of-order arrival changes the path but not the final a…
- [Revision Processing in a Stream Processing Engine: A High-Level Design](https://www.researchgate.net/publication/4234746_Revision_Processing_in_a_Stream_Processing_Engine_A_High-Level_Design) — <sub>Esther Ryvkina, Anurag S. Maskey, Mitch Cherniack, Stan Zdon · 2006</sub>  
  An explicit revision tuple type (insert/delete/replace + reference to the superseded output), and the engineering decision of how deep a revision history to retain.
- [Cayuga: A General Purpose Event Monitoring System](https://www.cidrdb.org/cidr2007/papers/cidr07p47.pdf) — <sub>Alan Demers, Johannes Gehrke, Biswanath Panda, Mirek Riedewa · 2007</sub>  
  Composable algebra plus automaton-instance indexing and explicit garbage collection of stale partial matches.
- [Questioning the Lambda Architecture](https://www.oreilly.com/radar/questioning-the-lambda-architecture/) — <sub>Jay Kreps (LinkedIn/Confluent) · 2014</sub>  
  Replay-from-log as the reprocessing primitive, and the insistence that there be exactly one implementation of the decision logic.

</details>


## Multi-agent coordination

I deliberately read the sceptics here before the enthusiasts, because the problem statement hands you a roster of ten agents and it would be easy to build all ten without asking whether any of them earn their keep. The honest reading is that multi-agent systems have a poor track record and a specific set of documented failure modes, and that the patterns which do work are narrower than the marketing suggests.

**[Constitutional AI: Harmlessness from AI Feedback](https://arxiv.org/abs/2212.08073)**  
<sub>Yuntao Bai, Saurav Kadavath, Sandipan Kundu, Amanda Askell, Jackson Kernion, Jared Kaplan et al. (Anthropic) · arXiv (Anthropic) · 2022</sub>

Two phases. Supervised phase: sample a response from the initial model, prompt the SAME model to critique its response against a randomly sampled written principle from a short 'constitution', then revise; fine-tune on the revised responses.

*What I took:* Principle-conditioned critique. The critic is never asked 'is this good?' — it is asked 'does this violate principle P?', with P drawn from an explicit written list.

*Where it lands in my design:* Write an explicit, versioned Intervention Constitution for the desk and make every guardrail check a principle-conditioned critique with the principle ID logged in the trace.

**[Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)**  
<sub>Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, Bhavya Chopra, Rishabh Tiwari, Kurt Keutzer, Aditya Parameswaran, Dan Klein, Kannan Ramchandran, Matei Zaharia, Joseph E. Gonzalez, Ion Stoica (UC Berkeley) · arXiv; NeurIPS 2025 Datasets & Benchmarks Track · 2025</sub>

MAST taxonomy built from 150 hand-annotated traces (inter-annotator kappa = 0.88) then scaled to MAST-Data, 1600+ annotated traces across 7 MAS frameworks and GPT-4/Claude 3/Qwen2.5/CodeLlama.

*What I took:* A ready-made failure-mode checklist to instrument against, and the empirical fact that ~79% of MAS failures are design/communication, not model capability. Also: prompt patches buy ~15% and then stop.

*Where it lands in my design:* Use MAST's 14 modes as named span-level assertions in our trace log — this converts the 15% 'non-negotiables' score into something measurable. Concretely: FM-1.5 (unaware of termination) -> hard round cap of 2 on the critique-refine loop with a deterministic tie-break;

**[When to use multi-agent systems (and when not to)](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)**  
<sub>Cara Phillips, with Paul Chen, Andy Schumeister, Brad Abrams, Theo Chu (Anthropic / Claude blog) · claude.com/blog · 2026</sub>

Names exactly three situations where multiple agents beat one: (1) context protection — isolating information that pollutes a single window; (2) parallelization — covering an information space larger than one context; (3) specialization — focused toolsets improving tool-selection reliability.

*What I took:* A three-question admission test for every agent you are tempted to add, and the rule to decompose by CONTEXT BOUNDARY not by problem type.

*Where it lands in my design:* Justify each agent in the design doc against the three criteria, and decompose by data-source context boundary (card/transaction stream; recurring-commitment registry; channel-activity/absence; support-tickets-and-comms/NLP) rather than by state label.

**[ChatDev: Communicative Agents for Software Development](https://arxiv.org/abs/2307.07924)**  
<sub>Chen Qian, Wei Liu, Hongzhang Liu, Nuo Chen, Yufan Dang, Jiahao Li, Cheng Yang, Weize Chen, Yusheng Su, Xin Cong, Juyuan Xu, Dahai Li, Zhiyuan Liu, Maosong Sun (Tsinghua / OpenBMB) · ACL 2024 · 2023</sub>

Two named mechanisms. CHAT CHAIN: the waterfall (design, coding, testing) is decomposed into a chain of atomic two-agent subtasks, each with exactly one instructor and one assistant, so that at any moment only two agents are talking and the chain — not a manager — determines what gets communicated next.

*What I took:* Communicative dehallucination — an agent's legal move set must include 'I need more evidence' — and the chain-of-dyads structure that keeps the active conversation at exactly two participants.

*Where it lands in my design:* 'Insufficient evidence' must be a first-class return value for every specialist, not a forced classification. This is directly what the dataset rewards: low confidence with 'not enough signal yet' is the CORRECT answer at early checkpoints, and a system whose agents are obliged to produce a state will hallucinate medical_hardship off one $125 pharmacy charge.

**[MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352)**  
<sub>Sirui Hong, Mingchen Zhuge, Jiaqi Chen, Xiawu Zheng, Yuheng Cheng, Ceyao Zhang, Jinlin Wang, Zili Wang, Steven Ka Shing Yau, Zijuan Lin, Liyang Zhou, Chenyu Ran, Lingfeng Xiao, Chenglin Wu, Jürgen Schmidhuber · arXiv (v7, Nov 2024); widely cited as ICLR 2024 · 2023</sub>

Encodes human Standardised Operating Procedures into prompt sequences so agents with role expertise (Product Manager, Architect, Project Manager, Engineer, QA) run an assembly line over a task.

*What I took:* Typed artefacts over free-text messages, plus role-scoped subscription to a shared pool instead of broadcast.

*Where it lands in my design:* Our evidence ledger IS the shared message pool, and every specialist publishes a typed Finding {finding_type, event_ids[], baseline_stats, effect_size, confidence, agent_id, timestamp} — never prose.

<details>
<summary>Skimmed or queued for the end term (17 more)</summary>

- [LLMs Get Lost In Multi-Turn Conversation](https://arxiv.org/abs/2505.06120) — <sub>Philippe Laban, Hiroaki Hayashi, Yingbo Zhou, Jennifer Nevil · 2025</sub>  
  Incremental information delivery is itself the failure cause, and early wrong commitments are unrecoverable inside a growing conversation.
- [Handoffs (OpenAI Agents SDK documentation)](https://openai.github.io/openai-agents-python/handoffs/) — <sub>OpenAI · 2025</sub>  
  The mechanics of the required 'handoff' pattern, and the exact location of the footgun: the convenience filter that strips tool calls is precisely what discards the evidence the receiving ag…
- [CAMEL: Communicative Agents for "Mind" Exploration of Large Language Model Society](https://arxiv.org/abs/2303.17760) — <sub>Guohao Li, Hasan Abed Al Kader Hammoud, Hani Itani, Dmitrii  · 2023</sub>  
  The four named conversational pathologies — they are the ones that appear in any free-form two-agent loop, and each maps onto a cheap deterministic detector.
- [AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation](https://arxiv.org/abs/2308.08155) — <sub>Qingyun Wu, Gagan Bansal, Jieyu Zhang, Yiran Wu, Beibin Li,  · 2023</sub>  
  The human_input_mode taxonomy and the speaker-selection abstraction. Round-robin is one concrete speaker-selection policy, not an architecture — that reframing is the honest one.
- [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents) — <sub>Walden Yan (Cognition AI) · 2025</sub>  
  Writes stay single-threaded; extra agents contribute intelligence, not actions. Pass full traces (the evidence ledger), not summaries, across any boundary.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — <sub>Jeremy Hadfield, Barry Zhang, Kenneth Lien, Florian Scholz,  · 2025</sub>  
  Orchestrator-worker with parallel, context-isolated, READ-ONLY workers plus one synthesising lead.
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) — <sub>Lianmin Zheng, Wei-Lin Chiang, Ying Sheng, Siyuan Zhuang, Zh · 2023</sub>  
  The 80%-equals-human-agreement number that legitimises LLM judging for OFFLINE evaluation, paired with the named biases that disqualify a naive judge from the online decision path.
- [CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing](https://arxiv.org/abs/2305.11738) — <sub>Zhibin Gou, Zhihong Shao, Yeyun Gong, Yelong Shen, Yujiu Yan · 2023</sub>  
  The critique channel must be a tool call that returns a verdict the generator cannot argue with. Verification, not deliberation.
- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents) — <sub>Erik Schluntz and Barry Zhang (Anthropic) · 2024</sub>  
  The evaluator-optimizer precondition — iterative refinement is only justified where evaluation criteria are CLEAR — and the voting flavour of parallelization as the cheap alternative to deba…
- [Stop Overvaluing Multi-Agent Debate — We Must Rethink Evaluation and Embrace Model Heterogeneity](https://arxiv.org/abs/2502.08788) — <sub>Hangfan Zhang, Zhiyao Cui, Jianhao Chen, Xinrun Wang, Qiaosh · 2025</sub>  
  If you run more than one reasoner, make them DIFFERENT models (or at minimum different prompts/temperatures/evidence views). Homogeneous multi-agent is self-consistency with extra latency.
- [Meta-Prompting: Enhancing Language Models with Task-Agnostic Scaffolding](https://arxiv.org/abs/2401.12954) — <sub>Mirac Suzgun (Stanford), Adam Tauman Kalai (OpenAI) · 2024</sub>  
  Orchestrator-worker implemented with ONE model and stateless, context-isolated experts — and the demonstrated beat over multi-persona prompting, which is the closest cousin of debate.
- [Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?](https://arxiv.org/abs/2402.18272) — <sub>Qineng Wang, Zihao Wang, Ying Su, Hanghang Tong, Yangqiu Son · 2024</sub>  
  Discussion is a substitute for demonstrations, not a supplement to them. If you can write good few-shot exemplars, you have already captured the discussion gain for one forward pass.
- [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651) — <sub>Aman Madaan, Niket Tandon, Prakhar Gupta, Skyler Hallinan, L · 2023</sub>  
  The three-role decomposition with a hard requirement that feedback be actionable and name a specific deficiency — and the stopping rule (stop when feedback says no further change needed or a…
- [Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs](https://arxiv.org/abs/2311.17371) — <sub>Andries Smit, Paul Duckworth, Nathan Grinsztajn, Thomas D. B · 2023</sub>  
  Two things: (1) self-consistency is the baseline debate must beat, and usually doesn't, at lower cost;
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171) — <sub>Xuezhi Wang, Jason Wei, Dale Schuurmans, Quoc Le, Ed Chi, Sh · 2022</sub>  
  Majority vote over k independently sampled rationales — and crucially the vote SPREAD as a free, calibrated confidence signal.
- [Improving Factuality and Reasoning in Language Models through Multiagent Debate](https://arxiv.org/abs/2305.14325) — <sub>Yilun Du, Shuang Li, Antonio Torralba, Joshua B. Tenenbaum,  · 2023</sub>  
  The mechanism worth borrowing is not the debate but the cross-exposure step: showing an agent a differing rationale changes its answer. Also the honest cost model N x R with context growth.
- [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798) — <sub>Jie Huang, Xinyun Chen, Swaroop Mishra, Huaixiu Steven Zheng · 2023</sub>  
  Critique-refiner loops are only worth running when the critic has access to something the generator did not: a tool, a ground-truth lookup, a deterministic check, or a different evidence vie…

</details>


## Retrieval freshness

Most of what I read here talked me out of things. The instinct is to put everything in a vector database; for a stream of near-identical card transactions that is close to the worst available choice, and several of these sources say so directly.

**[PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models](https://arxiv.org/abs/2402.07867)**  
<sub>Wei Zou, Runpeng Geng, Binghui Wang, Jinyuan Jia (Penn State, Illinois Institute of Technology) · USENIX Security 2025 (arXiv preprint Feb 2024) · 2025</sub>

First systematic knowledge-corruption attack on RAG. Formalises poisoning as an optimisation with two simultaneous objectives — a retrieval condition (the injected text must be retrieved for the target query) and a generation condition (once retrieved, it must induce the attacker's chosen answer) — and shows that injecting a tiny number o…

*What I took:* The threat model: any text in the retrieval corpus that a non-trusted party can influence is an injection vector, and the attack works precisely because the retriever is doing its job — it retrieves t…

*Where it lands in my design:* Forces a trust boundary inside our own corpus, which is easy to miss because the data looks internal. Our event stream contains free-text the CUSTOMER authors or influences: support ticket bodies, chat transcripts, merchant description strings.

*Where I think it doesn't apply:* PoisonedRAG attacks an open-domain QA corpus an adversary can write into at will (e.g. a wiki); our corpus is a bank's own event store with far tighter write paths, so the literal attack does not apply.

**[Feast documentation: Point-in-time joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins)**  
<sub>Feast (Linux Foundation / Tecton originated) · docs.feast.dev · 2026 (docs, continuously updated)</sub>

Feature values are stored as timestamped time series. A point-in-time-correct join takes an entity dataframe with per-row event_timestamp and, for each row, scans BACKWARD in event time from that row's timestamp up to the feature view's TTL, taking the latest feature value at or before it — and the TTL is relative to each row's own timest…

*What I took:* The two-clock as-of join, and specifically the created-timestamp filter as the operational mechanism for reproducing past state in the presence of late-arriving corrections.

*Where it lands in my design:* This is the concrete implementation of bi-temporal correctness at the feature layer, and it is where our evaluation integrity lives. Every aggregate feeding a checkpoint — historical healthcare transaction count (0 of 221), salary_credit inter-arrival statistics, activity-gap p90 (0-1 days), active standing-instruction set — is computed by an as-of join at as_of_time with BOTH clocks applied.

*Where I think it doesn't apply:* Vendor/OSS documentation rather than a paper, and the exact flag name is version-specific. Feast is also built for batch training-data generation and low-latency online serving of precomputed features;

**[Hubs in Space: Popular Nearest Neighbors in High-Dimensional Data](https://jmlr.org/papers/v11/radovanovic10a.html)**  
<sub>Miloš Radovanović, Alexandros Nanopoulos, Mirjana Ivanović (University of Novi Sad, University of Hildesheim) · Journal of Machine Learning Research 11:2487-2531 · 2010</sub>

Identifies HUBNESS as a distinct aspect of the curse of dimensionality.

*What I took:* In high-dimensional embedding spaces, a few generic, near-mean points hijack top-k results for unrelated queries, and points far from the mean become effectively unretrievable.

*Where it lands in my design:* Explains the specific failure we would hit if we naively embedded every one of the ~300-400 historical card transactions per customer.

*Where I think it doesn't apply:* From 2010 and studied on classical feature vectors and early text representations, not modern contrastively-trained sentence embeddings, which are explicitly optimised for uniformity/alignment and are less hub-prone than the space…

**[Text2SQL is Not Enough: Unifying AI and Databases with TAG](https://arxiv.org/abs/2408.14717)**  
<sub>Asim Biswal, Liana Patel, Siddarth Jha, Amog Kamsetty, Shu Liu, Joseph E. Gonzalez, Carlos Guestrin, Matei Zaharia (UC Berkeley Sky Computing Lab, Stanford) · arXiv / CIDR 2025; TAG-Bench released by Berkeley Sky Lab · 2024</sub>

Argues that Text2SQL covers only questions expressible in relational algebra and that RAG covers only questions answerable by point lookups of one or a few records — both are strict special cases of a general Table-Augmented Generation model (query synthesis -> database execution -> LM generation over the result).

*What I took:* The decomposition itself: exact/aggregate/set-shaped subquestions go to the database engine, and only the semantic residue goes to the LM.

*Where it lands in my design:* Defines the split between our feature store and our vector index, with named owners per query type.

*Where I think it doesn't apply:* TAG-Bench is a static warehouse benchmark over BIRD; it has no notion of streaming, out-of-order arrival, or point-in-time correctness, all of which are central for us.

**[Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://arxiv.org/abs/2409.04701)**  
<sub>Michael Günther, Isabelle Mohr, Daniel James Williams, Bo Wang, Han Xiao (Jina AI) · arXiv (v3 Jul 2025) · 2024</sub>

Inverts the usual pipeline. Instead of splitting a document and embedding each chunk independently, a long-context embedding model encodes the ENTIRE document's tokens in one forward pass, and chunking is applied afterwards to the token embeddings, just before mean pooling — so each chunk's pooled vector has already attended to the whole…

*What I took:* A training-free way to give a short, individually-meaningless span the context of its neighbourhood — the cheaper cousin of Anthropic's Contextual Retrieval, with no per-chunk LLM call.

*Where it lands in my design:* Offers the right encoding strategy for an event WINDOW rather than an event. A single record ('internal_transfer_out, 10000') is ambiguous in isolation;

*Where I think it doesn't apply:* Evaluated on natural-language documents with a Jina long-context encoder; gains depend on the model actually having a usable long context and on chunks being genuinely context-dependent.

<details>
<summary>Skimmed or queued for the end term (16 more)</summary>

- [Weaviate documentation: Vector index configuration (tombstones, cleanupIntervalSeconds, async indexing)](https://docs.weaviate.io/weaviate/config-refs/indexing/vector-index) — <sub>Weaviate · 2026 (docs, continuously updated)</sub>  
  Two operational facts: (1) deleted vectors keep participating in graph traversal until a background job runs, so 'deleted' evidence can still be retrieved for up to cleanupIntervalSeconds;
- [ACORN: Performant and Predicate-Agnostic Search Over Vector Embeddings and Structured Data](https://arxiv.org/abs/2403.04871) — <sub>Liana Patel, Peter Kraft, Carlos Guestrin, Matei Zaharia (St · 2024</sub>  
  The explicit statement that post-filtering is unsafe for selective predicates — you can silently get an empty or unrepresentative result set — and that predicate satisfaction should be enfor…
- [Qdrant documentation: Optimizer (vacuum optimizer, deleted_threshold, vacuum_min_vector_number)](https://qdrant.tech/documentation/concepts/optimizer/) — <sub>Qdrant · 2026 (docs, continuously updated)</sub>  
  The universal pattern across vector stores: delete is logical, reclamation is a background rebuild with a threshold, and 'update' is really delete+insert — meaning an updated record changes…
- [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172) — <sub>Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Mic · 2024</sub>  
  Position in the prompt is a real, measurable accuracy lever, and long contexts do not make retrieval quality irrelevant.
- [FreshDiskANN: A Fast and Accurate Graph-Based ANN Index for Streaming Similarity Search](https://arxiv.org/abs/2105.09613) — <sub>Aditi Singh, Suhas Jayaram Subramanya, Ravishankar Krishnasw · 2021</sub>  
  The two-tier hot/cold pattern — a small mutable index in front of a large stable index, with periodic merge — and the specific finding that deletes must be repaired by edge-reconnection, not…
- [NevIR: Negation in Neural Information Retrieval](https://arxiv.org/abs/2305.07614) — <sub>Orion Weller, Dawn Lawrie, Benjamin Van Durme (Johns Hopkins · 2024</sub>  
  Retrieval systems have essentially no representation of 'not' / 'absent' / 'stopped'. Any requirement expressed as a negation must be computed, not retrieved.
- [Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) — <sub>Anthropic · 2024</sub>  
  The core insight is that a chunk embedded without its surrounding context is unretrievable, and that the cheap fix is to write the context INTO the text before indexing — plus the concrete f…
- [TempRetriever: Fusion-based Temporal Dense Passage Retrieval for Time-Sensitive Questions](https://arxiv.org/abs/2502.21024) — <sub>Abdelrahman Abdallah, Bhawna Piryani, Jonas Wallat, Avishek  · 2025</sub>  
  Two things: (1) time-aware negatives — training/evaluating against distractors that are topically right but temporally wrong is the discriminative task that matters;
- [The Faiss Library](https://arxiv.org/abs/2401.08281) — <sub>Matthijs Douze, Alexandr Guzhva, Chengqi Deng, Jeff Johnson, · 2024</sub>  
  The explicit training prerequisite for IVF/PQ indexes, and the fact that 'delete' and 'update' are not first-class operations in a library that is otherwise the default choice.
- [FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation](https://arxiv.org/abs/2310.03214) — <sub>Tu Vu, Mohit Iyyer, Xuezhi Wang, Noah Constant, Jerry Wei, J · 2024</sub>  
  Three transferable mechanics: (1) an explicit freshness taxonomy over question types, (2) evidence cards carrying an explicit date field alongside the text, (3) the empirical rule that ~10-1…
- [Retrieval-Augmented Generation for Large Language Models: A Survey](https://arxiv.org/abs/2312.10997) — <sub>Yunfan Gao, Yun Xiong, Xinyu Gao, Kangxiang Jia, Jinliu Pan, · 2023 (v5 2024)</sub>  
  The paradigm ladder as a positioning device, and the pre-/post-retrieval decomposition as a checklist for which optimisations we have actually implemented.
- [On the Theoretical Limitations of Embedding-Based Retrieval](https://arxiv.org/abs/2508.21038) — <sub>Orion Weller, Michael Boratko, Iftekhar Naim, Jinhyuk Lee (G · 2025</sub>  
  The failure is architectural, not a training deficiency: no amount of better embedding training fixes a query whose correct answer is an arbitrary subset of a large set of mutually similar d…
- [Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf) — <sub>Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher (Un · 2009</sub>  
  A one-line, parameter-light, score-normalisation-free way to combine a dense ranking and a BM25 ranking — and the specific reason it works: using ranks sidesteps the incomparability of cosin…
- [BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models](https://arxiv.org/abs/2104.08663) — <sub>Nandan Thakur, Nils Reimers, Andreas Rücklé, Abhishek Srivas · 2021</sub>  
  Never ship a dense-only retriever into a domain the embedding model was not trained on, and always keep BM25 in the first stage as the robustness floor.
- [SPFresh: Incremental In-Place Update for Billion-Scale Vector Search](https://doi.org/10.1145/3600006.3613166) — <sub>Yuming Xu, Hengyu Liang, Jin Li, Shuotao Xu, Qi Chen, Qianxi · 2023</sub>  
  The named diagnosis — partition/centroid structures degrade under data distribution shift and the fix is local rebalancing rather than periodic global retrain — plus the concrete observation…
- [Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs](https://arxiv.org/abs/1603.09320) — <sub>Yu. A. Malkov, D. A. Yashunin · 2020</sub>  
  Incremental insert is native and cheap; the graph degrades gracefully as it grows.

</details>


## Calibration and human-in-the-loop

The deliverable grades timeliness in both directions, so 'low confidence' has to genuinely mean low. That makes calibration a scored property of the system rather than a nicety, and the literature on LLM confidence is not reassuring.

**[LangGraph Human-in-the-Loop / Interrupts (official documentation)](https://docs.langchain.com/oss/python/langgraph/interrupts)**  
<sub>LangChain, Inc. · docs.langchain.com (LangGraph OSS Python docs) · accessed 2026</sub>

interrupt() pauses graph execution mid-node and surfaces any JSON-serializable payload to the caller; execution resumes via Command(resume=value), and that value becomes the return value of the original interrupt() call.

*What I took:* Durable pause-on-thread as the HITL mechanism, plus the node-replay idempotency hazard that most implementations get wrong.

*Where it lands in my design:* Concrete implementation of hitl_status. escalated = an open interrupt on that customer's thread; human_approved / human_rejected / human_modified = the resume payload, recorded with reviewer id and timestamp in the trace log.

*Where I think it doesn't apply:* Vendor documentation, not peer-reviewed, and the API surface has changed across LangGraph versions (interrupt()/Command superseded the older NodeInterrupt and interrupt_before patterns) — pin the version in the writeup.

**[Selective Classification Can Magnify Disparities Across Groups](https://openreview.net/pdf?id=_3tRq40EohT)**  
<sub>Erik Jones, Shiori Sagawa, Pang Wei Koh, Ananya Kumar, Percy Liang (Stanford) · ICLR 2021 · 2021</sub>

Across five vision and NLP datasets, abstaining on low-confidence inputs raises average accuracy while simultaneously widening the accuracy gap between groups — and, counter-intuitively, increasing abstention can DECREASE accuracy on the worst-off group in absolute terms.

*What I took:* Abstention is not a free safety mechanism. Always report risk–coverage per subgroup, never only in aggregate.

*Where it lands in my design:* ARGUES AGAINST the comfortable assumption that 'when unsure, escalate' automatically makes the system safer. In a banking Customer-360 this is live fairness and regulatory exposure: if the model is confidently wrong about, say, small_business_cashflow_event for certain customer segments, escalation will never rescue them because the system never doubts itself there.

*Where I think it doesn't apply:* Demonstrated on vision and NLP classifiers with explicit group annotations and known spurious correlations.

**[The flaws of policies requiring human oversight of government algorithms](https://arxiv.org/abs/2109.05067)**  
<sub>Ben Green (University of Michigan / Harvard) · Computer Law & Security Review, vol. 45 · 2022</sub>

Surveys 41 real policies mandating human oversight of government algorithms and identifies two structural flaws. First, the empirical evidence shows people cannot actually perform the oversight functions the policies assume — they cannot reliably identify algorithmic errors or determine when to override.

*What I took:* A HITL checkpoint is not by itself a safety argument. If the reviewer cannot realistically detect the error class, the checkpoint launders risk rather than reducing it.

*Where it lands in my design:* ARGUES AGAINST the competition's own framing — the rubric asks for 'HITL approval checkpoints', and the tempting response is to sprinkle approve/reject gates everywhere and call the system safe.

*Where I think it doesn't apply:* Argues about government/public-sector algorithms in legally consequential settings (benefits, policing, sentencing) where the asymmetry of power is severe.

**[Calibrated Language Models Must Hallucinate](https://arxiv.org/abs/2311.14648)**  
<sub>Adam Tauman Kalai (OpenAI), Santosh S. Vempala (Georgia Tech) · STOC 2024 (56th Annual ACM Symposium on Theory of Computing) · 2023 (arXiv) / 2024 (STOC)</sub>

Proves a statistical lower bound: a pretrained LM satisfying a calibration condition appropriate for generative models MUST hallucinate 'arbitrary' facts — facts whose veracity is not determined by the training data — at a rate close to the Good–Turing monofact rate, i.e. the fraction of facts appearing exactly once in training.

*What I took:* Calibration is not a free good and is not the same as correctness. A perfectly calibrated generator still emits confident falsehoods about rare one-off facts.

*Where it lands in my design:* ARGUES AGAINST treating 'make the model calibrated' as the whole uncertainty story. The practical read: the enum-constrained part of our output (inferred_state, action, action_subtype) is a closed-set prediction where calibration is meaningful and conformal coverage is achievable, so all decision-critical uncertainty should be pushed there.

*Where I think it doesn't apply:* A theoretical result about pretraining-time facts under a specific calibration definition; it does not bound hallucination for a retrieval-grounded system where the facts are in context.

**[Detecting hallucinations in large language models using semantic entropy](https://doi.org/10.1038/s41586-024-07421-0)**  
<sub>Sebastian Farquhar, Jannik Kossen, Lorenz Kuhn, Yarin Gal (OATML, University of Oxford) · Nature, vol. 630 (8017), pp. 625–630 · 2024</sub>

Samples K generations (the authors note ~5 is usually enough), clusters them by bidirectional entailment using an NLI model or an LLM judge so that lexically different but semantically equivalent answers collapse into one cluster, then computes entropy over the cluster distribution rather than the token-sequence distribution.

*What I took:* Cluster-then-entropy: measure disagreement in meaning-space. Plus the AURAC framing — report accuracy as a function of rejection rate, which is exactly our escalation-rate curve.

*Where it lands in my design:* Our label space is a closed 14-value enum, so the expensive NLI clustering collapses to free exact-match clustering: sample the analyst agent k times over the same evidence window, count the distribution over enum values, take the entropy. That entropy is the primary band input.

*Where I think it doesn't apply:* The Nature paper targets confabulation in free-form generation; our closed enum is an easier setting where the method is nearly free but also less novel.

<details>
<summary>Skimmed or queued for the end term (17 more)</summary>

- [Consistent Estimators for Learning to Defer to an Expert](https://arxiv.org/abs/2006.01862) — <sub>Hussein Mozannar, David Sontag (MIT Clinical ML) · 2020</sub>  
  Deferral should be conditioned on expected human accuracy on that instance, not purely on model uncertainty. Model the expert, not just yourself.
- [Transaction monitoring in anti-money laundering: A qualitative analysis and points of view from industry](https://doi.org/10.1016/j.future.2024.05.027) — <sub>Berkan Oztas, Deniz Cetinkaya, Festus Adedoyin, Marcin Budka · 2024</sub>  
  Hard sector-specific evidence that threshold-based rule engines in exactly our domain run at 90–95% false positives, plus the constraint that regulators require the rule to remain explainabl…
- [The Foundations of Cost-Sensitive Learning](https://dblp.org/rec/conf/ijcai/Elkan01.html) — <sub>Charles Elkan (UC San Diego) · 2001</sub>  
  One threshold per action, derived from that action's own cost ratio. Costs set the operating point; accuracy does not.
- [To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-assisted Decision-making](https://arxiv.org/abs/2102.09692) — <sub>Zana Buçinca, Maja Barbara Malaya, Krzysztof Z. Gajos (Harva · 2021</sub>  
  Concrete UI mechanics that convert a rubber stamp into a real review: commit-first, on-demand disclosure, deliberate friction.
- [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170) — <sub>Isaac Gibbs, Emmanuel J. Candès (Stanford) · 2021</sub>  
  The online alpha update rule with step size gamma. Coverage is maintained by feedback, not by an i.i.d. assumption nobody in a live stream can honour.
- [Conformal Prediction Sets Improve Human Decision Making](https://arxiv.org/abs/2401.13744) — <sub>Jesse C. Cresswell, Yi Sui, Bhargava Kumar, Noël Vouitsis (L · 2024</sub>  
  Human-subjects RCT evidence that handing a person a variable-size SET beats handing them a ranked top-k, because set size is itself a legible uncertainty cue.
- [Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners (KnowNo)](https://arxiv.org/abs/2307.01928) — <sub>Allen Z. Ren, Anushri Dixit, Alexandra Bodrova, Sumeet Singh · 2023</sub>  
  The exact singleton-versus-set escalation rule for an LLM agent, and the reframing of 'when to ask a human' as coverage-constrained help-rate minimization.
- [Does automation bias decision-making?](https://doi.org/10.1006/ijhc.1999.0252) — <sub>Linda J. Skitka, Kathleen L. Mosier, Mark Burdick · 1999</sub>  
  Omission bias is the residual risk training cannot fix: humans stop looking for what the system does not surface.
- [Does the Whole Exceed its Parts? The Effect of AI Explanations on Complementary Team Performance](https://doi.org/10.1145/3411764.3445717) — <sub>Gagan Bansal, Tongshuang Wu, Joyce Zhou, Raymond Fok, Besmir · 2021</sub>  
  Explanation quality and persuasiveness are orthogonal. A fluent, citation-backed rationale increases acceptance of wrong answers as much as right ones.
- [Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs](https://arxiv.org/abs/2306.13063) — <sub>Miao Xiong, Zhiyuan Hu, Xinyang Lu, Yifei Li, Jie Fu, Junxia · 2023 (arXiv) / 2024 (ICLR)</sub>  
  Never trust a single verbalized confidence. Use agreement across k independent samples as the primary uncertainty signal and the verbalized number as a weak secondary feature.
- [On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599) — <sub>Chuan Guo, Geoff Pleiss, Yu Sun, Kilian Q. Weinberger (Corne · 2017</sub>  
  ECE and the reliability diagram as the metric for 'does low actually mean low', and a one-parameter recalibration fitted on held-out data.
- [Overriding of drug safety alerts in computerized physician order entry](https://doi.org/10.1197/jamia.M1809) — <sub>Heleen van der Sijs, Jos Aarts, Arnold Vulto, Marc Berg (Era · 2006</sub>  
  The empirical ceiling on human attention to machine alerts, from the domain that has studied it longest.
- [Teaching Models to Express Their Uncertainty in Words](https://arxiv.org/abs/2205.14334) — <sub>Stephanie Lin, Jacob Hilton, Owain Evans (Oxford / OpenAI) · 2022</sub>  
  A discrete verbal band (low/medium/high) can be a legitimate calibrated output rather than a cosmetic label — but only if it is fit and validated against outcomes, not merely prompted.
- [A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification](https://arxiv.org/abs/2107.07511) — <sub>Anastasios N. Angelopoulos, Stephen Bates (UC Berkeley) · 2021</sub>  
  Set size as the confidence band — not a scalar the model invented, but a set whose coverage is guaranteed by construction.
- [Language Models (Mostly) Know What They Know](https://arxiv.org/abs/2207.05221) — <sub>Saurav Kadavath, Tom Conerly, Amanda Askell, et al. (Anthrop · 2022</sub>  
  The P(True) trick: separate generating the hypothesis from scoring it, and show the scorer the full slate of competing hypotheses before it scores.
- [Mitigating LLM Hallucinations via Conformal Abstention](https://arxiv.org/abs/2405.01563) — <sub>Yasin Abbasi-Yadkori, Ilja Kuzborskij, David Stutz, András G · 2024</sub>  
  Conformal calibration applied to a self-consistency score rather than a softmax — the recipe when you have no logits and no fixed label set — plus the framing of abstention rate as the price…
- [Selective Classification for Deep Neural Networks](https://arxiv.org/abs/1705.08500) — <sub>Yonatan Geifman, Ran El-Yaniv (Technion) · 2017</sub>  
  The risk–coverage curve as the governing artefact, and specifying the target risk to derive the threshold rather than specifying the threshold and hoping.

</details>


## Guardrails, observability, regulation

The non-negotiables are 15% of the score and the problem statement is explicit that a prompt instruction does not count as a guardrail. I read for the difference between a control that is enforced and a control that is requested.

**[Equal Credit Opportunity Act / Regulation B, 12 CFR 1002.2(z) 'prohibited basis' and 1002.4(b) discouragement](https://www.consumerfinance.gov/rules-policy/regulations/1002/2/)**  
<sub>Consumer Financial Protection Bureau · eCFR / consumerfinance.gov · current</sub>

'Prohibited basis' means race, colour, religion, national origin, sex, marital status, or age (where the applicant can contract); the fact that all or part of the applicant's income derives from any public assistance program; or the good-faith exercise of a right under the Consumer Credit Protection Act.

*What I took:* That marital status, age and public-assistance income are themselves prohibited bases — so inferring them and then acting on them is the regulated act, not just denying credit on them.

*Where it lands in my design:* This is the sharpest domain-specific guardrail we can show, and it maps onto the enum one-to-one. marriage_or_relationship_change is marital status. retirement_transition and elder_vulnerability_or_scam_risk are age proxies.

**[Regulation (EU) 2024/1689 (EU AI Act): Article 12 record-keeping, Article 14 human oversight, Article 86 right to explanation, Annex III point 5(b)](https://artificialintelligenceact.eu/article/14/)**  
<sub>European Parliament and Council of the EU · artificialintelligenceact.eu / EUR-Lex · 2024</sub>

Annex III point 5(b) classifies as high-risk 'AI systems intended to be used to evaluate the creditworthiness of natural persons or establish their credit score, with the exception of AI systems used for the purpose of detecting financial fraud'.

*What I took:* Three hard design constraints — logging is an obligation not a feature; oversight must be effective and built-in, not nominal; and explanations must be reconstructible on demand after the fact.

*Where it lands in my design:* Note the carve-out precisely: fraud detection is exempt from the credit-scoring high-risk category, so our compliance_fraud_hold path sits outside Annex III 5(b) while the personalized_offer path, if it gates a credit product, sits inside it. That asymmetry justifies routing them through different governance in the architecture diagram.

**[Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657)**  
<sub>Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, Bhavya Chopra, Rishabh Tiwari, Kurt Keutzer, Aditya Parameswaran, Dan Klein, Kannan Ramchandran, Matei Zaharia, Joseph E. Gonzalez, Ion Stoica (UC Berkeley) · arXiv (ICML 2025) · 2025</sub>

Builds MAST, a taxonomy of 14 failure modes in three categories, from 150 traces across 7 multi-agent frameworks, validated with inter-annotator agreement kappa = 0.88, then scaled to 1600+ annotated traces.

*What I took:* The measured failure distribution as a prior on where to spend instrumentation, especially that 'disobey task specification' is the single largest mode and that verification failures are a quarter of…

*Where it lands in my design:* The problem statement mandates critique-refiner and debate patterns, and MAST says those patterns' own dominant failure is Incorrect/Incomplete Verification. So: instrument one counter per MAST mode as a first-class metric.

**[GDPR Article 22 and CJEU Case C-634/21 (SCHUFA Holding — Scoring)](https://gdpr-info.eu/art-22-gdpr/)**  
<sub>European Parliament and Council; Court of Justice of the European Union (First Chamber) · gdpr-info.eu ; CJEU judgment of 7 December 2023 · 2016 / 2023</sub>

Article 22(1) gives a data subject the right not to be subject to a decision based solely on automated processing, including profiling, producing legal effects or similarly significantly affecting them;

*What I took:* The SCHUFA holding that an upstream inferred score counts as the automated decision when a downstream human leans on it — 'a human clicks approve' is not automatically a defence.

*Where it lands in my design:* Our inferred_state is exactly a SCHUFA-shaped probability artefact: an inference about a person that a relationship manager will lean on. So hitl_status=human_approved only counts as meaningful human intervention if the reviewer sees the evidence and can actually reach a different conclusion — which is why the HITL UI must show the cited events and permit human_modified, not just approve/reject.

**[NIST SP 800-162: Guide to Attribute Based Access Control (ABAC) Definition and Considerations](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)**  
<sub>Vincent C. Hu, David Ferraiolo, Rick Kuhn, et al., NIST · NIST Computer Security Resource Center · 2014 (updated 2019)</sub>

Defines ABAC as authorization determined by evaluating attributes of the subject, the object, the requested operation and environment conditions against policy, rather than by pre-provisioned identity-to-permission mappings.

*What I took:* The PDP/PEP/PIP split, and environment-condition attributes (time, threat level) as legitimate inputs to an access decision.

*Where it lands in my design:* Our 'role-based data access at the data layer' should actually be ABAC, and the PEP sits inside the event store and the vector index, not in the agent.

<details>
<summary>Skimmed or queued for the end term (21 more)</summary>

- [The Algorithmic Foundations of Differential Privacy](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf) — <sub>Cynthia Dwork and Aaron Roth · 2014</sub>  
  Composition and a privacy budget: repeated querying is the leak, and the protection applies to aggregate release, not to per-record operational use.
- [Consumer Financial Protection Circular 2023-03: Adverse action notification requirements and the proper use of the CFPB's sample forms provided in Regulation B](https://www.consumerfinance.gov/compliance/circulars/circular-2023-03-adverse-action-notification-requirements-and-the-proper-use-of-the-cfpbs-sample-forms-provided-in-regulation-b/) — <sub>Consumer Financial Protection Bureau · 2023</sub>  
  The explicit rejection of the 'black-box' excuse, and the warning about reasons derived from behavioural surveillance data that no standard reason code describes.
- [Cryptographic Support for Secure Logs on Untrusted Machines](https://www.usenix.org/legacy/publications/library/proceedings/sec98/full_papers/schneier/schneier.pdf) — <sub>Bruce Schneier and John Kelsey · 1998</sub>  
  The hash-chained, forward-secure append-only log with a remote verifier — tamper-evidence obtained from a cheap primitive rather than from a database permission.
- [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837) — <sub>Luca Beurer-Kellner, Beat Buesser, Ana-Maria Creţu, Edoardo  · 2025</sub>  
  Plan-Then-Execute and Action-Selector, because our action space is already a closed enum of six values — the strongest patterns are the ones that are cheap when the action space is finite.
- [Defeating Prompt Injections by Design (CaMeL)](https://arxiv.org/abs/2503.18813) — <sub>Edoardo Debenedetti, Ilia Shumailov, Tianqi Fan, Jamie Hayes · 2025</sub>  
  Capability tags attached to data values and propagated through computation, with the policy check at the tool-call boundary — security that is a property of the data-flow graph, not of a mod…
- [Guardrails AI — open-source input/output validation framework for LLMs](https://guardrailsai.com/docs/concepts/validators) — <sub>Guardrails AI, Inc. · 2026</sub>  
  Per-validator failure policy (reask / filter / refrain / exception) as an explicit design axis, and Pydantic-typed output as the enforcement mechanism for a closed enum.
- [OpenTelemetry Semantic Conventions for Generative AI — Agent and Tool Spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) — <sub>OpenTelemetry Project (open-telemetry/semantic-conventions-g · 2026</sub>  
  Use the standard attribute names verbatim so traces are portable across Langfuse, Phoenix and any OTLP backend — and note the Development status honestly rather than presenting it as a froze…
- [NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails](https://arxiv.org/abs/2310.10501) — <sub>Traian Rebedea, Razvan Dinu, Makesh Sreedhar, Christopher Pa · 2023</sub>  
  The five-position rail taxonomy (input / dialog / retrieval / execution / output) as an architectural placement scheme, and the principle that the policy is a separate interpretable artifact…
- [Constitutional Classifiers: Defending against Universal Jailbreaks across Thousands of Hours of Red Teaming](https://arxiv.org/abs/2501.18837) — <sub>Mrinank Sharma, Meg Tong, Jesse Mu, et al. (Anthropic Safegu · 2025</sub>  
  The measured overhead numbers, and the constitution-as-config pattern: the policy is natural-language text that regenerates the classifier's training data, so policy changes are a data-gener…
- [Identifying the Risks of LM Agents with an LM-Emulated Sandbox (ToolEmu)](https://arxiv.org/abs/2309.15817) — <sub>Yangjun Ruan, Honghua Dong, Andrew Wang, Silviu Pitis, Yongc · 2023</sub>  
  Emulated high-stakes tools as a pre-production harness, and the 23.9% residual failure rate as the empirical basis for requiring a human gate on irreversible actions rather than trusting age…
- [Bypassing LLM Guardrails: An Empirical Analysis of Evasion Attacks against Prompt Injection and Jailbreak Detection Systems](https://arxiv.org/abs/2504.11168) — <sub>William Hackett, Lewis Birch, Stefan Trawicki, Neeraj Suri,  · 2025</sub>  
  Model-based classifiers are a probabilistic filter with an adversarially reachable 0% floor;
- [Microsoft Presidio — PII detection, redaction and anonymization framework](https://github.com/microsoft/presidio) — <sub>Microsoft (now maintained under the Data Privacy Stack org) · 2026</sub>  
  The offset-returning analyzer (so redaction is a span operation you can audit), the reversible-encrypt operator for round-trippable pseudonyms, and the vendor's own explicit disclaimer of co…
- [OWASP Top 10 for Large Language Model Applications, 2025 edition](https://genai.owasp.org/llm-top-10/) — <sub>OWASP GenAI Security Project · 2025</sub>  
  LLM06's 'least functionality + human approval for high-impact actions' framing, and LLM08 as the named risk for a live vector index that is written to by the same stream it is read from.
- [NIST SP 800-38G (and Rev. 1 draft): Recommendation for Block Cipher Modes of Operation — Methods for Format-Preserving Encryption](https://csrc.nist.gov/pubs/sp/800/38/g/upd1/final) — <sub>Morris Dworkin, NIST (Computer Security Division) · 2016 (Rev. 1 draft 2019)</sub>  
  FPE is safe only above a 10^6 domain, and the standard itself has been revised twice under attack — so treat FPE as a schema-compatibility tool, not as a security boundary.
- [AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents](https://arxiv.org/abs/2406.13352) — <sub>Edoardo Debenedetti, Jie Zhang, Mislav Balunović, Luca Beure · 2024</sub>  
  The two-axis evaluation discipline: report utility-under-attack and attack-success-rate separately, and the insistence that the harness be extensible because attacks move.
- [Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://arxiv.org/abs/2302.12173) — <sub>Kai Greshake, Sahar Abdelnabi, Shailesh Mishra, Christoph En · 2023</sub>  
  The threat model itself: any field that is attacker-influencable and later retrieved is an injection vector, and persistence into memory turns one injection into a standing compromise.
- [TRAIL: Trace Reasoning and Agentic Issue Localization](https://arxiv.org/abs/2505.08638) — <sub>Darshan Deshpande, Varun Gangal, Hersh Mehta, Jitin Krishnan · 2025</sub>  
  The empirical ceiling on LLM-as-trace-auditor, and the taxonomy as a labelling scheme for our own failure analysis.
- [Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations](https://arxiv.org/abs/2312.06674) — <sub>Hakan Inan, Kartikeya Upasani, Jianfeng Chi, Rashi Rungta, K · 2023</sub>  
  The zero-shot, prompt-supplied taxonomy pattern — a policy you can version-control and diff — plus the separation of input classification from output classification as two distinct calls wit…
- [Arize Phoenix and the OpenInference tracing specification](https://arize.com/docs/ax/instrument/what-are-traces) — <sub>Arize AI · 2026</sub>  
  The RETRIEVER span carrying retrieved documents *and their similarity scores* as first-class attributes, and the existence of a distinct GUARDRAIL span kind.
- [Langfuse — open-source LLM engineering platform (tracing, sessions, scores, evals)](https://langfuse.com/) — <sub>Langfuse GmbH · 2026</sub>  
  The trace/session/score data model — in particular that a human label is stored as a score on the same trace object as the automated one, which makes agreement measurable without a second pi…
- [Adaptive Attacks Break Defenses Against Indirect Prompt Injection Attacks on LLM Agents](https://arxiv.org/abs/2503.00061) — <sub>Qiusi Zhan, Richard Fang, Henil Shalin Panchal, Daniel Kang  · 2025</sub>  
  Static-attack evaluation is worthless; and prompt-level defenses (delimiters, 'ignore instructions in data', sandwiching) provide essentially no security margin and should not be counted as…

</details>


## Banking: life events, churn, intervention

I know the agent side better than I know retail banking, so I spent real time here. The most useful thing I read was not technical at all: it was the regulatory and ethical material on inferring sensitive circumstances from spend, which is directly load-bearing for one of my guardrails.

**[FG21/1: Guidance for firms on the fair treatment of vulnerable customers](https://www.fca.org.uk/publication/finalised-guidance/fg21-1.pdf)**  
<sub>UK Financial Conduct Authority · FCA Finalised Guidance, published 23 February 2021 · 2021</sub>

I read the PDF. Defines a vulnerable customer as someone who, due to their personal circumstances, is especially susceptible to harm, and frames vulnerability as a spectrum of risk driven by 4 key drivers: Health (conditions affecting day-to-day tasks), Life events (bereavement, job loss, relationship breakdown), Resilience (low ability t…

*What I took:* Three operational rules: the 4-driver taxonomy as a state ontology; the prohibition on labelling the customer;

*Where it lands in my design:* Maps almost one-to-one onto our state enum and is the regulatory citation behind our hardest guardrail.

*Where I think it doesn't apply:* UK-specific and principles-based rather than prescriptive; it gives no detection thresholds and does not directly regulate automated inference.

**Advisory on Elder Financial Exploitation (FIN-2022-A002)**  
<sub>US FinCEN (Financial Crimes Enforcement Network) · FinCEN Advisory, 15 June 2022 · 2022</sub>

I read the PDF. Reports over 62,000 EFE-related SARs filed in 2020 covering an estimated $3.4 billion in suspicious transactions (up from $2.6bn in 2019), rising to over 72,000 SARs in 2021. Lists 12 behavioural and 12 financial red flags.

*What I took:* A ready-made, authoritative, deterministic rule set for elder_vulnerability_or_scam_risk, plus the meta-rule that single flags are not determinative and must be scored against the customer's own histo…

*Where it lands in my design:* Supplies the concrete feature list for the elder-risk detector and justifies co-occurrence scoring rather than any-single-rule firing. It fits the measured dataset unusually well: 'uncharacteristic nonpayment for services' is our cancelled standing instructions; the receive-and-forward pattern is the 5000-in-09:00 / 4900-out-09:15 sweep;

*Where I think it doesn't apply:* US AML/BSA framing aimed at SAR filing, not customer-care outreach — acting on these flags means escalation and investigation, NOT contacting the customer with an offer, and in a real bank a SAR carries tipping-off restrictions.

**[Feature engineering strategies for credit card fraud detection](https://doi.org/10.1016/j.eswa.2015.12.030)**  
<sub>Alejandro Correa Bahnsen, Djamila Aouada, Aleksandar Stojanovic, Bjorn Ottersten (SnT, University of Luxembourg) · Expert Systems With Applications, 51:134-142 · 2016</sub>

I read the full PDF. States plainly that raw per-transaction features (amount, time, entry mode) give an incomplete profile of the customer, and builds two better families. (1) Transaction aggregation (after Whitrow et al.

*What I took:* The exact recipe: multi-window (1h to 168h) counts and sums grouped by merchant category and counterparty, plus circular-statistics time-of-day novelty — and the measured fact that raw amount features…

*Where it lands in my design:* This is the concrete feature spec for the swarm's numeric agent and the direct antidote to the dataset's amount-magnitude trap. Because aggregates are grouped by merchant category, a 4th healthcare transaction in a category with 0/221 history scores enormously on count-in-category-window, while the $12,000 tuition wire is one ordinary event in a familiar category.

*Where I think it doesn't apply:* It is a cost-sensitive FRAUD paper; the savings metric is fraud-specific and does not transfer to life-event inference, and the von Mises time-of-day feature may not vary meaningfully in our data.

**EU AI Act, Article 5(1)(b) - prohibited exploitation of vulnerabilities**  
<sub>European Parliament and Council; European Commission Guidelines on Prohibited AI Practices (February 2025) · Regulation (EU) 2024/1689, Official Journal of the EU; prohibitions applicable from 2 February 2025 · 2024 (in force 2025)</sub>

Prohibits placing on the market, putting into service or using an AI system that exploits any vulnerability of a person or group due to their AGE, DISABILITY, or a SPECIFIC SOCIAL OR ECONOMIC SITUATION, with the objective or EFFECT of materially distorting their behaviour in a manner that causes or is reasonably likely to cause significan…

*What I took:* A statutory, intent-independent prohibition covering exactly this system's worst failure mode: detect financial distress, then offer a credit product.

*Where it lands in my design:* Turns the central guardrail from a policy preference into a legal boundary and extends it beyond medical hardship. Deterministic rule set enforced before emission: states {medical_hardship, financial_distress_general, job_loss_or_income_disruption, elder_vulnerability_or_scam_risk} -> personalized_offer is forbidden, full stop, with the article id recorded in the refusal.

*Where I think it doesn't apply:* Verified via multiple law-firm and Commission-guidance summaries, not the Official Journal text; the regulation number 2024/1689 is from memory — verify before printing.

**Case C-184/20, OT v Vyriausioji tarnybines etikos komisija**  
<sub>Court of Justice of the European Union (Grand Chamber) · CJEU judgment, 1 August 2022 · 2022</sub>

The Grand Chamber held that publishing the name of a declarant's spouse/cohabitee/partner alongside their own is processing of special categories of personal data under Article 9(1) GDPR, because it is liable INDIRECTLY to reveal sexual orientation.

*What I took:* Inference IS processing. Deriving a sensitive category from non-sensitive inputs creates special category data carrying the full Article 9 burden — there is no 'we only used ordinary transaction data'…

*Where it lands in my design:* The legal reason our medical_hardship guardrail must be architectural rather than advisory, and it reaches past the action layer: the moment the pipeline computes a health-related state from pharmacy/diagnostics categories, it CREATES Article 9 data, which must be (a) access-controlled by role at the data layer (support/care roles can read the state and evidence;

*Where I think it doesn't apply:* Verified through multiple law-firm analyses of the judgment rather than the judgment text itself, so quote the 'comparison or deduction' formulation as reported.

<details>
<summary>Skimmed or queued for the end term (17 more)</summary>

- [ADBench: Anomaly Detection Benchmark](https://arxiv.org/abs/2206.09426) — <sub>Songqiao Han, Xiyang Hu, Hailiang Huang, Minqi Jiang, Yue Zh · 2022</sub>  
  Do not build a generic unsupervised detector and hope. Encode a small number of TYPED detectors matched to named anomaly shapes, and exploit the handful of labels you have.
- [Credit Card Fraud Detection: A Realistic Modeling and a Novel Learning Strategy](https://doi.org/10.1109/TNNLS.2017.2736643) — <sub>Andrea Dal Pozzolo, Giacomo Boracchi, Olivier Caelen, Cesare · 2018</sub>  
  The architectural admission that information available at decision time is systematically different from information available later, and that the answer is two reconciled parallel views ove…
- [How Companies Learn Your Secrets](https://www.nytimes.com/2012/02/19/magazine/shopping-habits.html) — <sub>Charles Duhigg · 2012</sub>  
  Two lessons in one story: (a) a basket of low-value, high-novelty purchases beats any single large transaction as a life-event detector — structurally identical to our $125 pharmacy and $450…
- [Did Target Really Predict a Teen's Pregnancy? The Inside Story](https://www.kdnuggets.com/2014/05/target-predict-teen-pregnancy-inside-story.html) — <sub>Gregory Piatetsky-Shapiro (KDnuggets) · 2014</sub>  
  Epistemic hygiene about the field's favourite parable: the most-cited evidence for 'transaction data reveals pregnancy with high precision' is an unverified anecdote, and the true base rate…
- [Leveraging fine-grained transaction data for customer life event predictions](https://doi.org/10.1016/j.dss.2019.113232) — <sub>Arno De Caigny, Kristof Coussement (IESEG School of Manageme · 2020</sub>  
  The counterparty pseudo-social-network feature — a new recurring counterparty is itself a feature — and their framing of rarity as the central modelling problem rather than an afterthought.
- [Data Spotlight: Suspicious Activity Reports on Elder Financial Exploitation - Issues and Trends](https://files.consumerfinance.gov/f/documents/cfpb_suspicious-activity-reports-elder-financial-exploitation_report.pdf) — <sub>US Consumer Financial Protection Bureau, Office for Older Am · 2019</sub>  
  The magnitude asymmetry (tens of thousands of dollars per incident) and the documented detection-to-intervention gap.
- [Scalable and Weakly Supervised Bank Transaction Classification](https://arxiv.org/abs/2305.18430) — <sub>Liam Toran, Cory Van Der Walt, Alan Sammarone, Alex Keller ( · 2023</sub>  
  The anchor-then-generalise pattern — deterministic high-precision rules produce labels and a learned model generalises beyond them — and the principle that category assignment is a separate,…
- ["Counting Your Customers" the Easy Way: An Alternative to the Pareto/NBD Model](https://doi.org/10.1287/mksc.1040.0098) — <sub>Peter S. Fader (Wharton), Bruce G. S. Hardie (London Busines · 2005</sub>  
  A latent-attrition posterior from recency and frequency alone, personalised by the customer's own baseline rate — silence scored against what THIS customer's cadence predicted, not a global…
- [CoLES: Contrastive Learning for Event Sequences with Self-Supervision](https://arxiv.org/abs/2002.08232;) — <sub>Dmitrii Babaev, Nikita Ovsov, Ivan Kireev, Maria Ivanova, Gl · 2022</sub>  
  A single learned customer-state vector built from raw event sequences and reusable across tasks — and specifically the augmentation premise that two windows of the same user should embed clo…
- [A Novel Profit Maximizing Metric for Measuring Classification Performance of Customer Churn Prediction Models](https://doi.org/10.1109/TKDE.2012.50) — <sub>Thomas Verbraken, Wouter Verbeke, Bart Baesens (KU Leuven) · 2013</sub>  
  Evaluation must encode asymmetric costs, and the model should output an optimal targeting fraction rather than a tuned probability cutoff.
- [Retention Futility: Targeting High-Risk Customers Might Be Ineffective](https://doi.org/10.1509/jmr.16.0163) — <sub>Eva Ascarza (Columbia / Harvard Business School) · 2018</sub>  
  Split the pipeline in two: a state/risk estimator (what is happening to this customer) and a separate action-value estimator (will an intervention change anything).
- [PS22/9: A new Consumer Duty (with FG22/5 final non-Handbook guidance)](https://www.fca.org.uk/publication/policy/ps22-9.pdf) — <sub>UK Financial Conduct Authority · 2022</sub>  
  'Avoid foreseeable harm' as a testable engineering predicate, plus the consumer-understanding outcome, which makes explanation quality a regulatory requirement rather than a nice-to-have.
- [Dynamic Prediction by Landmarking in Event History Analysis](https://doi.org/10.1111/j.1467-9469.2006.00529.x) — <sub>Hans C. van Houwelingen (Leiden University Medical Center) · 2007</sub>  
  The landmark-plus-horizon protocol as the correct inference AND evaluation discipline for 'predict at an arbitrary time using only what was known then'.
- [Causal Inference and Uplift Modelling: A Review of the Literature](https://proceedings.mlr.press/v67/gutierrez17a.html) — <sub>Pierre Gutierrez, Jean-Yves Gerardy (Dataiku) · 2017</sub>  
  The class-transformation trick, and the T-learner failure mode: predicting the outcome twice and subtracting is not the same as predicting the difference.
- [Customer attrition analysis for financial services using proportional hazard models](https://doi.org/10.1016/S0377-2217(03)00069-9) — <sub>Dirk Van den Poel, Bart Lariviere (Ghent University) · 2004</sub>  
  Hazard formulation with time-varying covariates: risk is a function of time since last activity and of CHANGES in behaviour, not of a snapshot.
- [Metalearners for estimating heterogeneous treatment effects using machine learning](https://arxiv.org/abs/1706.03461;) — <sub>Soren R. Kunzel, Jasjeet S. Sekhon, Peter J. Bickel, Bin Yu  · 2019 (preprint 2017)</sub>  
  The two-stage imputation structure, the insight that effect functions are usually simpler and smoother than outcome functions, and explicit handling of severe group-size imbalance.
- [Customer base analysis: partial defection of behaviourally loyal clients in a non-contractual FMCG retail setting](https://doi.org/10.1016/j.ejor.2003.12.010) — <sub>Wendy Buckinx, Dirk Van den Poel (Ghent University) · 2005</sub>  
  Treat degradation (a change in rate) as the label, and use inter-event-time irregularity as a first-class feature — not just count and recency but the variance of the gap distribution.

</details>
