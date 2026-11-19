# Form EC8A: extraction schema (v1)

**Status:** fields confirmed from public reporting of real sheets; no blank official template was retrievable (INEC manual and PU directory PDFs returned 404 on 2026-11-19). Field names are configurable in `apps/results/schema.py`.

## Fields
| Key | On the sheet | Type |
|---|---|---|
| `state`, `lga`, `ward`, `pu_name`, `pu_code` | Header | text / `SS/LL/WW/PPP` |
| `election` | Header (EC8A = presidential; EC8A(i)/(ii) = Senate/Reps) | text |
| `registered` | Number of voters on the register | int |
| `accredited` | Number of accredited voters | int |
| `ballots_issued` | Number of ballot papers issued to the polling unit | int |
| `unused` | Number of unused ballot papers | int |
| `spoilt` | Number of spoilt ballot papers | int |
| `rejected` | Number of rejected ballots | int |
| `total_valid` | Total number of valid votes | int |
| `total_used` | Total number of used ballot papers | int |
| `party_votes[acronym]` | Score per party, **in figures** | int |
| `party_words[acronym]` | Score per party, **in words** (parsed to int) | int / null |
| `cancelled` | Endorsed "Result Cancelled" / "NULL AND VOID" | bool |
| `signed_by_agents` | Agent signatures present | bool |
| `stamped` | Official stamp present | bool |

Every field is returned as `{value, confidence 0–1, unreadable}`.

## Arithmetic rules (`apps/trust/arithmetic.py`)
1. Σ party_votes = total_valid
2. total_valid + rejected = total_used (e.g. 467 + 6 = 473, Tribune, Ogun 2026)
3. total_used ≤ accredited ≤ registered
4. ballots_issued = total_used + unused + spoilt (e.g. 473 + 1,857 + 0 = 2,330)
5. figures = words per party
6. No negatives; integers only

Known real-world anomalies the rules catch: valid votes above accredited (CDD fact-check, Edo); more ballot rows than sheet rows (Yiaga, Ekiti 2026).

## Sources
- Tribune, Ota-Efun PU 3 EC8A worked figures: https://tribuneonlineng.com/inec-register-how-overloaded-polling-units-breached-registration-threshold-delayed-transmission-to-irev/
- CDD fact-check, valid > accredited: https://cddfactcheck.org/fact-check-form-ec8a-shows-higher-valid-votes-than-accredited-voters-in-pu-1-okpella-iv-etsako-east-lga/
- Dubawa forms explainer: https://dubawa.org/explainer-what-you-should-know-about-various-forms-used-on-election-day/
- Vanguard, collation chain + Electoral Act 2026 s.60(3): https://www.vanguardngr.com/2026/11/explainer-election-results-collation-chain-that-decides-nigerias-president/
- INEC presiding officer ("Result Cancelled"): https://inecnigeria.org/?p=3003
