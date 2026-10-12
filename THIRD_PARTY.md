# Dependencies and reference data

- liberty-parser 0.0.29: Thomas Kramer's Liberty parser; GPL-3.0-or-later. Installed separately through Python packaging; no source copied into this repository. https://codeberg.org/tok/liberty-parser
- NetworkX 3.2.1: graph algorithms; BSD-3-Clause. https://networkx.org/
- Yosys: external structural Verilog frontend; ISC license with separately licensed bundled components. https://github.com/YosysHQ/yosys
- Graphviz: external DOT/SVG renderer; Eclipse Public License. https://graphviz.org/license/
- pytest: test runner; MIT license. https://github.com/pytest-dev/pytest
- Optional YoWASP packages: portable Yosys distribution and runtime, installed separately. Native Yosys is the validated backend for this release. https://github.com/YoWASP/yosys

The project uses the GPL-3.0-or-later license. Third-party projects retain their own copyright and licensing terms.

## Nangate45 reference library

Downloaded October 6, 2026 from:
https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

SHA-256: `8d540a4d4cf6d09d27c87ad067857a9c0c2eeb023ab7a56e058cd3113db4e9b1`

Local path: `third_party/nangate45/NangateOpenCellLibrary_typical.lib` (ignored by Git). The original file and copyright header are unchanged. It is not included in the Python package. Refer to the upstream Nangate45 platform's license and notices before redistributing it. The tiny demonstration library and example circuits in `examples/` are authored for this project.
