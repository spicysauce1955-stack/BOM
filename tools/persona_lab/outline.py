"""Render the page the way a person perceives it: visible labels, not selectors.

Handing an agent `#btn-generate` hands it the developer's intent, which is the
one thing a real user does not have. Elements therefore get opaque handles and
are described only by what is actually legible on screen.
"""

from __future__ import annotations

import re

INTERACTIVE = "button, a[href], input, select, textarea, summary, [role=button]"

# The element sweep is shared by OUTLINE_JS and POINT_JS so a handle always
# resolves to the same element the persona was shown. Duplicating the sweep
# would let the two drift and silently mis-aim clicks.
_COLLECT = """
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const flat = (s) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
  const legible = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    // a select shows its chosen option; the rest of the list is behind a click
    if (tag === 'select')
      return el.selectedOptions.length ? el.selectedOptions[0].text : '';
    // a tick box shows the words printed next to it, never its form value
    if (type === 'checkbox' || type === 'radio') {
      const lab = (el.labels && el.labels[0]) || el.closest('label');
      return lab ? lab.innerText : '';
    }
    return el.innerText || el.value || '';
  };
  const els = [];
  for (const el of document.querySelectorAll(%r)) if (vis(el)) els.push(el);
  for (const el of document.querySelectorAll('svg')) if (vis(el)) els.push(el);
""" % INTERACTIVE

OUTLINE_JS = """
(() => {
%s
  const out = [];
  for (const el of els) {
    if (el.tagName.toLowerCase() === 'svg') {
      const r = el.getBoundingClientRect();
      out.push({
        role: 'canvas', label: el.getAttribute('viewBox') ? 'drawing area' : 'graphic',
        placeholder: '', has_title: false, title: '', disabled: false, checked: null,
        x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
        w: Math.round(r.width), h: Math.round(r.height)
      });
      continue;
    }
    const r = el.getBoundingClientRect();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const tick = (type === 'checkbox' || type === 'radio');
    out.push({
      role: el.tagName.toLowerCase(),
      label: flat(legible(el)),
      placeholder: el.getAttribute('placeholder') || '',
      has_title: !!el.getAttribute('title'),
      title: el.getAttribute('title') || '',
      disabled: !!el.disabled,
      checked: tick ? !!el.checked : null,
      x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
      w: Math.round(r.width), h: Math.round(r.height)
    });
  }
  return out;
})()
""" % _COLLECT

SCROLL_POINT_JS = """
(() => {
  // The plan and profile SVGs preventDefault() the wheel to zoom, by design.
  // A wheel dispatched at a fixed centre point always lands on one of them,
  // so the page never scrolls and the app reads as frozen. Aim off-canvas.
  const svgs = [...document.querySelectorAll('svg')].map(e => e.getBoundingClientRect());
  const W = innerWidth, H = innerHeight;
  const clear = (x, y) => !svgs.some(
    (r) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom);
  for (const y of [H * 0.5, H * 0.25, H * 0.75, H * 0.1])
    for (const x of [4, W - 4, W * 0.5])
      if (clear(x, y)) return [Math.round(x), Math.round(y)];
  return [4, Math.round(H * 0.5)];
})()
"""

POINT_JS = """
(() => {
%s
  const el = els[%%d];
  if (!el) return null;
  // A person scrolls to what they want to touch. Without this a click at a
  // negative viewport y silently lands on nothing and reads as "no feedback".
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = el.getBoundingClientRect();
  return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)];
})()
""" % _COLLECT

# The app's feedback channels — the surfaces a sighted user reads without
# deciding to. The status bar exists precisely to name the current mode and the
# next gesture; run 1 rendered interactive elements only, so it was invisible
# and every persona drew blind. Strictly this list: a persona must not become a
# superhuman reader of every heading, panel and table on the page.
FEEDBACK_JS = """
(() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const out = [];
  const add = (region, el) => {
    if (!el || !vis(el)) return;
    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    if (text) out.push({region: region, text: text});
  };
  add('status', document.getElementById('statusbar'));
  add('warning', document.getElementById('warnings'));
  // canvas events are edited in an on-canvas .popover, not a <dialog>
  for (const el of document.querySelectorAll('.popover, dialog[open], [role=dialog]'))
    add('dialog', el);
  add('getting started', document.getElementById('checklist'));
  return out;
})()
"""

REGION_CAP = 200

_WORD = re.compile(r"\w", re.UNICODE)


def clip(text: str, cap: int = REGION_CAP) -> str:
    """Cap a region, keeping its head AND its tail.

    The draw hint ends with the live cursor readout (station, x, y). A plain
    head-truncation would delete exactly the feedback that makes aiming
    possible, so an over-long region is elided in the middle instead.
    """
    text = " ".join(text.split())
    if len(text) <= cap:
        return text
    head = cap * 2 // 3
    return f"{text[:head].rstrip()} … {text[len(text) - (cap - head):].lstrip()}"


def render_feedback(regions: list[dict]) -> str:
    """The `screen says:` block. Regions with no text are omitted entirely."""
    lines = [f'  {r["region"]}: {clip(r["text"])}'
             for r in regions if (r.get("text") or "").strip()]
    return "screen says:\n" + "\n".join(lines) if lines else ""


def is_icon_only(label: str) -> bool:
    """A control whose whole visible label is a glyph — no word, no digit.

    Spec §3.2: these expose their glyph and are marked tooltip-on-hover,
    because whether a person can guess what ⤢ does is one of the questions
    the lab exists to ask, not one to answer for free.
    """
    return bool(label) and not _WORD.search(label)


def render(items: list[dict], feedback: list[dict] | None = None) -> str:
    """items -> the text a persona reads. Tooltips stay hidden until hovered.

    What the screen *says* comes first, the way a person reads the status line
    before hunting for a control.
    """
    lines = []
    for i, el in enumerate(items, start=1):
        handle = f"e{i:02d}"
        icon = is_icon_only(el["label"])
        if icon:
            what = f'icon:"{el["label"]}"'
        elif el["label"]:
            what = f'"{el["label"]}"'
        elif el["placeholder"]:
            what = f'placeholder:"{el["placeholder"]}"'
        else:
            what = "(no visible label)"
        bits = [f"[{handle}]", f'{el["role"]:<8}', what]
        if el["has_title"] and (icon or not el["label"]):
            bits.append("tooltip-on-hover")
        if el.get("checked") is not None:
            bits.append("[x]" if el["checked"] else "[ ]")
        if el["disabled"]:
            bits.append("disabled")
        bits.append(f'at({el["x"]},{el["y"]}) {el["w"]}x{el["h"]}')
        lines.append(" ".join(bits))
    says = render_feedback(feedback or [])
    body = "\n".join(lines)
    return f"{says}\n\n{body}" if says else body
