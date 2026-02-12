## Directory Structure (Keep Updated)
```
{{ project_root }}/
├── {{ project_slug }}/
│   ├── src/
│   │   ├── main.py                    # Main application entry point
│   │   ├── config/                    # Configuration files
│   │   ├── models/                    # Data models and schemas
│   │   ├── services/                  # Business logic services
│   │   ├── utils/                     # Utility functions
│   │   └── tests/                     # Unit and integration tests
│   ├── docs/                          # Documentation
│   ├── scripts/                       # Build and deployment scripts
│   ├── requirements.txt               # Python dependencies
│   ├── README.md                      # Project documentation
│   └── setup.py                       # Package setup
├── config/
│   ├── {{ project_slug }}_config.json     # Project configuration
│   └── log_config.json                # Multi-log routing configuration
├── docs/dev_plans/{{ project_slug }}/
│   ├── ARCHITECTURE_GUIDE.md          # System design and technical blueprint
│   ├── PHASE_PLAN.md                  # Development roadmap with phases and tasks
│   ├── CHECKLIST.md                   # Verification ledger with acceptance criteria
│   ├── PROGRESS_LOG.md                # Append-only audit trail (UTC timestamps)
│   ├── DOC_LOG.md                     # Documentation update log
│   ├── SECURITY_LOG.md                # Security events and decisions
│   └── BUG_LOG.md                     # Bug tracking and resolution log
└── tests/
    ├── unit/                          # Unit test suites
    ├── integration/                   # Integration test suites
    ├── fixtures/                      # Test data and fixtures
    └── conftest.py                    # PyTest configuration and fixtures
```

> This directory structure follows Python best practices with clear separation of concerns. Update this structure as the project evolves and grows.

{% if project_description %}
**Project Description:** {{ project_description }}
{% endif %}

{% if version %}
**Version:** {{ version }}
{% endif %}