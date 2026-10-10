// Synthetic differential fixture. See README.md for source/license provenance.
#[path = "../../crates/psmc-core/src/optimizer.rs"]
mod optimizer;
fn out(x: &[f64]) {
    use std::io::Write;
    for v in x {
        std::io::stdout().write_all(&v.to_ne_bytes()).unwrap()
    }
}
fn main() {
    for mode in 0..4 {
        for limit in [1, 10, 100, 1000] {
            let mut x = [0.0, 1.0, -2.0];
            let r = optimizer::hooke_jeeves(
                &mut x,
                &mut |x| {
                    out(x);
                    if mode == 1 {
                        return 7.0;
                    }
                    if mode == 2 && x[0] > 0.1 {
                        return f64::NAN;
                    }
                    if mode == 3 {
                        return x[0];
                    }
                    let mut sum = 0.0;
                    for i in 0..x.len() {
                        sum += (x[i] - i as f64) * (x[i] - i as f64)
                    }
                    sum
                },
                0.5,
                1e-7,
                limit,
            );
            out(&x);
            out(&[r]);
        }
    }
}
