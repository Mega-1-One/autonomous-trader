# PHASE 35 - STRICT ANTI-DATA-MINING PROTOCOL

## 1. Immutable Dataset & Preregistered Hypotheses
- **Immutable Dataset SHA256**: `25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728`
- **Preregistration**: Every candidate hypothesis must be registered in JSON with economic rationale prior to testing.

## 2. Statistical & Replication Requirements
- **Multiple-Testing Control**: Mandatory Benjamini-Hochberg FDR correction across all hypothesis families.
- **Chronological Validation**: 60% Train, 20% Validation, 20% untouched Out-of-Sample (OOS).
- **Cross-Instrument Replication**: A hypothesis discovered on one asset must independently replicate on at least one other correlated asset.
- **Economic Significance Floor**: Minimum Net Expectancy $> +0.05R$ after realistic ECN commissions and spread drag.
