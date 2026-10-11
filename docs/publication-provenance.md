# Publication history and frozen evidence

Before public release, the owner chose to replace their personal Git email with
GitHub's no-reply address. The original repository, draft release, hosted runs and
local raw evidence remain private. Public history was imported into a separate
repository, not force-pushed over the original GitHub object database. This keeps
old cached commits out of the public repository.

The rewrite changed only author, committer and tagger email metadata. All64
historical commit trees were checked for exact equality. The machine-readable
[commit mapping](publication-history-map.json) records original SHA, publication
SHA and unchanged tree SHA. Use it to resolve original commit IDs in frozen
scientific reports. Short IDs are prefixes of the full original hashes. Report
contents, input/output hashes, numerical results and failed screens were retained.
Do not interpret the new commit IDs as new scientific runs.

Historical hosted-run URLs were recorded before the private evidence repository
was renamed and are not public CI attestations. Public build and test runs are
available in [Actions](https://github.com/DylanCosto/psmc-rs/actions). Release
archives record the public source commit in BUILD.json, with native build
verification and SHA-256 manifests. Final publication rebuilds are checked against
the already-qualified executable hashes; matching bytes preserve that executable's
whole-genome replay evidence. This does not extend validation to untested hardware
or change the documented limits of scientific agreement.

Raw genomic inputs, the original email-bearing Git objects and private work files
are not part of the public repository or release assets. Third-party attribution
and upstream author identities are retained.
