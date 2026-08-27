# ADR-030: Report Projects Persisted Calculation Logic

- Status: Accepted (POST-V0.9 P3)
- Date: 2026-08-27
- Context: After `v0.9.0`, draft reports still used
  `cold_storage_concept_design@1.0.0`. `input_conditions` only allowed
  `zones` / `temperature_levels` / `coefficients_used`. Canonical render
  skipped arrays, so Word/PDF **输入条件** was often empty. Calculator runs
  already persist `formulas` (`formula_id`, `expression`, `description`)
  and sometimes `steps`. Reports must not recalculate those formulas.

## Decision

1. Keep report type identity `cold_storage_concept_design@1.0.0`.
   Additive schema only. Do not invent a parallel report type.

2. `input_conditions` gains optional scalar properties for the V0.9 five
   KEY. Values come from persisted five-stage / operator process input /
   zone `input_snapshot`. Missing KEY are omitted. No silent defaults.

3. New optional section `calculation_logic` projects persisted
   `formulas` and `steps` per canonical stage. Assembler **copies** those
   records. It does not re-run calculators, does not embed full Python
   formula code in prompts, and does not invent steps when the run has
   none.

4. Canonical render must emit those scalars and tables. An empty
   **输入条件** / missing logic section is a defect when persisted KEY or
   formulas exist.

5. Vue report preview may display the same persisted JSON. Vue must not
   compute engineering values.

## Consequences

- Localization catalogs gain keys for the five KEY labels and for
  `section.calculation_logic` / step table headers. Catalog identity
  stays `1.0.0`; content hash changes.
- Quality evaluation must not treat the new optional section as a
  missing required block when no formulas were persisted.
- Formula recuts remain calculator-module work, not report work.

## Alternatives rejected

- Recalculating in the report assembler or in Vue.
- Bumping the report type to `@2.0.0` in this package.
- Encoding Chinese `item_name` as the only translation key (TD-022 stays
  a later projection cleanup).
