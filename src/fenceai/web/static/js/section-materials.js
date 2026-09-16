// WHAT GETS CUT FOR ONE STRETCH — the materials block on an office job card.
//
// The office opens a job it did not draw. The card beside the map already says
// how long the stretch is, what it stands on and what it looks like from the
// side; this says what the yard will CUT for it. Without it the only answer to
// "what is this bit of fence made of" is the BOM tab, which is a flat list for
// the whole job sorted by sku — the right shape for placing an order and the
// wrong one for the question a person asks while looking at a drawing.
//
// **It shows cut PIECES. It never shows money, and it never shows bars.**
// Both are pooled across the whole job and neither can be apportioned to a
// stretch by re-sorting:
//
//   * money. `js/tabs.js` already refused a per-section price in as many words —
//     "an apportionment nothing measured" — because a BOM line is a PURCHASE.
//     One bag of screws is bought once for a fence; a third of it is not a fact
//     about section B.
//   * bars purchased. The same argument, one level down. A cut piece is real —
//     somebody walks to a saw and makes it — but the BAR it came out of is not
//     the stretch's. `report/structure.py::Part` carries `from_bars` (which bar
//     of the cut plan this piece came off) and `shared_with` (the other elements
//     the same physical piece serves), and those two fields exist precisely
//     because an offcut shared between two sections belongs to neither. A card
//     that printed "2 bars" would be inventing the division the cut plan
//     deliberately does not make.
//
// So: sku, count, cut length. What gets BOUGHT stays on the BOM, where it is
// true, and the card says so rather than leaving the reader to wonder whether
// the numbers should add up to a purchase order.
//
// **Pure half, separable.** `linesForRun` is arithmetic over the grouped BOM and
// touches no DOM — the same contract `bayRects` keeps in `js/section-elevation.js`,
// and the reason both are testable in node instead of only in a browser. It does
// not import `state.js`. (`i18n.js` and `units.js` are imported for the RENDER
// half only; both load under bare node, so importing them costs the pure half
// nothing.)
//
// **House style, not a screen.** Like `js/elevation.js` and
// `js/section-elevation.js`, `renderSectionMaterials` creates and RETURNS a
// detached element. It subscribes to nothing, reads no application state, owns
// no DOM id, and takes its one piece of interactivity as an opt-in callback. The
// caller decides where the element goes and when it is rebuilt — which is what
// lets a card re-render on `locale-changed` without this module knowing that
// event exists.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { tagOf } from "./structure-data.js";
import { fmt, roleWord, sentence, unitLabel } from "./units.js";

// ------------------------------------------------------------------ pure half

/**
 * @typedef {object} CutPiece
 * @property {string} sku
 * @property {number} qty        count of pieces, or a length when `unit` is "mm"
 * @property {string} unit       "each" | "cut" | "application" | "mm"
 * @property {string} role       post | cap | concrete | rail | screw | infill | …
 * @property {string} slotKey    which part of the panel this is, when it is one
 * @property {?number} cutLengthMm
 * @property {?string} lengthBasis  "width" | "slope"
 * @property {string[]} sharedWith  other elements this same physical piece serves
 */

/** The section groups for one run, as plain data.
 *
 *  @param {?{groups?: object[]}} grouped a `GroupedBom` (`report/bom_groups.py`)
 *  @param {?string} runId the run this card is about — `Section.run_id`
 *  @returns {{runId: string, state: ("no-run"|"no-lines"|"lines"),
 *             lines: CutPiece[]}}
 *
 *  **Selection is by `element_id`, and that is the key fact about this data.** A
 *  group with `kind: "section"` carries a RUN id in `element_id`, not a section
 *  tag — `bom_groups.py` says why at length: `js/structure-data.js` is the one
 *  tag source for the whole app, and a second tag derivation is how the schedule
 *  and this card would come to disagree about which stretch is "B". So the match
 *  is `runId`, and the tag is the caller's to print.
 *
 *  **`node` and `gate` groups are deliberately left out.** They are not an
 *  oversight and they must not be folded in:
 *
 *    * a `node` group is a post standing where two runs meet. `Post.run_ref` is
 *      `node:<id>` — the strategy's own answer that it belongs to NEITHER run —
 *      and adding it to the card of every run that touches the node would count
 *      one post twice across two cards. That is the first of the two asymmetries
 *      the office-screen design warns about, and the reason the grouped BOM
 *      names a "shared posts" bucket instead of picking a side.
 *    * a `gate` group is a standalone gate: `run_ref is None`, in no section at
 *      all. Hanging it off the nearest stretch would contradict the data to make
 *      a screen tidier.
 *
 *  Both are real materials for the job and both live on the BOM. The card links
 *  there rather than quietly absorbing them.
 *
 *  **Three states, never two.** "This job has no worked-out plan" and "this
 *  stretch asks for nothing" are different answers, and only the first means
 *  somebody has to press Generate. Collapsing them into an empty array is the
 *  shape of audit finding B01 — a failed read rendering as "nothing is wrong" —
 *  and `js/job-screen.js` already splits the same pair twice (`flagsRunId`,
 *  `status`). Loading is NOT one of these states, because it is not a property
 *  of the data: see `renderSectionMaterials`.
 */
export function linesForRun(grouped, runId) {
  const run = String(runId ?? "");
  // No run id and no grouped BOM are the same answer for the same reason:
  // nothing has been worked out for this job yet. A card asked about a run the
  // caller cannot name has no plan behind it either.
  if (!run || !grouped || !Array.isArray(grouped.groups)) {
    return { runId: run, state: "no-run", lines: [] };
  }
  const raw = [];
  for (const group of grouped.groups) {
    if (group?.kind !== "section" || String(group.element_id ?? "") !== run) continue;
    for (const line of group.lines || []) raw.push(cutPiece(line));
  }
  const lines = merged(raw);
  return { runId: run, state: lines.length ? "lines" : "no-lines", lines };
}

/** One wire line, normalised.
 *
 *  `shared_with` is read off the line because that is the field that says a
 *  piece is shared, and nothing else can. It is `report/structure.py::Part`'s
 *  own name for it — the other elements one physical piece serves, inverted from
 *  the demand line's `pegs` — and a client MUST NOT invert the pegs itself: the
 *  `/bom` route says so on the way out ("a second inversion of them in JS is how
 *  the two views would come to disagree about which bay bought a rail").
 *
 *  `bom_groups.GroupedLine` did not carry the field until this branch added it, so today every line
 *  reads as unshared and no row is marked. That is the honest failure — a count
 *  that is right per stretch and silent about one piece serving two of them —
 *  rather than the dishonest one, which would be guessing sharing from the merge
 *  key. Two stretches of a symmetric fence legitimately want the same sku at the
 *  same cut length, and a card that called that "shared" would tell a person the
 *  two rails in front of them are one rail.
 */
function cutPiece(line) {
  const shared = line?.shared_with ?? line?.sharedWith ?? [];
  return {
    sku: String(line?.sku ?? ""),
    qty: Number(line?.qty) || 0,
    unit: String(line?.unit ?? ""),
    role: String(line?.role ?? ""),
    slotKey: String(line?.slot_key ?? ""),
    cutLengthMm: line?.cut_length_mm == null ? null : Number(line.cut_length_mm),
    lengthBasis: line?.length_basis == null ? null : String(line.length_basis),
    sharedWith: (Array.isArray(shared) ? shared : []).map(String).filter(Boolean),
  };
}

/** One row per (sku, unit, role, cut length, length basis, sharing).
 *
 *  **Deliberately a SHORTER key than the backend's**, and this is the one place
 *  this module recomputes anything. `bom_groups._merged` keys on `slot_key` too,
 *  because the setting-out schedule reports parts per element and "rail#0" and
 *  "rail#1" are different rows there. A card is not that sheet: it answers "what
 *  will the yard cut for this stretch", and two rows reading `RAIL-3050 · rail ·
 *  4 · 2400 mm` one above the other look like the same line entered twice. A
 *  reader who counts them gets eight rails. Summing across slots is sound —
 *  those are genuinely distinct pieces of the same product at the same length —
 *  and the slot survives on each `CutPiece` for anything that wants it.
 *
 *  **`length_basis` stays in the key**, for the reason `bom_groups.py` keeps it:
 *  a raked bay's rail is cut ON THE SLOPE, so two pieces of the same nominal
 *  length are two different cuts and merging them would report one.
 *
 *  **Sharing stays in the key too**, and that is rule 3 of this module's
 *  existence. A piece serving several elements must not be absorbed into the
 *  count of pieces that serve one, because the whole point of marking it is that
 *  the reader should not add it to another card's total.
 */
function merged(lines) {
  const out = new Map();
  for (const line of lines) {
    const key = [line.sku, line.unit, line.role, line.cutLengthMm,
                 line.lengthBasis, [...line.sharedWith].sort().join(",")].join(" ");
    const seen = out.get(key);
    if (seen) seen.qty += line.qty;
    else out.set(key, { ...line, sharedWith: [...line.sharedWith] });
  }
  // The same leading sort key the backend already used, so a stretch reads in
  // the same order here as it does in the grouped BOM panel. A surface that
  // invented its own idea of "most important first" would be a second answer to
  // a question nobody asked it.
  return [...out.values()].sort((a, b) =>
    a.sku.localeCompare(b.sku)
    || (a.cutLengthMm ?? -1) - (b.cutLengthMm ?? -1)
    || a.unit.localeCompare(b.unit)
    || a.role.localeCompare(b.role));
}

// ---------------------------------------------------------------- the element

/** A `unit` as a word in the reader's language, or the raw token.
 *
 *  Same mechanism as `units.js::roleWord` and `enumWord`, one namespace along:
 *  `t()` returns the KEY on a miss, so an unregistered unit shows itself rather
 *  than printing `unit.bundle` at somebody. Units are an open vocabulary — a new
 *  one arrives with a new product kind and needs no amendment — so a miss is the
 *  expected case, not a bug.
 *
 *  It is NOT `units.js::unitLabel`, which is the mm/cm DISPLAY preference. The
 *  two collide in exactly one place and the collision matters: a line whose unit
 *  is literally `"mm"` is a LENGTH, not a count, and it is `unitLabel` that has
 *  to render it — see `qtyCells`.
 */
function unitWord(unit) {
  if (!unit) return "";
  const key = `unit.${unit}`;
  const word = t(key);
  return word === key ? unit : word;
}

/** The count and the unit, together, because they have to agree.
 *
 *  Lifted from `js/tabs.js::qtyCells`, which carries the scar: a qty is a COUNT
 *  ("8 each") unless its unit says it is a length, and putting every qty through
 *  the mm→display converter reported `0.8 each` to anybody who had switched the
 *  app to cm — wrong by a factor of ten, on the one surface built to answer
 *  "what does this stretch need". When the unit IS `mm` the number must be
 *  converted AND the label swapped, or a converted figure sits under a literal
 *  "mm" while the same screen says cm elsewhere.
 */
function qtyCells(qty, unit) {
  return unit === "mm"
    ? `<td class="num">${esc(fmt(qty))}</td><td>${esc(unitLabel())}</td>`
    : `<td class="num">${esc(String(qty))}</td><td dir="auto">${esc(unitWord(unit))}</td>`;
}

/** What the yard cuts for this piece, in the reader's display unit.
 *
 *  `sentence()` rather than `esc(tu(...))`: a figure dropped into a Hebrew line
 *  needs `<bdi>` around it or it reorders against the punctuation beside it, and
 *  escaping AFTER interpolating is the bug `units.js::sentence` exists to
 *  prevent. The locale string carries `{len_mm} {u}` and never a literal unit.
 *
 *  A cut "on the slope" is called out because it is a different piece from a cut
 *  of the same nominal length across the width — a raked bay's rail is longer
 *  than the bay is wide, and an installer who cuts to the nominal number has
 *  wasted the bar.
 */
function cutText(line) {
  if (line.cutLengthMm == null) return "";
  const len = sentence("job.materials_cut", { len_mm: line.cutLengthMm });
  return line.lengthBasis === "slope"
    ? `${len} <span class="meta">${esc(t("job.materials_on_slope"))}</span>`
    : len;
}

/** The row that stops a shared piece being counted twice.
 *
 *  A piece that serves several elements appears in each of their groups whole —
 *  a continuous rail crossing three bays is ONE rail and pegs to all three
 *  (contract obligation 14). Per stretch that is the right number; read across
 *  two cards it is the same rail counted twice, and the only thing standing
 *  between a reader and that mistake is the row saying so. `report/structure.py`
 *  makes the identical call on the setting-out sheet and for the identical
 *  reason: "would read as one piece per bay unless the row says otherwise".
 *
 *  The elements it also serves are named rather than counted, because "shared
 *  with 2 others" sends a reader hunting and `A/B3` does not. With
 *  `onSelectElement` they become buttons to those elements; without it they are
 *  inert ids. Ids get `.sku` + `<bdi>` like every other identifier in this app —
 *  RTL must not reorder `span@run1:0-1500` into a different-looking id.
 */
function sharedRow(line, interactive) {
  // The element's TAG, falling back to its id. The docstring above argues that
  // naming beats counting because "`A/B3` does not send a reader hunting" — and
  // then printed `span@ra:0-1500`, which does. `structure-data.js: tagOf` is the
  // one place that translation lives; `warnings.js` already uses it for exactly
  // this, and it answers the id back when no structure report is loaded.
  const label = (id) => tagOf(id) || id;
  const chips = line.sharedWith.map((id) => (interactive
    ? `<button type="button" class="section-materials-share-chip sku"
              data-element="${esc(id)}">${esc(label(id))}</button>`
    : `<bdi class="sku">${esc(label(id))}</bdi>`)).join(" ");
  // One is the common case — `_shared_with` returns the pegs outside this
  // section — and "it also serves 1 other elements" is the plural bug this
  // bundle has a house pattern for (`strategy.posts_one`).
  const note = line.sharedWith.length === 1
    ? "job.materials_shared_note_one" : "job.materials_shared_note";
  return `<tr class="section-materials-share-row">
      <td colspan="4">
        <span class="section-materials-shared">${esc(t("job.materials_shared"))}</span>
        <span class="meta">${sentence(note, { n: line.sharedWith.length })}</span>
        ${chips}
      </td>
    </tr>`;
}

/** A detached element listing what gets cut for this stretch.
 *
 *  @param {?{groups?: object[]}} grouped a `GroupedBom`, or null when the job has
 *         no worked-out run
 *  @param {?string} runId the stretch's `run_id`
 *  @param {{onSelectElement?: (elementId: string) => void, loading?: boolean}} [opts]
 *  @returns {HTMLElement} a `<section>`, unattached, carrying `data-state`
 *
 *  **Four answers, and `data-state` is where they are legible.** `"loading"`,
 *  `"no-run"`, `"no-lines"`, `"lines"`. The first three all render as a short
 *  sentence and would otherwise be indistinguishable to anything reading the
 *  DOM — including the reader, who needs to know whether to press Generate, to
 *  wait, or to accept that this stretch genuinely needs nothing.
 *
 *  **Loading is the CALLER's fact, not the data's**, which is why it arrives as
 *  an option instead of being inferred from a null `grouped`. A half-loaded
 *  fetch passed in as "nothing" would render "this job has not been worked out",
 *  which is `js/job-screen.js`'s own stated failure mode — a wrong answer shaped
 *  exactly like a right one. The option exists so a caller can say "not yet"
 *  without this module having to guess, and it reuses `job.loading` rather than
 *  minting a second word for the same wait.
 *
 *  `onSelectElement` is the ONLY interactivity and it is opt-in, like
 *  `onSelectBay` on the side view. Without it the block is inert, which is what a
 *  reading surface wants; with it, the elements a shared piece also serves become
 *  buttons. It is also the seam for the bay-level drill-down the office-screen
 *  design names but defers — an element id is what `/explain/{element}` already
 *  takes.
 */
export function renderSectionMaterials(grouped, runId, opts = {}) {
  const box = document.createElement("section");
  box.className = "section-materials";
  const read = linesForRun(grouped, runId);
  const state = opts.loading ? "loading" : read.state;
  box.dataset.state = state;

  const head = `<h4 class="section-materials-title">${esc(t("job.materials"))}</h4>`;

  if (state !== "lines") {
    // Said out loud, one sentence each. An empty block would read as "this
    // stretch needs nothing" in all three cases, and two of the three are not
    // that.
    const key = state === "loading" ? "job.loading"
      : state === "no-run" ? "job.materials_no_run"
        : "job.materials_none";
    box.innerHTML = `${head}<p class="meta section-materials-empty">${esc(t(key))}</p>`;
    return box;
  }

  const interactive = typeof opts.onSelectElement === "function";
  const rows = read.lines.map((line) => {
    // The role beside the sku because a sku is opaque to the office and "rail"
    // is not. `roleWord` and not the raw token: `role` is a backend enum, and
    // printing `rail` in a Hebrew-first UI is untranslated English in the cell
    // that a reader scans first.
    const row = `<tr class="section-materials-row"${
        line.sharedWith.length ? ' data-shared="1"' : ""}>
        <td><bdi class="sku">${esc(line.sku)}</bdi>${line.role
          ? ` <span class="meta" dir="auto">${esc(roleWord(line.role))}</span>` : ""}</td>
        ${qtyCells(line.qty, line.unit)}
        <td class="num">${cutText(line)}</td>
      </tr>`;
    return line.sharedWith.length ? row + sharedRow(line, interactive) : row;
  }).join("");

  box.innerHTML = `${head}
    <table class="section-materials-table">
      <thead><tr>
        <th>${esc(t("job.materials_col_product"))}</th>
        <th class="num">${esc(t("job.materials_col_count"))}</th>
        <th></th>
        <th class="num">${esc(t("job.materials_col_cut"))}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="meta section-materials-hint">${esc(t("job.materials_hint"))}</p>`;

  if (interactive) {
    box.addEventListener("click", (ev) => {
      const chip = ev.target.closest?.("[data-element]");
      if (!chip || !box.contains(chip)) return;
      // **The stop is load-bearing, not tidiness.** The card this block sits in
      // carries `data-run` and the job screen selects a stretch from any click
      // that bubbles up to it. Without this, choosing the bay a shared rail also
      // serves would select the whole stretch at the same instant — two
      // selections from one gesture, with the loser decided by handler order.
      ev.stopPropagation();
      opts.onSelectElement(chip.getAttribute("data-element"));
    });
  }
  return box;
}
