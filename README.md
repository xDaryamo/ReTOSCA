
[![codecov](https://codecov.io/gh/xDaryamo/tosca-roundtrip/graph/badge.svg?token=ro729s0Eyg)](https://codecov.io/gh/xDaryamo/tosca-roundtrip)

# TOSCA Roundtrip

**TOSCA Roundtrip** is a toolchain that enables **deterministic parsing and transformation** of TOSCA 2.0 service templates into an **intermediate representation (IR)**, by leveraging **Puccini Clout** graphs.

The goal is to support **roundtrip engineering** between high-level TOSCA specifications and various Infrastructure-as-Code (IaC) models.

---

## Architecture Overview

The project is organized into **modular packages**, following clean software engineering principles:

| Layer               | Purpose                                                                  |
|---------------------|--------------------------------------------------------------------------|
| `src/ir/`            | Pydantic-based **Intermediate Representation** models                   |
| `src/clout_to_ir/`   | **Parsing engine** to convert Clout ➔ IR                               |
| `src/clout_to_ir/mapping/`           | Helpers for **category inference**, **attribute**, **capability** mapping |
| `src/clout_to_ir/exceptions/`        | Custom **error hierarchy** for robust error reporting                   |

The conversion process is divided into clear **steps**:
- **Loader**: Load Clout from file or dictionary
- **Parser**: Validate and structure Clout data
- **Mapping**: Map Clout vertices/edges to IR nodes and relations
- **Inference**: Deduce missing information (e.g., node categories)

---

# Practical Checklist for the Thesis Project

## Phase 1 — Deterministic Forward Engineering (TOSCA → IaC)

- [x] Define a **formal intermediate representation (IR)** for service topologies.
- [x] Parse a **TOSCA 2.0** template into **Clout** format using **Puccini**.
- [x] Develop a **deterministic parser**:
  - [x] Load Clout graphs.
  - [ ] Map Clout vertexes and edges into IR (Nodes, Relations, etc.).
  - [ ] Heuristically **infer node categories** (Compute, Storage, etc.).
- [ ] Build a **code generator** that transforms IR into:
  - [ ] Ansible playbook.
  - [ ] Terraform configuration (optional)

## Phase 2 — Deterministic Reverse Engineering (IaC → TOSCA)

- [ ] Define how to **ingest existing IaC code** (e.g., Terraform plans).
- [ ] Develop an **IaC parser**:
  - [ ] Extract topology information from IaC files.
  - [ ] Populate the IR.
- [ ] Build a **TOSCA 2.0 generator**:
  - [ ] Serialize the IR into a valid TOSCA 2.0 YAML template.
- [ ] Validate the output using **Puccini**.

## Phase 3 — LLM-based Engineering (Forward and Reverse)

- [ ] Experiment with **prompt engineering** to:
  - [ ] Generate IaC from TOSCA via LLM (forward).
  - [ ] Abstract IaC into TOSCA via LLM (reverse).
- [ ] Compare **accuracy** and **loss metrics** between deterministic and LLM approaches.

## Phase 4 — Roundtrip Evaluation

- [ ] Execute the **roundtrip**:
  - [ ] TOSCA → IaC → TOSCA (deterministic path).
  - [ ] TOSCA → IaC → TOSCA (LLM-assisted path).
- [ ] Measure:
  - [ ] **Fidelity** (how much the structure changes).
  - [ ] **Information loss** (which fields are lost).
  - [ ] **Semantic correctness**.

## License

Licensed under the MIT License.

