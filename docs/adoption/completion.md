# Adoption release completion — 2026-10-11

PSMC-rs0.8.0 is published at [GitHub Releases](https://github.com/DylanCosto/psmc-rs/releases/tag/v0.8.0).
The release source is `d91ab61f78bc7a399d30f53e01f7d54b8f03717b`.
[Native CI](https://github.com/DylanCosto/psmc-rs/actions/runs/38170017723) passed on
Linux x86-64 and ARM64. This document records completed scope, not a prediction of
adoption or independent scientific endorsement.

| Requirement | Evidence and result |
| --- | --- |
| Licensing, upstream attribution, citation | Root LICENSE, NOTICE.md, validated CITATION.cff, original PSMC/phlash notices and pinned Rust runtime inventory; all included in archives. |
| Tagged binaries and installation | Two native GNU/Linux archives, checksums, BUILD.json, native verification and VALIDATION.json published. Eight assets downloaded anonymously; all42 packaged files per architecture checked. See bench/public-release-verification.json. |
| Tutorial and workflow | docs/tutorial.md; inspect, split, fit, bootstrap, resume, CSV export and plotting demonstrated. Earlier synthetic workflow took4.01s excluding dependency installation (bench/adoption-workflow.json). Native regression tests cover interruption/resume and invalid/tampered inputs; downloaded x86 strict golden and equivalent/export smoke checks pass. |
| README and benchmark presentation | Usage-first README, benchmark PNG/SVG and source data. Controlled results remain explicitly v0.6.3, with single-core/full-affinity and shared-host/memory limits separated. No new0.8 speed claim. |
| Broader scientific qualification | All30 matched HG001 whole-genome bootstrap pairs and four additional-pattern HG001/HG002 comparisons passed predeclared screens. Strict/C bytes matched; compiler controls passed. See docs/adoption-qualification-report.md and its independent audit. Final release executable bytes match the whole-genome replay binary. |
| Stable numerical construction investigation | Component/Decimal and full-fit investigation completed; candidate stays outside production because fit trajectories changed. docs/stable-model-report.md preserves results. Strict production arithmetic is unchanged. |
| Packaging and community materials | Local container workflow and runtime notices verified; no registry image claimed. Methods note, contribution/security guidance, external-pilot checklist, feedback form and announcement draft prepared. Private vulnerability reporting enabled on GitHub. |
| Publication privacy and provenance | Owner-selected no-reply history,64 identical historical source trees, original evidence retained privately. Anonymous public clone checked for absence of the personal email; checked original private repository/commit URLs are inaccessible. See docs/publication-provenance.md and bench/publication-{history-audit,access-verification}.json. |

The published executable hashes are unchanged from the qualified native binaries:
- x86-64: `e27d7bbf7250b8a121fdd985690cc47de18ffa952105c0cf00bdfcce9d6230f5`
- ARM64: `4b247fe217cea3a539671cbe927b1310bfe87bae3cc9bb719cdcb24581a1afa8`

Qualification remains specific to tested inputs/settings. ARM has native build and
regression evidence, not whole-genome science or speed qualification. Previous
failed pilot screens remain documented. The user's own workload is not claimed
as tested. No invitations or announcement messages were sent, no independent lab
feedback was received, and no preprint/DOI or package/container registry submission
is claimed. Those require owner-selected participants or additional author/account
information. The prepared materials are available for that follow-up.
