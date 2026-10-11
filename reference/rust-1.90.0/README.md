# Rust runtime notices

The GNU/Linux executables include Rust standard-library and compiler support code
from the pinned Rust 1.90.0 toolchain. These files preserve the upstream licenses,
copyright notices and dependency inventory; `inventory.json` records their
provenance and SHA-256 hashes. The inventory is intentionally broader than the
platform-specific code retained by the linker and does not assert every listed
dependency is present in a Linux executable.

`COPYRIGHT-library.html` is the unmodified standard-library notice inventory from
the official Rust distribution, including third-party license texts. Root Rust
MIT/Apache texts, the in-tree Unicode/BSD license texts and compiler-builtins'
license are included separately. These notices supplement PSMC-rs's root license;
they do not replace upstream terms. Compiler-builtins' combined-license wording
is preserved verbatim. Recheck this inventory whenever the toolchain changes.

The dynamically linked system libraries are supplied by the host distribution.
The container base supplies its own shared libraries and packaged copyright files.
