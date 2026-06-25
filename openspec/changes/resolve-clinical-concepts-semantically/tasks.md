## 1. Concept Resolution

- [x] 1.1 Add resolver tests for respiratory phrase variants including `causa respiratorias`
- [x] 1.2 Add false-positive tests for phrases that should remain description lookup
- [x] 1.3 Normalize noisy clinical phrases before concept matching
- [x] 1.4 Expand respiratory concept aliases only as needed to cover observed variants

## 2. Planner And SQL Behavior

- [x] 2.1 Update semantic planning so known concepts produce code or prefix filters before literal description filters
- [x] 2.2 Add tests proving respiratory concepts emit `diagnostico_principal_prefix=J%`
- [x] 2.3 Add SQL-generation or validator regression proving raw `%respiratorias%` is not used for known respiratory concepts
- [x] 2.4 Run concept resolver, semantic planner, and affected query regression tests
