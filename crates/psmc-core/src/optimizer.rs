//! Literal translation of `kmin.c` from lh3/psmc commit
//! 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a. Callback order and side effects are observable.
/* The MIT License

   Copyright (c) 2008, by Heng Li <lh3@live.co.uk>

   Permission is hereby granted, free of charge, to any person obtaining
   a copy of this software and associated documentation files (the
   "Software"), to deal in the Software without restriction, including
   without limitation the rights to use, copy, modify, merge, publish,
   distribute, sublicense, and/or sell copies of the Software, and to
   permit persons to whom the Software is furnished to do so, subject to
   the following conditions:

   The above copyright notice and this permission notice shall be
   included in all copies or substantial portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
   EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
   MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
   NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
   BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
   ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
   CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
   SOFTWARE.
*/

fn explore<F: FnMut(&[f64]) -> f64>(
    func: &mut F,
    x1: &mut [f64],
    mut fx1: f64,
    dx: &mut [f64],
    n_calls: &mut usize,
) -> f64 {
    let mut j = *n_calls;
    for k in 0..x1.len() {
        x1[k] += dx[k];
        let mut ftmp = func(x1);
        j += 1;
        if ftmp < fx1 {
            fx1 = ftmp;
        } else {
            dx[k] = 0.0 - dx[k];
            x1[k] += dx[k] + dx[k];
            ftmp = func(x1);
            j += 1;
            if ftmp < fx1 {
                fx1 = ftmp;
            } else {
                x1[k] -= dx[k];
            }
        }
    }
    *n_calls = j;
    fx1
}

/// The nominal call limit is checked between whole exploration blocks, as in C.
/// The last callback may differ from the accepted `x`; no callback is added on return.
pub fn hooke_jeeves<F: FnMut(&[f64]) -> f64>(
    x: &mut [f64],
    func: &mut F,
    radius: f64,
    eps: f64,
    max_calls: usize,
) -> f64 {
    let n = x.len();
    let r = radius;
    let mut radius = r;
    let mut x1 = vec![0.0; n];
    let mut dx = vec![0.0; n];
    for k in 0..n {
        dx[k] = x[k].abs() * r;
        if dx[k] == 0.0 {
            dx[k] = r;
        }
    }
    let mut fx = func(x);
    let mut n_calls = 1;
    let mut fx1;
    loop {
        x1.copy_from_slice(x);
        fx1 = explore(func, &mut x1, fx, &mut dx, &mut n_calls);
        while fx1 < fx {
            for k in 0..n {
                let t = x[k];
                dx[k] = if x1[k] > x[k] {
                    dx[k].abs()
                } else {
                    0.0 - dx[k].abs()
                };
                x[k] = x1[k];
                x1[k] = x1[k] + x1[k] - t;
            }
            fx = fx1;
            if n_calls >= max_calls {
                break;
            }
            fx1 = func(&x1);
            n_calls += 1;
            fx1 = explore(func, &mut x1, fx1, &mut dx, &mut n_calls);
            if fx1 >= fx {
                break;
            }
            let mut k = 0;
            while k != n {
                if (x1[k] - x[k]).abs() > 0.5 * dx[k].abs() {
                    break;
                }
                k += 1;
            }
            if k == n {
                break;
            }
        }
        if radius >= eps {
            if n_calls >= max_calls {
                break;
            }
            radius *= r;
            for k in 0..n {
                dx[k] *= r;
            }
        } else {
            break;
        }
    }
    fx1
}

#[cfg(test)]
mod tests {
    use super::hooke_jeeves;

    #[test]
    fn flat_objective_preserves_last_callback_and_radius_boundary() {
        let mut x = [1.0];
        let mut visited = Vec::new();
        let result = hooke_jeeves(
            &mut x,
            &mut |v| {
                visited.push(v[0]);
                7.0
            },
            0.5,
            0.25,
            50_000,
        );
        assert_eq!(visited, [1.0, 1.5, 0.5, 0.75, 1.25, 1.125, 0.875]);
        assert_eq!(x, [1.0]);
        assert_eq!(result, 7.0);
    }

    #[test]
    fn nominal_limit_does_not_interrupt_coordinate_exploration() {
        let mut x = [1.0, 2.0];
        let mut visited = Vec::new();
        hooke_jeeves(
            &mut x,
            &mut |v| {
                visited.push(v.to_vec());
                f64::NAN
            },
            0.5,
            1e-7,
            1,
        );
        assert_eq!(
            visited,
            [
                vec![1.0, 2.0],
                vec![1.5, 2.0],
                vec![0.5, 2.0],
                vec![1.0, 3.0],
                vec![1.0, 1.0]
            ]
        );
        assert_eq!(x, [1.0, 2.0]);
    }
}
