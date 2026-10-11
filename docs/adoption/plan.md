# Adoption and release plan

Authorized 2026-10-11. Starting source d19ce8f; installed 0.7.0 remains available.
This plan covers the user's complete adoption request, including binary releases.
It does not promise popularity, independent participation, or untested platforms.

## Acceptance-gated milestones

1. **Project and release foundations.** MIT license covering new work with original
   notices retained; third-party notice inventory; valid CITATION.cff; contribution
   instructions, issue templates and security reporting guidance. Reproducible
   packaging script and release CI. Archive contains executable, licenses, version,
   source/build provenance, checksums, tutorial and only synthetic example input.
   Verify extraction and an actual fit from the packaged executable.
2. **First-use experience.** Small deterministic synthetic fixture and tutorial:
   inspect input, fit, split blocks, bootstrap and plot/export with explicitly
   supplied mutation rate and generation time. Measure tutorial completion time.
   Provide clear errors, progress and bounded memory. Add a tested interruption/
   resume contract that verifies input, settings and completed outputs; never reuse
   altered or incomplete results. Preserve legacy output and numerical defaults.
3. **Numerical investigation.** Derive stable equivalent-only model expressions
   before implementation. Compare with the existing Decimal oracle, ordinary and
   extreme parameter sweeps, full fits and frozen controls. Strict/C must remain
   byte exact. Do not promote an arithmetic candidate merely because it is finite.
   Failed candidates stay experimental or outside production with evidence retained.
4. **Broader qualification.** Write protocol before new results: additional state
   patterns, available independent public inputs, 30 matched whole-genome bootstrap
   samples, distribution/uncertainty and likelihood comparisons. Preserve failed
   screens. Freeze binaries/settings, deterministic draws and resource guards.
   Limit concurrent job memory, avoid copying genomes, and stop on disk/RAM floors.
   Qualify actual CI hardware separately; emulation is not hardware qualification.
5. **Release and presentation.** Rewrite README around installation and usage;
   retain full guarantees/limitations in linked docs. Generate a benchmark chart
   from existing evidence with single-core and multicore results separated. Publish
   an audited tagged release, Linux archives/checksums and CI results, then download
   the uploaded archive and test it. Public visibility follows the publication audit;
   do not upload raw genomic inputs or private work artifacts. Add descriptive topics.
6. **Adoption and scientific communication.** Prepare an onboarding checklist,
   independent reproduction/feedback form, methods note and announcement. Establish
   package-manager/container installation where practical. Identify external pilot
   users with the owner; sending invitations requires explicit recipient authorization.
   Report actual external feedback only after receipt. A preprint/DOI submission or
   account integration is a separate concrete action requiring complete author details.

## Resource and scientific rules

Work sequentially by acceptance gate. No cancelled simulations are resumed, no
large cohort download, paid compute purchase, benchmark threshold relaxation or
private-data publication. Use existing local data and bounded jobs. Keep raw
artifacts in ignored work/, compact provenance in Git, and a minimum 25 GiB disk
floor for large validation jobs with at least 4 GiB available RAM. Compilation and
small tests do not imply whole-genome resource qualification. Completed historical
reports remain immutable except clearly labeled current status/link corrections.

## Progress

- [x] Repository and current hosted CI inspected; starting tree clean.
- [x] Read numerical contracts and repository instructions.
- [x] Foundations and packaged binary verified (native x86-64/ARM64 CI; CFF validated).
- [x] Tutorial and workflow features verified (2092668; native CI 38154388521).
- [x] Stable-model investigation concluded; candidate isolated, adoption deferred.
- [x] Broader qualification completed and independently audited; all declared screens passed.
- [x] Native archives, uploaded private-draft assets and local container independently verified.
- [ ] Public publication and anonymous download verified; owner metadata decision pending.
- [x] Onboarding checklist, feedback form, methods note and announcement draft prepared.
- [ ] External participation: no recipients authorized or feedback received; owner-led follow-up.

## Decisions and open inputs

Default citation author: Dylan Costo unless corrected by the owner; no invented
ORCID, affiliation, DOI or coauthor. Preserve Heng Li/GRL/Broad notices and cite
Li & Durbin's original PSMC paper. New feature release version is selected only
when scope freezes; do not tag an unfinished candidate. The current private repo
remains private while release preparation and the publication audit are underway.

### Release candidate ready for the publication decision

Private draft `v0.8.0` points to `8cffa32df97d7d7c980863bd8c965b88c98748fd`.
Native Linux x86-64 and ARM64 CI38163968928 passed. All eight uploaded draft
assets were downloaded and checked against the native build artifacts; all40
packaged files per architecture passed their checksums. Downloaded x86 execution
passed strict golden, equivalent completion and both provenance exports. Runtime
notices are bundled. Executables are unchanged from the whole-genome replay.
Container workflow and completed-bootstrap resume passed; no registry image is
published. Verified0.8.0 is installed in project-local bin/, retaining0.7.0.

The audit found one personal email identity in existing commit/tag metadata.
The owner has been asked whether to publish it unchanged or use a no-reply
publication history while retaining original evidence privately. Until answered,
the repository stays private and the release stays draft. No history rewrite or
public announcement has been performed. Draft downloads do not prove anonymous
public access; that final check follows the publication decision.
