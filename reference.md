

```text
┌──────────────────────────────────────────────────────────┐
│                  KNOWLEDGE PLATFORM                      │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Shared Semantic Model / Domain Language            │  │
│  │                                                    │  │
│  │ Product, Component, Role, Assembly, Slot,          │  │
│  │ Interface, Dimension, Material, Constraint,        │  │
│  │ Installation Method, Topology Concept, Units       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Product Definitions        Assembly / Fence Models      │
│  Compatibility              Installation Knowledge       │
│  Rules and Constraints      Manuals and Evidence         │
│  Terminology / Synonyms     Provenance and Versions      │
│                                                          │
│  Search / Retrieval / Evaluation / AI APIs               │
└───────────────────────────┬──────────────────────────────┘
                            │ published versioned snapshot
                            ▼
┌──────────────────────────────────────────────────────────┐
│                 PLANNING / BOM PLATFORM                  │
│                                                          │
│  Project and Map                                         │
│  Actual Topology                                         │
│  Planning Runs                                           │
│  Strategy and Decisions                                  │
│  Requirement Generation                                  │
│  Product Selection                                       │
│  Cutting / Packaging / Inventory Allocation              │
│  Final BOM                                               │
└───────────────────────────┬──────────────────────────────┘
                            ▼
                         ┌─────┐
                         │ UI  │
                         └─────┘
```

# The shared language

There should be a small, explicit **Semantic Core** or **Domain Kernel** containing the concepts that every subsystem understands.

For example:

```text
ProductDefinition
ProductVariant
SKU
ComponentRole
AssemblyDefinition
AssemblySlot
InterfaceDefinition
Compatibility
Quantity
Unit
Dimension
Material
Constraint
InstallationMethod
TopologyElementType
Requirement
EntityReference
VersionReference
ProvenanceReference
```

This means that `rail`, `post`, `panel`, `gate`, and `bracket` are not merely strings appearing independently in different tables.

They have stable semantic identities:

```text
ComponentRole:
    id: role:horizontal_rail
    parent: role:structural_member
    orientation: horizontal
```

An assembly slot can reference that role:

```text
AssemblySlot:
    id: slot:panel.top_rail
    accepts_role: role:horizontal_rail
    quantity: 1
```

A product can implement it:

```text
ProductDefinition:
    id: product:acme.rail.2x6
    fulfills_roles:
      - role:horizontal_rail
```

A rule can target it:

```text
Constraint:
    target_role: role:horizontal_rail
    condition:
      wind_zone >= 3
    requirement:
      max_unsupported_span <= 1800 mm
```

And the planner can request it:

```text
Requirement:
    role: role:horizontal_rail
    required_length: 1760 mm
    required_interfaces:
      - interface:panel_post_connection
```

That is the shared language.

# One concept, several representations

The critical issue is that the word **product** can mean several different things.

## 1. Product definition — Knowledge

This describes what the product is:

```text
ProductDefinition
    semantic category
    dimensions
    material
    profile
    supported component roles
    connection interfaces
    compatible products
    installation properties
    structural properties
```

This belongs in the Knowledge Platform.

## 2. SKU or commercial catalog item

This describes how it is sold:

```text
CatalogItem
    SKU
    manufacturer
    package quantity
    stock length
    finish
    color
    supplier
    price
    active/discontinued
```

This may be a Catalog module **inside the Knowledge Platform**, particularly if the Knowledge Platform is your reusable domain-data platform.

Some rapidly changing values—price, live availability, warehouse quantity—may remain in an operational service while still referencing the same product identity.

## 3. Inventory item

This describes what physically exists:

```text
InventoryItem
    SKU
    warehouse
    lot
    quantity
    condition
    remnant length
    reservation status
```

This is operational state, not reusable knowledge.

## 4. Planned component

This describes how the product is used in a specific project:

```text
PlannedComponent
    project
    planning run
    assembly slot
    selected product version
    selected SKU
    cut length
    location on map
```

This belongs to Planning/BOM.

So all four objects speak the same language, but they are not the same record.

# Assemblies work the same way

There are also multiple meanings of “assembly.”

## Reusable assembly definition — Knowledge

```text
FencePanelDefinition
    2 × post roles
    2 × rail roles
    2 × bar roles
    N × infill roles
    connection interfaces
    slot ordering
    dimensional formulas
    allowed substitutions
```

This belongs in the Knowledge Platform.

## Fence model or product-system variant — Knowledge

```text
FenceModelVersion
    uses FencePanelDefinition
    allowed post product families
    allowed rail profiles
    nominal height
    allowed span range
    installation variants
```

Also reusable knowledge.

## Assembly instance — Planning

```text
PanelInstance
    project: P17
    span: S12
    width: 1760 mm
    model_version: privacy-panel-v3
    selected products
    installation decisions
```

This belongs to Planning/BOM.

The planner does not redefine what a fence panel means. It instantiates a versioned reusable assembly definition.

# Where should the shared models live?

I would introduce an explicit module called something like:

```text
domain-language
semantic-core
domain-kernel
shared-contracts
```

Conceptually:

```text
                   ┌───────────────────────┐
                   │   Semantic Core       │
                   │                       │
                   │ IDs, types, roles,    │
                   │ units, relations,     │
                   │ predicates, refs      │
                   └───────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
      Knowledge Platform   Planning/BOM         UI/API
      Catalog module       Runtime models       View models
      Assembly models
      Rules
```

The Knowledge Platform can be the **governance home** of this shared language, but the Semantic Core should remain a small, dependency-light contract rather than requiring every component to import the entire Knowledge implementation.

For example:

```text
semantic-core/
    identity
    quantities
    units
    component-roles
    interfaces
    entity-references
    predicates
    version-references

knowledge/
    sources
    products
    assemblies
    installation-methods
    compatibility
    constraints
    provenance
    publishing

planning/
    projects
    topology
    planning-runs
    strategies
    decisions
    requirements
    fulfillment
    bom
```

# Shared contracts, not shared ORM entities

A trap would be to place all database ORM classes in one package and import them everywhere:

```text
planning imports KnowledgeProduct ORM
BOM directly queries KnowledgeAssembly tables
UI modifies KnowledgeRule rows
```

That creates strong persistence coupling.

Instead, share explicit contracts:

```text
ProductDefinitionDTO
AssemblyDefinitionDTO
KnowledgeSnapshot
Requirement
EntityRef
VersionRef
Quantity
ConstraintEvaluation
```

These can be represented through:

- JSON Schema;
    
- Pydantic/domain models;
    
- Protobuf;
    
- OpenAPI schemas;
    
- generated SDK types;
    
- an internal schema registry.
    

The exact technology is secondary. The important part is that there is **one semantic definition** for each shared concept.

# Do not make the semantic model entirely generic

Another trap is attempting to represent the whole system as:

```text
entities
attributes
relationships
```

with every value stored in generic JSON or EAV rows.

That looks flexible but makes critical engineering logic difficult to validate and query.

A better hybrid is:

```text
Generic semantic infrastructure:
    semantic_type
    relation_type
    terminology
    entity_reference
    provenance
    source evidence

Typed domain models:
    product_definition
    product_dimension
    assembly_definition
    assembly_slot
    interface_definition
    compatibility_rule
    installation_method
    constraint_definition
```

The generic layer provides common meaning and extensibility. The typed models enforce correctness for important domain concepts.

# A concrete example

Suppose a manual says:

> Rail R3000 may be used as the top or bottom rail in Privacy Series panels. Maximum unsupported span is 1,800 mm in Wind Zone 3.

The Knowledge Platform stores:

```text
ProductDefinition:
    product:rail-r3000
    roles:
      - top_rail
      - bottom_rail
    stock_length: 3000 mm
    interfaces:
      - privacy_panel_post_connection

Compatibility:
    product:rail-r3000
    compatible_with:
      assembly_family:privacy_series

Constraint:
    target: role:horizontal_rail
    applies_when:
      product = product:rail-r3000
      wind_zone = 3
    effect:
      max_unsupported_span = 1800 mm

Evidence:
    manual X
    version 4
    page 17
    table 3
```

The fence model says:

```text
AssemblyDefinition:
    privacy_panel
    slots:
      - top_rail: role:horizontal_rail
      - bottom_rail: role:horizontal_rail
      - left_post: role:post
      - right_post: role:post
      - infill: role:vertical_infill
```

The planner receives a project span of 1,760 mm and creates:

```text
AssemblyInstance:
    assembly: privacy_panel
    width: 1760 mm
    knowledge_snapshot: KS-42

Requirement:
    role: horizontal_rail
    quantity: 2
    required_finished_length: 1760 mm

SelectedProduct:
    product_definition: rail-r3000
    catalog_sku: R3000-WHITE
```

Fulfillment then decides:

```text
Purchase:
    2 × R3000-WHITE

Cuts:
    rail 1: 1760 mm
    rail 2: 1760 mm
```

Every stage uses the same product, role, assembly, quantity, and interface semantics.

# The corrected architectural statement

I would now describe your three main components like this:

## Knowledge Platform

Owns reusable, versioned domain intelligence:

- shared semantic language;
    
- product engineering definitions;
    
- catalog/master data;
    
- assemblies and fence models;
    
- component roles and interfaces;
    
- compatibility;
    
- installation methods;
    
- rules and constraints;
    
- source documents and visual evidence;
    
- provenance;
    
- terminology and synonyms;
    
- publishing, indexing, retrieval, and AI APIs.
    

## Planning/BOM Platform

Owns project-specific application:

- project input;
    
- map and topology;
    
- selected knowledge snapshot;
    
- planning strategy;
    
- decisions and explanations;
    
- assembly instances;
    
- requirements;
    
- product/SKU selections;
    
- cuts and packaging;
    
- inventory allocation;
    
- purchase BOM and final output.
    

## UI

Allows users to:

- maintain Knowledge;
    
- review extracted knowledge;
    
- define or edit products and assemblies;
    
- configure projects;
    
- inspect planner decisions;
    
- override results;
    
- approve BOMs;
    
- compare versions and scenarios.
    

# The key rule

The rule I would use is:

> **Knowledge owns definitions. Planning owns instances.**

More precisely:

```text
Knowledge:
    What is a post?
    What is this product?
    What is a panel assembly?
    Which roles can this product fulfill?
    Which products are compatible?
    What installation methods exist?
    What constraints apply?

Planning:
    Which post is placed here?
    Which panel model is instantiated on this span?
    Which product version was selected?
    What cut is required?
    What must be bought?
```

