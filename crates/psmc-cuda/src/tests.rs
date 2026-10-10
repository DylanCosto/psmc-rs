use super::*;
use psmc_core::{
    Pattern,
    em::{DenseBackend, NoObserver},
    rng::LegacyRng,
};
fn exact(a: f64, b: f64) {
    assert!(
        a.to_bits() == b.to_bits() || a.is_nan() && b.is_nan(),
        "{a:?} != {b:?}"
    );
}
fn compare(a: &Counts, b: &Counts) {
    for (&a, &b) in
        a.a0.iter()
            .chain(&a.a)
            .chain(&a.e)
            .chain([&a.q0])
            .zip(b.a0.iter().chain(&b.a).chain(&b.e).chain([&b.q0]))
    {
        exact(a, b);
    }
}
fn settings(n: usize) -> Settings {
    Settings {
        pattern: Pattern {
            text: format!("{n}*1"),
            groups: (0..n).collect(),
            n_free: n,
        },
        max_t: 15.0,
        alpha: 0.1,
        tr_ratio: 4.0,
        ran_init: 0.0,
        divergence: None,
        initial_params: None,
        explicit_times: None,
    }
}
#[test]
#[ignore = "requires CUDA GPU and NVRTC; run explicitly"]
fn shapes_masks_tiles_cache_and_parameter_changes() {
    for n in [1, 2, 4, 23, 31, 64, 65, 129] {
        let settings = settings(n);
        let mut model = Model::new(&settings, 12, 100, &mut LegacyRng::new(42));
        let sequences: Vec<Sequence> = [1, 2, 6, 7, 8, 31, 32, 33, 255]
            .iter()
            .enumerate()
            .map(|(i, &length)| Sequence {
                name: format!("s{i}"),
                observations: (0..length).map(|j| ((j * 13 + i) % 3) as u8).collect(),
            })
            .collect();
        let mut refs: Vec<_> = sequences.iter().collect();
        refs.extend([&sequences[3], &sequences[3], &sequences[0]]);
        let mut dense = DenseBackend::default();
        for tile in [1, 7, 32, 16384] {
            let mut cuda = CudaBackend::new(n, SimdMode::Auto, tile).unwrap();
            for round in 0..2 {
                model.params[0] += 0.001;
                model.update(&settings);
                let (expected, lk) = dense
                    .expectation(&model, &refs, round, &mut NoObserver)
                    .unwrap();
                let (got, glk) = cuda
                    .expectation(&model, &refs, round, &mut NoObserver)
                    .unwrap();
                compare(&expected, &got);
                exact(lk, glk);
            }
            assert_eq!(cuda.stats().cache_hits, 6);
            cuda.cache_enabled = false;
            let (a, lk) = dense
                .expectation(&model, &refs, 2, &mut NoObserver)
                .unwrap();
            let (b, bl) = cuda.expectation(&model, &refs, 2, &mut NoObserver).unwrap();
            compare(&a, &b);
            exact(lk, bl);
        }
    }
}
#[test]
#[ignore = "requires CUDA GPU and NVRTC; run explicitly"]
fn counts_pathologies_subnormals_signed_zero_and_nonfused_products() {
    let mut device = driver::Device::new().unwrap();
    let n = 4;
    let sites = 37;
    let all_values = [
        0.0,
        -0.0,
        f64::from_bits(1),
        f64::MIN_POSITIVE,
        1e-200,
        1e200,
        1.0000000000000002,
        f64::INFINITY,
        f64::NAN,
        -1.0,
    ];
    let mut f = vec![0.0; sites * n];
    let mut b = f.clone();
    let mut ae = vec![0.0; 3 * n * n];
    for finite_only in [true, false] {
        let values: Vec<_> = all_values
            .iter()
            .copied()
            .filter(|x| !finite_only || x.is_finite() && x.abs() < 1e150)
            .collect();
        for phase in 0..values.len() {
            for (i, x) in f.iter_mut().enumerate() {
                *x = values[(i + phase) % values.len()];
            }
            for (i, x) in b.iter_mut().enumerate() {
                *x = values[(i * 3 + phase) % values.len()];
            }
            for (i, x) in ae.iter_mut().enumerate() {
                *x = values[(i * 7 + phase) % values.len()];
            }
            let obs: Vec<_> = (0..sites).map(|i| (i % 3) as u8).collect();
            let mut expected = vec![1e-25; n * n];
            for u in 0..sites {
                for k in 0..n {
                    for l in 0..n {
                        expected[k * n + l] +=
                            f[u * n + k] * ae[obs[u] as usize * n * n + k * n + l] * b[u * n + l];
                    }
                }
            }
            device.prepare(&ae).unwrap();
            let mut actual = vec![0.0; n * n];
            for start in (0..sites).step_by(7) {
                let end = (start + 7).min(sites);
                device
                    .tile(
                        &f[start * n..end * n],
                        &b[start * n..end * n],
                        &obs[start..end],
                        &mut actual,
                        n,
                        start == 0,
                        end == sites,
                    )
                    .unwrap();
            }
            for (a, b) in actual.into_iter().zip(expected) {
                exact(a, b);
            }
        }
    }
}

#[test]
#[ignore = "requires CUDA GPU and NVRTC; run explicitly"]
fn concurrent_large_pageable_uploads_are_ordered_before_kernels() {
    std::thread::scope(|scope| {
        for n in [23, 64] {
            scope.spawn(move || {
                let settings = settings(n);
                let mut model = Model::new(&settings, 10, 100, &mut LegacyRng::new(42));
                let sequences: Vec<_> = [4097, 3001, 515, 1]
                    .into_iter()
                    .enumerate()
                    .map(|(j, length)| Sequence {
                        name: format!("{j}"),
                        observations: (0..length).map(|i| ((i * 17 + j) % 3) as u8).collect(),
                    })
                    .collect();
                let refs: Vec<_> = sequences.iter().collect();
                let mut cpu = psmc_cpu::CpuBackend::new(n);
                let mut cuda = CudaBackend::new(n, SimdMode::Auto, 4096).unwrap();
                for round in 0..12 {
                    model.params[0] += 0.003;
                    model.update(&settings);
                    let (a, al) = cpu
                        .expectation(&model, &refs, round, &mut NoObserver)
                        .unwrap();
                    let (b, bl) = cuda
                        .expectation(&model, &refs, round, &mut NoObserver)
                        .unwrap();
                    compare(&a, &b);
                    exact(al, bl);
                }
            });
        }
    });
}
