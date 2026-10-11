//! Fail-closed bootstrap resume. Kernel lock lifetime follows the open File.
use crate::{Options, digest};
use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::Path,
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub const SUFFIXES: [&str; 3] = ["psmc", "stats.json", "draws.jsonl"];

pub fn lock(directory: &Path) -> Result<File> {
    let path = directory.join("run.lock");
    if fs::symlink_metadata(&path).is_ok_and(|m| !m.is_file()) {
        return Err("checkpoint lock must be a regular file".into());
    }
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::AsRawFd;
        unsafe extern "C" {
            fn flock(fd: std::ffi::c_int, operation: std::ffi::c_int) -> std::ffi::c_int;
        }
        // SAFETY: valid owned fd; LOCK_EX|LOCK_NB. File stays open for the run.
        if unsafe { flock(file.as_raw_fd(), 2 | 4) } != 0 {
            return Err("bootstrap directory is locked by another process (or filesystem locking is unsupported)".into());
        }
    }
    #[cfg(not(target_os = "linux"))]
    return Err("resumable bootstrap currently requires Linux advisory file locks".into());
    Ok(file)
}
fn regular(path: &Path) -> Result<()> {
    if !fs::symlink_metadata(path)?.is_file() {
        return Err(format!("checkpoint requires a regular file: {}", path.display()).into());
    }
    Ok(())
}
pub fn identity(
    options: &Options,
    sequences: &[psmc_core::Sequence],
    seed: i64,
    replicates: usize,
) -> Result<String> {
    // Debug representation preserves round-trip f64 settings. Executable hash
    // makes this private format explicitly local to the same build.
    Ok(format!(
        "PSMC-RESUME-1\nexecutable={}\ninput={}\nseed={seed}\nreplicates={replicates}\nsettings={:?}\niterations={}\nbackend={}\nmode={}\ncache={}\nsimd={}\ndecode={}\nfull={}\nprobability={}\ncap={}\ncuda_tile={}\ncuda_memory={}\n",
        digest::file(std::env::current_exe()?)?,
        digest::sequences(sequences),
        options.settings,
        options.iterations,
        options.backend,
        options.mode,
        options.cache,
        options.simd.name(),
        options.decode,
        options.full,
        options.probability,
        options.cap,
        options.cuda_tile_sites,
        options.cuda_memory_mib
    ))
}
pub fn contract(directory: &Path, expected: &str, resume: bool) -> Result<()> {
    let path = directory.join("resume-contract.txt");
    if resume {
        regular(&path)?;
        if fs::read_to_string(path)? != expected {
            return Err("resume contract mismatch: input, seed, fit settings or executable changed; use the original configuration or a new directory".into());
        }
    } else {
        atomic(directory, "resume-contract.txt", expected)?;
    }
    Ok(())
}
fn atomic(directory: &Path, name: &str, text: &str) -> Result<()> {
    // Preserve any interrupted write under a distinct name on every attempt.
    let mut n = 0;
    let (path, mut file) = loop {
        let path = directory.join(format!(".{name}.{n}.partial"));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(file) => break (path, file),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => n += 1,
            Err(e) => return Err(e.into()),
        }
    };
    file.write_all(text.as_bytes())?;
    file.sync_all()?;
    let final_path = directory.join(name);
    if final_path.exists() {
        return Err("checkpoint destination already exists".into());
    }
    fs::rename(path, final_path)?;
    File::open(directory)?.sync_all()?;
    Ok(())
}
pub fn complete(directory: &Path, index: usize, nonfinite: bool) -> Result<()> {
    let mut text = format!("PSMC-COMPLETE-1\n{nonfinite}\n");
    for suffix in SUFFIXES {
        let path = directory.join(format!("replicate-{index:02}.{suffix}"));
        regular(&path)?;
        File::open(&path)?.sync_all()?;
        text.push_str(&format!("{} {suffix}\n", digest::file(path)?));
    }
    atomic(directory, &format!("replicate-{index:02}.complete"), &text)
}
pub fn verify(directory: &Path, index: usize) -> Result<Option<bool>> {
    let marker = directory.join(format!("replicate-{index:02}.complete"));
    match fs::symlink_metadata(&marker) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.into()),
        Ok(_) => regular(&marker)?,
    }
    let text = fs::read_to_string(marker)?;
    let lines: Vec<_> = text.lines().collect();
    if lines.len() != 5 || lines[0] != "PSMC-COMPLETE-1" {
        return Err("invalid completion marker".into());
    }
    let nonfinite = lines[1].parse::<bool>()?;
    for (suffix, line) in SUFFIXES.into_iter().zip(&lines[2..]) {
        let path = directory.join(format!("replicate-{index:02}.{suffix}"));
        regular(&path)?;
        if *line != format!("{} {suffix}", digest::file(path)?) {
            return Err(format!(
                "completed replicate {index} failed checksum verification; no files changed"
            )
            .into());
        }
    }
    Ok(Some(nonfinite))
}
pub fn preserve_partial(directory: &Path, index: usize) -> Result<()> {
    let paths: Vec<_> = SUFFIXES
        .into_iter()
        .map(|suffix| directory.join(format!("replicate-{index:02}.{suffix}")))
        .filter(|p| fs::symlink_metadata(p).is_ok())
        .collect();
    if paths.is_empty() {
        return Ok(());
    }
    let mut n = 0;
    let destination = loop {
        let path = directory.join(format!("incomplete-{index:02}-{n}"));
        match fs::create_dir(&path) {
            Ok(()) => break path,
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => n += 1,
            Err(e) => return Err(e.into()),
        }
    };
    for p in paths {
        fs::rename(&p, destination.join(p.file_name().unwrap()))?;
    }
    Ok(())
}
