"""Render the page the way a person perceives it: visible labels, not selectors.

Handing an agent `#btn-generate` hands it the developer's intent, which is the
one thing a real user does not have. Elements therefore get opaque handles and
are described only by what is actually legible on screen.
"""

from __future__ import annotations

import re

INTERACTIVE = "button, a[href], input, select, textarea, summary, [role=button]"

OUTLINE_JS = """
(() => {
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
  const out = [];
  for (const el of document.querySelectorAll(%r)) {
    if (!vis(el)) continue;
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
  for (const el of document.querySelectorAll('svg')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    out.push({
      role: 'canvas', label: el.getAttribute('viewBox') ? 'drawing area' : 'graphic',
      placeholder: '', has_title: false, title: '', disabled: false, checked: null,
      x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
      w: Math.round(r.width), h: Math.round(r.height)
    });
  }
  return out;
})()
""" % INTERACTIVE

_WORD = re.compile(r"\w", re.UNICODE)


def is_icon_only(label: str) -> bool:
    """A control whose whole visible label is a glyph — no word, no digit.

    Spec §3.2: these expose their glyph and are marked tooltip-on-hover,
    because whether a person can guess what ⤢ does is one of the questions
    the lab exists to ask, not one to answer for free.
    """
    return bool(label) and not _WORD.search(label)


def render(items: list[dict]) -> str:
    """items -> the text a persona reads. Tooltips stay hidden until hovered."""
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
    return "\n".join(lines)
