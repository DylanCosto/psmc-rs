# PHLASH comparator audit

PHLASH is a credible existing GPU demographic-inference method and structured-HMM prior art. Its posterior approximation is a different scientific output from a legacy PSMC fit with resampled bootstrap replicates. The small runs here establish that its Python API and custom GPU likelihood kernel execute on this computer; they do not establish posterior accuracy, convergence, whole-genome throughput, or a compatibility speedup.

The primary repository was cloned into `work/phlash-upstream` and pinned to commit [`96a6e3f8e01053271e88d21c97862198422d9ae0`](https://github.com/jthlab/phlash/tree/96a6e3f8e01053271e88d21c97862198422d9ae0), committed 2025-09-29, package version 1.0.6. The checkout was unmodified; post-run verification confirmed the installed package originated there and all 19 installed Python source files matched it byte for byte. The license is MIT. PHLASH's README says Python 3.10+, but this pin's authoritative [package metadata](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/pyproject.toml) requires Python 3.12+ and JAX >=0.4.25,<0.6.0. Installation used the versions in its checked-in `uv.lock`.

## What differs from legacy inference

The public interface returns a list of `DemographicModel(theta, rho, eta)` objects. At this pin, `fit` uses BlackJAX Stein variational gradient descent (SVGD) with AMSGrad and interacting particles. Treat these as a posterior approximation, not independent MCMC draws or bootstrap fits. A prior, minibatch gradients, the parameterization, stopping rules, and chunk handling all contribute to the answer. The [example](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/notebooks/example.md) documents posterior summaries; the implementation is in [mcmc.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/mcmc.py).

The default pattern `14*1+1*2` has 16 hidden intervals and 15 tied size parameters. `PSMCParams.from_dm` actually asserts that there are 16 intervals. The time grid is geometric; theta is held static after its empirical initialization, while transformed size, time, and recombination parameters vary. The recombination-to-mutation ratio is restricted to [0.1,10]. These details preclude assuming that a shared `.psmcfa` file implies the same optimization problem. See [params.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/params.py) and [util.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/util.py).

The density combines a prior, chunk likelihoods, and an allele-frequency-spectrum term. The log recombination-ratio prior and optional alpha/beta penalties are explicit. For PSMCFA the adapter constructs a one-element dummy spectrum, rather than recovering a multi-sample spectrum that is absent from this format. See [model.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/model.py).

There is no defensible conversion between a number of posterior particles and 30 PSMC bootstrap replicates. The user's existing parallel bootstrap execution also means serial PSMC is not the relevant end-to-end throughput comparator.

## Settings that must be recorded

| Setting | Source default | Local feasibility setting |
|---|---|---|
| Iterations | 1,000, possibly stopped using held-out data | 2 |
| Particles | 500 | 4 |
| HMM intervals / pattern | 16 / `14*1+1*2` | unchanged |
| Input window | 100 bp | 100 bp |
| Holdout through `phlash.psmc` | First contig held out when there is more than one | `False` |
| Chunk overlap | 500 bins | 10 bins |
| Chunk length | Approximately one fifth of shortest contig in bins | 200 bins |
| Minibatch | `max(1,min(5,int(number_of_chunks/niter)))` | 2 |
| Data loading workers | Executor default | 1 |
| Custom GPU arithmetic | `double_precision=False` | `True` |
| JAX random key | Seed 1 | Seed 1 |
| AMSGrad learning rate | 0.1 | unchanged |
| Initialization covariance scale `sigma` | 1.0 | unchanged |
| Initial rho/theta, t1, tM | 1.0, 0.0001, 15 | unchanged |
| Alpha / beta penalties | 0 / 0 | unchanged |
| Mutation rate supplied | None | None |
| Plot/progress | Live callback attempted; progress enabled | Materializing finite-value callback; progress disabled |

The source can additionally subsample stored chunks before fitting if their count exceeds five times minibatch size times iteration count. Therefore full data exposure must be verified, rather than inferred from the number of input bytes. The local fixture produces 20 chunks and is below that subsampling threshold.

## Structured GPU implementation

The JAX `matvec_smc` uses a reverse cumulative sum and a forward scan for the lower/upper/diagonal structure of an SMC-prime transition matrix. The CUDA implementation contains an explicit O(M) matvec with forward and reverse loops, keeps observations on the device, and provides likelihood and likelihood-gradient kernels. This is substantive prior art for exploiting transition structure. It is not the legacy full-count E-step, and it is not evidence that PHLASH's transition construction matches original PSMC. See [hmm.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/hmm.py), [transition.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/transition.py), and [gpu.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/gpu.py).

The custom CUDA code is compiled at runtime through NVRTC; a command-line `nvcc` is not required for this path. Its training arithmetic defaults to float32, despite package-wide JAX x64 being enabled. The likelihood-gradient kernel uses a floating-point atomic addition for normalization, so its existence does not satisfy this project's deterministic reduction contract. Setting double precision alone does not restore the original model, optimizer, sequence semantics, or reproducibility guarantees.

## Input audit and a reproduced chunk-coverage issue

`RawContig.from_psmcfa_iter` maps uppercase K to 1 and uppercase N to -1; every other character becomes 0. It does not validate a canonical PSMC alphabet. Missing observations have emission probability one. The `phlash.psmc` convenience function defaults to withholding the first record when multiple records exist. It also consumes its `window_size` argument without forwarding it to `fit`; a non-100 bp workflow requires checking the direct `fit` route and matching `RawContig.window_size`. See [psmc.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/psmc.py).

This pin's VCF adapter requires samples and a region but rejects its mask argument. It initializes all bins as homozygous, marks heterozygosity only at observed variant records, and contains an explicit missing-data TODO. It does not establish the required callable-reference evidence for absent VCF records. Accordingly the local comparison uses synthetic PSMCFA, not VCF.

Source inspection also identified a chunk-coverage problem. With 10,000 input bins, chunk size 2,000 (the automatic 20% rule), and overlap 500, `_chunk_het_matrix` returns four chunks of length 2,500 with starts spaced by 2,000. Their union ends at bin 8,499. The last 1,500 bins are omitted. A direct test against the unmodified function, with heterozygosity confined to that tail, returned zero heterozygous observations. This is a pin-specific, reproduced behavior; it requires correction or a validated workaround before scientific adoption. The smoke fixture's 2,000/200/10 geometry covers its tail and does not encounter that omission. Relevant source: [data.py](https://github.com/jthlab/phlash/blob/96a6e3f8e01053271e88d21c97862198422d9ae0/src/phlash/data.py).

Exact coverage reproducer, run in the isolated environment:

```python
import numpy as np
from phlash.data import _chunk_het_matrix
x = np.zeros((1, 10000), dtype=np.int8)
x[0, -1500:] = 1
chunks = _chunk_het_matrix(x, overlap=500, chunk_size=2000)
print(chunks.shape, int(x.sum()), int((chunks == 1).sum()))
# observed: (4, 2500) 1500 0
```

## Measured local feasibility

The fixture contains two records of 2,000 bins each, generated with Python seed 20261009 and weights T:88, K:10, N:2. It represents 400,000 base pairs at 100 bp per bin, but is random test data rather than a demographic simulation. Its SHA-256 is `ba1390aaa032a5bd15c5f93c820e863155e10e3ad3d2b520e59cebaafadd589e`.

Both runs completed exactly two iterations and returned four finite model objects. They ran in fresh processes; fit timings include data loading and JIT/compilation overhead. No timing ratio is reported because the tiny, nonconverged runs are dominated by setup and do not represent the user's workload.

| Run | Actual likelihood backend | Fit seconds | Process-body seconds | Main peak RSS KiB | Child peak RSS KiB |
|---|---|---:|---:|---:|---:|
| CPU smoke | `phlash.hmm.PureJaxPSMCKernel` | 6.138849 | 7.308889 | 751,388 | 362,540 |
| Hybrid smoke | `phlash.gpu.PSMCKernel`; JAX on CPU | 6.094120 | 6.893090 | 947,956 | 443,700 |

The GPU is an NVIDIA GeForce RTX 5060 Ti, 16,311 MiB reported VRAM, driver 595.91.07, compute capability 12.0. PHLASH reported NVRTC compilation for `sm_120` and one GPU. The hybrid run explicitly rejected fallback and confirmed the custom GPU kernel. JAX model construction and optimization remained on `TFRT_CPU_0`; this is not a test of the complete JAX GPU installation. Device-memory peak was not measured. Host memory values are Linux `ru_maxrss` for separate processes, not simultaneous summed memory.

System Python 3.12.3 had neither PHLASH/JAX nor pip/ensurepip. A separate environment under `work/phlash-probe-env` was created with the app's bundled Python 3.12.14. The source package and CPU dependencies were installed there with constraints derived from the pinned upstream lock. A second installation added only cuda-python 12.9.2, cuda-bindings 12.9.2, cuda-pathfinder 1.2.2, nvidia-cuda-nvrtc-cu12 12.9.86, and nvidia-cuda-runtime-cu12 12.9.79. Their platform wheel sizes total approximately 106 MB plus small Python wrappers. The isolated environment occupies approximately 1.4 GB installed. Global packages were not modified. `pip check` reported no broken requirements. The full JAX CUDA extra was not installed: upstream lock entries for cuBLAS and cuDNN alone exceed 1.2 GB of compressed wheels.

## Reproduction and remaining gate

From the workspace root, the commands actually used for the fitting stages were:

```bash
timeout 180s work/phlash-probe-env/bin/python outputs/psmc-rs/bench/phlash_probe.py --output outputs/psmc-rs/bench/phlash.json --work-dir work/phlash-probe
timeout 180s work/phlash-probe-env/bin/python outputs/psmc-rs/bench/phlash_probe.py --output work/phlash-gpu.json --work-dir work/phlash-probe --require-gpu
```

The first was run before adding the minimal CUDA dependencies. The final `bench/phlash.json` consolidates both original run records and the coverage test. To repeat the GPU smoke now without replacing that consolidated record:

```bash
timeout 180s work/phlash-probe-env/bin/python outputs/psmc-rs/bench/phlash_probe.py --output work/phlash-gpu-repeat.json --work-dir work/phlash-probe --require-gpu
```

For a clean environment on another machine, fetch the pinned source, create a Python 3.12 virtual environment, extract `name==version` constraints for registry packages from its `uv.lock`, and install that local source with `pip install -c constraints.txt ./phlash-upstream`. Add the five CUDA packages above for the tested hybrid configuration. The exact installed versions are preserved per run in the result JSON. The upstream-supported full-GPU alternative is installation with the `gpu` extra, followed by the same probe with `--require-gpu` and verification that JAX itself lists a GPU; that larger installation was not performed here.

Real-data posterior validation, default-scale posterior convergence, full JAX GPU operation, peak device memory, and representative runtime are all `not_run`. No genomic data were accessed. No PHLASH code was changed or external scientific result published. Before choosing PHLASH for the user's scientific task, validate callability and complete sequence coverage, resolve the reproduced chunk issue, agree on posterior outputs, and run an appropriately converged comparison on authorized data. Phase 1 of the compatibility project is a separate review gate.
