"""Resource policy for Phase 3a: one allowed CPU, sequential child processes."""
import os


def resource_policy():
    affinity = sorted(os.sched_getaffinity(0))
    if len(affinity) != 1:
        raise SystemExit('Pin this runner to one allowed CPU with taskset -c CPU first.')
    if os.nice(0) < 10:
        os.nice(10 - os.nice(0))
    return {'affinity': affinity, 'nice': os.nice(0), 'cargo_jobs': 1,
            'rust_test_threads': 1, 'inference_threads_per_fit': 1,
            'parallel_jobs': False, 'shared_host': True}
