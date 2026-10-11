# Copyright and attribution

New PSMC-rs code and documentation are distributed under the root MIT LICENSE.
Original notices in translated source files remain in force and must be retained.

- **PSMC:** the model, optimizer and legacy conventions derive from Heng Li and
  Richard Durbin's PSMC. Pinned source: lh3/psmc commit
  82fa2ada83ee463fe1251b562ae3d60e82d7ad6a. Copyright notices name Genome Research
  Ltd (2007–2009), Broad Institute (2009–2015), and Heng Li (2008 where applicable).
  See reference/LICENSE.psmc.txt and individual source headers for the complete
  notices. Cite Li & Durbin (2011), doi:10.1038/nature10231, for the method.
- **phlash:** prior evaluation/reference material retains
  reference/LICENSE.phlash.txt (Jonathan Terhorst, 2024, MIT). This notice does
  not claim that phlash endorses PSMC-rs. The production Rust engine does not
  invoke phlash or Python inference.
- **System libraries:** GNU/Linux builds dynamically link the system C/math and
  zlib libraries. Their distributions and licenses are separate; the binary
  archive does not bundle those shared libraries. Static builds require an
  additional bundled-library license inventory before distribution.

Synthetic tutorial/test fixtures are generated for this project. Public human
inputs used in local qualification are not distributed with source or binaries.
PSMC-rs is an independent implementation, not an official release of lh3/psmc.
