# Fence AI SaaS — Research, Architecture & Implementation Planning Mission

You are responsible for taking the supplied **Fence AI SaaS Architecture Foundation** and turning it into a technically grounded, implementable system design and execution plan.

The supplied document describes the product vision and current architectural principles. Treat it as the **starting specification**, not as a final technical design.

Your job is to:

1. deeply research relevant technologies, existing systems, open-source projects, algorithms, AI models, libraries, standards, and data sources;
2. investigate the difficult technical problems in this project and alternative ways to solve them;
3. design the system architecture, domain model, reasoning infrastructure, knowledge infrastructure, APIs, storage and computation components;
4. validate the proposed architecture against realistic fence-construction scenarios and edge cases;
5. break the design into an executable implementation plan;
6. create tasks that AI coding agents can implement, test and integrate incrementally.

Do **not** begin implementation until the research and architecture phases are sufficiently complete.

---

# 1. First: Understand the Product

Read the supplied architecture document completely.

Extract and maintain a concise list of:

* product goals;
* architectural principles already established;
* hard requirements;
* assumptions;
* unresolved design questions;
* important edge cases;
* concepts that still lack precise definitions.

Do not silently change the product model described in the document.

If you believe an established design decision should change, explicitly document:

* the existing decision;
* the proposed alternative;
* why;
* advantages;
* disadvantages;
* migration/architectural consequences.

Maintain a living:

`docs/architecture/open-questions.md`

Do not block progress on every unanswered question. Mark assumptions explicitly and continue when reasonable.

---

# 2. Research Phase

Perform broad technical research before selecting technologies.

Research should include both:

* components that could be directly reused;
* systems/projects from which architectural ideas can be borrowed.

For every important source, preserve links and explain exactly why it is relevant.

Prefer:

1. official documentation;
2. academic papers;
3. mature open-source projects;
4. well-established engineering references;
5. high-quality technical articles.

Avoid choosing technologies primarily because they are popular.

## 2.1 Geometry, Topology and Construction Representation

Research how systems represent:

* paths and polylines;
* vertices and edges;
* segment ranges;
* angles;
* elevation;
* terrain profiles;
* walls and mounting surfaces;
* transitions between installation conditions;
* 2D / 2.5D geometry;
* parametric structures;
* dependency relationships between geometry and generated structures.

Investigate relevant concepts/projects from areas such as:

* CAD;
* BIM;
* computational geometry;
* GIS;
* graph-based modeling;
* parametric modeling;
* constraint-based design.

We probably do **not** need a full CAD/BIM system, but those domains may contain useful abstractions.

Determine what should be implemented ourselves versus reused.

---

# 2.2 Structural + Textual Knowledge

This is one of the central research problems.

Investigate architectures for combining:

### Structured information

Examples:

* dimensions;
* products;
* topology;
* constraints;
* compatibility;
* rules;
* decisions;
* inventory;
* BOM objects.

with:

### Unstructured information

Examples:

* expert comments;
* installation notes;
* product documentation;
* unusual customer requirements;
* heuristics;
* historical job explanations;
* expert corrections.

Research approaches including, where relevant:

* relational data models;
* graph databases;
* property graphs;
* document databases;
* knowledge graphs;
* semantic layers;
* embeddings/vector search;
* hybrid retrieval;
* structured outputs from LLMs;
* ontology/schema approaches;
* provenance models.

The goal is **not** to put everything into a vector database.

Determine which information should remain deterministic and structured and which information benefits from semantic retrieval or LLM interpretation.

---

# 2.3 Rules and Knowledge Engine

Research possible approaches for representing and executing:

* hard constraints;
* company rules;
* preferences;
* heuristics;
* exceptions;
* contextual rules;
* project-specific overrides;
* product-specific rules;
* rule precedence;
* conflicting rules;
* rule scopes;
* versioned rules.

Investigate:

* rule engines;
* policy engines;
* constraint solvers;
* logic programming;
* DSLs;
* decision tables;
* graph-based rules;
* custom rule representations.

Evaluate whether an existing engine is appropriate or whether a small domain-specific rule layer should be built.

Pay particular attention to:

* explainability;
* traceability;
* versioning;
* testability;
* dynamically adding rules;
* determining which decisions are affected by a rule change.

---

# 2.4 Constraint Solving and Strategy Generation

Research how the system can generate valid **construction strategies** from:

* topology;
* products;
* hard constraints;
* rules;
* preferences;
* textual annotations;
* user overrides.

Investigate relevant techniques such as:

* constraint satisfaction;
* SMT solving;
* CP-SAT;
* mixed integer programming;
* graph algorithms;
* search;
* heuristic planning;
* optimization;
* LLM-guided planning combined with deterministic validation.

Determine where deterministic algorithms should be used and where AI reasoning is actually beneficial.

Do not use an LLM for a calculation merely because an LLM is available.

---

# 2.5 Material Optimization / BOM

Research:

* cutting-stock problems;
* bin packing;
* 1D cutting optimization;
* 2D cutting if potentially relevant;
* package rounding;
* inventory allocation;
* leftovers/remnants;
* reusable remnants;
* substitutions;
* cost optimization;
* waste minimization;
* preserving valuable remnants;
* minimizing cuts;
* multi-objective optimization.

Investigate suitable mature optimization libraries/solvers.

The system must distinguish at least:

`Construction Requirement`

from:

`Material Demand`

from:

`Inventory Allocation`

from:

`Purchase BOM`

from:

`Cut Plan`

---

# 2.6 Product Modeling

Research suitable representations for products with different consumption semantics.

Examples include:

* indivisible products;
* linear cuttable stock;
* panels/sheets;
* packaged consumables;
* volume-based materials;
* assemblies;
* product families;
* compatible components;
* alternatives/substitutions;
* reusable materials;
* reusable remnants.

The product model must remain extensible without adding special-case code for every new SKU.

---

# 2.7 Explainable Decision Infrastructure

This is a major architectural requirement.

Research methods for producing an explicit **decision/provenance graph** rather than relying on hidden LLM chain-of-thought.

A decision should potentially reference:

* topology facts;
* products;
* rules;
* constraints;
* annotations;
* assumptions;
* AI interpretations;
* previous decisions;
* user overrides.

And produce:

* structural elements;
* warnings;
* BOM requirements;
* further decisions.

The architecture should allow questions such as:

* Why is this post here?
* Why was this product selected?
* Which rule caused this?
* Which topology feature triggered this decision?
* What depends on this rule?
* What changes if I alter this wall?
* Which decisions involved uncertain AI interpretation?
* Which decisions were manually overridden?

Research provenance/event-sourcing/dependency-graph concepts if useful.

---

# 2.8 Human Corrections and Learning

Research how the system can learn from the expert during normal work without unsafe uncontrolled self-modification.

Desired loop:

`system proposes → expert changes → system observes → expert explains → system proposes generalized knowledge → expert reviews → knowledge becomes active`

Investigate approaches for:

* correction capture;
* examples/counterexamples;
* rule induction;
* structured extraction;
* confidence;
* approval workflows;
* versioning;
* regression testing;
* preventing over-generalization.

The preferred mechanism is likely **knowledge evolution**, not continuous model retraining.

Verify this assumption.

---

# 2.9 AI / Model Layer

Research which model capabilities are required rather than simply picking one model.

Potential responsibilities include:

* natural-language interpretation;
* structured extraction;
* knowledge retrieval;
* rule proposal;
* ambiguity detection;
* strategy critique;
* explanation generation;
* document/product-spec understanding;
* visual understanding where useful.

Compare relevant current models and deployment options.

Consider:

* cost;
* latency;
* context size;
* structured output reliability;
* tool calling;
* reasoning;
* multimodality;
* model portability;
* cloud versus local deployment;
* model abstraction so models can later be replaced.

Do not architect the system around one specific model vendor unless necessary.

---

# 2.10 Existing Projects and Inspiration

Search aggressively for existing:

* fence design software;
* railing/balustrade configurators;
* construction BOM systems;
* parametric configurators;
* CAD/BIM configurators;
* product configurators;
* cutting optimizers;
* rule engines;
* visual graph editors;
* geometry engines;
* constraint systems;
* knowledge systems;
* explainable AI systems;
* AI-assisted CAD/design projects.

For each interesting project classify it as:

`directly reusable`

`useful component`

`architectural inspiration`

`algorithmic inspiration`

`not suitable`

Evaluate open-source projects for:

* license;
* maintenance/activity;
* maturity;
* API quality;
* documentation;
* extensibility;
* security;
* ecosystem;
* lock-in.

Do not introduce a dependency simply because it demonstrates the concept.

---

# 2.11 External Data and Skills

Investigate online information sources that could improve the system.

Examples:

* manufacturer product catalogs;
* installation manuals;
* building regulations where relevant;
* material specifications;
* CAD/product files;
* industry standards;
* dimensional data;
* historical company jobs;
* inventory/ERP sources.

Distinguish:

* authoritative data;
* useful reference material;
* customer/company-specific knowledge.

Also identify reusable AI-agent skills/tools that could help with:

* research;
* architecture;
* database design;
* testing;
* optimization;
* frontend visualization;
* documentation;
* code review;
* security review.

---

# 3. Research Deliverables

Create:

`research/`

with structured reports rather than one enormous research dump.

At minimum:

`research/geometry-topology.md`

`research/knowledge-representation.md`

`research/rules-constraints.md`

`research/optimization-bom.md`

`research/product-modeling.md`

`research/explainability-provenance.md`

`research/learning-from-corrections.md`

`research/ai-models.md`

`research/open-source-landscape.md`

`research/external-data-sources.md`

`research/technology-evaluation.md`

Each significant technology should include:

* what it does;
* where it could fit;
* benefits;
* limitations;
* maturity;
* license where relevant;
* alternatives;
* recommendation.

For important architectural choices produce a comparison matrix.

Do not merely enumerate tools.

Make decisions.

---

# 4. Architecture Phase

Only after sufficient research, design the system.

Produce:

`docs/architecture/system-design.md`

The architecture should clearly separate responsibilities.

A likely conceptual flow is:

`Construction Topology`

*

`Product Knowledge`

*

`Rules / Knowledge`

*

`Human Intent / Annotations`

↓

`Strategy Reasoning Engine`

↓

`Construction Strategy`

↓

`Material Requirements`

↓

`Inventory / Optimization`

↓

`Purchase BOM + Cut Plan`

while simultaneously maintaining:

`Decision / Provenance Graph`

and:

`Expert Correction → Knowledge Evolution`

Do not preserve this decomposition blindly if research demonstrates a substantially better one, but explain any departure.

---

# 5. Domain Model

Create:

`docs/architecture/domain-model.md`

Define major entities and relationships.

Do this conceptually before optimizing database tables.

Likely concepts include:

* Project
* Topology
* Path
* Vertex
* Run
* SegmentRange
* ElevationProfile
* InstallationSurface
* Wall
* Opening
* Gate
* Obstacle
* Annotation
* IntentConstraint
* Product
* ProductFamily
* ConsumptionSemantics
* CompatibilityRule
* ConstructionStrategy
* StructuralElement
* Post
* Span
* MountingDecision
* Requirement
* MaterialDemand
* InventoryItem
* Remnant
* CutPlan
* BOM
* Rule
* Constraint
* Preference
* Heuristic
* Override
* Decision
* Evidence
* Assumption
* Warning
* KnowledgeCandidate
* KnowledgeVersion

For each important entity document:

* identity;
* properties;
* relationships;
* lifecycle;
* ownership;
* versioning behavior.

Include example serialized objects.

---

# 6. Knowledge Architecture

Create a dedicated:

`docs/architecture/knowledge-system.md`

Specify how the system handles:

* structured facts;
* rules;
* constraints;
* preferences;
* heuristics;
* free-text knowledge;
* product documentation;
* annotations;
* examples;
* counterexamples;
* overrides;
* learned candidates.

Define:

### Authority

Which sources outrank others?

### Scope

Does knowledge apply to:

* global system;
* company;
* product family;
* product;
* installation type;
* project;
* topology range?

### Provenance

Where did the knowledge come from?

### Versioning

How does knowledge change?

### Validation

How is a new rule tested before activation?

### Conflicts

What happens when rules disagree?

---

# 7. Decision / Explainability Architecture

Create:

`docs/architecture/decision-model.md`

A decision should not merely contain generated explanation text.

It must have structured dependencies.

For example:

`Topology Fact T14`

*

`Product Constraint P7`

*

`Rule R31`

*

`User Annotation A9`

↓

`Decision D18`

↓

`Transition Post S22`

The natural-language explanation should be derived from this evidence.

Define how downstream dependency tracking works so the system can eventually perform incremental recomputation.

---

# 8. AI Architecture

Create:

`docs/architecture/ai-layer.md`

Define exactly where AI is allowed to participate.

Separate:

### Deterministic operations

Examples:

* geometry;
* dimensional calculations;
* constraint validation;
* known rule execution;
* inventory arithmetic;
* cut optimization.

from:

### AI-assisted operations

Examples:

* interpreting comments;
* extracting information from documents;
* suggesting generalized rules;
* handling incomplete heuristics;
* generating human explanations;
* identifying suspicious solutions;
* proposing alternatives.

Every AI-produced structured interpretation should preserve:

`original input`

*

`structured interpretation`

*

`confidence/evidence where appropriate`

The system should be capable of replacing the underlying AI model later.

---

# 9. Architecture Decision Records

For important choices create ADRs:

`docs/adr/ADR-XXXX-title.md`

Examples:

* topology representation;
* geometry engine;
* graph versus relational knowledge;
* rule engine;
* optimizer;
* decision graph;
* event/versioning model;
* vector search usage;
* AI provider abstraction.

Each ADR should contain:

* problem;
* considered alternatives;
* decision;
* reasons;
* consequences;
* unresolved risks.

---

# 10. Validate the Architecture With Scenarios

Before implementation planning, create a set of representative scenarios.

Examples:

### Scenario A — Simple straight fence

Basic ground installation.

### Scenario B — Non-divisible span

3m topology using nominal 1.8m sections.

### Scenario C — Slope

Fence runs uphill.

### Scenario D — Mixed mounting

Part of one run is on soil and another part on brick wall.

### Scenario E — Complex height intent

Wall elevation changes while customer requires a consistent privacy height.

### Scenario F — Cutting optimization

3m rails cut into several required lengths.

### Scenario G — Packaged material

47 screws purchased in boxes of 20.

### Scenario H — Inventory remnants

Use previous rail leftovers where appropriate.

### Scenario I — Expert correction

Expert modifies a proposed structural decision and teaches the system why.

### Scenario J — Conflicting knowledge

Product constraint conflicts with company preference or annotation.

Walk every scenario through:

`Topology → Knowledge → Strategy → Decisions → Requirements → Optimization → BOM`

If the architecture cannot represent a scenario cleanly, revise it.

---

# 11. Security and Reliability Review

Before implementation planning, perform a lightweight architecture review covering:

* tenant separation;
* permissions;
* auditability;
* malicious/incorrect natural-language instructions;
* AI hallucinations;
* schema validation;
* unsafe knowledge updates;
* corrupted rules;
* inconsistent product data;
* rollback;
* deterministic recalculation;
* data migrations;
* reproducibility.

Important construction decisions must not become authoritative solely because an LLM stated them.

---

# 12. Implementation Planning

Once architecture is stable enough, create:

`plan/implementation-roadmap.md`

Do not organize the project initially by arbitrary frontend/backend tickets.

Organize it by **vertical capabilities** and architectural dependencies.

A possible progression is:

### Foundation

* repository/workspace;
* coding standards;
* CI;
* test harness;
* schemas;
* versioning;
* observability.

### Domain Core

* topology representation;
* product model;
* rule/knowledge model;
* construction strategy model;
* decision model.

### Deterministic Engines

* geometry operations;
* rule evaluation;
* constraints;
* dependency tracking.

### Strategy Generation

* simple deterministic strategy;
* AI-assisted interpretation;
* strategy validation.

### BOM

* requirements;
* packaging;
* cut optimization;
* inventory;
* leftovers.

### Explainability

* provenance;
* decision graph;
* explanations;
* impact analysis.

### Learning

* corrections;
* knowledge candidates;
* approval;
* regression cases.

### Product Experience

* API;
* visual editor;
* review workflow;
* knowledge management.

But derive the actual sequencing from the architecture and dependency graph.

---

# 13. Task Breakdown

Create atomic work packages under:

`plan/tasks/`

Every task must contain:

### Goal

What capability is being produced?

### Context

Why does it exist?

### Dependencies

What must already exist?

### Inputs

Schemas/interfaces/components used.

### Outputs

Exactly what should be created.

### Interfaces

APIs/contracts that must remain compatible.

### Acceptance Criteria

Observable criteria for completion.

### Tests

Unit/integration/property/scenario tests required.

### Documentation

What must be updated.

### Non-goals

What is deliberately outside the task.

### Validation Command

How an agent can prove the task is complete.

Tasks should be sized so that an AI coding agent can complete one without needing to redesign the entire architecture.

---

# 14. Testing Strategy

Create:

`docs/testing/strategy.md`

The project needs more than normal unit tests.

Use multiple levels.

### Unit tests

Algorithms and domain behavior.

### Property/invariant tests

Examples:

* spans cannot exceed product hard limits;
* total cuts cannot exceed stock length including kerf;
* packaged quantities cannot under-supply demand;
* topology references must remain valid.

### Rule tests

Each rule should have examples and counterexamples.

### Golden scenarios

Known fence jobs with expert-approved output.

### Regression tests

Every expert correction that becomes generalized knowledge should potentially become a regression case.

### Integration tests

Full:

`Topology → Strategy → BOM`

pipelines.

### AI evaluation

Test structured extraction and rule-proposal behavior separately from deterministic correctness.

The LLM should never be used as the only judge of whether another LLM produced a correct engineering result.

---

# 15. Agent Execution Model

Once implementation starts, work iteratively.

For each task:

`read relevant architecture`

↓

`implement smallest coherent capability`

↓

`unit tests`

↓

`integration/scenario tests`

↓

`review against acceptance criteria`

↓

`update documentation`

↓

`commit/checkpoint`

Do not allow multiple agents to independently redesign the same component.

If subagents are available, use them primarily for bounded work such as:

* targeted research;
* test generation;
* code review;
* security review;
* algorithm evaluation.

Architecture ownership and integration should remain coherent.

---

# 16. Maintain Traceability

We should be able to trace:

`Product requirement`

↓

`Architecture component`

↓

`Design decision`

↓

`Implementation task`

↓

`Code`

↓

`Test`

This is particularly important because the product itself is intended to provide explainability and traceability.

Use IDs where useful for:

* requirements;
* ADRs;
* scenarios;
* tasks.

---

# 17. Avoid Premature Complexity

The architecture must support future sophistication, but the first implementation should establish the smallest strong foundation.

Avoid starting with:

* full CAD;
* full BIM;
* a massive ontology;
* autonomous self-learning;
* dozens of microservices;
* unnecessary distributed infrastructure;
* complicated multi-agent orchestration.

Prefer:

`simple core + strong abstractions + explicit extension points`

over:

`large generalized framework before real fence cases exist`.

---

# 18. Research and Design Gates

Do not move between phases simply because documents exist.

### Gate A — Research complete enough

We understand viable approaches and major tradeoffs.

### Gate B — Domain model viable

Representative fence cases can be represented without hacks.

### Gate C — Reasoning architecture viable

Rules, text, constraints, products and topology can jointly influence strategy.

### Gate D — Explainability viable

Every important generated structural choice can reference its causes.

### Gate E — BOM architecture viable

Cutting, packages, inventory and leftovers are represented correctly.

### Gate F — Learning loop viable

Expert corrections can safely become candidate reusable knowledge.

Only after these gates are reasonably satisfied should broad implementation begin.

---

# 19. Final Planning Deliverables

At the end of the planning phase I expect the repository to contain approximately:

```text
README.md

research/
    geometry-topology.md
    knowledge-representation.md
    rules-constraints.md
    optimization-bom.md
    product-modeling.md
    explainability-provenance.md
    learning-from-corrections.md
    ai-models.md
    open-source-landscape.md
    external-data-sources.md
    technology-evaluation.md

docs/
    architecture/
        system-design.md
        domain-model.md
        knowledge-system.md
        decision-model.md
        ai-layer.md

    adr/
        ...

    testing/
        strategy.md

    scenarios/
        ...

plan/
    implementation-roadmap.md
    dependency-graph.md

    tasks/
        ...
```

The exact structure may evolve if there is a good reason.

---

# 20. How to Work

Be rigorous but pragmatic.

Continuously distinguish:

**KNOWN**

from:

**ASSUMED**

from:

**PROPOSED**

from:

**UNRESOLVED**.

For technical recommendations:

* research first;
* cite sources;
* compare alternatives;
* state tradeoffs;
* make a recommendation.

Do not generate large amounts of generic architecture prose.

Every design artifact should help us make a decision or implement something.

When uncertain, investigate with a concrete scenario rather than inventing abstractions.

Most importantly:

**Preserve the central product philosophy:**

The user defines the physical topology and intent.

The system proposes an editable construction strategy.

Structured rules, textual knowledge, products and constraints jointly inform that strategy.

Every important decision is explainable.

Expert corrections improve explicit system knowledge over time.

The deterministic system remains responsible for things that must be correct; AI is used where interpretation, discovery and flexible reasoning actually add value.
