WORKING PRODUCT + ARCHITECTURE FOUNDATION

Fence AI SaaS

Visual construction topology, explainable strategy generation, BOM
optimization, and expert-in-the-loop learning

Version 0.1 \| 9 August 2026

| **Purpose:** Capture the product and reasoning architecture agreed so far, so it can be refined into a technical design and later decomposed into implementable work for development teams. This is intentionally a foundation, not a frozen specification. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

**Core idea**

The user describes the physical installation primarily through a visual
construction topology. The system combines that topology with products,
structured and textual knowledge, rules, preferences, annotations, and
inventory to propose an editable construction strategy. Every meaningful
system decision is represented explicitly so the user can inspect,
comment on, override, and teach the system.

# 1. Product vision and guiding principles

- **Visual-first, not chat-first.** The construction topology is the
  main project artifact. Text is a supporting channel for comments,
  clarification, teaching, and exceptions.

- **Topology before strategy.** The user first describes what physically
  exists and what must be installed. The system then proposes how to
  construct the fence.

- **Strategy is editable.** AI output is a proposal, not an opaque
  answer. The user can move, split, replace, pin, annotate, or override
  generated construction decisions.

- **Knowledge is infrastructure.** Company expertise must live in
  explicit, mutable knowledge objects rather than a single giant system
  prompt.

- **Explainability is structural.** The platform records explicit
  decision dependencies and provenance rather than relying on hidden
  chain-of-thought.

- **Human corrections are valuable data.** Corrections can remain
  project-specific or become candidate reusable rules after expert
  review.

- **Deterministic where possible, AI where useful.** Geometry, rule
  evaluation, constraints, inventory, packaging, and optimization should
  be machine-checkable. LLMs interpret, reason at fuzzy boundaries,
  learn, explain, and critique.

- **Designed to evolve.** Products, topology concepts, rule types,
  optimization policies, and reasoning modules must be addable or
  replaceable without redesigning the entire system.

| **Important terminology:** This document uses “decision trace” or “decision graph” instead of literal chain-of-thought. The system should expose the facts, rules, constraints, assumptions, alternatives, and causes of a decision - not hidden model reasoning. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 2. Conceptual architecture

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>KNOWLEDGE SUBSTRATE<br />
+--------------------------------------------------+<br />
| Facts | Rules | Preferences | Heuristics |<br />
| Text knowledge | Examples | Overrides |<br />
+-----------------------+--------------------------+<br />
|<br />
|<br />
CONSTRUCTION TOPOLOGY ----------+---------- PRODUCT MODEL /
INVENTORY<br />
|<br />
v<br />
STRATEGY REASONING ENGINE<br />
+-----------------------------------+<br />
| Geometry / topology analysis |<br />
| Rule + constraint evaluation |<br />
| Strategy search / optimization |<br />
| LLM interpretation + reasoning |<br />
| Validation / critic |<br />
+----------------+------------------+<br />
|<br />
v<br />
CONSTRUCTION STRATEGY<br />
|<br />
+----------+-----------+<br />
v v<br />
STRUCTURAL RESULT DECISION GRAPH<br />
| |<br />
+----------+-----------+<br />
v<br />
USER REVIEW<br />
comment / edit / override<br />
|<br />
+----------+-----------+<br />
v v<br />
Project-specific Knowledge candidate<br />
override |<br />
review<br />
|<br />
v<br />
KNOWLEDGE SUBSTRATE</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**The rule / knowledge engine is an input to strategy generation, not a
later validation step.** A construction strategy must be generated while
respecting product constraints, physical topology, company rules, human
intent, and existing inventory or material policies.

# 3. Construction topology - the physical source of truth

The construction topology describes the installation environment and
customer intent without forcing the user to manually engineer the
finished fence. It should be primarily authored on a visual map/canvas,
with text comments attached to meaningful map objects.

| **Topology concern** | **Examples**                                                            | **Key principle**                                                            |
|----------------------|-------------------------------------------------------------------------|------------------------------------------------------------------------------|
| Horizontal geometry  | Runs, points, angles, corners, gates, openings                          | Geometry is continuous; generated fence sections do not define the topology. |
| Vertical geometry    | Elevation, uphill/downhill profile, wall height, desired top line       | Terrain/base elevation and fence top profile are distinct.                   |
| Installation base    | Soil, concrete, brick wall, mixed conditions, transitions               | Base conditions may change inside one run.                                   |
| Intent / constraints | Desired privacy height, clearance, alignment, aesthetics                | User intent must be represented separately from generated structure.         |
| Annotations          | Comments on a point, segment, sub-range, gate, corner, or whole project | Text must retain spatial scope and original wording.                         |
| Physical obstacles   | Existing structures, walls, unavailable mounting points                 | These constrain strategy generation but are not fence products.              |

| **Key separation:** Fence run != generated fence section != installation/base segment. A 3 m run may be fulfilled by two unequal or equal construction spans; a base transition may occur inside either span; the strategy engine decides whether that is permitted. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 4. Construction strategy - the editable system proposal

A strategy is the system's proposed way to build a fence on a specific
topology. The same topology may support multiple valid strategies with
different cost, appearance, waste, installation effort, or robustness.

| **Strategy component**       | **Typical contents**                                                                                 |
|------------------------------|------------------------------------------------------------------------------------------------------|
| Structural points            | Posts, anchors, supports, special transition points, gate supports.                                  |
| Spans / sections             | Panel boundaries, custom widths, generated section lengths, shared structural boundaries.            |
| Vertical behavior            | Follow slope, step, keep top level, custom transitions.                                              |
| Mounting decisions           | Ground mount, masonry mount, wall transition treatment, brackets, reinforcement.                     |
| Product selections           | Fence series, post type, rail type, mounting components, substitutions.                              |
| Overrides / pinned decisions | Human-enforced placement or product decisions that strategy generation must preserve.                |
| Uncertainty / warnings       | Missing facts, assumptions, unresolved conflicts, low-confidence interpretations.                    |
| Decision references          | Links from each generated element back to facts, rules, constraints, and annotations that caused it. |

**The topology should remain stable while strategies are generated,
compared, edited, or discarded.** This allows the system to propose
alternatives without corrupting the user-authored description of
reality.

# 5. Product and material model

Products are not simple SKU records. The platform must model how a
resource is purchased, consumed, transformed, reused, combined, and
constrained during installation.

| **Consumption semantics** | **Examples**                        | **Needed behavior**                                                |
|---------------------------|-------------------------------------|--------------------------------------------------------------------|
| Indivisible discrete      | Posts, caps, gates                  | Count individual units; may have compatible variants.              |
| Divisible linear          | 3 m rails, channels                 | Cut into required lengths; account for kerf and reusable remnants. |
| Divisible sheet / area    | Panels or sheets                    | Potential 2D cutting / orientation constraints.                    |
| Packaged discrete         | Screws in boxes of 20               | Engineering quantity differs from purchase quantity.               |
| Volume / coverage based   | Concrete, paint                     | Demand converted using coverage or installation geometry.          |
| Assembly / kit            | Gate assembly, post kit             | One sellable item may imply or contain multiple components.        |
| Substitutable             | Compatible bracket or post families | Substitution controlled by rules, availability, cost, or approval. |
| Reusable / leftover stock | Rail remnants, open screw package   | Inventory may satisfy future demand if policy allows.              |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Example: linear product policy<br />
<br />
Rail R300<br />
purchase length: 3000 mm<br />
divisible: true<br />
cut kerf: 3 mm<br />
reusable leftovers: true<br />
minimum reusable remnant: configurable<br />
<br />
Example: packaged consumable<br />
<br />
Screw S10<br />
engineering unit: single screw<br />
purchase unit: box<br />
quantity per box: 20<br />
opened package reusable: configurable</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 6. Knowledge substrate - structured and textual knowledge together

The platform needs a hybrid knowledge model. Some knowledge is exact and
machine-readable; some begins as natural language, examples, or expert
judgement. Both must be preserved, scoped, versioned, and usable by the
reasoning engine.

| **Knowledge object**     | **Purpose**                                                            | **Example**                                                       |
|--------------------------|------------------------------------------------------------------------|-------------------------------------------------------------------|
| Fact                     | Exact property of a product, topology, inventory item, or project.     | Panel max width = 1800 mm; segment support = masonry.             |
| Hard rule                | Constraint that normally makes a strategy invalid if violated.         | Series X span may not exceed 1800 mm.                             |
| Soft rule / preference   | Company practice that influences ranking rather than validity.         | Prefer approximately equal panel widths.                          |
| Heuristic                | Useful but not fully formalized knowledge.                             | Stepped sections often look better on steep grades.               |
| Text knowledge           | Natural-language guidance that may not yet have a formal schema.       | Avoid tiny pieces near the gate.                                  |
| Annotation               | Project-specific note attached to topology or strategy.                | Keep top aligned with neighbor fence.                             |
| Override                 | Explicit human decision that constrains recomputation.                 | Force a support at this existing foundation point.                |
| Example / counterexample | Concrete evidence showing when a rule should or should not apply.      | Job 214 demonstrates exception on concrete.                       |
| Knowledge candidate      | AI-proposed reusable rule derived from correction or repeated pattern. | When gate X borders a slope above threshold, add reinforced post. |

## 6.1 Authority, scope, and conflict handling

Every knowledge object should carry authority and scope so conflicts can
be detected rather than silently resolved. A provisional precedence
model is:

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Safety / hard product constraints<br />
|<br />
Explicit approved project exceptions (when permitted)<br />
|<br />
Company rules<br />
|<br />
Project requirements / annotations<br />
|<br />
Company preferences<br />
|<br />
Heuristics<br />
|<br />
AI suggestions</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

This ordering is not final. Safety-critical or manufacturer constraints
may need to be non-overridable, while some “hard” business rules may
allow authorized exceptions. The implementation should therefore model
authority explicitly rather than hard-code one universal precedence
list.

# 7. Strategy reasoning engine

The reasoning engine combines deterministic computation with AI-assisted
interpretation. The objective is not to let an LLM invent a BOM
directly, but to orchestrate specialized reasoning modules over explicit
project state.

1.  Normalize and validate the topology and attached annotations.

2.  Resolve product and installation facts relevant to the affected
    topology.

3.  Interpret textual guidance into candidate structured constraints or
    intents while preserving original text.

4.  Apply hard constraints and identify mandatory structural decisions.

5.  Generate feasible construction alternatives.

6.  Score or optimize alternatives using company preferences and project
    objectives.

7.  Validate the proposed strategy against geometry, product
    constraints, rules, and unresolved assumptions.

8.  Produce the structural strategy together with an explicit decision
    graph and warnings.

9.  After user edits, recompute only affected dependencies where
    possible.

## 7.1 Hard constraints, soft preferences, objectives, and overrides

| **Type**               | **Meaning**                                                            | **Example**                                  |
|------------------------|------------------------------------------------------------------------|----------------------------------------------|
| Hard constraint        | A candidate strategy is invalid unless an authorized exception exists. | Panel width \<= manufacturer maximum.        |
| Soft preference        | Influences strategy ranking.                                           | Prefer symmetrical or similarly sized spans. |
| Optimization objective | A measurable quantity to minimize/maximize.                            | Minimize new stock, cost, waste, or cuts.    |
| Human override         | A user decision that the generator must preserve.                      | Place a post at a specific point.            |

These categories must remain distinct. Conflating them will make the
system unpredictable and make user corrections difficult to interpret.

# 8. Explainability through a decision graph

Every meaningful generated structural element should be traceable to the
evidence that caused it. This should be persisted as structured data,
not reconstructed after the fact from prose.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Topology Segment S7 ----+<br />
|<br />
Rule R18 --------------+----&gt; Decision D43 ----&gt; Reinforced Post
P12<br />
|<br />
Annotation N31 --------+<br />
|<br />
Product constraint ----+</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

| **Decision field**     | **Purpose**                                                                   |
|------------------------|-------------------------------------------------------------------------------|
| Action                 | What the system decided or generated.                                         |
| Scope                  | Which topology/strategy objects the decision affects.                         |
| Inputs                 | Facts, product properties, inventory state, annotations, and prior decisions. |
| Rules / constraints    | Structured knowledge that required or preferred the action.                   |
| Assumptions            | Unverified interpretation used to proceed.                                    |
| Alternatives           | Optional feasible choices considered or available to the user.                |
| Confidence / certainty | Whether the decision is deterministic, inferred, or uncertain.                |
| Status                 | Proposed, accepted, edited, rejected, pinned, superseded.                     |
| Provenance             | Who/what created or changed the decision and under which knowledge versions.  |

This graph enables high-value interactions: “Why is this post here?”,
“What changes if this rule is disabled?”, “Which decisions depend on
this note?”, and “Show every AI-interpreted assumption that has not been
confirmed.”

# 9. Expert review, correction, and learning loop

The expert should be able to work normally, correcting the proposed
construction rather than separately documenting every rule in advance.
The system captures the correction in context and decides whether it is
merely a project override or evidence of reusable knowledge.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>System proposes strategy<br />
|<br />
Expert accepts / comments / changes structure<br />
|<br />
System records the affected decision + context<br />
|<br />
+-------------------------+---------------------------+<br />
| |<br />
Project-specific correction Reusable pattern?<br />
| |<br />
Persist as override Propose knowledge candidate<br />
|<br />
Expert reviews/edits<br />
|<br />
Versioned knowledge</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

- The system must not silently convert every correction into a permanent
  global rule.

- A candidate rule should show the triggering examples, scope, proposed
  conditions, and expected consequences.

- The expert can approve, edit, reject, restrict scope, add
  counterexamples, or leave the knowledge as unstructured guidance.

- Original comments and correction history should remain available even
  after a structured interpretation is created.

# 10. Requirement, fulfillment, and BOM architecture

Construction strategy and purchasing are separate reasoning stages. The
structural strategy first creates engineering demand; a fulfillment
engine then maps that demand to inventory, cuts, packages,
substitutions, and purchases.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Construction Strategy<br />
|<br />
v<br />
Engineering / Material Demand<br />
- required pieces<br />
- required lengths<br />
- fastener counts<br />
- installation materials<br />
|<br />
v<br />
Fulfillment + Optimization<br />
- on-hand inventory<br />
- remnants / leftovers<br />
- cutting plans + kerf<br />
- package rounding<br />
- substitution policy<br />
- waste / cost / cut objectives<br />
|<br />
v<br />
Purchase BOM + Allocation / Cut Plan</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

Example: 48 required screws may become three boxes of 20; several
one-meter rails may be cut from 3 m stock; a 746 mm remnant may
eliminate a new stock cut if it satisfies the applicable reuse policy.

# 11. Changeability, versioning, and incremental recomputation

The product is expected to evolve during real work. Therefore the
architecture should treat knowledge, product definitions, strategies,
and user interpretations as versioned state with explicit dependencies.

- **Version knowledge.** Rules, preferences, product constraints, and
  structured interpretations should have stable IDs and versions.

- **Preserve provenance.** A strategy records which versions of
  rules/products were used to produce it.

- **Support local overrides.** A project can diverge from general
  defaults without mutating global knowledge.

- **Recompute incrementally.** Changing one wall height should
  invalidate affected decisions, structural elements, and BOM demand -
  not necessarily regenerate the entire project.

- **Expose impact before destructive change.** Changing a global rule
  should support impact analysis on dependent projects or strategies.

- **Keep history.** Accepted and rejected decisions, comments, and rule
  changes are useful for audit, debugging, and future learning.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Changed fact / rule<br />
|<br />
Affected constraints<br />
|<br />
Affected decisions<br />
|<br />
Affected structural elements<br />
|<br />
Affected engineering demand<br />
|<br />
Affected allocation / purchase BOM</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 12. Role of the LLM

The LLM should be a bounded reasoning and language layer around explicit
domain services, not the only source of truth.

| **LLM role**                    | **Responsibility**                                                                                        |
|---------------------------------|-----------------------------------------------------------------------------------------------------------|
| Interpreter                     | Convert natural-language comments into candidate structured intents or constraints; retain original text. |
| Reasoning assistant             | Handle ambiguous or novel situations not fully captured by deterministic rules.                           |
| Knowledge acquisition assistant | Turn corrections and recurring patterns into reviewable rule/knowledge candidates.                        |
| Explainer                       | Convert the decision graph into clear user-facing explanations at the right level of detail.              |
| Critic / reviewer               | Look for inconsistencies, missing inputs, suspicious strategies, conflicting rules, and edge cases.       |

| **Boundary:** Geometry, unit conversion, package arithmetic, deterministic rule evaluation, inventory accounting, cut feasibility, and constraint checks should not depend on free-form model output when they can be computed exactly. |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 13. UI contract (principles only - detailed UX deferred)

Detailed UI design is intentionally deferred, but the architecture
assumes the following interaction contract:

- The visual construction topology is the primary project input and
  remains distinguishable from AI-generated construction strategy.

- The construction strategy should be visual and preferably rendered as
  an editable overlay on the same topology, with contextual
  elevation/side views only where needed.

- Comments and annotations are attached to topology or strategy objects,
  not lost in an unrelated chat transcript.

- Users can inspect why a generated object exists, comment on the
  decision, edit it, or pin/override it.

- Warnings and uncertainty should be spatially linked to the affected
  construction element.

- Text conversation remains available for guidance and teaching, but
  should not replace structured project state.

# 14. Suggested domain boundaries / services

These are candidate boundaries for the technical design, not mandatory
microservices. They identify responsibilities that should remain
separable even if initially implemented in one application.

| **Boundary**            | **Owns**                                                                                       |
|-------------------------|------------------------------------------------------------------------------------------------|
| Topology service        | Geometry, elevation/base profiles, topology objects, spatial annotations, validation.          |
| Product catalog         | Product definitions, compatibility, consumption semantics, manufacturer constraints.           |
| Knowledge service       | Rules, preferences, heuristics, text knowledge, versions, authority, examples/counterexamples. |
| Strategy engine         | Feasible strategy generation, constraints, alternatives, scoring, user overrides.              |
| Decision graph / audit  | Decision nodes, dependencies, explanations, provenance, status history.                        |
| Inventory / fulfillment | Stock, remnants, package conversion, allocation, cutting-stock optimization, purchase BOM.     |
| AI orchestration        | Text interpretation, knowledge candidate generation, explanation, critique, tool invocation.   |
| Project / collaboration | Project versions, comments, user actions, approvals, permissions, review states.               |

# 15. Non-negotiable architectural properties

- No important company rule exists only inside an opaque prompt.

- No generated BOM item should be impossible to trace back to structural
  demand.

- No meaningful construction decision should be impossible to explain
  from persisted inputs and rules.

- Original human text is preserved alongside any AI-generated structured
  interpretation.

- Knowledge changes are versioned and reviewable.

- User overrides are explicit first-class state, not fragile prompt
  text.

- The same topology can support multiple strategy versions or
  alternatives.

- Inventory and purchasing are separated from physical construction
  requirements.

- The system can represent unknowns and ambiguity instead of fabricating
  certainty.

- Core deterministic calculations are testable independently of the LLM.

# 16. Open design questions before implementation planning

The following questions should be resolved through concrete fence
examples and expert interviews before committing to detailed schemas or
algorithms:

**1.** What are the minimum topology primitives required for the
company's real installations?

**2.** Which structural decisions are always deterministic versus
genuinely expert judgement?

**3.** What product consumption/transformation types occur beyond rails,
screws, panels, posts, concrete, and assemblies?

**4.** Which constraints are manufacturer/safety constraints and which
are company conventions that may be overridden?

**5.** How should strategy alternatives be ranked: cost, appearance,
installation time, waste, inventory consumption, number of cuts,
robustness, or a weighted combination?

**6.** When do base transitions or height changes require a structural
boundary?

**7.** How should uncertainty in textual annotations be represented and
confirmed?

**8.** Which corrections should be considered evidence for a reusable
rule, and who is authorized to approve them?

**9.** What inventory granularity is available in practice, especially
for remnants and opened packages?

**10.** What must be persisted for auditability, reproducibility, and
future re-evaluation when knowledge changes?

# 17. Recommended path from this document to developer tasks

Do not immediately split the entire system into implementation tickets.
First turn this foundation into a technical design using a small set of
representative real installations. Then decompose the validated design
into vertical and platform workstreams.

| **Phase**                  | **Deliverable**                                                                                       | **Outcome**                                                           |
|----------------------------|-------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| A. Domain discovery        | 3-10 representative installations, current expert BOMs, exceptions, product examples, corrections.    | Validates the model against reality.                                  |
| B. Domain model design     | Topology schema, strategy schema, knowledge object schema, decision graph, product semantics.         | Stable contracts for teams.                                           |
| C. Reasoning design        | Rule evaluation, constraint model, strategy generation lifecycle, uncertainty and override semantics. | Defines deterministic vs AI responsibilities.                         |
| D. Fulfillment design      | Demand model, packaging, inventory/remnants, cut optimizer, objective configuration.                  | Separates construction correctness from procurement optimization.     |
| E. API / event design      | Service interfaces, versioning, recomputation events, provenance and audit contracts.                 | Enables parallel implementation.                                      |
| F. UX design               | Topology editing, strategy overlay, decision review, annotations, teach mode.                         | Turns backend capabilities into the intended nontechnical experience. |
| G. Team task decomposition | Epics, vertical slices, contract tests, acceptance criteria.                                          | Produces implementation-ready work for developer teams.               |

## 17.1 Likely future team workstreams

- Topology / geometry platform

- Product catalog and knowledge platform

- Strategy / constraints / optimization engine

- Inventory and BOM fulfillment engine

- Decision graph, audit, and explainability

- AI orchestration and expert-learning workflow

- Visual application / interaction layer

- Testing, simulation, golden cases, and domain-validation tooling

**Recommended next artifact:** Create a Domain Model & Reasoning Design
v0.1 using several real fence cases. That document should define
concrete entities, IDs, relations, lifecycle states, schemas, example
decision graphs, and rule evaluation semantics. Only then should we
produce detailed developer tasks.
