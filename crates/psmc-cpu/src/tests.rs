use super::*;
use psmc_core::{Pattern, Settings, hmm, rng::LegacyRng};

fn toy_model() -> Model {
    Model {
        n: 2,
        params: vec![],
        t: vec![],
        sigma: vec![0.6, 0.4],
        c_pi: 0.0,
        c_sigma: 0.0,
        initial: vec![0.6, 0.4],
        transition: vec![0.7, 0.3, 0.2, 0.8],
        emission: vec![0.9, 0.25, 0.1, 0.75, 1.0, 1.0],
    }
}

fn same_float(actual: f64, expected: f64) {
    if expected.is_nan() {
        assert!(actual.is_nan(), "{actual:?} != NaN");
    } else {
        assert_eq!(
            actual.to_bits(),
            expected.to_bits(),
            "{actual:?} != {expected:?}"
        );
    }
}

fn same_slice(actual: &[f64], expected: &[f64]) {
    assert_eq!(actual.len(), expected.len());
    for (&a, &e) in actual.iter().zip(expected) {
        same_float(a, e);
    }
}

fn compare(workspace: &mut Workspace, prepared: &PreparedModel<'_>, observations: &[u8]) {
    let ae = hmm::pre_backward(prepared.model);
    let expected_messages = hmm::forward_backward(prepared.model, observations, &ae);
    let expected_counts = hmm::expectation(prepared.model, observations, &expected_messages, &ae);
    let (messages, counts) = workspace.evaluate(prepared, observations);
    assert_eq!(messages.n, expected_messages.n);
    assert_eq!(messages.length, observations.len());
    same_slice(&messages.forward, &expected_messages.forward);
    same_slice(&messages.backward, &expected_messages.backward);
    same_slice(&messages.scales, &expected_messages.scales);
    same_float(messages.log_likelihood, expected_messages.log_likelihood);
    same_float(messages.backward_check, expected_messages.backward_check);
    same_slice(&counts.a0, &expected_counts.a0);
    same_slice(&counts.a, &expected_counts.a);
    same_slice(&counts.e, &expected_counts.e);
    same_float(counts.q0, expected_counts.q0);
}

#[test]
fn every_short_observation_pattern_matches_dense_exactly() {
    let model = toy_model();
    let prepared = PreparedModel::new(&model);
    let mut workspace = Workspace::new(model.n);
    // All 3,279 observation strings of lengths 1..=7, including singletons,
    // all missing, long runs, alternating symbols and boundary placements.
    for length in 1..=7 {
        for pattern in 0..3_usize.pow(length as u32) {
            let mut id = pattern;
            let observations: Vec<_> = (0..length)
                .map(|_| {
                    let symbol = (id % 3) as u8;
                    id /= 3;
                    symbol
                })
                .collect();
            compare(&mut workspace, &prepared, &observations);
        }
    }
}

#[test]
fn original_models_and_reused_different_length_buffers_match_dense_exactly() {
    for n in [1, 2, 4, 23, 64] {
        for explicit in [false, true] {
            let settings = Settings {
                pattern: Pattern {
                    text: n.to_string(),
                    groups: (0..n).collect(),
                    n_free: n,
                },
                max_t: 15.0,
                alpha: 0.1,
                tr_ratio: 4.0,
                ran_init: 0.1,
                divergence: (!explicit).then_some(0.001),
                initial_params: None,
                explicit_times: explicit
                    .then(|| (0..n).map(|i| i as f64 * 15.0 / n as f64).collect()),
            };
            let mut rng = LegacyRng::new(42);
            let mut model = Model::new(&settings, 130, 1370, &mut rng);
            let mut workspace = Workspace::new(n);
            for update in 0..3 {
                if update != 0 {
                    model.params[0] *= 1.01;
                    model.params[1] *= 0.99;
                    model.update(&settings);
                }
                let prepared = PreparedModel::new(&model);
                for length in [1, 127, 3, 503, 1, 499, 31] {
                    let observations: Vec<_> = (0..length)
                        .map(|i| match i % 17 {
                            0 | 5 => 1,
                            8..=13 => 2,
                            _ => 0,
                        })
                        .collect();
                    compare(&mut workspace, &prepared, &observations);
                }
                compare(&mut workspace, &prepared, &[2; 257]);
            }
        }
    }
}

#[test]
fn every_repeated_record_retains_its_tiny_count_contribution() {
    let model = toy_model();
    let prepared = PreparedModel::new(&model);
    let mut workspace = Workspace::new(model.n);
    let mut aggregate = Counts::zero(model.n);
    let (_, first) = workspace.evaluate(&prepared, &[2]);
    let saved = first.clone();
    for _ in 0..7 {
        let (_, counts) = workspace.evaluate(&prepared, &[2]);
        same_slice(&counts.a, &saved.a);
        same_slice(&counts.e, &saved.e);
        aggregate.add(counts);
    }
    let mut expected = 0.0;
    for _ in 0..7 {
        expected += TINY;
    }
    assert!(
        aggregate
            .a
            .iter()
            .all(|&v| v.to_bits() == expected.to_bits())
    );
    assert!(
        aggregate.e[..4]
            .iter()
            .all(|&v| v.to_bits() == expected.to_bits())
    );
    assert_eq!(&aggregate.e[4..], &[0.0, 0.0]);
}

#[test]
fn impossible_and_nonfinite_models_preserve_dense_classification() {
    let mut model = toy_model();
    model.emission[..2].fill(0.0);
    let prepared = PreparedModel::new(&model);
    let mut workspace = Workspace::new(model.n);
    for observations in [&[0][..], &[0, 1, 2][..], &[2, 2, 0, 1, 2][..]] {
        compare(&mut workspace, &prepared, observations);
    }
    drop(prepared);
    model.transition[0] = f64::NAN;
    model.emission[0] = f64::NAN;
    let prepared = PreparedModel::new(&model);
    compare(&mut workspace, &prepared, &[0, 1, 2, 0]);
}

#[test]
fn shorter_records_retain_allocations_but_expose_only_their_own_cells() {
    let model = toy_model();
    let prepared = PreparedModel::new(&model);
    let mut workspace = Workspace::new(model.n);
    workspace.evaluate(&prepared, &[0; 1000]);
    let forward = workspace.messages.forward.as_ptr();
    let backward = workspace.messages.backward.as_ptr();
    let scales = workspace.messages.scales.as_ptr();
    workspace.evaluate(&prepared, &[2]);
    assert_eq!(forward, workspace.messages.forward.as_ptr());
    assert_eq!(backward, workspace.messages.backward.as_ptr());
    assert_eq!(scales, workspace.messages.scales.as_ptr());
    assert_eq!(workspace.messages.forward.len(), 4);
    assert_eq!(workspace.messages.backward.len(), 4);
    assert_eq!(workspace.messages.scales.len(), 2);
    compare(&mut workspace, &prepared, &[0; 999]);
}

#[test]
#[should_panic(expected = "HMM sequence must be nonempty")]
fn rejects_empty_sequence() {
    let model = toy_model();
    Workspace::new(model.n).evaluate(&PreparedModel::new(&model), &[]);
}

#[test]
#[should_panic(expected = "HMM observations must be encoded as 0, 1, or 2")]
fn rejects_bad_observation() {
    let model = toy_model();
    Workspace::new(model.n).evaluate(&PreparedModel::new(&model), &[0, 3]);
}
