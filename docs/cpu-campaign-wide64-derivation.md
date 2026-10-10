# Ordered 64-state AVX scheduling

Reference: pinned `lh3/psmc` commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`, `khmm.c` forward and
backward matrix-vector loops. The Phase 3a CPU transpose and emission-product
layouts are unchanged. The dense Rust oracle, model construction, objective and
optimizer remain unchanged.

For each destination k, forward accumulates `sum = sum + f[l]*A[l,k]`
for ascending l, then multiplies `emission[k]*sum`. Backward accumulates
`sum = sum + AE_transpose[l,k]*b[l]` in ascending l, then divides by the
original scale. Four independent AVX accumulators compute destinations k..k+15.
Each lane receives precisely the original ordered operations and operand order.
No horizontal reductions, FMA, reassociation, reduced precision or approximate
functions are introduced. Counts, likelihood scaling, boundaries and all scalar
tails are unchanged.

The specialized functions require exactly 64 states, so each source matrix is
64 by 64, and k is 0,16,32,48. A group's largest destination is 63 and its
largest row is 63: every unaligned load/store is inside the checked slice.
The private AVX capability requires runtime CPU/OS detection. Safe callers check
all slice lengths before entering the unsafe implementation; Rust borrowing
prevents mutable output/input aliasing. Unsupported hardware uses the existing
scalar path; forced AVX still reports an error when unavailable.

## Candidate progression and rejection evidence

`cpu_campaign_kernel_variants.py` tests 8/16-destination scheduling and 64/256-site
count tiles. Tiling preserves per-cell site order but is slower on the screened
complete fits. Generic wide scheduling improves the 64-state kernels, but complete
23-state cases are mixed. See `cpu-campaign-kernels.json` and the kernel derivation.

`cpu_campaign_confirm.py` keeps wide loops inside the existing functions, enabled
only at 64 states. Six balanced ABBA/BAAB blocks show a full K64/N30 median ratio
1.109x (Phase 3a CPU/candidate CPU), but K23 controls regress approximately 4%.
That implementation is rejected.

`cpu_campaign_split_confirm.py` moves wide loops into separate fixed-shape
functions, preserving generic function bodies. Full K64/N30 improves in every
block, median ratio 1.116x. The old K23 fit is neutral (1.004x), while the new
model-based K23 bootstrap has a 0.987x median, with variation. The final release
benchmark must evaluate whether that small control difference persists.

`cpu_campaign_record_dispatch.py` instead chooses a const-specialized evaluate
body once per record and keeps the original safe generic kernel wrappers. Its
separate confirmation is retained in `cpu-campaign-record-confirm.json`.
Only the final measured implementation is eligible for promotion; other source
copies are experiments.

Masked tails are a separate experiment with guard-page bounds tests. Although
isolated timings improve, full fits regress, so masks are rejected. The proposed
64-state change retains original scalar tails for every other state count.

## Numerical tests and gates

Both confirmations run full debug and release suites and compare each complete
warmup/measured fit against pinned vanilla C (only MM Version is excluded).
Isolated lane tests cover n=1..33,63,64,65, offset buffers, signed zeros,
subnormals, extreme finite values and nonfinite classes. HMM tests compare every
message, scale and count with the dense oracle. Complete C snapshots, optimizer
callbacks, all original bootstraps, scheduler/cache and final frozen-binary timing
remain required before release. A passing screen alone is not release acceptance.

All processes are sequential on CPU 0 at nice 10. Balanced ordering reduces time
order bias but cannot eliminate shared-host frequency/cache interference. These
synthetic timings do not establish real-workload, ARM/NEON or AVX-512 performance.

The per-record specialization's completed small-state controls regress (median
paired ratios 0.986x and 0.946x), so it is rejected regardless of its final K64
result. The simpler separate-function candidate is selected for the complete
release gates. No numerical tolerance or scientific contract is changed by this
performance selection.

## Final candidate source

The selected implementation is the separate-function variant with the original
per-call shape checks. It adds no `Workspace::evaluate` specialization. Production
changes are confined to `psmc-cpu/src/simd.rs` plus the 0.3.1 version strings and
package metadata. Five additional invalid-shape assertions exercise the 64-state
dispatch before memory access. They extend an existing test, so the workspace
still reports 32 tests in each build mode. Formatting removes redundant integer
`+ 0` indexing; the release executable is unchanged by that cleanup. Final build
hashes, snapshots and timings identify the actual tested artifact.
