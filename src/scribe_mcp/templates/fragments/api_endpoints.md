## API Endpoints
<!-- ID: api_endpoints -->
### Core REST API
| Method | Endpoint | Description | Parameters | Response |
|--------|----------|-------------|------------|----------|
| GET | `/api/v1/{project_slug}/status` | Get project status | - | Project status object |
| POST | `/api/v1/{project_slug}/entries` | Append new log entry | `message`, `status`, `meta` | Created entry object |
| GET | `/api/v1/{project_slug}/entries` | Query log entries | `start`, `end`, `filter` | Array of entry objects |
| GET | `/api/v1/{project_slug}/projects` | List all projects | - | Array of project objects |
| POST | `/api/v1/{project_slug}/docs` | Update documentation | `doc`, `action`, `section`, `content` | Update result |

### Documentation Management API
| Method | Endpoint | Description | Parameters | Response |
|--------|----------|-------------|------------|----------|
| PUT | `/api/v1/{project_slug}/docs/{doc_name}/sections/{section_id}` | Replace document section | `content`, `metadata` | Updated document |
| POST | `/api/v1/{project_slug}/docs/{doc_name}/sections/{section_id}/status` | Update checklist status | `status`, `proof` | Updated status |
| POST | `/api/v1/{project_slug}/docs/{doc_name}/generate` | Generate documentation templates | `documents`, `overwrite` | Generated files list |

### Security & Monitoring API
| Method | Endpoint | Description | Parameters | Response |
|--------|----------|-------------|------------|----------|
| GET | `/api/v1/{project_slug}/health` | Health check | - | System health status |
| GET | `/api/v1/{project_slug}/metrics` | System metrics | - | Performance metrics |
| GET | `/api/v1/{project_slug}/security/audit` | Security audit trail | `start`, `end` | Security events |

> All endpoints support JSON responses with proper HTTP status codes and error handling. Rate limiting applies to public endpoints.