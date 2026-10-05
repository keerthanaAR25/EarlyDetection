# API Documentation

Base URL: `http://localhost:8000/api`
Interactive docs (Swagger): `http://localhost:8000/docs`

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/summary` | GET | Executive summary counts |
| `/alerts` | GET | Ring candidates at HIGH/CRITICAL risk (`?risk_level=`) |
| `/rings` | GET | All ring candidates (`?limit=&offset=`) |
| `/rings/{id}` | GET | One ring candidate's full detail |
| `/rings/{id}/graph` | GET | Evidence subgraph (nodes/edges) |
| `/rings/{id}/timeline` | GET | Pattern sequence + window IDs |
| `/rings/{id}/patterns` | GET | Pattern events touching this ring's accounts |
| `/rings/{id}/evidence` | GET | Full forensic evidence record |
| `/rings/{id}/explanation` | GET | Risk score breakdown + top factors |
| `/accounts/{id}` | GET | Account detail + ring membership |
| `/transactions` | GET | Transactions (`?account_id=&limit=&offset=`) |
| `/patterns` | GET | Pattern events (`?pattern_type=&limit=&offset=`) |
| `/metrics` | GET | Model comparison metrics (all splits) |
| `/lead-time` | GET | Lead-time summary statistics |
| `/models` | GET | List of trained model names |
| `/analyze` | POST | Triggers full pipeline re-run (background job in production) |
| `/retrain` | POST | Triggers model retraining (background job in production) |
| `/upload` | POST | Dataset upload validation (stub — see docs/limitations.md) |

Every GET endpoint reads from the database populated by
`scripts/load_database.py` — no endpoint returns fabricated data.
Risk scores that haven't been computed return the string
`"Not yet evaluated"`, never a placeholder number.
