# Fixtures — what we expect to receive, not what anyone published

**Nothing in this directory is real published data.** The Knowledge Platform is
still designing; it has published nothing, and these files are this repo's
statement of what it expects a snapshot to look like, written from
`../contract.md` §1.2 and §1.3.

They exist for three reasons, and the third is the point:

1. They exercise the `ParameterTable` loader against a whole document rather than
   unit fixtures assembled in a test.
2. They make the loader reachable, so the codes it emits stop being strings
   nothing renders.
3. **They are evidence for the other team while they are still designing.** The
   frontend design makes this argument for its own step 1: *"building against it
   is what tells the Knowledge team whether their endpoint returns what a
   reviewer actually needs — before they implement it."* A design phase is when
   that is worth most, and it is the opposite of inventing behaviour at the
   boundary: it produces a question to ask, not a commitment to defend.

**They are NOT the contract, and they bind nobody.** The contract is frozen and
hash-verified; these are a reading of it. Where a fixture and the contract
disagree, the contract is right and the fixture is a bug.

`tenant`, `snapshot_id` and the source ids are deliberately obvious
(`FIXTURE-*`, `not-a-real-tenant`) so that a file from here can never be mistaken
for something that arrived over the wire. That is how a hypothesis quietly
becomes a fact nobody checked.
