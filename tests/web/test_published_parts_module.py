"""Published milli-unit precision must survive display, including cm mode."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node unavailable")
def test_public_quantity_display_preserves_fractional_source_dimensions():
    static = Path(__file__).resolve().parents[2] / "src/fenceai/web/static"
    subprocess.run(["node", "--input-type=module", "-e", """
      import assert from 'node:assert/strict';
      import { quantityText } from './js/published-parts.js';
      const q = {amount_milli: 22225, unit: 'mm'};
      assert.equal(quantityText(q, 'mm'), '22.225 mm');
      assert.equal(quantityText(q, 'cm'), '2.2225 cm');
      assert.equal(quantityText({amount_milli: 1368425, unit: 'mm'}, 'mm'), '1368.425 mm');
      assert.equal(quantityText({amount_milli: -1, unit: 'mm'}, 'cm'), '-0.0001 cm');
      assert.equal(quantityText({amount_milli: 0, unit: 'mm'}, 'mm'), '0 mm');
      assert.equal(quantityText({amount_milli: 1000, unit: 'in'}, 'cm'), '1 in');
      assert.equal(quantityText({key: 'vinyl'}, 'mm'), 'vinyl');
      assert.equal(q.amount_milli, 22225);
    """], cwd=static, check=True, capture_output=True, text=True)
