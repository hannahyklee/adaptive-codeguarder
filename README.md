# adaptive-codeguarder

This repository includes code to test a modification to `CodeGuarder` from ["Give LLMs a Security Course: Securing Retrieval-Augmented Code
  Generation via Knowledge Injection"](https://doi.org/10.1145/3719027.3765049). The original repository provided by the authors is included under `CodeGuarder/` and has been trimmed of unused bulk, and has been modified to use `uv` rather than `conda`. Data and code were originally published at https://zenodo.org/records/16957113. 

The modification includes a new `adaptive fallback` option, which uses a lightweight LLM as a judge to filter contradictory examples during prompt generation. New code is under `adaptive-fallback/`.

## Running Experiments

See the `README.md` under `adaptive-fallback/` for reproduction instructions.

## License

Source: Lin, Bo et al., "Give LLMs a Security Course" (CCS '25) artifact, https://zenodo.org/records/16957113, DOI 10.5281/zenodo.16957113. Listed under Zenodo with a CC BY 4.0 license.
