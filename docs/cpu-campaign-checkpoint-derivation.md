# Exact checkpoint/recompute experiment

Naively accumulating counts while traversing backward would reverse the original
site-order sum, so direct backward/count fusion is ineligible for the strict path.
This candidate instead retains the original ascending count order and regenerates
both message directions within ascending computational tiles. It is an isolated
fixed-model experiment, not an integrated fitting backend.

1. Run the ordinary forward recursion with two rolling state vectors. Retain every
   scale and normalized forward messages at sites 1, 1+T, 1+2T, ... and L.
2. Run the ordinary backward recursion with two rolling vectors using those exact
   scales. Retain backward messages at the same boundaries.
3. Visit adjacent boundary pairs in ascending order. Seed the tile's first forward
   row and last backward row from their saved messages. Regenerate forward rows
   in ascending order and backward rows in descending order, using the same
   expressions, AVX/scalar lanes and observation symbols. Recomputed forward
   scales are checked against the retained values exactly (NaNs by class).
4. Accumulate all transition and emission counts for the tile in original site
   order, retaining the original tiny initialization, products, scaling, final-site
   emission omission and count multiplicity. The next tile continues the same
   scalar count accumulators; there is no partial-sum reduction.

Every recursive row has the same input bits as its original computation, so an
induction from each stored boundary proves identical regenerated messages on the
unchanged numerical stack. Boundary rows overlap only for reconstruction; each
statistical transition/site contribution is added once. Missing bins retain their
transitions. Real sequence boundaries alone reset the HMM. A one-site record has
no transition/emission accumulation and retains the legacy initial-state count.

The original grouped product/log likelihood uses the full saved scale array.
The underflow diagnostic and initial-state counts use the exact first backward
checkpoint. No changed Q, optimizer, model parameter or likelihood formula is
introduced. Tests inspect every reconstructed forward/backward element and every
count against the existing workspace, across short/tail/tile boundaries, scalar
and AVX execution, reused capacities and impossible observations.

Storage changes from roughly 2*L*K message cells plus L scales to roughly
2*(L/T)*K checkpoint cells, 2*(T+1)*K temporary cells, L scales and rolling vectors.
Forward and backward work is approximately doubled. Counts remain full and have
unchanged arithmetic complexity. Whether smaller working sets offset recomputation
must be measured. Tile sizes 64/256/1024 and two lengths/state counts are swept;
none is declared universally optimal.

Correctness processes allocate both implementations and inspect every message.
Memory/timing processes allocate only the selected implementation and compare a
complete-count/likelihood checksum to the separate exact check. This prevents the
oracle's peak allocation from contaminating the candidate RSS measurement.
Promotion would additionally require CLI/observer/cache integration, safe memory
admission, full fitting and all snapshot/bootstrap gates. A useful memory reduction
alone is not a claim of faster CPU inference.
