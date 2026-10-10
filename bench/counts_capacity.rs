// Allocation-capacity diagnostic, not an RSS or performance benchmark.
// Replays old Vec::resize and new reserve_exact + resize using the HG block sizes.
fn main() {
    let mut old: Vec<f64> = Vec::new();
    let mut new: Vec<f64> = Vec::new();
    println!("[");
    for (index, bins) in [50_000, 58_185, 50_000].into_iter().enumerate() {
        let cells = (bins + 1) * 64;
        old.resize(cells, 0.0);
        if cells > new.capacity() {
            new.reserve_exact(cells - new.len());
        }
        new.resize(cells, 0.0);
        assert_eq!(old.len(), new.len());
        assert_eq!(old, new);
        println!(
            "{}{{\"bins\": {}, \"length_cells\": {}, \"old_capacity_cells\": {}, \"new_capacity_cells\": {}, \"old_capacity_bytes\": {}, \"new_capacity_bytes\": {}}}",
            if index == 0 { "" } else { "," },
            bins, cells, old.capacity(), new.capacity(), old.capacity() * 8, new.capacity() * 8
        );
    }
    println!("]");
}
