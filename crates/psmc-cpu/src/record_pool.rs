//! Cooperative record queue. It owns no threads: idle fit workers become helpers.
//! Jobs own their inputs, and callers reduce returned results in input order.
use std::{
    collections::VecDeque,
    sync::{
        Arc, Condvar, Mutex,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
    time::Duration,
};
type Job = Box<dyn FnOnce() + Send + 'static>;
#[derive(Default)]
pub struct RecordPool {
    queue: Mutex<VecDeque<Job>>,
    wake: Arc<Condvar>,
    stopped: AtomicBool,
    helpers: AtomicUsize,
    helper_jobs: AtomicUsize,
}
impl RecordPool {
    pub fn has_helpers(&self) -> bool {
        self.helpers.load(Ordering::Acquire) > 0
    }
    pub fn helper_jobs(&self) -> usize {
        self.helper_jobs.load(Ordering::Relaxed)
    }
    pub fn stop(&self) {
        self.stopped.store(true, Ordering::Release);
        self.wake.notify_all();
    }
    fn help_one(&self, reserve: usize) -> bool {
        let job = {
            let mut queue = self.queue.lock().expect("record queue");
            if queue.len() > reserve {
                queue.pop_front()
            } else {
                None
            }
        };
        if let Some(job) = job {
            job();
            true
        } else {
            false
        }
    }
    pub fn help_until_stopped(&self) {
        self.help_with_reserve(0);
    }
    pub fn help_with_reserve(&self, reserve: usize) {
        self.helpers.fetch_add(1, Ordering::Release);
        while !self.stopped.load(Ordering::Acquire) {
            if self.help_one(reserve) {
                self.helper_jobs.fetch_add(1, Ordering::Relaxed);
            } else {
                let guard = self.queue.lock().expect("record queue");
                if guard.len() <= reserve && !self.stopped.load(Ordering::Acquire) {
                    drop(
                        self.wake
                            .wait_timeout(guard, Duration::from_millis(10))
                            .expect("record wait"),
                    );
                }
            }
        }
        self.helpers.fetch_sub(1, Ordering::Release);
    }
    pub(crate) fn map<T: Send + 'static, F: Fn(Vec<u8>) -> T + Send + Sync + 'static>(
        &self,
        records: Vec<Vec<u8>>,
        evaluate: F,
    ) -> Vec<T> {
        let evaluate = Arc::new(evaluate);
        let slots: Vec<_> = records
            .into_iter()
            .map(|obs| {
                let slot = Arc::new(Mutex::new(None));
                let result = slot.clone();
                let evaluate = evaluate.clone();
                let wake = self.wake.clone();
                self.queue
                    .lock()
                    .expect("record queue")
                    .push_back(Box::new(move || {
                        let value = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                            evaluate(obs)
                        }));
                        *result.lock().expect("record result") = Some(value);
                        wake.notify_all();
                    }));
                slot
            })
            .collect();
        self.wake.notify_all();
        slots
            .into_iter()
            .map(|slot| {
                loop {
                    if let Some(result) = slot.lock().expect("record result").take() {
                        break match result {
                            Ok(value) => value,
                            Err(panic) => std::panic::resume_unwind(panic),
                        };
                    }
                    // A waiting fit remains a worker. No nested pools, blocked-worker
                    // deadlock or scheduling-dependent floating-point reduction.
                    if !self.help_one(0) {
                        let guard = self.queue.lock().expect("record queue");
                        if guard.is_empty() {
                            drop(
                                self.wake
                                    .wait_timeout(guard, Duration::from_millis(1))
                                    .expect("record wait"),
                            );
                        }
                    }
                }
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn results_are_ordered_and_panics_return_to_owner() {
        let pool = Arc::new(RecordPool::default());
        std::thread::scope(|scope| {
            for _ in 0..3 {
                let p = pool.clone();
                scope.spawn(move || p.help_until_stopped());
            }
            let out = pool.map((0..200).map(|i| vec![i]).collect(), |v| {
                if v[0] % 3 == 0 {
                    std::thread::yield_now();
                }
                v[0]
            });
            assert_eq!(out, (0..200).collect::<Vec<_>>());
            assert!(
                std::panic::catch_unwind(std::panic::AssertUnwindSafe(
                    || pool.map(vec![vec![0]], |_| panic!("fixture"))
                ))
                .is_err()
            );
            pool.stop();
        });
    }
}

// Each OS worker retains one strict workspace. Record jobs otherwise repeatedly
// allocate full forward/backward histories, hiding the scheduling benefit.
thread_local! {
    static DENSE_WORKSPACE: std::cell::RefCell<Option<(usize,crate::SimdMode,crate::Workspace)>> = const {std::cell::RefCell::new(None)};
}
pub(crate) fn dense_record(
    model: &psmc_core::model::Model,
    mode: crate::SimdMode,
    obs: &[u8],
) -> (psmc_core::hmm::Counts, f64, f64) {
    DENSE_WORKSPACE.with(|cell| {
        let mut storage = cell.borrow_mut();
        if storage
            .as_ref()
            .is_none_or(|(n, m, _)| *n != model.n || *m != mode)
        {
            *storage = Some((
                model.n,
                mode,
                crate::Workspace::with_simd(model.n, mode).expect("validated SIMD mode"),
            ));
        }
        let workspace = &mut storage.as_mut().unwrap().2;
        let prepared = workspace.prepare(model);
        let (messages, counts) = workspace.evaluate(&prepared, obs);
        (
            counts.clone(),
            messages.log_likelihood,
            messages.backward_check,
        )
    })
}
