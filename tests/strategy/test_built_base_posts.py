"""A fence on a built base stands ON it, not in it.

Panels already rested on the base top (span bottoms include it). Posts were
still recorded at ground level, so a post on a 600 mm wall was measured from the
ground, straight through the wall, and then charged embedment on top of that.
`Post.base_z_mm` is the elevation the post stands on; `ground_z_mm` stays the
true ground, which is what embedment is measured into.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.topology.model import (
    BasePayload, BaseTopPayload, BaseTopPoint, ElevationSamplePayload, HeightIntentPayload,
)
from tests.conftest import add_interval_event, add_point_event, straight_topology

WALL_MM = 600


def _wall_topology(length_mm: int = 6000, wall_mm: int = WALL_MM):
    topo = straight_topology(length_mm)
    add_interval_event(topo, "run1", "base", 0, length_mm,
                       BasePayload(surface="masonry_wall"))
    add_interval_event(topo, "run1", "top", 0, length_mm, BaseTopPayload(
        points=[BaseTopPoint(pos_permille=0, z_mm=wall_mm),
                BaseTopPoint(pos_permille=1000, z_mm=wall_mm)]))
    return topo


def test_posts_stand_on_the_wall_top():
    result = generate(_wall_topology(), demo_knowledge(), demo_catalog())
    assert result.strategy.posts
    for post in result.strategy.posts:
        assert post.ground_z_mm == 0            # the ground has not moved
        assert post.base_z_mm == WALL_MM        # what the post stands on


def test_panels_and_posts_start_at_the_same_elevation():
    """The visible bug: panels rested on the wall while posts started below it."""
    result = generate(_wall_topology(), demo_knowledge(), demo_catalog())
    span = result.strategy.spans[0]
    post = next(p for p in result.strategy.posts if p.run_ref.startswith("run"))
    assert span.bottom_z_start_mm == WALL_MM
    assert post.base_z_mm == span.bottom_z_start_mm


def test_a_wall_does_not_count_towards_the_post_length():
    """A 2 m fence on a 600 mm wall needs a 2 m post, not a 2.6 m one."""
    topo = _wall_topology()
    add_interval_event(topo, "run1", "h", 0, 6000, HeightIntentPayload(height_mm=2000))
    result = generate(topo, demo_knowledge(), demo_catalog())
    lengths = [w for w in result.strategy.warnings if w.code == "insufficient_post_length"]
    # POST-S is 2600 mm; measured from the ground through the wall this would be
    # 600 (wall) + 1400 (panel above it) + 600 (embed) = ... plus the old double
    # count. Standing on the wall, a masonry-mounted post needs only what shows.
    assert not lengths, [w.params for w in lengths]


def test_ground_posts_still_pay_for_embedment():
    """Nothing changes off a built base: a soil post is still measured from the
    ground and still needs its embedment."""
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "h", 0, 6000, HeightIntentPayload(height_mm=2200))
    result = generate(topo, demo_knowledge(), demo_catalog())
    post = next(p for p in result.strategy.posts if p.run_ref.startswith("run"))
    assert post.base_z_mm == post.ground_z_mm
    warns = [w for w in result.strategy.warnings if w.code == "insufficient_post_length"]
    assert warns, "2200 mm panel + 600 mm embed exceeds the 2600 mm POST-S"
    assert warns[0].params["required_mm"] == 2800


def test_the_base_top_follows_the_ground_under_it():
    """base_z is ground + base top: on a slope each post stands on its own piece
    of wall."""
    topo = _wall_topology()
    add_point_event(topo, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(topo, "run1", "z1", 6000, ElevationSamplePayload(z_mm=600))
    result = generate(topo, demo_knowledge(), demo_catalog())
    for post in result.strategy.posts:
        assert post.base_z_mm == post.ground_z_mm + WALL_MM
    grounds = {p.ground_z_mm for p in result.strategy.posts}
    assert len(grounds) > 1, "the fixture is supposed to be on a slope"
