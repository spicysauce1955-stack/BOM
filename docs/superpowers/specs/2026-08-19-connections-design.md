# Connections — how the pieces of a panel are put together

Date: 2026-08-19. Status: design, awaiting review.
Arc B of three (A: the picker repair, shipped separately. B: this. C: item tolerance).

A panel is an assembly, and this system has no word for *assembled*. It describes each
piece on its own — this board is 100 wide, that rail has a 12 mm groove — and hopes the
numbers line up. Every fact about two pieces MEETING is stored as an adjective on one of
them, scattered over three objects and ten fields.

This arc gives the relationship a name. A **connection** says two pieces meet, where they
meet, how, and by how much. From that, a cut length is arithmetic nobody authors, a
tongue-and-groove board becomes expressible for the first time, and three of the panel's
authoring refusals become states the schema cannot hold.

---

## 1. What is smeared, and where

| field | on | what it really says |
|---|---|---|
| `joint: butt \| channel \| groove \| bracket \| overlap` | `FrameSlot`, `Member` | how this piece meets the one it lands on |
| `channel_depth_mm` | `FrameSlot` | how deep the housing that receives another piece is |
| `insertion_margin_mm` | `FrameSlot` | clearance so the received piece can be tipped in |
| `base_engagement_mm`, `top_engagement_mm` | `Member` | how far the piece goes into what it lands on |
| `base_ref`, `top_ref` | `Member` | WHICH pieces it lands on |
| `length_rule`, `overlap_mm` | `PartRequirement` | how long it is therefore cut |
| `gap_after_mm` | `Member` | spacing to its neighbour — *"MAY be negative: an overlap"* |
| `FixingRule.basis: per_member_crossing` | `FixingRule` | a screw wherever two pieces cross |

Ten fields, three objects, one absent concept. Three symptoms follow from that:

**Two of the five `joint` values are refused as unbuilt.** `_unsupported_features` rejects
`bracket` and `overlap` because *"neither has a field that could make it mean anything, and
a kind with no numbers behind it is a butt joint wearing a better name."* They have no
numbers because a slot is the wrong place to put them — the numbers belong to the meeting,
not to either piece.

**One rule already derives its length from the joint.** `between_frame` computes
`(top − base) − half each face + both engagements`. So for one of five cases the length is
already a consequence of how the pieces meet. The other four have no joint object for the
post relationship, so they get named rules instead.

**Board-to-board is inexpressible.** The nearest thing is a negative `gap_after_mm`, which
gets the spacing right and says nothing about the boards being joined. The panel-canvas
design records dropping tongue-and-groove and dogear from the starter templates because
*"the panel model does not express a board profile."*

---

## 2. What a connection is

Two endpoints, how they meet, and by how much.

```python
class Endpoint(BaseModel):
    # exactly one of `slot` or `bay` — refused at load if both or neither
    slot: str | None = None                       # a slot key: a rail, a member, the post
    bay: Literal["ground", "top"] | None = None   # the bay itself, which is not a slot
    at: Literal["end", "body", "edge"] = "end"
    datum: Literal["centre", "face"] | None = None  # against a post only; None elsewhere
    clearance_mm: Mm = 0                          # assembly slack AT THIS END (§6)

class Connection(BaseModel):
    a: Endpoint
    b: Endpoint
    how: Literal["butts", "laps", "housed", "interlocks", "bracketed"] = "butts"
    amount_mm: int = 0            # signed; see the sign rule below
```

**The sign rule, stated once.** `amount_mm` is *how far past its datum the piece ends*.
Positive runs past or seats in; negative stops short. So `laps +50` runs 50 past the post,
`housed +12` seats 12 into a rail, and `butts −10` holds back 10 — the gate trade's
*finish size = opening − allowance*. `laps` and `housed` require a positive amount and
`butts` permits any sign, because "laps by −10" is a sentence with no meaning.

**One connection per end, and the invariant that follows.** A piece that is cut to length
has two ends, so it is named by exactly two `end` connections. A piece named by fewer has
no resolvable length, and that is refused at load — the same guardrail
`length_rule`-with-no-refs gives today, said once for all cases instead of twice for one.
`body` and `edge` connections are additional and unbounded: a slat may cross four rails.

Connections are a list on `PanelSpec`, beside `frame`, `infill` and `fixings` — first
class, so *"what does this rail meet?"* is a question that can be asked.

**The post needs no special case.** It is already a slot (`FenceModel.post: PostSlot`), so
`Endpoint(slot="post")` is an ordinary reference. Only `ground` and `top` name the bay,
because the bay is not part of the panel.

### The kind of joint is derived, never stored

Timber-framing CAD classifies a joint by which parts of the two members meet, and we
borrow the taxonomy rather than invent one:

| | a meets | b meets | our case |
|---|---|---|---|
| **L** | end | end | two rails meeting on one post centre |
| **T** | end | body | a rail's end at a post · a slat's end at a rail |
| **X** | body | body | a slat crossing a rail — the crossing that earns a screw |
| **E** | edge | edge | tongue-and-groove, shiplap, board-on-board |

L/T/X is COMPAS Timber's vocabulary. **E is ours**, and it is the one timber framing does
not need: beams meet at points, boards interlock along their length. Adding it is the
reason board-to-board becomes expressible.

Nothing stores the letter. It falls out of the two `at` values, so it can never disagree
with them.

---

## 3. Length becomes arithmetic

A piece's length is the distance between what its two ends meet, adjusted by how they meet
it. Every current rule maps over with nothing lost:

| today | as connections |
|---|---|
| `centre_to_centre` | two connections, each `butts` the post at `datum="centre"` |
| `clear_between_posts` | two connections, each `butts` the post at `datum="face"` |
| `overlap`, `overlap_mm: 50` | two connections, each `laps` the post, `amount_mm: +50` |
| `panel_height` | ends meet `bay="ground"` and `bay="top"` |
| `between_frame` + refs + engagements | ends `housed` into two named slots, `amount_mm: +engagement` |

And one thing becomes sayable that is not today: **held back 10 mm each end**,
`amount_mm: −10`. The chain-link trade needs it — *gate finish size = opening − allowance*
— and our unsigned `overlap_mm` cannot express it.

**The arithmetic is the one `_between_frame_extent` already performs**, generalised from
"between two frame members" to "between two endpoints". That function also returns WHERE
the piece starts, and it must keep doing so from the same calculation: the elevation draws
the rectangle the cut list buys, or the picture starts lying about the panel it is derived
from.

**The slope correction stops being an if-chain.** Today it applies to three of five rules
by name. It becomes a property of the endpoints: a connection between two POSTS runs along
the fence line and takes the correction; one between two frame members measures inside the
panel, where both ends slope together, and does not. That is the same answer the resolver
gives today, derived instead of enumerated.

---

## 4. What this deletes

* **`length_rule` and `overlap_mm`** — a compressed instruction for the calculation above.
* **`base_ref` / `top_ref`** — naming what a piece meets IS the connection.
* **`gap_after_mm`'s second meaning.** It keeps its first — spacing between neighbours —
  and loses the negative-means-overlap trick to an `E` connection, which says the boards
  are joined rather than merely close.
* **The dead half of `JointKind`.** `bracket` and `overlap` gain a home for their numbers
  and stop being refused; `how` replaces the enum.
* **Three authoring refusals become unrepresentable** rather than validated: a frame slot
  declaring `between_frame` with nothing to measure between, an infill member declaring it
  without both refs, and refs carried under a rule that ignores them.

`FixingRule.basis` **stays as it is.** An `X` connection is a crossing, so
`per_member_crossing` could be derived from connections — but the other five bases are not
crossings, and converting fixings would double this arc. Named here so the overlap is
deliberate rather than missed.

---

## 5. Edge connections, and where a profile lives

A board interlocking with its neighbour is an `E` connection: `interlocks`, with an amount.

**The amount is on the connection; the profile is on the item.** A 12 mm tongue and a
12 mm rebate are different cuts and different products, but that is a fact about what you
BUY, not about the panel's design. So the connection says *interlocks by 12*, an item
declares its own profile, and the two are matched by the **interface token** the part
library already has — `interface: "vinyl-routed-5x5"`, a token both sides declare.

This keeps the rule the part library set and must not lose: **no pair table.** A connection
does not enumerate which items fit which. It states a requirement once, and items qualify
or do not, exactly as a part's spec works.

**An edge connection changes effective coverage**, and the infill fit must read it: two
100 mm boards overlapping 20 cover 180, not 200. Today the fit learns this from
`gap_after_mm = −20`; afterwards it learns it from the connection. Same number, said as a
fact about the pair rather than a property of one of them.

---

## 6. Clearance is an assembly fact

`insertion_margin_mm` exists today with a comment explaining a trick: clearance at the
bottom of a channel *"so the member can be tipped in"*. That is not geometry. It is how the
thing goes together — you drop the piece into the deep end and lift it into the shallow
one.

So `clearance_mm` sits on the **endpoint**, not the connection — a connection has two ends
and they need not be equally slack, which is precisely the trick: one end deep, one end
shallow.

**And it earns a refusal the system cannot currently make:** a piece housed at both ends
with clearance at neither cannot be assembled at all. Today that model publishes cleanly
and the shop discovers it. With clearance on the connection it is a load-time error.

**Assembly ORDER is not stored.** It is derivable — you enter the end with more clearance
first — and a second authority over it would drift from the numbers that decide it.

---

## 7. The author states them, the system suggests

Connections are authored data. The system proposes them and never applies one silently.

* Add an infill member to a panel that already has two horizontal frame slots → propose
  *"housed into the bottom rail and the top rail"*, because a vertical member between two
  horizontal slots has one obvious pair of ends.
* Drag a rail's end past a post on the canvas → propose *"laps 50 past the post"*.
* Every connection renders as a badge on the drawing: visible, editable, deletable.

This is the mitigation the research pointed at. SketchUp's inference engine is the proof
that gesture-captured constraints work, and its decade-old top-voted complaint is that you
cannot see or disable what it chose. A proposal you accept is not an inference you did not
notice.

**Nothing is proposed for a case with more than one sensible answer.** A member between
three rails has no obvious pair, so the author says which — proposing one and being wrong
teaches an author to distrust every proposal.

---

## 8. Migration, and the gate

Every current model maps onto §3's table mechanically, so migration emits connections from
the fields it deletes. The demo models carry four shapes: rails centre-to-centre, slats
`between_frame` with engagements, a channelled variant, and the routed vinyl line.

**The acceptance test is the compatibility gate, byte-identical on BOM, decision graph and
resolved geometry.** This arc changes how a length is DESCRIBED and not what it is; every
golden scenario must produce the identical fence. Anything that moves is a bug in the
migration.

Run identity is expected to hold too — unlike the part library, this adds no new input to
the digest.

---

## 9. Out of scope, by name

* **Item tolerance** — ranges on an item's dimensions, containment matching, opt-in per
  item. Arc C, and independent of everything here.
* **Converting fixings to connections** — §4.
* **A board profile in the catalog.** This arc makes the CONNECTION expressible; a product
  that declares it is a catalog change, and a tongue-and-groove starter template is a
  catalog change first and a template second.
* **The canvas gesture itself.** §7 specifies what a proposal is and when it appears; the
  drag interaction that produces one is the authoring-surface arc.
