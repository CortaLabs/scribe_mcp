# Dead Code Analysis Report

**Analysis Date**: 2026-01-05
**Files Analyzed**: 209
**Agent**: ResearchAgent-Phase4-DeadCode

## Executive Summary

- **Total Unused Imports**: 435
- **Unreferenced Definitions**: 1030
- **Files with Parse Errors**: 0

## Unused Imports by File

### .scribe/docs/dev_plans/scribe_systematic_audit_1/token_measurement_query_entries.py

- Line 6: `List` (imported but never used)

### .scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/dead_code_analyzer.py

- Line 8: `os` (imported but never used)

### .scribe/temp_circular_dep_analyzer.py

- Line 7: `os` (imported but never used)

### config/__init__.py

- Line 3: `annotations` (imported but never used)
- Line 5: `settings` (imported but never used)

### config/log_config.py

- Line 3: `annotations` (imported but never used)
- Line 10: `Tuple` (imported but never used)

### config/repo_config.py

- Line 7: `annotations` (imported but never used)
- Line 10: `os` (imported but never used)

### config/settings.py

- Line 3: `annotations` (imported but never used)

### config/vector_config.py

- Line 6: `annotations` (imported but never used)

### db/__init__.py

- Line 3: `ops` (imported but never used)
- Line 3: `pool` (imported but never used)

### db/ops.py

- Line 3: `annotations` (imported but never used)

### db/pool.py

- Line 3: `annotations` (imported but never used)

### demo/demo_global_scribe.py

- Line 99: `RepoConfig` (imported but never used)

### doc_management/__init__.py

- Line 3: `apply_doc_change` (imported but never used)

### doc_management/change_logger.py

- Line 3: `annotations` (imported but never used)
- Line 13: `Tuple` (imported but never used)

### doc_management/change_rollback.py

- Line 3: `annotations` (imported but never used)

### doc_management/conflict_resolver.py

- Line 3: `annotations` (imported but never used)

### doc_management/diff_visualizer.py

- Line 3: `annotations` (imported but never used)
- Line 12: `Tuple` (imported but never used)
- Line 14: `ChangeRecord` (imported but never used)
- Line 14: `DiffResult` (imported but never used)

### doc_management/file_watcher.py

- Line 3: `annotations` (imported but never used)
- Line 22: `utcnow` (imported but never used)

### doc_management/integrity_verifier.py

- Line 3: `annotations` (imported but never used)
- Line 7: `json` (imported but never used)
- Line 13: `Set` (imported but never used)

### doc_management/manager.py

- Line 3: `annotations` (imported but never used)
- Line 7: `difflib` (imported but never used)
- Line 14: `Tuple` (imported but never used)
- Line 27: `ToolValidator` (imported but never used)

### doc_management/performance_monitor.py

- Line 3: `annotations` (imported but never used)

### doc_management/sync_manager.py

- Line 3: `annotations` (imported but never used)
- Line 7: `json` (imported but never used)
- Line 14: `Tuple` (imported but never used)

### plugins/registry.py

- Line 13: `annotations` (imported but never used)
- Line 16: `importlib.util` (imported but never used)
- Line 23: `Type` (imported but never used)
- Line 27: `settings` (imported but never used)

### plugins/vector_indexer.py

- Line 14: `annotations` (imported but never used)
- Line 21: `timezone` (imported but never used)
- Line 23: `Tuple` (imported but never used)
- Line 40: `settings` (imported but never used)
- Line 42: `VectorIndexRecord` (imported but never used)
- Line 836: `concurrent.futures` (imported but never used)

### reminders.py

- Line 9: `annotations` (imported but never used)
- Line 12: `timezone` (imported but never used)

### scripts/check_vector_index.py

- Line 4: `annotations` (imported but never used)

### scripts/migrate_database.py

- Line 13: `json` (imported but never used)
- Line 18: `Dict` (imported but never used)
- Line 18: `Any` (imported but never used)

### scripts/reindex_docs.py

- Line 7: `annotations` (imported but never used)

### scripts/reindex_vector.py

- Line 7: `annotations` (imported but never used)

### scripts/scribe.py

- Line 12: `annotations` (imported but never used)

### scripts/scribe_cli.py

- Line 9: `asyncio` (imported but never used)
- Line 17: `RepoConfig` (imported but never used)
- Line 17: `reload_repo_config` (imported but never used)
- Line 18: `get_plugin_security_info` (imported but never used)
- Line 19: `check_permission` (imported but never used)

### scripts/scribe_probe.py

- Line 9: `annotations` (imported but never used)

### scripts/test_mcp_server.py

- Line 4: `annotations` (imported but never used)

### security/sandbox.py

- Line 8: `annotations` (imported but never used)
- Line 10: `os` (imported but never used)

### server.py

- Line 3: `annotations` (imported but never used)
- Line 458: `tools` (imported but never used)
- Line 510: `load_active_project` (imported but never used)

### shared/__init__.py

- Line 3: `LoggingContext` (imported but never used)
- Line 3: `ProjectResolutionError` (imported but never used)
- Line 3: `clean_list` (imported but never used)
- Line 3: `compose_log_line` (imported but never used)
- Line 3: `default_status_emoji` (imported but never used)
- Line 3: `ensure_metadata_requirements` (imported but never used)
- Line 3: `normalize_metadata` (imported but never used)
- Line 3: `normalize_meta_filters` (imported but never used)
- Line 3: `resolve_log_definition` (imported but never used)
- Line 3: `resolve_logging_context` (imported but never used)
- Line 15: `LoggingToolMixin` (imported but never used)
- Line 16: `ProjectInfo` (imported but never used)
- Line 16: `ProjectRegistry` (imported but never used)

### shared/base_logging_tool.py

- Line 3: `annotations` (imported but never used)

### shared/execution_context.py

- Line 3: `annotations` (imported but never used)

### shared/logging_utils.py

- Line 7: `annotations` (imported but never used)

### shared/project_registry.py

- Line 1: `annotations` (imported but never used)

### state/__init__.py

- Line 3: `StateManager` (imported but never used)

### state/agent_identity.py

- Line 3: `annotations` (imported but never used)
- Line 5: `hashlib` (imported but never used)
- Line 6: `json` (imported but never used)
- Line 9: `datetime` (imported but never used)
- Line 9: `timezone` (imported but never used)

### state/agent_manager.py

- Line 3: `annotations` (imported but never used)
- Line 10: `ConflictError` (imported but never used)

### state/manager.py

- Line 3: `annotations` (imported but never used)

### storage/__init__.py

- Line 3: `annotations` (imported but never used)

### storage/base.py

- Line 3: `annotations` (imported but never used)

### storage/models.py

- Line 1: `annotations` (imported but never used)

### storage/postgres.py

- Line 3: `annotations` (imported but never used)

### storage/sqlite.py

- Line 3: `annotations` (imported but never used)
- Line 16: `MilestoneRecord` (imported but never used)
- Line 16: `ChecklistRecord` (imported but never used)
- Line 16: `DocumentSectionRecord` (imported but never used)
- Line 16: `CustomTemplateRecord` (imported but never used)
- Line 16: `DocumentChangeRecord` (imported but never used)
- Line 16: `SyncStatusRecord` (imported but never used)

### template_engine/__init__.py

- Line 3: `Jinja2TemplateEngine` (imported but never used)
- Line 3: `TemplateEngineError` (imported but never used)
- Line 3: `TemplateNotFoundError` (imported but never used)
- Line 3: `TemplateValidationError` (imported but never used)
- Line 3: `TemplateRenderError` (imported but never used)
- Line 3: `DEFAULT_VARIABLES` (imported but never used)
- Line 3: `RESTRICTED_BUILTINS` (imported but never used)

### template_engine/engine.py

- Line 3: `annotations` (imported but never used)
- Line 10: `Union` (imported but never used)
- Line 12: `Template` (imported but never used)

### templates/__init__.py

- Line 3: `annotations` (imported but never used)

### tests/debug_vector_processing.py

- Line 20: `faiss` (imported but never used)
- Line 21: `np` (imported but never used)
- Line 22: `SentenceTransformer` (imported but never used)

### tests/test_append_entry_config.py

- Line 6: `json` (imported but never used)
- Line 8: `datetime` (imported but never used)
- Line 8: `timezone` (imported but never used)
- Line 9: `Any` (imported but never used)
- Line 9: `Dict` (imported but never used)
- Line 9: `List` (imported but never used)

### tests/test_append_entry_priority.py

- Line 18: `LogPriority` (imported but never used)
- Line 18: `LogCategory` (imported but never used)

### tests/test_append_entry_tee_routing.py

- Line 1: `annotations` (imported but never used)

### tests/test_base_logging_tool.py

- Line 3: `annotations` (imported but never used)
- Line 5: `asyncio` (imported but never used)

### tests/test_bulletproof_corrector_enhancements.py

- Line 9: `json` (imported but never used)
- Line 10: `datetime` (imported but never used)

### tests/test_bulletproof_fallback_manager.py

- Line 12: `Mock` (imported but never used)
- Line 12: `MagicMock` (imported but never used)

### tests/test_config_manager.py

- Line 11: `Any` (imported but never used)
- Line 11: `Dict` (imported but never used)

### tests/test_db_activation.py

- Line 16: `asyncio` (imported but never used)
- Line 17: `time` (imported but never used)
- Line 18: `json` (imported but never used)
- Line 19: `Path` (imported but never used)
- Line 20: `Dict` (imported but never used)
- Line 20: `Any` (imported but never used)
- Line 29: `validate_session_isolation` (imported but never used)

### tests/test_diff_compiler.py

- Line 1: `annotations` (imported but never used)

### tests/test_doc_management.py

- Line 8: `timedelta` (imported but never used)

### tests/test_doc_management_basic.py

- Line 7: `asyncio` (imported but never used)
- Line 9: `time` (imported but never used)
- Line 12: `MagicMock` (imported but never used)

### tests/test_dual_parameter_integration.py

- Line 11: `json` (imported but never used)
- Line 22: `server` (imported but never used)

### tests/test_dual_parameter_logic.py

- Line 7: `asyncio` (imported but never used)

### tests/test_dual_parameter_support.py

- Line 19: `append_entry` (imported but never used)

### tests/test_enhanced_append_entry.py

- Line 19: `Any` (imported but never used)
- Line 19: `Dict` (imported but never used)
- Line 19: `List` (imported but never used)
- Line 33: `Settings` (imported but never used)

### tests/test_error_handler.py

- Line 11: `Mock` (imported but never used)

### tests/test_estimator.py

- Line 11: `math` (imported but never used)
- Line 13: `Dict` (imported but never used)
- Line 13: `Any` (imported but never used)

### tests/test_exception_healer.py

- Line 15: `Mock` (imported but never used)
- Line 16: `Dict` (imported but never used)
- Line 16: `Any` (imported but never used)
- Line 19: `BulletproofParameterCorrector` (imported but never used)

### tests/test_failure_priority.py

- Line 15: `asyncio` (imported but never used)
- Line 19: `MagicMock` (imported but never used)
- Line 19: `AsyncMock` (imported but never used)
- Line 19: `patch` (imported but never used)
- Line 26: `reminders` (imported but never used)

### tests/test_frontmatter.py

- Line 1: `annotations` (imported but never used)

### tests/test_function_decomposition_integration.py

- Line 8: `Dict` (imported but never used)
- Line 8: `Any` (imported but never used)
- Line 22: `RotateLogConfig` (imported but never used)

### tests/test_get_project_integration.py

- Line 13: `datetime` (imported but never used)
- Line 13: `timezone` (imported but never used)
- Line 14: `get_project` (imported but never used)

### tests/test_health_check.py

- Line 18: `scribe_mcp.storage.sqlite` (imported but never used)
- Line 19: `scribe_mcp.state.manager` (imported but never used)
- Line 20: `scribe_mcp.state.agent_manager` (imported but never used)
- Line 21: `scribe_mcp.tools.health_check` (imported but never used)
- Line 22: `scribe_mcp.server` (imported but never used)

### tests/test_jinja2_engine.py

- Line 10: `TemplateEngineError` (imported but never used)

### tests/test_list_projects_integration.py

- Line 11: `json` (imported but never used)
- Line 13: `datetime` (imported but never used)
- Line 13: `timezone` (imported but never used)

### tests/test_logging_utils.py

- Line 3: `annotations` (imported but never used)
- Line 10: `Optional` (imported but never used)

### tests/test_manage_docs_checklist_helper.py

- Line 1: `annotations` (imported but never used)

### tests/test_manage_docs_create_doc.py

- Line 1: `annotations` (imported but never used)

### tests/test_manage_docs_generate_toc.py

- Line 1: `annotations` (imported but never used)

### tests/test_manage_docs_patch_range.py

- Line 1: `annotations` (imported but never used)

### tests/test_manage_docs_reminders.py

- Line 1: `annotations` (imported but never used)

### tests/test_manage_docs_structured_edit.py

- Line 1: `annotations` (imported but never used)

### tests/test_manage_docs_validate_crosslinks.py

- Line 1: `annotations` (imported but never used)

### tests/test_mcp_tools_enhancements.py

- Line 8: `tempfile` (imported but never used)
- Line 9: `json` (imported but never used)
- Line 11: `patch` (imported but never used)
- Line 11: `AsyncMock` (imported but never used)
- Line 12: `datetime` (imported but never used)
- Line 12: `timezone` (imported but never used)
- Line 18: `apply_doc_change` (imported but never used)
- Line 27: `ToolValidator` (imported but never used)
- Line 27: `BulletproofParameterCorrector` (imported but never used)

### tests/test_migration_priority_columns.py

- Line 11: `json` (imported but never used)
- Line 18: `ProjectRecord` (imported but never used)

### tests/test_multi_repo_file_ops.py

- Line 1: `annotations` (imported but never used)

### tests/test_parameter_validator.py

- Line 8: `annotations` (imported but never used)
- Line 10: `json` (imported but never used)
- Line 12: `datetime` (imported but never used)
- Line 13: `Dict` (imported but never used)
- Line 13: `Any` (imported but never used)

### tests/test_performance.py

- Line 32: `append_entry` (imported but never used)
- Line 35: `slugify_project_name` (imported but never used)

### tests/test_plugin_registry_runtime.py

- Line 3: `annotations` (imported but never used)

### tests/test_project_registry.py

- Line 9: `pytest` (imported but never used)

### tests/test_query_entries_config.py

- Line 8: `Any` (imported but never used)
- Line 8: `Dict` (imported but never used)
- Line 15: `VALID_DOCUMENT_TYPES` (imported but never used)

### tests/test_read_file_readable.py

- Line 5: `Path` (imported but never used)

### tests/test_reminder_hash_session.py

- Line 3: `pytest` (imported but never used)
- Line 6: `settings` (imported but never used)

### tests/test_reminder_history_schema.py

- Line 3: `annotations` (imported but never used)

### tests/test_reminder_storage.py

- Line 10: `annotations` (imported but never used)
- Line 16: `datetime` (imported but never used)
- Line 16: `timezone` (imported but never used)
- Line 16: `timedelta` (imported but never used)

### tests/test_reminder_time_variables.py

- Line 1: `annotations` (imported but never used)

### tests/test_rotate_log_config.py

- Line 16: `Any` (imported but never used)
- Line 16: `Dict` (imported but never used)
- Line 16: `List` (imported but never used)
- Line 16: `Optional` (imported but never used)

### tests/test_rotation_utils.py

- Line 10: `json` (imported but never used)
- Line 14: `time` (imported but never used)
- Line 29: `store_rotation_metadata` (imported but never used)
- Line 29: `get_rotation_history` (imported but never used)
- Line 29: `verify_rotation_integrity` (imported but never used)
- Line 29: `get_audit_summary` (imported but never used)
- Line 38: `get_project_state` (imported but never used)
- Line 38: `update_project_state` (imported but never used)
- Line 38: `get_next_sequence_number` (imported but never used)
- Line 38: `generate_rotation_id` (imported but never used)

### tests/test_sandbox_bypass.py

- Line 4: `os` (imported but never used)

### tests/test_session_isolation.py

- Line 23: `Any` (imported but never used)
- Line 23: `Dict` (imported but never used)
- Line 24: `MagicMock` (imported but never used)
- Line 24: `patch` (imported but never used)

### tests/test_template_engine_manage_docs.py

- Line 3: `annotations` (imported but never used)

### tests/test_tool_calls_schema.py

- Line 8: `datetime` (imported but never used)
- Line 8: `timezone` (imported but never used)

### tests/test_tool_logger.py

- Line 12: `patch` (imported but never used)
- Line 12: `mock_open` (imported but never used)

### tests/test_tools.py

- Line 3: `annotations` (imported but never used)

### tests/test_utils.py

- Line 3: `annotations` (imported but never used)

### tests/test_vector_complete_integration.py

- Line 14: `patch` (imported but never used)
- Line 14: `AsyncMock` (imported but never used)
- Line 15: `datetime` (imported but never used)
- Line 15: `timezone` (imported but never used)
- Line 33: `initialize_plugins` (imported but never used)
- Line 33: `get_plugin_registry` (imported but never used)
- Line 37: `VectorIndexRecord` (imported but never used)
- Line 37: `VectorShardMetadata` (imported but never used)

### tests/test_vector_entry_ids.py

- Line 3: `pytest` (imported but never used)
- Line 4: `tempfile` (imported but never used)
- Line 5: `Path` (imported but never used)
- Line 6: `patch` (imported but never used)

### tests/test_vector_indexer.py

- Line 9: `AsyncMock` (imported but never used)

### tests/test_vector_integration.py

- Line 9: `AsyncMock` (imported but never used)
- Line 10: `datetime` (imported but never used)
- Line 10: `timezone` (imported but never used)

### tests/test_vector_performance.py

- Line 318: `threading` (imported but never used)
- Line 319: `concurrent.futures` (imported but never used)

### tests/test_vector_search_tools.py

- Line 6: `AsyncMock` (imported but never used)

### tools/__init__.py

- Line 3: `append_entry` (imported but never used)
- Line 4: `delete_project` (imported but never used)
- Line 5: `generate_doc_templates` (imported but never used)
- Line 6: `get_project` (imported but never used)
- Line 7: `list_projects` (imported but never used)
- Line 8: `query_entries` (imported but never used)
- Line 9: `read_recent` (imported but never used)
- Line 10: `read_file` (imported but never used)
- Line 11: `sentinel_tools` (imported but never used)
- Line 12: `rotate_log` (imported but never used)
- Line 13: `set_project` (imported but never used)
- Line 14: `manage_docs` (imported but never used)
- Line 15: `vector_search` (imported but never used)
- Line 16: `manage_docs_validation` (imported but never used)
- Line 17: `doctor` (imported but never used)

### tools/agent_project_utils.py

- Line 3: `annotations` (imported but never used)

### tools/append_entry.py

- Line 3: `annotations` (imported but never used)
- Line 9: `timezone` (imported but never used)
- Line 22: `ensure_agent_session` (imported but never used)
- Line 22: `validate_agent_session` (imported but never used)
- Line 30: `ensure_metadata_requirements` (imported but never used)
- Line 39: `LogPriority` (imported but never used)
- Line 39: `LogCategory` (imported but never used)
- Line 53: `_manage_docs_validation` (imported but never used)

### tools/base/__init__.py

- Line 3: `BaseTool` (imported but never used)
- Line 4: `ToolResult` (imported but never used)
- Line 5: `normalize_dict_param` (imported but never used)
- Line 5: `normalize_list_param` (imported but never used)
- Line 6: `ToolMetadata` (imported but never used)
- Line 6: `ToolParameter` (imported but never used)
- Line 6: `ToolExample` (imported but never used)
- Line 6: `get_tool_metadata` (imported but never used)
- Line 6: `list_tools_by_category` (imported but never used)
- Line 6: `list_deprecated_tools` (imported but never used)
- Line 6: `get_tool_examples` (imported but never used)
- Line 6: `validate_tool_parameters` (imported but never used)
- Line 6: `generate_tool_help` (imported but never used)
- Line 6: `TOOL_METADATA` (imported but never used)

### tools/base/base_tool.py

- Line 3: `annotations` (imported but never used)
- Line 7: `Awaitable` (imported but never used)
- Line 7: `Callable` (imported but never used)
- Line 7: `Optional` (imported but never used)

### tools/base/parameter_normalizer.py

- Line 7: `annotations` (imported but never used)

### tools/base/tool_metadata.py

- Line 7: `annotations` (imported but never used)

### tools/base/tool_result.py

- Line 3: `annotations` (imported but never used)
- Line 5: `Union` (imported but never used)

### tools/config/append_entry_config.py

- Line 9: `annotations` (imported but never used)
- Line 13: `datetime` (imported but never used)
- Line 14: `Union` (imported but never used)
- Line 17: `ConfigManager` (imported but never used)
- Line 17: `resolve_fallback_chain` (imported but never used)
- Line 18: `ErrorHandler` (imported but never used)

### tools/config/query_entries_config.py

- Line 8: `annotations` (imported but never used)
- Line 10: `re` (imported but never used)
- Line 16: `ErrorHandler` (imported but never used)
- Line 16: `HealingErrorHandler` (imported but never used)

### tools/config/rotate_log_config.py

- Line 16: `annotations` (imported but never used)
- Line 18: `json` (imported but never used)
- Line 20: `Union` (imported but never used)

### tools/delete_project.py

- Line 3: `annotations` (imported but never used)
- Line 12: `ensure_agent_session` (imported but never used)
- Line 12: `validate_agent_session` (imported but never used)
- Line 16: `slugify_project_name` (imported but never used)

### tools/doctor.py

- Line 3: `annotations` (imported but never used)

### tools/generate_doc_templates.py

- Line 3: `annotations` (imported but never used)

### tools/get_project.py

- Line 3: `annotations` (imported but never used)

### tools/health_check.py

- Line 3: `annotations` (imported but never used)
- Line 5: `List` (imported but never used)
- Line 5: `Optional` (imported but never used)
- Line 57: `asyncio` (imported but never used)

### tools/list_projects.py

- Line 3: `annotations` (imported but never used)

### tools/manage_docs.py

- Line 3: `annotations` (imported but never used)
- Line 17: `SECTION_MARKER` (imported but never used)

### tools/manage_docs_validation.py

- Line 13: `annotations` (imported but never used)

### tools/project_utils.py

- Line 3: `annotations` (imported but never used)

### tools/query_entries.py

- Line 3: `annotations` (imported but never used)
- Line 7: `timezone` (imported but never used)
- Line 17: `validate_enum_value` (imported but never used)
- Line 17: `validate_range` (imported but never used)
- Line 25: `ErrorHandler` (imported but never used)
- Line 26: `ToolValidator` (imported but never used)
- Line 28: `ProjectResolutionError` (imported but never used)

### tools/read_file.py

- Line 3: `annotations` (imported but never used)
- Line 5: `asyncio` (imported but never used)

### tools/read_recent.py

- Line 3: `annotations` (imported but never used)
- Line 18: `resolve_logging_context` (imported but never used)

### tools/rotate_log.py

- Line 3: `annotations` (imported but never used)
- Line 8: `uuid` (imported but never used)
- Line 12: `Sequence` (imported but never used)
- Line 21: `BulkProcessor` (imported but never used)
- Line 23: `shared_resolve_log_definition` (imported but never used)
- Line 23: `resolve_logging_context` (imported but never used)
- Line 36: `normalize_dict_param` (imported but never used)
- Line 37: `ToolValidator` (imported but never used)
- Line 46: `get_audit_manager` (imported but never used)
- Line 49: `compute_file_hash` (imported but never used)
- Line 54: `get_state_manager` (imported but never used)
- Line 61: `reminders` (imported but never used)

### tools/sentinel_tools.py

- Line 3: `annotations` (imported but never used)

### tools/set_project.py

- Line 3: `annotations` (imported but never used)
- Line 367: `uuid` (imported but never used)

### tools/vector_search.py

- Line 7: `annotations` (imported but never used)
- Line 13: `get_agent_project_data` (imported but never used)

### utils/__init__.py

- Line 3: `append_line` (imported but never used)
- Line 3: `ensure_parent` (imported but never used)
- Line 3: `read_tail` (imported but never used)
- Line 3: `rotate_file` (imported but never used)
- Line 4: `format_utc` (imported but never used)
- Line 4: `utcnow` (imported but never used)
- Line 5: `ResponseFormatter` (imported but never used)
- Line 5: `default_formatter` (imported but never used)
- Line 5: `create_pagination_info` (imported but never used)
- Line 5: `PaginationInfo` (imported but never used)
- Line 6: `TokenEstimator` (imported but never used)
- Line 6: `TokenMetrics` (imported but never used)
- Line 6: `TokenBudget` (imported but never used)
- Line 6: `token_estimator` (imported but never used)
- Line 7: `get_response_formatter` (imported but never used)
- Line 7: `get_token_estimator` (imported but never used)
- Line 7: `get_configured_response_formatter` (imported but never used)
- Line 7: `get_configured_token_estimator` (imported but never used)
- Line 7: `configured_formatter` (imported but never used)
- Line 7: `configured_token_estimator` (imported but never used)
- Line 7: `reset_configured_instances` (imported but never used)

### utils/audit.py

- Line 9: `os` (imported but never used)
- Line 10: `uuid` (imported but never used)

### utils/bulk_processor.py

- Line 12: `Union` (imported but never used)
- Line 13: `re` (imported but never used)

### utils/config_manager.py

- Line 18: `annotations` (imported but never used)

### utils/context_safety.py

- Line 6: `annotations` (imported but never used)

### utils/diff_compiler.py

- Line 3: `annotations` (imported but never used)

### utils/error_handler.py

- Line 8: `annotations` (imported but never used)

### utils/estimator.py

- Line 18: `annotations` (imported but never used)
- Line 23: `NamedTuple` (imported but never used)

### utils/files.py

- Line 3: `annotations` (imported but never used)
- Line 10: `tempfile` (imported but never used)
- Line 16: `Iterable` (imported but never used)

### utils/frontmatter.py

- Line 3: `annotations` (imported but never used)
- Line 7: `Optional` (imported but never used)

### utils/integrity.py

- Line 12: `json` (imported but never used)

### utils/logs.py

- Line 3: `annotations` (imported but never used)

### utils/optimization.py

- Line 11: `_default_formatter` (imported but never used)
- Line 12: `_default_token_estimator` (imported but never used)

### utils/parameter_validator.py

- Line 8: `annotations` (imported but never used)

### utils/reminder_engine.py

- Line 11: `annotations` (imported but never used)
- Line 15: `os` (imported but never used)
- Line 16: `time` (imported but never used)
- Line 19: `Set` (imported but never used)
- Line 19: `Tuple` (imported but never used)

### utils/reminder_monitoring.py

- Line 25: `timedelta` (imported but never used)

### utils/reminder_validator.py

- Line 7: `annotations` (imported but never used)
- Line 9: `json` (imported but never used)
- Line 10: `Path` (imported but never used)
- Line 11: `Set` (imported but never used)
- Line 13: `ReminderInstance` (imported but never used)

### utils/response.py

- Line 10: `dataclass` (imported but never used)

### utils/search.py

- Line 3: `annotations` (imported but never used)

### utils/sentinel_logs.py

- Line 3: `annotations` (imported but never used)
- Line 10: `Optional` (imported but never used)

### utils/time.py

- Line 3: `annotations` (imported but never used)

### utils/tool_logger.py

- Line 22: `Any` (imported but never used)
- Line 22: `Dict` (imported but never used)

## Unreferenced Definitions

### MEDIUM Severity

- **reload_repo_config** (function) in `config/repo_config.py:380`
- **on_any_event** (function) in `doc_management/file_watcher.py:114`
- **DefaultDict** (class) in `doc_management/manager.py:2418`
- **register_metric_callback** (function) in `doc_management/performance_monitor.py:245`
- **get_plugin_security_info** (function) in `plugins/registry.py:511`
- **parse_entry** (function) in `plugins/registry.py:105`
- **execute_hook_pre_append** (function) in `plugins/registry.py:435`
- **execute_hook_post_append** (function) in `plugins/registry.py:445`
- **execute_hook_pre_rotate** (function) in `plugins/registry.py:453`
- **execute_hook_post_rotate** (function) in `plugins/registry.py:461`
- **get_reminder_engine** (function) in `reminders.py:380`
- **reload_reminders** (function) in `reminders.py:395`
- **get_safe_relative_path** (function) in `security/sandbox.py:126`
- **cleanup_repository** (function) in `security/sandbox.py:319`
- **run_stdio** (function) in `server.py:52`
- **set_status** (function) in `shared/project_registry.py:170`
- **with_project** (function) in `state/manager.py:49`
- **MilestoneRecord** (class) in `storage/models.py:48`
- **ChecklistRecord** (class) in `storage/models.py:78`
- **DocumentSectionRecord** (class) in `storage/models.py:111`
- **CustomTemplateRecord** (class) in `storage/models.py:124`
- **DocumentChangeRecord** (class) in `storage/models.py:136`
- **SyncStatusRecord** (class) in `storage/models.py:149`
- **AgentReportCardRecord** (class) in `storage/models.py:163`
- **VectorIndexRecord** (class) in `storage/models.py:179`
- **record_tool_call_sync** (function) in `storage/sqlite.py:2032`
- **TestAppendEntryConfig** (class) in `tests/test_append_entry_config.py:14`
- **test_default_initialization** (function) in `tests/test_append_entry_config.py:17`
- **test_full_initialization** (function) in `tests/test_append_entry_config.py:66`
- **test_validation_success** (function) in `tests/test_append_entry_config.py:136`
- **test_validation_invalid_status** (function) in `tests/test_append_entry_config.py:150`
- **test_validation_invalid_items_json** (function) in `tests/test_append_entry_config.py:157`
- **test_validation_invalid_items_not_array** (function) in `tests/test_append_entry_config.py:164`
- **test_validation_invalid_items_list** (function) in `tests/test_append_entry_config.py:171`
- **test_validation_invalid_timestamp** (function) in `tests/test_append_entry_config.py:178`
- **test_validation_negative_numbers** (function) in `tests/test_append_entry_config.py:185`
- **test_validation_zero_values** (function) in `tests/test_append_entry_config.py:208`
- **test_validation_invalid_agent** (function) in `tests/test_append_entry_config.py:231`
- **test_validation_invalid_log_type** (function) in `tests/test_append_entry_config.py:244`
- **test_validation_disabled** (function) in `tests/test_append_entry_config.py:251`
- **test_normalize_booleans** (function) in `tests/test_append_entry_config.py:260`
- **test_normalize_numeric_parameters** (function) in `tests/test_append_entry_config.py:286`
- **test_normalize_string_parameters** (function) in `tests/test_append_entry_config.py:310`
- **test_normalize_agent_sanitization** (function) in `tests/test_append_entry_config.py:322`
- **test_normalize_metadata** (function) in `tests/test_append_entry_config.py:329`
- **test_from_legacy_params_basic** (function) in `tests/test_append_entry_config.py:335`
- **test_from_legacy_params_with_kwargs** (function) in `tests/test_append_entry_config.py:367`
- **test_to_dict** (function) in `tests/test_append_entry_config.py:385`
- **test_to_legacy_params** (function) in `tests/test_append_entry_config.py:403`
- **test_merge_with_defaults** (function) in `tests/test_append_entry_config.py:437`
- **test_is_bulk_mode_explicit_items** (function) in `tests/test_append_entry_config.py:461`
- **test_is_bulk_mode_auto_split** (function) in `tests/test_append_entry_config.py:471`
- **test_estimate_processing_time_single_entry** (function) in `tests/test_append_entry_config.py:497`
- **test_estimate_processing_time_bulk_mode** (function) in `tests/test_append_entry_config.py:507`
- **test_estimate_processing_time_large_content** (function) in `tests/test_append_entry_config.py:522`
- **test_estimate_processing_time_with_items_json** (function) in `tests/test_append_entry_config.py:537`
- **test_estimate_processing_time_invalid_json** (function) in `tests/test_append_entry_config.py:549`
- **test_edge_case_empty_config** (function) in `tests/test_append_entry_config.py:563`
- **test_edge_case_maximum_values** (function) in `tests/test_append_entry_config.py:587`
- **test_edge_case_special_characters** (function) in `tests/test_append_entry_config.py:614`
- **test_integration_with_phase1_utilities** (function) in `tests/test_append_entry_config.py:633`
- **test_backward_compatibility_preservation** (function) in `tests/test_append_entry_config.py:652`
- **test_comprehensive_validation_coverage** (function) in `tests/test_append_entry_config.py:672`
- **test_error_response_appends_context** (function) in `tests/test_base_logging_tool.py:54`
- **test_success_with_entries_uses_formatter** (function) in `tests/test_base_logging_tool.py:77`
- **test_validate_metadata_requirements** (function) in `tests/test_base_logging_tool.py:112`
- **test_translate_project_error** (function) in `tests/test_base_logging_tool.py:118`
- **test_detect_bulk_mode_true_for_items_json** (function) in `tests/test_bulk_processor_detect_bulk_mode.py:4`
- **test_detect_bulk_mode_true_for_items_list** (function) in `tests/test_bulk_processor_detect_bulk_mode.py:8`
- **test_detect_bulk_mode_true_for_multiline_message** (function) in `tests/test_bulk_processor_detect_bulk_mode.py:12`
- **test_detect_bulk_mode_false_for_long_single_line_message** (function) in `tests/test_bulk_processor_detect_bulk_mode.py:16`
- **test_detect_bulk_mode_false_for_pipe_characters** (function) in `tests/test_bulk_processor_detect_bulk_mode.py:21`
- **TestBulletproofParameterCorrectorEnhancements** (class) in `tests/test_bulletproof_corrector_enhancements.py:14`
- **test_correct_intelligent_parameter_numeric_params** (function) in `tests/test_bulletproof_corrector_enhancements.py:17`
- **test_correct_intelligent_parameter_list_params** (function) in `tests/test_bulletproof_corrector_enhancements.py:41`
- **test_correct_intelligent_parameter_message_params** (function) in `tests/test_bulletproof_corrector_enhancements.py:59`
- **test_correct_intelligent_parameter_metadata_params** (function) in `tests/test_bulletproof_corrector_enhancements.py:78`
- **test_correct_intelligent_parameter_status_params** (function) in `tests/test_bulletproof_corrector_enhancements.py:96`
- **test_correct_fuzzy_parameter_match_exact_match** (function) in `tests/test_bulletproof_corrector_enhancements.py:112`
- **test_correct_fuzzy_parameter_match_substring_match** (function) in `tests/test_bulletproof_corrector_enhancements.py:127`
- **test_correct_fuzzy_parameter_match_fuzzy_match** (function) in `tests/test_bulletproof_corrector_enhancements.py:141`
- **test_correct_fuzzy_parameter_match_fallback** (function) in `tests/test_bulletproof_corrector_enhancements.py:150`
- **test_correct_complex_parameter_combination_pagination** (function) in `tests/test_bulletproof_corrector_enhancements.py:159`
- **test_correct_complex_parameter_combination_dates** (function) in `tests/test_bulletproof_corrector_enhancements.py:183`
- **test_apply_contextual_correction_search_operations** (function) in `tests/test_bulletproof_corrector_enhancements.py:197`
- **test_apply_contextual_correction_create_operations** (function) in `tests/test_bulletproof_corrector_enhancements.py:213`
- **test_apply_contextual_correction_delete_operations** (function) in `tests/test_bulletproof_corrector_enhancements.py:228`
- **test_correct_read_recent_parameters_type_errors** (function) in `tests/test_bulletproof_corrector_enhancements.py:241`
- **test_correct_read_recent_parameters_token_explosion_prevention** (function) in `tests/test_bulletproof_corrector_enhancements.py:256`
- **test_correct_query_entries_parameters_enum_validation** (function) in `tests/test_bulletproof_corrector_enhancements.py:268`
- **test_correct_query_entries_parameters_array_correction** (function) in `tests/test_bulletproof_corrector_enhancements.py:286`
- **test_correct_manage_docs_parameters_create_research_doc** (function) in `tests/test_bulletproof_corrector_enhancements.py:299`
- **test_correct_append_entry_parameters_bulk_performance** (function) in `tests/test_bulletproof_corrector_enhancements.py:325`
- **test_correct_rotate_log_parameters_rotation_validation** (function) in `tests/test_bulletproof_corrector_enhancements.py:348`
- **test_parse_date_parameter_valid_formats** (function) in `tests/test_bulletproof_corrector_enhancements.py:376`
- **test_parse_date_parameter_invalid_formats** (function) in `tests/test_bulletproof_corrector_enhancements.py:398`
- **test_backward_compatibility** (function) in `tests/test_bulletproof_corrector_enhancements.py:445`
- **test_backward_compatibility** (function) in `tests/test_bulletproof_fallback_manager.py:590`
- **TestBulletproofFallbackManager** (class) in `tests/test_bulletproof_fallback_manager.py:22`
- **TestBulletproofFallbackManagerPerformance** (class) in `tests/test_bulletproof_fallback_manager.py:607`
- **setUp** (function) in `tests/test_bulletproof_fallback_manager.py:25`
- **setUp** (function) in `tests/test_bulletproof_fallback_manager.py:610`
- **test_initialization** (function) in `tests/test_bulletproof_fallback_manager.py:34`
- **test_resolve_parameter_fallback_level1_success** (function) in `tests/test_bulletproof_fallback_manager.py:43`
- **test_resolve_parameter_fallback_level2_success** (function) in `tests/test_bulletproof_fallback_manager.py:60`
- **test_resolve_parameter_fallback_level3_success** (function) in `tests/test_bulletproof_fallback_manager.py:77`
- **test_resolve_parameter_fallback_level4_emergency** (function) in `tests/test_bulletproof_fallback_manager.py:96`
- **test_apply_operation_fallback_with_exception_healing** (function) in `tests/test_bulletproof_fallback_manager.py:117`
- **test_apply_operation_fallback_read_recent** (function) in `tests/test_bulletproof_fallback_manager.py:132`
- **test_apply_operation_fallback_query_entries** (function) in `tests/test_bulletproof_fallback_manager.py:148`
- **test_apply_operation_fallback_manage_docs** (function) in `tests/test_bulletproof_fallback_manager.py:164`
- **test_apply_operation_fallback_append_entry** (function) in `tests/test_bulletproof_fallback_manager.py:179`
- **test_apply_operation_fallback_rotate_log** (function) in `tests/test_bulletproof_fallback_manager.py:195`
- **test_apply_operation_fallback_generic** (function) in `tests/test_bulletproof_fallback_manager.py:210`
- **test_emergency_fallback_all_tools** (function) in `tests/test_bulletproof_fallback_manager.py:242`
- **test_intelligent_parameter_resolution** (function) in `tests/test_bulletproof_fallback_manager.py:255`
- **test_intelligent_parameter_resolution_with_exception** (function) in `tests/test_bulletproof_fallback_manager.py:277`
- **test_generate_emergency_content_read_recent** (function) in `tests/test_bulletproof_fallback_manager.py:299`
- **test_generate_emergency_content_query_entries** (function) in `tests/test_bulletproof_fallback_manager.py:311`
- **test_generate_emergency_content_manage_docs** (function) in `tests/test_bulletproof_fallback_manager.py:323`
- **test_generate_emergency_content_append_entry** (function) in `tests/test_bulletproof_fallback_manager.py:334`
- **test_generate_emergency_content_rotate_log** (function) in `tests/test_bulletproof_fallback_manager.py:346`
- **test_generate_emergency_content_unknown_tool** (function) in `tests/test_bulletproof_fallback_manager.py:357`
- **test_apply_context_aware_defaults_read_recent** (function) in `tests/test_bulletproof_fallback_manager.py:368`
- **test_apply_context_aware_defaults_query_entries** (function) in `tests/test_bulletproof_fallback_manager.py:383`
- **test_apply_context_aware_defaults_manage_docs** (function) in `tests/test_bulletproof_fallback_manager.py:400`
- **test_apply_context_aware_defaults_append_entry** (function) in `tests/test_bulletproof_fallback_manager.py:415`
- **test_apply_context_aware_defaults_rotate_log** (function) in `tests/test_bulletproof_fallback_manager.py:432`
- **test_context_aware_fallback_methods** (function) in `tests/test_bulletproof_fallback_manager.py:448`
- **test_parameter_specific_fallback_patterns** (function) in `tests/test_bulletproof_fallback_manager.py:463`
- **test_emergency_fallback_patterns** (function) in `tests/test_bulletproof_fallback_manager.py:484`
- **test_integration_with_task31_enhancements** (function) in `tests/test_bulletproof_fallback_manager.py:506`
- **test_integration_with_task33_enhancements** (function) in `tests/test_bulletproof_fallback_manager.py:521`
- **test_four_level_fallback_chain_integration** (function) in `tests/test_bulletproof_fallback_manager.py:539`
- **test_parameter_resolution_performance** (function) in `tests/test_bulletproof_fallback_manager.py:614`
- **test_operation_fallback_performance** (function) in `tests/test_bulletproof_fallback_manager.py:631`
- **setUp** (function) in `tests/test_bulletproof_integration.py:22`
- **test_integration_with_task31_enhancements** (function) in `tests/test_bulletproof_integration.py:199`
- **test_integration_with_task33_enhancements** (function) in `tests/test_bulletproof_integration.py:215`
- **TestBulletproofFallbackIntegration** (class) in `tests/test_bulletproof_integration.py:19`
- **test_four_level_fallback_chain_working** (function) in `tests/test_bulletproof_integration.py:26`
- **test_operation_fallback_guaranteed_success** (function) in `tests/test_bulletproof_integration.py:49`
- **test_emergency_fallback_always_succeeds** (function) in `tests/test_bulletproof_integration.py:70`
- **test_zero_failure_guarantee_comprehensive** (function) in `tests/test_bulletproof_integration.py:98`
- **test_performance_under_stress** (function) in `tests/test_bulletproof_integration.py:155`
- **test_tool_specific_integration** (function) in `tests/test_bulletproof_integration.py:233`
- **TestConfigManager** (class) in `tests/test_config_manager.py:24`
- **TestConvenienceFunctions** (class) in `tests/test_config_manager.py:347`
- **setup_method** (function) in `tests/test_config_manager.py:27`
- **test_apply_parameter_defaults_basic** (function) in `tests/test_config_manager.py:31`
- **test_apply_parameter_defaults_with_required_keys** (function) in `tests/test_config_manager.py:42`
- **test_apply_parameter_defaults_missing_required** (function) in `tests/test_config_manager.py:53`
- **test_resolve_fallback_chain_basic** (function) in `tests/test_config_manager.py:62`
- **test_resolve_fallback_chain_with_none_and_empty** (function) in `tests/test_config_manager.py:73`
- **test_merge_project_settings_basic** (function) in `tests/test_config_manager.py:87`
- **test_merge_project_settings_no_defaults** (function) in `tests/test_config_manager.py:102`
- **test_validate_enum_value_valid** (function) in `tests/test_config_manager.py:113`
- **test_validate_enum_value_invalid** (function) in `tests/test_config_manager.py:123`
- **test_validate_enum_value_non_string** (function) in `tests/test_config_manager.py:130`
- **test_validate_range_valid_int** (function) in `tests/test_config_manager.py:137`
- **test_validate_range_valid_float** (function) in `tests/test_config_manager.py:145`
- **test_validate_range_out_of_bounds** (function) in `tests/test_config_manager.py:153`
- **test_validate_range_invalid_string** (function) in `tests/test_config_manager.py:161`
- **test_build_response_payload_basic** (function) in `tests/test_config_manager.py:166`
- **test_build_response_payload_ok_override** (function) in `tests/test_config_manager.py:177`
- **test_apply_response_defaults_basic** (function) in `tests/test_config_manager.py:197`
- **test_apply_response_defaults_no_overwrite** (function) in `tests/test_config_manager.py:210`
- **test_normalize_json_parameter_dict** (function) in `tests/test_config_manager.py:220`
- **test_normalize_json_parameter_string** (function) in `tests/test_config_manager.py:226`
- **test_normalize_json_parameter_invalid_json** (function) in `tests/test_config_manager.py:232`
- **test_normalize_json_parameter_none** (function) in `tests/test_config_manager.py:238`
- **test_create_template_context_basic** (function) in `tests/test_config_manager.py:243`
- **test_create_template_context_default_author** (function) in `tests/test_config_manager.py:255`
- **test_load_config_with_cache_file_exists** (function) in `tests/test_config_manager.py:262`
- **test_load_config_with_cache_file_not_exists** (function) in `tests/test_config_manager.py:280`
- **test_load_config_with_cache_invalid_json** (function) in `tests/test_config_manager.py:293`
- **test_validate_and_normalize_list_string** (function) in `tests/test_config_manager.py:305`
- **test_validate_and_normalize_list_list** (function) in `tests/test_config_manager.py:313`
- **test_validate_and_normalize_list_none** (function) in `tests/test_config_manager.py:318`
- **test_apply_configuration_overrides_all_allowed** (function) in `tests/test_config_manager.py:323`
- **test_apply_configuration_overrides_with_allowlist** (function) in `tests/test_config_manager.py:334`
- **test_apply_parameter_defaults_function** (function) in `tests/test_config_manager.py:350`
- **test_resolve_fallback_chain_function** (function) in `tests/test_config_manager.py:359`
- **test_validate_enum_value_function** (function) in `tests/test_config_manager.py:364`
- **test_validate_range_function** (function) in `tests/test_config_manager.py:369`
- **test_build_response_payload_function** (function) in `tests/test_config_manager.py:374`
- **test_apply_response_defaults_function** (function) in `tests/test_config_manager.py:381`
- **test_compile_unified_diff_applies_cleanly** (function) in `tests/test_diff_compiler.py:7`
- **TestFileSystemWatcher** (class) in `tests/test_doc_management.py:22`
- **TestSyncManager** (class) in `tests/test_doc_management.py:128`
- **TestChangeLogger** (class) in `tests/test_doc_management.py:239`
- **TestDiffVisualizer** (class) in `tests/test_doc_management.py:388`
- **TestConflictResolver** (class) in `tests/test_doc_management.py:508`
- **TestIntegrityVerifier** (class) in `tests/test_doc_management.py:646`
- **TestPerformanceMonitor** (class) in `tests/test_doc_management.py:786`
- **TestChangeRollbackManager** (class) in `tests/test_doc_management.py:965`
- **test_file_change_event_creation** (function) in `tests/test_doc_management.py:37`
- **test_watcher_methods** (function) in `tests/test_doc_management.py:83`
- **test_sync_conflict_creation** (function) in `tests/test_doc_management.py:144`
- **test_sync_operation_creation** (function) in `tests/test_doc_management.py:159`
- **test_to_epoch_conversion** (function) in `tests/test_doc_management.py:187`
- **test_change_record_creation** (function) in `tests/test_doc_management.py:255`
- **test_generate_change_id** (function) in `tests/test_doc_management.py:284`
- **test_generate_change_id** (function) in `tests/test_doc_management.py:1054`
- **test_calculate_content_hash** (function) in `tests/test_doc_management.py:351`
- **test_diff_result_creation** (function) in `tests/test_doc_management.py:411`
- **test_diff_visualization_creation** (function) in `tests/test_doc_management.py:429`
- **test_conflict_analysis_creation** (function) in `tests/test_doc_management.py:544`
- **test_resolution_action_creation** (function) in `tests/test_doc_management.py:560`
- **test_calculate_content_similarity** (function) in `tests/test_doc_management.py:625`
- **test_integrity_check_creation** (function) in `tests/test_doc_management.py:662`
- **test_integrity_report_creation** (function) in `tests/test_doc_management.py:679`
- **test_get_cache_stats** (function) in `tests/test_doc_management.py:772`
- **test_performance_metric_creation** (function) in `tests/test_doc_management.py:802`
- **test_operation_metrics_creation** (function) in `tests/test_doc_management.py:816`
- **test_system_metrics_creation** (function) in `tests/test_doc_management.py:836`
- **test_track_operation_start** (function) in `tests/test_doc_management.py:863`
- **test_change_log_entry_creation** (function) in `tests/test_doc_management.py:982`
- **test_rollback_plan_creation** (function) in `tests/test_doc_management.py:1001`
- **test_imports** (function) in `tests/test_doc_management.py:1139`
- **test_file_change_event_creation** (function) in `tests/test_doc_management_basic.py:76`
- **test_watcher_methods** (function) in `tests/test_doc_management_basic.py:103`
- **test_sync_conflict_creation** (function) in `tests/test_doc_management_basic.py:127`
- **test_sync_operation_creation** (function) in `tests/test_doc_management_basic.py:141`
- **test_to_epoch_conversion** (function) in `tests/test_doc_management_basic.py:169`
- **test_change_record_creation** (function) in `tests/test_doc_management_basic.py:191`
- **test_generate_change_id** (function) in `tests/test_doc_management_basic.py:221`
- **test_generate_change_id** (function) in `tests/test_doc_management_basic.py:405`
- **test_calculate_content_hash** (function) in `tests/test_doc_management_basic.py:235`
- **test_get_cache_stats** (function) in `tests/test_doc_management_basic.py:289`
- **test_track_operation_start** (function) in `tests/test_doc_management_basic.py:321`
- **TestDocManagementImports** (class) in `tests/test_doc_management_basic.py:25`
- **TestFileSystemWatcherBasic** (class) in `tests/test_doc_management_basic.py:68`
- **TestSyncManagerBasic** (class) in `tests/test_doc_management_basic.py:119`
- **TestChangeLoggerBasic** (class) in `tests/test_doc_management_basic.py:188`
- **TestIntegrityVerifierBasic** (class) in `tests/test_doc_management_basic.py:251`
- **TestPerformanceMonitorBasic** (class) in `tests/test_doc_management_basic.py:304`
- **TestConflictResolverBasic** (class) in `tests/test_doc_management_basic.py:355`
- **TestChangeRollbackManagerBasic** (class) in `tests/test_doc_management_basic.py:388`
- **TestDiffVisualizerBasic** (class) in `tests/test_doc_management_basic.py:420`
- **TestDocManagementIntegration** (class) in `tests/test_doc_management_basic.py:461`
- **test_import_file_watcher** (function) in `tests/test_doc_management_basic.py:28`
- **test_import_sync_manager** (function) in `tests/test_doc_management_basic.py:33`
- **test_import_change_logger** (function) in `tests/test_doc_management_basic.py:40`
- **test_import_diff_visualizer** (function) in `tests/test_doc_management_basic.py:45`
- **test_import_conflict_resolver** (function) in `tests/test_doc_management_basic.py:49`
- **test_import_integrity_verifier** (function) in `tests/test_doc_management_basic.py:54`
- **test_import_performance_monitor** (function) in `tests/test_doc_management_basic.py:59`
- **test_import_change_rollback_manager** (function) in `tests/test_doc_management_basic.py:63`
- **test_conflict_severity_enum** (function) in `tests/test_doc_management_basic.py:373`
- **test_conflict_resolution_enum** (function) in `tests/test_doc_management_basic.py:380`
- **test_all_modules_importable** (function) in `tests/test_doc_management_basic.py:464`
- **TestEntryLimitManager** (class) in `tests/test_entry_limit.py:37`
- **test_limit_entries_default_mode** (function) in `tests/test_entry_limit.py:40`
- **test_limit_entries_full_mode** (function) in `tests/test_entry_limit.py:52`
- **test_limit_entries_compact_mode** (function) in `tests/test_entry_limit.py:64`
- **test_limit_entries_readable_mode** (function) in `tests/test_entry_limit.py:72`
- **test_limit_entries_structured_mode** (function) in `tests/test_entry_limit.py:80`
- **test_limit_entries_expandable_mode** (function) in `tests/test_entry_limit.py:88`
- **test_priority_filtering** (function) in `tests/test_entry_limit.py:96`
- **test_priority_filtering_multiple** (function) in `tests/test_entry_limit.py:110`
- **test_priority_based_sorting** (function) in `tests/test_entry_limit.py:121`
- **test_custom_max_entries_override** (function) in `tests/test_entry_limit.py:161`
- **test_custom_max_entries_larger_than_available** (function) in `tests/test_entry_limit.py:172`
- **test_metadata_accuracy** (function) in `tests/test_entry_limit.py:183`
- **test_empty_entries_list** (function) in `tests/test_entry_limit.py:197`
- **test_entries_without_priority_field** (function) in `tests/test_entry_limit.py:207`
- **test_entries_without_timestamp** (function) in `tests/test_entry_limit.py:226`
- **test_no_sorting_by_priority** (function) in `tests/test_entry_limit.py:243`
- **test_priority_filter_with_custom_limit** (function) in `tests/test_entry_limit.py:254`
- **test_complete_entries_returned** (function) in `tests/test_entry_limit.py:268`
- **test_unrecognized_mode_uses_default** (function) in `tests/test_entry_limit.py:280`
- **test_priority_filter_no_matches** (function) in `tests/test_entry_limit.py:290`
- **TestErrorHandler** (class) in `tests/test_error_handler.py:25`
- **test_create_validation_error_basic** (function) in `tests/test_error_handler.py:28`
- **test_create_validation_error_with_alternative** (function) in `tests/test_error_handler.py:39`
- **test_create_validation_error_with_context** (function) in `tests/test_error_handler.py:52`
- **test_create_validation_error_minimal** (function) in `tests/test_error_handler.py:65`
- **test_create_project_resolution_error_basic** (function) in `tests/test_error_handler.py:75`
- **test_create_project_resolution_error_includes_last_known_hint** (function) in `tests/test_error_handler.py:89`
- **test_create_project_resolution_error_default_suggestion** (function) in `tests/test_error_handler.py:113`
- **test_create_parameter_error_basic** (function) in `tests/test_error_handler.py:124`
- **test_create_parameter_error_with_expected_received** (function) in `tests/test_error_handler.py:135`
- **test_create_parameter_error_with_suggestion** (function) in `tests/test_error_handler.py:148`
- **test_create_enum_error_case_sensitive** (function) in `tests/test_error_handler.py:160`
- **test_create_enum_error_case_insensitive** (function) in `tests/test_error_handler.py:173`
- **test_create_enum_error_close_matches** (function) in `tests/test_error_handler.py:186`
- **test_create_range_error_min_value** (function) in `tests/test_error_handler.py:198`
- **test_create_range_error_max_value** (function) in `tests/test_error_handler.py:210`
- **test_create_range_error_both_bounds** (function) in `tests/test_error_handler.py:222`
- **test_create_regex_error** (function) in `tests/test_error_handler.py:235`
- **test_create_file_operation_error_not_found** (function) in `tests/test_error_handler.py:248`
- **test_create_file_operation_error_permission** (function) in `tests/test_error_handler.py:264`
- **test_create_file_operation_error_generic** (function) in `tests/test_error_handler.py:277`
- **test_create_storage_error_basic** (function) in `tests/test_error_handler.py:290`
- **test_create_storage_error_custom_suggestion** (function) in `tests/test_error_handler.py:303`
- **test_create_rate_limit_error_basic** (function) in `tests/test_error_handler.py:316`
- **test_create_rate_limit_error_with_description** (function) in `tests/test_error_handler.py:327`
- **test_create_missing_requirement_error_single** (function) in `tests/test_error_handler.py:339`
- **test_create_missing_requirement_error_multiple** (function) in `tests/test_error_handler.py:350`
- **test_create_missing_requirement_error_custom_suggestion** (function) in `tests/test_error_handler.py:361`
- **test_handle_safe_operation_success** (function) in `tests/test_error_handler.py:373`
- **test_handle_safe_operation_failure** (function) in `tests/test_error_handler.py:386`
- **test_handle_safe_operation_with_context** (function) in `tests/test_error_handler.py:400`
- **test_create_warning_response_basic** (function) in `tests/test_error_handler.py:417`
- **test_create_warning_response_with_context** (function) in `tests/test_error_handler.py:435`
- **test_find_close_matches_exact_match** (function) in `tests/test_error_handler.py:451`
- **test_find_close_matches_partial_match** (function) in `tests/test_error_handler.py:460`
- **test_find_close_matches_no_match** (function) in `tests/test_error_handler.py:470`
- **test_all_methods_return_dict** (function) in `tests/test_error_handler.py:479`
- **test_all_error_responses_have_ok_false** (function) in `tests/test_error_handler.py:499`
- **TestEntryCountEstimate** (class) in `tests/test_estimator.py:28`
- **TestPaginationInfo** (class) in `tests/test_estimator.py:46`
- **TestChunkCalculation** (class) in `tests/test_estimator.py:76`
- **TestFileSizeEstimator** (class) in `tests/test_estimator.py:94`
- **TestThresholdEstimator** (class) in `tests/test_estimator.py:252`
- **TestPaginationCalculator** (class) in `tests/test_estimator.py:295`
- **TestBulkProcessingCalculator** (class) in `tests/test_estimator.py:365`
- **TestTokenEstimator** (class) in `tests/test_estimator.py:417`
- **TestEstimatorUtilities** (class) in `tests/test_estimator.py:479`
- **TestIntegration** (class) in `tests/test_estimator.py:563`
- **test_entry_count_estimate_creation** (function) in `tests/test_estimator.py:31`
- **test_pagination_info_creation** (function) in `tests/test_estimator.py:49`
- **test_chunk_calculation_creation** (function) in `tests/test_estimator.py:79`
- **test_estimator_initialization** (function) in `tests/test_estimator.py:97`
- **test_clamp_bytes_per_line** (function) in `tests/test_estimator.py:111`
- **test_estimate_entry_count_basic** (function) in `tests/test_estimator.py:127`
- **test_estimate_entry_count_with_cache** (function) in `tests/test_estimator.py:153`
- **test_refine_estimate_with_sampling** (function) in `tests/test_estimator.py:189`
- **test_compute_bytes_per_line** (function) in `tests/test_estimator.py:225`
- **test_compute_estimation_band** (function) in `tests/test_estimator.py:255`
- **test_classify_estimate** (function) in `tests/test_estimator.py:272`
- **test_create_pagination_info** (function) in `tests/test_estimator.py:298`
- **test_calculate_pagination_indices** (function) in `tests/test_estimator.py:325`
- **test_calculate_total_pages** (function) in `tests/test_estimator.py:344`
- **test_calculate_chunks** (function) in `tests/test_estimator.py:368`
- **test_calculate_optimal_chunk_size** (function) in `tests/test_estimator.py:394`
- **test_estimate_tokens_string** (function) in `tests/test_estimator.py:420`
- **test_estimate_tokens_dict_list** (function) in `tests/test_estimator.py:438`
- **test_estimate_response_tokens** (function) in `tests/test_estimator.py:457`
- **test_utilities_initialization** (function) in `tests/test_estimator.py:482`
- **test_estimate_file_operations_nonexistent** (function) in `tests/test_estimator.py:492`
- **test_estimate_file_operations_existing** (function) in `tests/test_estimator.py:503`
- **test_estimate_file_operations_with_cache** (function) in `tests/test_estimator.py:533`
- **test_end_to_end_estimation_workflow** (function) in `tests/test_estimator.py:566`
- **TestExceptionHealer** (class) in `tests/test_exception_healer.py:22`
- **test_heal_complex_exception_combination_type_conversion** (function) in `tests/test_exception_healer.py:25`
- **test_heal_complex_exception_combination_parameter_conflicts** (function) in `tests/test_exception_healer.py:42`
- **test_heal_complex_exception_combination_missing_parameters** (function) in `tests/test_exception_healer.py:55`
- **test_apply_intelligent_exception_recovery_value_error** (function) in `tests/test_exception_healer.py:68`
- **test_apply_intelligent_exception_recovery_type_error** (function) in `tests/test_exception_healer.py:82`
- **test_apply_intelligent_exception_recovery_key_error** (function) in `tests/test_exception_healer.py:92`
- **test_apply_intelligent_exception_recovery_file_error** (function) in `tests/test_exception_healer.py:103`
- **test_apply_intelligent_exception_recovery_database_error** (function) in `tests/test_exception_healer.py:114`
- **test_apply_intelligent_exception_recovery_general_error** (function) in `tests/test_exception_healer.py:125`
- **test_heal_emergency_exception_emergency_strategy** (function) in `tests/test_exception_healer.py:136`
- **test_heal_emergency_exception_minimal_strategy** (function) in `tests/test_exception_healer.py:150`
- **test_heal_emergency_exception_cache_strategy** (function) in `tests/test_exception_healer.py:160`
- **test_heal_emergency_exception_unknown_strategy** (function) in `tests/test_exception_healer.py:170`
- **test_analyze_exception_pattern_parameter_validation** (function) in `tests/test_exception_healer.py:180`
- **test_analyze_exception_pattern_resource_access** (function) in `tests/test_exception_healer.py:205`
- **test_analyze_exception_pattern_operation_logic** (function) in `tests/test_exception_healer.py:219`
- **test_analyze_exception_pattern_unknown_category** (function) in `tests/test_exception_healer.py:233`
- **test_heal_parameter_validation_error_read_recent** (function) in `tests/test_exception_healer.py:248`
- **test_heal_parameter_validation_error_query_entries** (function) in `tests/test_exception_healer.py:263`
- **test_heal_parameter_validation_error_manage_docs** (function) in `tests/test_exception_healer.py:278`
- **test_heal_parameter_validation_error_append_entry** (function) in `tests/test_exception_healer.py:293`
- **test_heal_parameter_validation_error_top_level_context_params** (function) in `tests/test_exception_healer.py:309`
- **test_heal_parameter_validation_error_rotate_log** (function) in `tests/test_exception_healer.py:331`
- **test_heal_parameter_validation_error_unknown_operation** (function) in `tests/test_exception_healer.py:346`
- **test_heal_document_operation_error_with_alternative_paths** (function) in `tests/test_exception_healer.py:360`
- **test_heal_document_operation_error_create_missing** (function) in `tests/test_exception_healer.py:375`
- **test_heal_document_operation_error_emergency_fallback** (function) in `tests/test_exception_healer.py:390`
- **test_heal_bulk_processing_error_empty_batch** (function) in `tests/test_exception_healer.py:404`
- **test_heal_bulk_processing_error_with_items** (function) in `tests/test_exception_healer.py:420`
- **test_heal_bulk_processing_error_accepts_bulk_items_key** (function) in `tests/test_exception_healer.py:439`
- **test_heal_emergency_exception_always_provides_healed_values** (function) in `tests/test_exception_healer.py:451`
- **test_heal_operation_specific_error_failure_shape_has_healed_values** (function) in `tests/test_exception_healer.py:460`
- **test_heal_rotation_error_permission_issues** (function) in `tests/test_exception_healer.py:469`
- **test_heal_rotation_error_general_error** (function) in `tests/test_exception_healer.py:483`
- **test_apply_healing_chain_level1_success** (function) in `tests/test_exception_healer.py:500`
- **test_apply_healing_chain_level2_success** (function) in `tests/test_exception_healer.py:526`
- **test_apply_healing_chain_level3_success** (function) in `tests/test_exception_healer.py:555`
- **test_helper_categorize_exception** (function) in `tests/test_exception_healer.py:581`
- **test_helper_assess_severity** (function) in `tests/test_exception_healer.py:593`
- **test_helper_identify_risk_factors** (function) in `tests/test_exception_healer.py:603`
- **test_helper_analyze_environment** (function) in `tests/test_exception_healer.py:622`
- **test_helper_get_alternative_document_paths** (function) in `tests/test_exception_healer.py:633`
- **test_helper_heal_individual_item** (function) in `tests/test_exception_healer.py:644`
- **test_helper_heal_parameter_conflicts** (function) in `tests/test_exception_healer.py:660`
- **test_helper_heal_missing_combinations** (function) in `tests/test_exception_healer.py:670`
- **test_backward_compatibility** (function) in `tests/test_function_decomposition_integration.py:285`
- **test_append_entry_decomposition** (function) in `tests/test_function_decomposition_integration.py:59`
- **test_query_entries_decomposition** (function) in `tests/test_function_decomposition_integration.py:123`
- **test_rotate_log_decomposition** (function) in `tests/test_function_decomposition_integration.py:190`
- **test_target_directory_defaults_to_project_root** (function) in `tests/test_generate_doc_templates_target_dir.py:6`
- **test_target_directory_treats_base_dir_as_repo_root** (function) in `tests/test_generate_doc_templates_target_dir.py:11`
- **test_target_directory_accepts_docs_dev_plans_dir** (function) in `tests/test_generate_doc_templates_target_dir.py:18`
- **test_target_directory_accepts_docs_dev_plans_slug_dir** (function) in `tests/test_generate_doc_templates_target_dir.py:26`
- **TestFormatProjectContext** (class) in `tests/test_get_project_formatter.py:23`
- **test_with_5_entries** (function) in `tests/test_get_project_formatter.py:113`
- **test_with_fewer_than_5_entries** (function) in `tests/test_get_project_formatter.py:139`
- **test_with_no_entries** (function) in `tests/test_get_project_formatter.py:160`
- **test_timestamp_parsing_iso_format** (function) in `tests/test_get_project_formatter.py:175`
- **test_timestamp_parsing_utc_format** (function) in `tests/test_get_project_formatter.py:197`
- **test_with_long_messages_no_truncation** (function) in `tests/test_get_project_formatter.py:219`
- **test_with_missing_docs** (function) in `tests/test_get_project_formatter.py:243`
- **test_agent_name_truncation** (function) in `tests/test_get_project_formatter.py:267`
- **test_location_section_dev_plan_path** (function) in `tests/test_get_project_formatter.py:289`
- **test_footer_status_with_timestamp** (function) in `tests/test_get_project_formatter.py:306`
- **test_footer_status_without_timestamp** (function) in `tests/test_get_project_formatter.py:326`
- **test_document_counts_display** (function) in `tests/test_get_project_formatter.py:346`
- **test_header_box_formatting** (function) in `tests/test_get_project_formatter.py:368`
- **test_emoji_display_in_entries** (function) in `tests/test_get_project_formatter.py:384`
- **test_default_emoji_when_missing** (function) in `tests/test_get_project_formatter.py:404`
- **sample_docs** (function) in `tests/test_get_project_integration.py:55`
- **TestReadRecentProgressEntries** (class) in `tests/test_get_project_integration.py:87`
- **TestGatherDocInfo** (class) in `tests/test_get_project_integration.py:184`
- **TestGetProjectIntegration** (class) in `tests/test_get_project_integration.py:239`
- **test_translate_project_error_includes_last_known_project_hint** (function) in `tests/test_last_known_project_hint.py:9`
- **TestFormatProjectsTable** (class) in `tests/test_list_projects_formatters.py:21`
- **TestFormatProjectDetail** (class) in `tests/test_list_projects_formatters.py:182`
- **TestFormatNoProjectsFound** (class) in `tests/test_list_projects_formatters.py:356`
- **TestIntegrationScenarios** (class) in `tests/test_list_projects_formatters.py:435`
- **test_basic_table_formatting** (function) in `tests/test_list_projects_formatters.py:24`
- **test_active_project_marking** (function) in `tests/test_list_projects_formatters.py:100`
- **test_filter_display_in_footer** (function) in `tests/test_list_projects_formatters.py:124`
- **test_no_last_entry_shows_never** (function) in `tests/test_list_projects_formatters.py:149`
- **test_pagination_single_page** (function) in `tests/test_list_projects_formatters.py:164`
- **test_single_project_detail_view** (function) in `tests/test_list_projects_formatters.py:185`
- **test_no_custom_content_hides_section** (function) in `tests/test_list_projects_formatters.py:262`
- **test_modified_docs_warning** (function) in `tests/test_list_projects_formatters.py:295`
- **test_no_registry_info_fallback** (function) in `tests/test_list_projects_formatters.py:325`
- **test_empty_state_with_single_filter** (function) in `tests/test_list_projects_formatters.py:359`
- **test_empty_state_with_multiple_filters** (function) in `tests/test_list_projects_formatters.py:384`
- **test_empty_state_with_no_filters** (function) in `tests/test_list_projects_formatters.py:404`
- **test_suggestions_always_present** (function) in `tests/test_list_projects_formatters.py:421`
- **test_ansi_color_support_disabled** (function) in `tests/test_list_projects_formatters.py:438`
- **test_long_project_name_truncation** (function) in `tests/test_list_projects_formatters.py:459`
- **TestGatherDocInfo** (class) in `tests/test_list_projects_integration.py:18`
- **TestListProjectsIntegration** (class) in `tests/test_list_projects_integration.py:139`
- **TestListProjectsPagination** (class) in `tests/test_list_projects_integration.py:326`
- **TestIntegration** (class) in `tests/test_log_enums.py:267`
- **TestLogPriority** (class) in `tests/test_log_enums.py:25`
- **TestLogCategory** (class) in `tests/test_log_enums.py:47`
- **TestValidatePriority** (class) in `tests/test_log_enums.py:74`
- **TestValidateCategory** (class) in `tests/test_log_enums.py:122`
- **TestInferPriorityFromStatus** (class) in `tests/test_log_enums.py:169`
- **TestGetPrioritySortKey** (class) in `tests/test_log_enums.py:215`
- **test_enum_values** (function) in `tests/test_log_enums.py:28`
- **test_enum_values** (function) in `tests/test_log_enums.py:50`
- **test_enum_membership** (function) in `tests/test_log_enums.py:35`
- **test_enum_membership** (function) in `tests/test_log_enums.py:63`
- **test_enum_count** (function) in `tests/test_log_enums.py:42`
- **test_enum_count** (function) in `tests/test_log_enums.py:69`
- **test_valid_lowercase** (function) in `tests/test_log_enums.py:77`
- **test_valid_lowercase** (function) in `tests/test_log_enums.py:125`
- **test_valid_uppercase** (function) in `tests/test_log_enums.py:84`
- **test_valid_uppercase** (function) in `tests/test_log_enums.py:132`
- **test_valid_mixed_case** (function) in `tests/test_log_enums.py:91`
- **test_valid_mixed_case** (function) in `tests/test_log_enums.py:138`
- **test_enum_passthrough** (function) in `tests/test_log_enums.py:96`
- **test_enum_passthrough** (function) in `tests/test_log_enums.py:143`
- **test_none_value** (function) in `tests/test_log_enums.py:101`
- **test_none_value** (function) in `tests/test_log_enums.py:148`
- **test_invalid_string** (function) in `tests/test_log_enums.py:105`
- **test_invalid_string** (function) in `tests/test_log_enums.py:152`
- **test_invalid_type** (function) in `tests/test_log_enums.py:113`
- **test_invalid_type** (function) in `tests/test_log_enums.py:160`
- **test_high_priority_statuses** (function) in `tests/test_log_enums.py:172`
- **test_medium_priority_statuses** (function) in `tests/test_log_enums.py:177`
- **test_low_priority_statuses** (function) in `tests/test_log_enums.py:183`
- **test_case_insensitive** (function) in `tests/test_log_enums.py:187`
- **test_case_insensitive** (function) in `tests/test_log_enums.py:238`
- **test_unknown_status_defaults_to_medium** (function) in `tests/test_log_enums.py:194`
- **test_all_standard_statuses** (function) in `tests/test_log_enums.py:200`
- **test_critical_highest** (function) in `tests/test_log_enums.py:218`
- **test_high_second** (function) in `tests/test_log_enums.py:223`
- **test_medium_third** (function) in `tests/test_log_enums.py:228`
- **test_low_lowest** (function) in `tests/test_log_enums.py:233`
- **test_enum_input** (function) in `tests/test_log_enums.py:243`
- **test_sort_ordering** (function) in `tests/test_log_enums.py:250`
- **test_invalid_priority_raises** (function) in `tests/test_log_enums.py:256`
- **test_none_priority_raises** (function) in `tests/test_log_enums.py:261`
- **test_status_to_priority_to_sort_key** (function) in `tests/test_log_enums.py:270`
- **test_validate_then_sort** (function) in `tests/test_log_enums.py:282`
- **test_round_trip_priority** (function) in `tests/test_log_enums.py:295`
- **test_round_trip_category** (function) in `tests/test_log_enums.py:302`
- **test_normalize_metadata_with_dict** (function) in `tests/test_logging_utils.py:27`
- **test_normalize_metadata_with_cli_string_pairs** (function) in `tests/test_logging_utils.py:37`
- **test_normalize_metadata_invalid_input** (function) in `tests/test_logging_utils.py:44`
- **test_normalize_metadata_handles_json_array_string** (function) in `tests/test_logging_utils.py:50`
- **test_normalize_metadata_handles_sequence_pairs** (function) in `tests/test_logging_utils.py:57`
- **test_normalize_meta_filters_success** (function) in `tests/test_logging_utils.py:64`
- **test_normalize_meta_filters_invalid_key** (function) in `tests/test_logging_utils.py:70`
- **test_clean_list_handles_strings_and_duplicates** (function) in `tests/test_logging_utils.py:76`
- **test_compose_log_line_includes_metadata** (function) in `tests/test_logging_utils.py:84`
- **test_default_status_emoji_prefers_explicit** (function) in `tests/test_logging_utils.py:97`
- **test_resolve_log_definition_uses_cache** (function) in `tests/test_logging_utils.py:104`
- **test_chunking_splits_on_headings** (function) in `tests/test_manage_docs_chunking.py:6`
- **test_chunking_repeats_heading_when_split** (function) in `tests/test_manage_docs_chunking.py:20`
- **test_semantic_limits_defaults** (function) in `tests/test_manage_docs_semantic_limits.py:8`
- **test_semantic_limits_total_caps_logs** (function) in `tests/test_manage_docs_semantic_limits.py:15`
- **test_semantic_limits_overrides** (function) in `tests/test_manage_docs_semantic_limits.py:22`
- **test_doc_index_skip_for_logs** (function) in `tests/test_manage_docs_semantic_limits.py:32`
- **TestIntegrationScenarios** (class) in `tests/test_mcp_tools_enhancements.py:334`
- **TestManageDocsEnumValidation** (class) in `tests/test_mcp_tools_enhancements.py:33`
- **TestComparisonSymbolValidation** (class) in `tests/test_mcp_tools_enhancements.py:104`
- **TestEnhancedParameterValidator** (class) in `tests/test_mcp_tools_enhancements.py:164`
- **TestManageDocsDocumentCreation** (class) in `tests/test_mcp_tools_enhancements.py:256`
- **TestErrorHandlingAndMessages** (class) in `tests/test_mcp_tools_enhancements.py:384`
- **test_valid_actions_enum_includes_creation_actions** (function) in `tests/test_mcp_tools_enhancements.py:36`
- **test_invalid_action_gets_corrected** (function) in `tests/test_mcp_tools_enhancements.py:64`
- **test_replace_section_requires_section_param** (function) in `tests/test_mcp_tools_enhancements.py:79`
- **test_status_update_requires_metadata** (function) in `tests/test_mcp_tools_enhancements.py:91`
- **test_validate_comparison_symbols_accepts_safe_content** (function) in `tests/test_mcp_tools_enhancements.py:107`
- **test_validate_comparison_symbols_detects_numeric_comparisons** (function) in `tests/test_mcp_tools_enhancements.py:120`
- **test_validate_comparison_symbols_in_meta_escapes_operators** (function) in `tests/test_mcp_tools_enhancements.py:132`
- **test_normalise_meta_handles_comparison_symbols** (function) in `tests/test_mcp_tools_enhancements.py:146`
- **test_validate_string_param_basic_validation** (function) in `tests/test_mcp_tools_enhancements.py:167`
- **test_validate_string_param_length_validation** (function) in `tests/test_mcp_tools_enhancements.py:183`
- **test_validate_enum_param** (function) in `tests/test_mcp_tools_enhancements.py:195`
- **test_validate_metadata_structure** (function) in `tests/test_mcp_tools_enhancements.py:208`
- **test_validate_comparison_operators_in_validator** (function) in `tests/test_mcp_tools_enhancements.py:225`
- **test_validate_list_param** (function) in `tests/test_mcp_tools_enhancements.py:238`
- **test_manage_docs_with_comparison_symbols_in_metadata** (function) in `tests/test_mcp_tools_enhancements.py:337`
- **test_append_entry_with_escaped_comparison_symbols** (function) in `tests/test_mcp_tools_enhancements.py:352`
- **test_enhanced_validator_integration** (function) in `tests/test_mcp_tools_enhancements.py:366`
- **test_document_validation_error_messages** (function) in `tests/test_mcp_tools_enhancements.py:387`
- **test_parameter_validation_error_context** (function) in `tests/test_mcp_tools_enhancements.py:407`
- **test_suggestions_in_error_messages** (function) in `tests/test_mcp_tools_enhancements.py:418`
- **test_validate_enum_value_valid** (function) in `tests/test_parameter_validator.py:48`
- **test_validate_enum_value_invalid** (function) in `tests/test_parameter_validator.py:57`
- **TestToolValidator** (class) in `tests/test_parameter_validator.py:18`
- **test_validate_message_valid_messages** (function) in `tests/test_parameter_validator.py:21`
- **test_validate_message_invalid_newlines** (function) in `tests/test_parameter_validator.py:29`
- **test_validate_message_invalid_pipes** (function) in `tests/test_parameter_validator.py:40`
- **test_validate_regex_pattern_valid** (function) in `tests/test_parameter_validator.py:68`
- **test_validate_regex_pattern_invalid** (function) in `tests/test_parameter_validator.py:75`
- **test_validate_range_valid** (function) in `tests/test_parameter_validator.py:84`
- **test_validate_range_invalid** (function) in `tests/test_parameter_validator.py:100`
- **test_validate_timestamp_valid** (function) in `tests/test_parameter_validator.py:114`
- **test_validate_timestamp_empty** (function) in `tests/test_parameter_validator.py:123`
- **test_validate_timestamp_invalid** (function) in `tests/test_parameter_validator.py:137`
- **test_sanitize_identifier_valid** (function) in `tests/test_parameter_validator.py:149`
- **test_sanitize_identifier_sanitization** (function) in `tests/test_parameter_validator.py:155`
- **test_sanitize_identifier_fallback** (function) in `tests/test_parameter_validator.py:161`
- **test_validate_json_metadata_valid** (function) in `tests/test_parameter_validator.py:167`
- **test_validate_json_metadata_invalid** (function) in `tests/test_parameter_validator.py:187`
- **test_validate_json_metadata_with_custom_field_name** (function) in `tests/test_parameter_validator.py:206`
- **test_validate_json_metadata_fallback_parsing** (function) in `tests/test_parameter_validator.py:212`
- **test_validate_list_parameter_string** (function) in `tests/test_parameter_validator.py:222`
- **test_validate_list_parameter_with_different_delimiter** (function) in `tests/test_parameter_validator.py:233`
- **test_validate_list_parameter_with_empty_items** (function) in `tests/test_parameter_validator.py:241`
- **test_validate_list_parameter_sequence** (function) in `tests/test_parameter_validator.py:249`
- **test_validate_list_parameter_empty** (function) in `tests/test_parameter_validator.py:260`
- **test_validate_document_types_valid** (function) in `tests/test_parameter_validator.py:267`
- **test_validate_document_types_invalid** (function) in `tests/test_parameter_validator.py:279`
- **test_validate_document_types_empty** (function) in `tests/test_parameter_validator.py:292`
- **test_validate_parameters_against_schema_valid** (function) in `tests/test_parameter_validator.py:304`
- **test_validate_parameters_against_schema_missing_required** (function) in `tests/test_parameter_validator.py:333`
- **test_validate_parameters_against_schema_type_mismatch** (function) in `tests/test_parameter_validator.py:347`
- **test_validate_parameters_against_schema_enum_violation** (function) in `tests/test_parameter_validator.py:362`
- **test_validate_parameters_against_schema_range_violation** (function) in `tests/test_parameter_validator.py:378`
- **test_validate_parameters_against_schema_regex_violation** (function) in `tests/test_parameter_validator.py:398`
- **test_validate_parameters_against_schema_invalid_regex_pattern** (function) in `tests/test_parameter_validator.py:413`
- **test_validate_metadata_requirements_with_real_utility** (function) in `tests/test_parameter_validator.py:428`
- **test_validate_metadata_requirements_fallback** (function) in `tests/test_parameter_validator.py:445`
- **test_validate_parameters_against_schema_optional_fields** (function) in `tests/test_parameter_validator.py:455`
- **test_parse_timestamp_helper** (function) in `tests/test_parameter_validator.py:472`
- **test_validate_message_parametrized** (function) in `tests/test_parameter_validator.py:497`
- **test_validate_enum_value_parametrized** (function) in `tests/test_parameter_validator.py:507`
- **test_parse_timestamp_parametrized** (function) in `tests/test_parameter_validator.py:522`
- **test_plugin_registry_loads_builtin_vector_indexer** (function) in `tests/test_plugin_registry_runtime.py:15`
- **test_ensure_schema_adds_registry_columns** (function) in `tests/test_project_registry.py:88`
- **test_touch_entry_auto_promotes_planning_to_in_progress** (function) in `tests/test_project_registry.py:103`
- **test_record_doc_update_sets_doc_hygiene_flags** (function) in `tests/test_project_registry.py:171`
- **test_get_project_enriches_meta_with_activity_and_drift** (function) in `tests/test_project_registry.py:223`
- **test_to_dict** (function) in `tests/test_query_entries_config.py:326`
- **TestConvenienceFunctions** (class) in `tests/test_query_entries_config.py:407`
- **TestQueryEntriesConfigBasicFunctionality** (class) in `tests/test_query_entries_config.py:25`
- **TestQueryEntriesConfigValidation** (class) in `tests/test_query_entries_config.py:126`
- **TestQueryEntriesConfigNormalization** (class) in `tests/test_query_entries_config.py:273`
- **TestQueryEntriesConfigUtilityMethods** (class) in `tests/test_query_entries_config.py:323`
- **TestComplexSearchScenarios** (class) in `tests/test_query_entries_config.py:435`
- **test_default_configuration** (function) in `tests/test_query_entries_config.py:28`
- **test_full_configuration** (function) in `tests/test_query_entries_config.py:55`
- **test_pagination_mode_detection** (function) in `tests/test_query_entries_config.py:91`
- **test_string_parameter_conversion** (function) in `tests/test_query_entries_config.py:109`
- **test_valid_message_modes** (function) in `tests/test_query_entries_config.py:129`
- **test_invalid_message_mode** (function) in `tests/test_query_entries_config.py:137`
- **test_valid_search_scopes** (function) in `tests/test_query_entries_config.py:147`
- **test_invalid_search_scope** (function) in `tests/test_query_entries_config.py:155`
- **test_valid_document_types** (function) in `tests/test_query_entries_config.py:165`
- **test_invalid_document_types** (function) in `tests/test_query_entries_config.py:173`
- **test_valid_relevance_threshold** (function) in `tests/test_query_entries_config.py:183`
- **test_invalid_relevance_threshold** (function) in `tests/test_query_entries_config.py:192`
- **test_valid_regex_pattern** (function) in `tests/test_query_entries_config.py:204`
- **test_invalid_regex_pattern** (function) in `tests/test_query_entries_config.py:213`
- **test_valid_pagination_parameters** (function) in `tests/test_query_entries_config.py:224`
- **test_invalid_page_parameter** (function) in `tests/test_query_entries_config.py:231`
- **test_invalid_page_size_parameters** (function) in `tests/test_query_entries_config.py:241`
- **test_valid_time_ranges** (function) in `tests/test_query_entries_config.py:253`
- **test_invalid_time_range** (function) in `tests/test_query_entries_config.py:262`
- **test_message_mode_normalization** (function) in `tests/test_query_entries_config.py:276`
- **test_search_scope_normalization** (function) in `tests/test_query_entries_config.py:284`
- **test_list_parameter_normalization** (function) in `tests/test_query_entries_config.py:289`
- **test_pagination_mode_resolution** (function) in `tests/test_query_entries_config.py:302`
- **test_to_tool_params** (function) in `tests/test_query_entries_config.py:341`
- **test_from_legacy_params** (function) in `tests/test_query_entries_config.py:354`
- **test_create_search_config** (function) in `tests/test_query_entries_config.py:369`
- **test_get_search_description** (function) in `tests/test_query_entries_config.py:384`
- **test_get_search_description_empty** (function) in `tests/test_query_entries_config.py:400`
- **test_create_query_config** (function) in `tests/test_query_entries_config.py:410`
- **test_create_search_config_function** (function) in `tests/test_query_entries_config.py:421`
- **test_complex_search_configuration** (function) in `tests/test_query_entries_config.py:438`
- **test_edge_case_parameters** (function) in `tests/test_query_entries_config.py:468`
- **test_maximum_boundary_values** (function) in `tests/test_query_entries_config.py:485`
- **test_validate_search_parameters_accepts_fields_list** (function) in `tests/test_query_entries_fields_parameter.py:4`
- **test_correct_intelligent_parameter_search_scope_returns_string** (function) in `tests/test_query_entries_fields_parameter.py:36`
- **TestReminderHashSession** (class) in `tests/test_reminder_hash_session.py:9`
- **test_hash_without_session_id** (function) in `tests/test_reminder_hash_session.py:12`
- **test_hash_with_session_id_flag_off** (function) in `tests/test_reminder_hash_session.py:40`
- **test_hash_with_session_id_flag_on** (function) in `tests/test_reminder_hash_session.py:89`
- **test_hash_different_sessions_different_hash** (function) in `tests/test_reminder_hash_session.py:137`
- **test_hash_same_session_same_hash** (function) in `tests/test_reminder_hash_session.py:185`
- **TestReminderHistorySchema** (class) in `tests/test_reminder_history_schema.py:32`
- **test_reminder_history_table_exists** (function) in `tests/test_reminder_history_schema.py:35`
- **test_reminder_history_columns** (function) in `tests/test_reminder_history_schema.py:47`
- **test_reminder_history_foreign_key_constraint** (function) in `tests/test_reminder_history_schema.py:77`
- **test_reminder_history_check_constraint** (function) in `tests/test_reminder_history_schema.py:91`
- **test_reminder_history_indexes_exist** (function) in `tests/test_reminder_history_schema.py:131`
- **test_reminder_history_index_columns** (function) in `tests/test_reminder_history_schema.py:147`
- **test_reminder_history_cascade_delete** (function) in `tests/test_reminder_history_schema.py:168`
- **test_reminder_history_insert_and_query** (function) in `tests/test_reminder_history_schema.py:210`
- **test_reminder_history_no_breaking_changes** (function) in `tests/test_reminder_history_schema.py:262`
- **TestReminderStorage** (class) in `tests/test_reminder_storage.py:63`
- **test_record_reminder_shown_insert** (function) in `tests/test_reminder_storage.py:66`
- **test_record_reminder_shown_update** (function) in `tests/test_reminder_storage.py:107`
- **test_check_reminder_cooldown_within_window** (function) in `tests/test_reminder_storage.py:153`
- **test_check_reminder_cooldown_outside_window** (function) in `tests/test_reminder_storage.py:176`
- **test_check_reminder_cooldown_no_history** (function) in `tests/test_reminder_storage.py:204`
- **test_cleanup_reminder_history_by_session** (function) in `tests/test_reminder_storage.py:219`
- **test_cleanup_reminder_history_global** (function) in `tests/test_reminder_storage.py:263`
- **test_cleanup_reminder_history_respects_retention** (function) in `tests/test_reminder_storage.py:307`
- **test_reminder_cascade_on_session_delete** (function) in `tests/test_reminder_storage.py:327`
- **test_performance_under_5ms** (function) in `tests/test_reminder_storage.py:367`
- **test_reminder_engine_adds_now_variables** (function) in `tests/test_reminder_time_variables.py:8`
- **setup_method** (function) in `tests/test_response_formatter_helpers.py:26`
- **setup_method** (function) in `tests/test_response_formatter_helpers.py:142`
- **setup_method** (function) in `tests/test_response_formatter_helpers.py:239`
- **TestFormatRelativeTime** (class) in `tests/test_response_formatter_helpers.py:23`
- **TestGetDocLineCount** (class) in `tests/test_response_formatter_helpers.py:139`
- **TestDetectCustomContent** (class) in `tests/test_response_formatter_helpers.py:236`
- **test_just_now** (function) in `tests/test_response_formatter_helpers.py:30`
- **test_minutes_ago** (function) in `tests/test_response_formatter_helpers.py:37`
- **test_hours_ago** (function) in `tests/test_response_formatter_helpers.py:51`
- **test_days_ago** (function) in `tests/test_response_formatter_helpers.py:65`
- **test_weeks_ago** (function) in `tests/test_response_formatter_helpers.py:79`
- **test_months_ago** (function) in `tests/test_response_formatter_helpers.py:93`
- **test_timestamp_formats** (function) in `tests/test_response_formatter_helpers.py:107`
- **test_invalid_timestamp** (function) in `tests/test_response_formatter_helpers.py:127`
- **test_existing_file** (function) in `tests/test_response_formatter_helpers.py:146`
- **test_nonexistent_file** (function) in `tests/test_response_formatter_helpers.py:160`
- **test_directory_path** (function) in `tests/test_response_formatter_helpers.py:165`
- **test_empty_file** (function) in `tests/test_response_formatter_helpers.py:171`
- **test_file_with_known_lines** (function) in `tests/test_response_formatter_helpers.py:182`
- **test_file_without_trailing_newline** (function) in `tests/test_response_formatter_helpers.py:196`
- **test_unicode_file** (function) in `tests/test_response_formatter_helpers.py:209`
- **test_string_path** (function) in `tests/test_response_formatter_helpers.py:223`
- **test_string_path** (function) in `tests/test_response_formatter_helpers.py:324`
- **test_path_object** (function) in `tests/test_response_formatter_helpers.py:229`
- **test_path_object** (function) in `tests/test_response_formatter_helpers.py:330`
- **test_nonexistent_directory** (function) in `tests/test_response_formatter_helpers.py:243`
- **test_empty_directory** (function) in `tests/test_response_formatter_helpers.py:251`
- **test_research_directory** (function) in `tests/test_response_formatter_helpers.py:260`
- **test_bugs_directory** (function) in `tests/test_response_formatter_helpers.py:276`
- **test_jsonl_files** (function) in `tests/test_response_formatter_helpers.py:286`
- **test_combined_content** (function) in `tests/test_response_formatter_helpers.py:300`
- **test_real_project_directory** (function) in `tests/test_response_formatter_helpers.py:336`
- **TestLineNumbering** (class) in `tests/test_response_formatter_readable.py:34`
- **TestASCIIBoxes** (class) in `tests/test_response_formatter_readable.py:134`
- **TestTableFormatting** (class) in `tests/test_response_formatter_readable.py:227`
- **TestCoreFormatters** (class) in `tests/test_response_formatter_readable.py:292`
- **TestFormatRouter** (class) in `tests/test_response_formatter_readable.py:465`
- **TestFormatConstants** (class) in `tests/test_response_formatter_readable.py:568`
- **TestBackwardCompatibility** (class) in `tests/test_response_formatter_readable.py:584`
- **TestAppendEntryFormatting** (class) in `tests/test_response_formatter_readable.py:634`
- **TestPhase3aReadRecentEnhancements** (class) in `tests/test_response_formatter_readable.py:919`
- **TestPhase3bQueryEntriesEnhancements** (class) in `tests/test_response_formatter_readable.py:1089`
- **test_single_line** (function) in `tests/test_response_formatter_readable.py:37`
- **test_ten_lines** (function) in `tests/test_response_formatter_readable.py:47`
- **test_hundred_lines** (function) in `tests/test_response_formatter_readable.py:62`
- **test_thousand_lines** (function) in `tests/test_response_formatter_readable.py:77`
- **test_ten_thousand_lines** (function) in `tests/test_response_formatter_readable.py:92`
- **test_custom_start_line** (function) in `tests/test_response_formatter_readable.py:107`
- **test_empty_content** (function) in `tests/test_response_formatter_readable.py:118`
- **test_single_newline** (function) in `tests/test_response_formatter_readable.py:124`
- **test_header_box_basic** (function) in `tests/test_response_formatter_readable.py:137`
- **test_header_box_width** (function) in `tests/test_response_formatter_readable.py:157`
- **test_footer_box_basic** (function) in `tests/test_response_formatter_readable.py:168`
- **test_footer_box_with_reminders** (function) in `tests/test_response_formatter_readable.py:183`
- **test_box_long_values** (function) in `tests/test_response_formatter_readable.py:197`
- **test_box_dict_values** (function) in `tests/test_response_formatter_readable.py:214`
- **test_basic_table** (function) in `tests/test_response_formatter_readable.py:230`
- **test_table_alignment** (function) in `tests/test_response_formatter_readable.py:253`
- **test_empty_table** (function) in `tests/test_response_formatter_readable.py:271`
- **test_table_with_varying_lengths** (function) in `tests/test_response_formatter_readable.py:277`
- **test_format_readable_file_content** (function) in `tests/test_response_formatter_readable.py:295`
- **test_format_readable_log_entries** (function) in `tests/test_response_formatter_readable.py:335`
- **test_format_readable_log_entries_empty** (function) in `tests/test_response_formatter_readable.py:377`
- **test_format_readable_projects** (function) in `tests/test_response_formatter_readable.py:383`
- **test_format_readable_projects_empty** (function) in `tests/test_response_formatter_readable.py:414`
- **test_format_readable_confirmation** (function) in `tests/test_response_formatter_readable.py:420`
- **test_format_readable_error** (function) in `tests/test_response_formatter_readable.py:445`
- **test_format_constants_exist** (function) in `tests/test_response_formatter_readable.py:571`
- **test_format_constant_values** (function) in `tests/test_response_formatter_readable.py:577`
- **test_existing_format_entry** (function) in `tests/test_response_formatter_readable.py:587`
- **test_existing_format_response** (function) in `tests/test_response_formatter_readable.py:607`
- **test_existing_format_projects_response** (function) in `tests/test_response_formatter_readable.py:620`
- **test_single_entry_basic** (function) in `tests/test_response_formatter_readable.py:637`
- **test_single_entry_with_reasoning** (function) in `tests/test_response_formatter_readable.py:656`
- **test_single_entry_with_dict_reasoning** (function) in `tests/test_response_formatter_readable.py:679`
- **test_single_entry_with_reminders** (function) in `tests/test_response_formatter_readable.py:703`
- **test_single_entry_without_reminders** (function) in `tests/test_response_formatter_readable.py:724`
- **test_single_entry_failed** (function) in `tests/test_response_formatter_readable.py:740`
- **test_bulk_entry_success** (function) in `tests/test_response_formatter_readable.py:755`
- **test_bulk_entry_partial_success** (function) in `tests/test_response_formatter_readable.py:792`
- **test_parse_reasoning_block_json_string** (function) in `tests/test_response_formatter_readable.py:827`
- **test_parse_reasoning_block_dict** (function) in `tests/test_response_formatter_readable.py:841`
- **test_parse_reasoning_block_missing** (function) in `tests/test_response_formatter_readable.py:853`
- **test_parse_reasoning_block_malformed_json** (function) in `tests/test_response_formatter_readable.py:862`
- **test_extract_compact_log_line** (function) in `tests/test_response_formatter_readable.py:874`
- **test_extract_compact_log_line_fallback** (function) in `tests/test_response_formatter_readable.py:890`
- **test_no_ansi_colors_in_append_entry** (function) in `tests/test_response_formatter_readable.py:900`
- **test_log_entries_with_reasoning_blocks** (function) in `tests/test_response_formatter_readable.py:922`
- **test_log_entries_without_reasoning** (function) in `tests/test_response_formatter_readable.py:952`
- **test_smart_message_truncation** (function) in `tests/test_response_formatter_readable.py:973`
- **test_smart_truncation_fallback** (function) in `tests/test_response_formatter_readable.py:988`
- **test_compact_timestamp_format** (function) in `tests/test_response_formatter_readable.py:999`
- **test_pagination_display** (function) in `tests/test_response_formatter_readable.py:1031`
- **test_ansi_colors_enabled_for_read_recent** (function) in `tests/test_response_formatter_readable.py:1043`
- **test_uuid_agent_truncation** (function) in `tests/test_response_formatter_readable.py:1066`
- **test_query_results_header_with_message_filter** (function) in `tests/test_response_formatter_readable.py:1092`
- **test_query_results_multiple_filters** (function) in `tests/test_response_formatter_readable.py:1118`
- **test_query_results_no_search_context** (function) in `tests/test_response_formatter_readable.py:1147`
- **test_query_results_empty_results** (function) in `tests/test_response_formatter_readable.py:1173`
- **test_query_filter_truncation** (function) in `tests/test_response_formatter_readable.py:1185`
- **test_to_dict** (function) in `tests/test_rotate_log_config.py:193`
- **test_default_configuration** (function) in `tests/test_rotate_log_config.py:28`
- **test_from_legacy_params** (function) in `tests/test_rotate_log_config.py:320`
- **TestRotateLogConfigBasics** (class) in `tests/test_rotate_log_config.py:25`
- **TestRotateLogConfigNormalization** (class) in `tests/test_rotate_log_config.py:136`
- **TestRotateLogConfigMethods** (class) in `tests/test_rotate_log_config.py:190`
- **TestRotateLogConfigFactoryMethods** (class) in `tests/test_rotate_log_config.py:317`
- **TestRotateLogConfigBackwardCompatibility** (class) in `tests/test_rotate_log_config.py:373`
- **TestRotateLogConfigEdgeCases** (class) in `tests/test_rotate_log_config.py:411`
- **TestRotateLogConfigIntegration** (class) in `tests/test_rotate_log_config.py:468`
- **test_post_initialization_validation** (function) in `tests/test_rotate_log_config.py:45`
- **test_invalid_dry_run_mode** (function) in `tests/test_rotate_log_config.py:55`
- **test_invalid_custom_metadata** (function) in `tests/test_rotate_log_config.py:60`
- **test_invalid_threshold_entries** (function) in `tests/test_rotate_log_config.py:65`
- **test_invalid_log_selection_combination** (function) in `tests/test_rotate_log_config.py:70`
- **test_no_log_selection** (function) in `tests/test_rotate_log_config.py:84`
- **test_invalid_suffix** (function) in `tests/test_rotate_log_config.py:89`
- **test_invalid_bytes_per_line_bounds** (function) in `tests/test_rotate_log_config.py:97`
- **test_invalid_estimation_band_ratio** (function) in `tests/test_rotate_log_config.py:113`
- **test_invalid_estimation_band_min** (function) in `tests/test_rotate_log_config.py:127`
- **test_dry_run_mode_normalization** (function) in `tests/test_rotate_log_config.py:139`
- **test_dry_run_mode_default** (function) in `tests/test_rotate_log_config.py:147`
- **test_log_types_normalization** (function) in `tests/test_rotate_log_config.py:155`
- **test_dry_run_default_from_confirm** (function) in `tests/test_rotate_log_config.py:163`
- **test_threshold_entries_default** (function) in `tests/test_rotate_log_config.py:181`
- **test_to_dict_omits_defaults** (function) in `tests/test_rotate_log_config.py:211`
- **test_get_parsed_metadata** (function) in `tests/test_rotate_log_config.py:222`
- **test_get_parsed_metadata_none** (function) in `tests/test_rotate_log_config.py:232`
- **test_get_parsed_metadata_invalid** (function) in `tests/test_rotate_log_config.py:239`
- **test_is_dry_run** (function) in `tests/test_rotate_log_config.py:249`
- **test_is_auto_threshold_mode** (function) in `tests/test_rotate_log_config.py:263`
- **test_get_effective_threshold** (function) in `tests/test_rotate_log_config.py:277`
- **test_create_validation_error** (function) in `tests/test_rotate_log_config.py:291`
- **test_apply_response_defaults** (function) in `tests/test_rotate_log_config.py:304`
- **test_create_for_auto_rotation** (function) in `tests/test_rotate_log_config.py:336`
- **test_create_for_manual_rotation** (function) in `tests/test_rotate_log_config.py:348`
- **test_create_for_dry_run** (function) in `tests/test_rotate_log_config.py:360`
- **test_create_rotate_log_config_function** (function) in `tests/test_rotate_log_config.py:376`
- **test_validate_rotate_log_params_success** (function) in `tests/test_rotate_log_config.py:389`
- **test_validate_rotate_log_params_failure** (function) in `tests/test_rotate_log_config.py:400`
- **test_empty_log_types_list** (function) in `tests/test_rotate_log_config.py:414`
- **test_large_threshold_value** (function) in `tests/test_rotate_log_config.py:423`
- **test_complex_custom_metadata** (function) in `tests/test_rotate_log_config.py:431`
- **test_rotate_all_with_custom_configuration** (function) in `tests/test_rotate_log_config.py:453`
- **test_phase_1_validator_integration** (function) in `tests/test_rotate_log_config.py:471`
- **test_phase_1_config_manager_integration** (function) in `tests/test_rotate_log_config.py:480`
- **test_phase_1_error_handler_integration** (function) in `tests/test_rotate_log_config.py:488`
- **TestConvenienceFunctions** (class) in `tests/test_rotation_utils.py:418`
- **setup_method** (function) in `tests/test_rotation_utils.py:51`
- **setup_method** (function) in `tests/test_rotation_utils.py:154`
- **setup_method** (function) in `tests/test_rotation_utils.py:255`
- **setup_method** (function) in `tests/test_rotation_utils.py:421`
- **TestIntegrityUtils** (class) in `tests/test_rotation_utils.py:48`
- **TestAuditTrailManager** (class) in `tests/test_rotation_utils.py:151`
- **TestRotationStateManager** (class) in `tests/test_rotation_utils.py:252`
- **test_entry_count_estimation_cache_invalidation** (function) in `tests/test_rotation_utils.py:442`
- **test_compute_file_hash** (function) in `tests/test_rotation_utils.py:62`
- **test_compute_file_hash_nonexistent** (function) in `tests/test_rotation_utils.py:71`
- **test_verify_file_integrity** (function) in `tests/test_rotation_utils.py:76`
- **test_create_file_metadata** (function) in `tests/test_rotation_utils.py:91`
- **test_hash_file_string** (function) in `tests/test_rotation_utils.py:103`
- **test_count_file_lines** (function) in `tests/test_rotation_utils.py:109`
- **test_create_rotation_metadata** (function) in `tests/test_rotation_utils.py:114`
- **test_benchmark_hash_performance** (function) in `tests/test_rotation_utils.py:135`
- **test_store_rotation_metadata** (function) in `tests/test_rotation_utils.py:168`
- **test_get_rotation_history** (function) in `tests/test_rotation_utils.py:173`
- **test_get_rotation_by_uuid** (function) in `tests/test_rotation_utils.py:189`
- **test_get_audit_summary** (function) in `tests/test_rotation_utils.py:207`
- **test_cleanup_old_rotations** (function) in `tests/test_rotation_utils.py:219`
- **test_list_audited_projects** (function) in `tests/test_rotation_utils.py:237`
- **test_get_project_state_initial** (function) in `tests/test_rotation_utils.py:269`
- **test_generate_rotation_id** (function) in `tests/test_rotation_utils.py:279`
- **test_get_next_sequence_number** (function) in `tests/test_rotation_utils.py:287`
- **test_update_project_state** (function) in `tests/test_rotation_utils.py:301`
- **test_hash_chain_tracking** (function) in `tests/test_rotation_utils.py:314`
- **test_get_project_statistics** (function) in `tests/test_rotation_utils.py:342`
- **test_cleanup_project_state** (function) in `tests/test_rotation_utils.py:355`
- **test_list_tracked_projects** (function) in `tests/test_rotation_utils.py:375`
- **test_reset_project_state** (function) in `tests/test_rotation_utils.py:387`
- **test_global_settings** (function) in `tests/test_rotation_utils.py:400`
- **test_audit_manager_convenience_functions** (function) in `tests/test_rotation_utils.py:425`
- **test_state_manager_convenience_functions** (function) in `tests/test_rotation_utils.py:433`
- **test_path_traversal_with_dots** (function) in `tests/test_sandbox_bypass.py:19`
- **test_symlink_hijacking** (function) in `tests/test_sandbox_bypass.py:45`
- **test_absolute_path_escape** (function) in `tests/test_sandbox_bypass.py:69`
- **test_permission_boundary_violations** (function) in `tests/test_sandbox_bypass.py:93`
- **test_environment_variable_injection** (function) in `tests/test_sandbox_bypass.py:115`
- **test_device_file_access** (function) in `tests/test_sandbox_bypass.py:140`
- **test_temporary_directory_escape** (function) in `tests/test_sandbox_bypass.py:164`
- **test_unicode_encoding_bypass** (function) in `tests/test_sandbox_bypass.py:189`
- **TestFormatProjectSitrepNew** (class) in `tests/test_set_project_formatters.py:20`
- **TestFormatProjectSitrepExisting** (class) in `tests/test_set_project_formatters.py:129`
- **TestEdgeCases** (class) in `tests/test_set_project_formatters.py:361`
- **test_header_shows_new_project_created** (function) in `tests/test_set_project_formatters.py:64`
- **test_location_section_present** (function) in `tests/test_set_project_formatters.py:72`
- **test_template_doc_line_counts** (function) in `tests/test_set_project_formatters.py:80`
- **test_progress_log_shows_empty_ready** (function) in `tests/test_set_project_formatters.py:88`
- **test_status_shows_planning_new_project** (function) in `tests/test_set_project_formatters.py:96`
- **test_next_steps_tip_present** (function) in `tests/test_set_project_formatters.py:102`
- **test_handles_missing_docs_gracefully** (function) in `tests/test_set_project_formatters.py:108`
- **test_dev_plan_path_extraction** (function) in `tests/test_set_project_formatters.py:116`
- **test_header_shows_project_activated** (function) in `tests/test_set_project_formatters.py:177`
- **test_status_annotation_active_work** (function) in `tests/test_set_project_formatters.py:186`
- **test_status_without_annotation** (function) in `tests/test_set_project_formatters.py:194`
- **test_per_log_breakdown_in_total_entries** (function) in `tests/test_set_project_formatters.py:206`
- **test_per_log_breakdown_excludes_zero_counts** (function) in `tests/test_set_project_formatters.py:214`
- **test_modified_doc_warnings** (function) in `tests/test_set_project_formatters.py:226`
- **test_progress_log_shows_entries_count** (function) in `tests/test_set_project_formatters.py:239`
- **test_custom_content_section_when_present** (function) in `tests/test_set_project_formatters.py:247`
- **test_custom_content_section_omitted_when_absent** (function) in `tests/test_set_project_formatters.py:257`
- **test_relative_time_formatting** (function) in `tests/test_set_project_formatters.py:273`
- **test_handles_missing_per_log_counts** (function) in `tests/test_set_project_formatters.py:284`
- **test_handles_missing_last_entry_at** (function) in `tests/test_set_project_formatters.py:297`
- **test_all_docs_modified_warnings** (function) in `tests/test_set_project_formatters.py:310`
- **test_empty_docs_list** (function) in `tests/test_set_project_formatters.py:328`
- **test_multiple_jsonl_files** (function) in `tests/test_set_project_formatters.py:340`
- **test_footer_tip_present** (function) in `tests/test_set_project_formatters.py:352`
- **test_new_project_with_colors_enabled** (function) in `tests/test_set_project_formatters.py:369`
- **test_existing_project_with_colors_enabled** (function) in `tests/test_set_project_formatters.py:393`
- **test_minimal_data_new_project** (function) in `tests/test_set_project_formatters.py:406`
- **test_minimal_data_existing_project** (function) in `tests/test_set_project_formatters.py:416`
- **TestBackwardCompatibility** (class) in `tests/test_set_project_sitrep.py:436`
- **TestHelperFunctions** (class) in `tests/test_set_project_sitrep.py:61`
- **TestNewProjectSITREP** (class) in `tests/test_set_project_sitrep.py:178`
- **TestExistingProjectSITREP** (class) in `tests/test_set_project_sitrep.py:252`
- **TestNewVsExistingDetection** (class) in `tests/test_set_project_sitrep.py:382`
- **test_template_engine_renders_builtin_and_custom_templates** (function) in `tests/test_template_engine_manage_docs.py:27`
- **test_replace_section_auto_inserts_anchor** (function) in `tests/test_template_engine_manage_docs.py:623`
- **test_replace_section_missing_anchor_requires_allow_append** (function) in `tests/test_template_engine_manage_docs.py:631`
- **test_replace_section_duplicate_anchor_fails** (function) in `tests/test_template_engine_manage_docs.py:637`
- **test_toggle_checklist_status_metadata_only_updates_proof** (function) in `tests/test_template_engine_manage_docs.py:644`
- **test_toggle_checklist_status_creates_section_when_missing** (function) in `tests/test_template_engine_manage_docs.py:651`
- **TestRecursionPrevention** (class) in `tests/test_tool_logger.py:26`
- **TestToolLogPath** (class) in `tests/test_tool_logger.py:172`
- **TestAppendJsonlLine** (class) in `tests/test_tool_logger.py:188`
- **TestLogToolCall** (class) in `tests/test_tool_logger.py:224`
- **TestTimestampFormat** (class) in `tests/test_tool_logger.py:350`
- **test_no_forbidden_imports_runtime** (function) in `tests/test_tool_logger.py:40`
- **test_module_has_minimal_imports** (function) in `tests/test_tool_logger.py:125`
- **test_verification_function_exists** (function) in `tests/test_tool_logger.py:152`
- **test_module_structure_isolated** (function) in `tests/test_tool_logger.py:157`
- **test_returns_path_object** (function) in `tests/test_tool_logger.py:175`
- **test_correct_log_path** (function) in `tests/test_tool_logger.py:180`
- **test_creates_parent_directory** (function) in `tests/test_tool_logger.py:191`
- **test_appends_with_newline** (function) in `tests/test_tool_logger.py:200`
- **test_adds_newline_if_missing** (function) in `tests/test_tool_logger.py:214`
- **test_minimal_call** (function) in `tests/test_tool_logger.py:227`
- **test_all_optional_parameters** (function) in `tests/test_tool_logger.py:251`
- **test_graceful_error_handling** (function) in `tests/test_tool_logger.py:285`
- **test_valid_json_format** (function) in `tests/test_tool_logger.py:307`
- **test_multiple_calls_append** (function) in `tests/test_tool_logger.py:328`
- **test_timestamp_is_utc_iso_format** (function) in `tests/test_tool_logger.py:353`
- **isolated_state** (function) in `tests/test_tools.py:41`
- **test_set_and_get_project_roundtrip** (function) in `tests/test_tools.py:81`
- **test_append_and_read_recent** (function) in `tests/test_tools.py:103`
- **test_append_entry_uses_slugified_log_path** (function) in `tests/test_tools.py:143`
- **test_append_entry_accepts_json_string_meta** (function) in `tests/test_tools.py:163`
- **test_append_entry_accepts_sequence_metadata** (function) in `tests/test_tools.py:181`
- **test_append_entry_items_list_string_meta** (function) in `tests/test_tools.py:203`
- **test_rotate_log_creates_archive** (function) in `tests/test_tools.py:224`
- **test_generate_doc_templates_renders_files** (function) in `tests/test_tools.py:238`
- **test_log_rotation_triggers_when_max_bytes_reached** (function) in `tests/test_tools.py:268`
- **TestEnhancedRotationEngine** (class) in `tests/test_tools.py:309`
- **test_rotate_log_dry_run_precision_controls** (function) in `tests/test_tools.py:387`
- **test_enhanced_rotation_with_integrity** (function) in `tests/test_tools.py:312`
- **test_rotation_with_custom_metadata** (function) in `tests/test_tools.py:406`
- **test_rotation_with_invalid_metadata** (function) in `tests/test_tools.py:437`
- **test_rotation_hash_chain_tracking** (function) in `tests/test_tools.py:457`
- **test_rotation_integrity_verification** (function) in `tests/test_tools.py:496`
- **test_rotation_history_tracking** (function) in `tests/test_tools.py:528`
- **test_rotation_error_handling** (function) in `tests/test_tools.py:563`
- **test_rotation_performance_monitoring** (function) in `tests/test_tools.py:614`
- **test_sanitize_identifier_strips_brackets** (function) in `tests/test_utils.py:26`
- **test_validate_message_disallows_newlines_and_pipes** (function) in `tests/test_utils.py:32`
- **test_normalise_meta_orders_and_sanitises_keys** (function) in `tests/test_utils.py:38`
- **test_clean_meta_value_replaces_newlines_and_pipes** (function) in `tests/test_utils.py:44`
- **TestVectorIntegrationWorkflow** (class) in `tests/test_vector_complete_integration.py:42`
- **cleanup_after_test** (function) in `tests/test_vector_complete_integration.py:424`
- **TestDeterministicEntryIDs** (class) in `tests/test_vector_entry_ids.py:15`
- **test_get_repo_slug_basic** (function) in `tests/test_vector_entry_ids.py:18`
- **test_get_repo_slug_with_special_chars** (function) in `tests/test_vector_entry_ids.py:24`
- **test_get_repo_slug_with_spaces** (function) in `tests/test_vector_entry_ids.py:29`
- **test_get_repo_slug_empty_fallback** (function) in `tests/test_vector_entry_ids.py:34`
- **test_deterministic_entry_id_basic** (function) in `tests/test_vector_entry_ids.py:39`
- **test_deterministic_entry_id_consistency** (function) in `tests/test_vector_entry_ids.py:55`
- **test_deterministic_entry_id_uniqueness** (function) in `tests/test_vector_entry_ids.py:71`
- **test_deterministic_entry_id_meta_order_independence** (function) in `tests/test_vector_entry_ids.py:98`
- **test_deterministic_entry_id_empty_meta** (function) in `tests/test_vector_entry_ids.py:117`
- **test_compose_line_with_entry_id** (function) in `tests/test_vector_entry_ids.py:131`
- **test_compose_line_without_entry_id** (function) in `tests/test_vector_entry_ids.py:150`
- **test_entry_id_reproducibility_across_calls** (function) in `tests/test_vector_entry_ids.py:169`
- **TestVectorIndexer** (class) in `tests/test_vector_indexer.py:29`
- **TestVectorIndexerEdgeCases** (class) in `tests/test_vector_indexer.py:279`
- **test_initialization_success** (function) in `tests/test_vector_indexer.py:71`
- **test_initialization_disabled_by_config** (function) in `tests/test_vector_indexer.py:80`
- **test_initialization_missing_dependencies** (function) in `tests/test_vector_indexer.py:95`
- **test_get_repo_slug** (function) in `tests/test_vector_indexer.py:104`
- **test_index_creation** (function) in `tests/test_vector_indexer.py:118`
- **test_mapping_database_creation** (function) in `tests/test_vector_indexer.py:138`
- **test_get_index_status** (function) in `tests/test_vector_indexer.py:221`
- **test_post_append_hook** (function) in `tests/test_vector_indexer.py:234`
- **test_cleanup** (function) in `tests/test_vector_indexer.py:251`
- **test_load_existing_index_with_metadata_mismatch** (function) in `tests/test_vector_indexer.py:300`
- **test_filter_application** (function) in `tests/test_vector_indexer.py:381`
- **test_search_overfetches_for_filtered_results** (function) in `tests/test_vector_indexer.py:434`
- **TestVectorIntegration** (class) in `tests/test_vector_integration.py:32`
- **TestVectorIntegrationWithoutDeps** (class) in `tests/test_vector_integration.py:535`
- **test_graceful_degradation_without_dependencies** (function) in `tests/test_vector_integration.py:538`
- **TestVectorPerformance** (class) in `tests/test_vector_performance.py:30`
- **TestVectorScalability** (class) in `tests/test_vector_performance.py:424`
- **test_embedding_generation_performance** (function) in `tests/test_vector_performance.py:54`
- **test_index_creation_and_search_performance** (function) in `tests/test_vector_performance.py:101`
- **test_memory_usage_performance** (function) in `tests/test_vector_performance.py:236`
- **test_concurrent_search_performance** (function) in `tests/test_vector_performance.py:291`
- **test_index_size_performance** (function) in `tests/test_vector_performance.py:358`
- **test_large_index_scalability** (function) in `tests/test_vector_performance.py:435`
- **TestVectorSearchTools** (class) in `tests/test_vector_search_tools.py:30`
- **TestVectorToolRegistration** (class) in `tests/test_vector_search_tools.py:340`
- **TestVectorToolsWithoutDependencies** (class) in `tests/test_vector_search_tools.py:439`
- **test_register_vector_tools_success** (function) in `tests/test_vector_search_tools.py:343`
- **test_register_vector_tools_no_plugin** (function) in `tests/test_vector_search_tools.py:359`
- **test_register_vector_tools_plugin_not_initialized** (function) in `tests/test_vector_search_tools.py:372`
- **test_register_vector_tools_with_exception** (function) in `tests/test_vector_search_tools.py:389`
- **test_get_vector_indexer_not_initialized** (function) in `tests/test_vector_search_tools.py:408`
- **test_get_vector_indexer_success** (function) in `tests/test_vector_search_tools.py:422`
- **test_get_vector_indexer_without_dependencies** (function) in `tests/test_vector_search_tools.py:449`
- **BaseTool** (class) in `tools/base/base_tool.py:13`
- **safe_get_nested** (function) in `tools/base/parameter_normalizer.py:119`
- **list_tools_by_category** (function) in `tools/base/tool_metadata.py:396`
- **list_deprecated_tools** (function) in `tools/base/tool_metadata.py:401`
- **get_tool_examples** (function) in `tools/base/tool_metadata.py:406`
- **validate_tool_parameters** (function) in `tools/base/tool_metadata.py:412`
- **generate_tool_help** (function) in `tools/base/tool_metadata.py:437`
- **parameter_error** (function) in `tools/base/tool_result.py:80`
- **heal_and_validate** (function) in `tools/config/query_entries_config.py:137`
- **copy_with** (function) in `tools/config/rotate_log_config.py:415`
- **load_project_config_by_path** (function) in `tools/project_utils.py:120`
- **load_config_project** (function) in `tools/project_utils.py:127`
- **RotationTarget** (class) in `tools/rotate_log.py:365`
- **parse_json_items** (function) in `utils/bulk_processor.py:327`
- **validate_bulk_items** (function) in `utils/bulk_processor.py:348`
- **prepare_parallel_bulk_items** (function) in `utils/bulk_processor.py:383`
- **create_processing_chunks** (function) in `utils/bulk_processor.py:444`
- **optimize_for_performance** (function) in `utils/bulk_processor.py:506`
- **apply_token_budget_to_response** (function) in `utils/config_manager.py:674`
- **suggest_pagination** (function) in `utils/context_safety.py:181`
- **heal_and_execute** (function) in `utils/error_handler.py:471`
- **create_healing_response** (function) in `utils/error_handler.py:557`
- **auto_heal_parameter_type** (function) in `utils/estimator.py:722`
- **reset_configured_instances** (function) in `utils/optimization.py:102`
- **get_optimization_suggestion** (function) in `utils/tokens.py:222`
- **get_usage_stats** (function) in `utils/tokens.py:251`
- **get_tokenizer_info** (function) in `utils/tokens.py:297`
- **save_metrics** (function) in `utils/tokens.py:321`
- **load_metrics** (function) in `utils/tokens.py:342`

### LOW Severity

- **_log_async_error** (function) in `plugins/vector_indexer.py:212`
- **_start_background_loop** (function) in `plugins/vector_indexer.py:381`
- **_build_config** (function) in `reminders.py:292`
- **_apply_tone** (function) in `reminders.py:350`
- **_make_reminder** (function) in `reminders.py:356`
- **_iter_doc_files** (function) in `scripts/reindex_vector.py:95`
- **_write_json** (function) in `state/manager.py:231`
- **_write_json_atomic** (function) in `state/manager.py:239`
- **_migrate_document_sections_sync** (function) in `storage/sqlite.py:1110`
- **_ensure_column_sync** (function) in `storage/sqlite.py:1164`
- **_migrate_agent_sessions_schema_sync** (function) in `storage/sqlite.py:1179`
- **_ensure_index_sync** (function) in `storage/sqlite.py:1204`
- **_execute_sync** (function) in `storage/sqlite.py:1215`
- **_execute_many_sync** (function) in `storage/sqlite.py:1226`
- **_fetchone_sync** (function) in `storage/sqlite.py:1238`
- **_fetchall_sync** (function) in `storage/sqlite.py:1250`
- **_measure_disk_usage** (function) in `tests/test_performance.py:105`
- **_add_healing_info_to_response** (function) in `tools/manage_docs.py:296`
- **_resolve_emojis** (function) in `tools/query_entries.py:1987`
- **_clean_list** (function) in `tools/query_entries.py:2010`
- **_normalise_boundary** (function) in `tools/query_entries.py:2014`
- **_heal_rotate_log_parameters** (function) in `tools/rotate_log.py:141`
- **_add_healing_info_to_rotate_response** (function) in `tools/rotate_log.py:350`
- **_merge_single_rotation_response** (function) in `tools/rotate_log.py:1892`
- **_overlaps** (function) in `tools/set_project.py:789`
- **_get_priority_sort_key** (function) in `utils/entry_limit.py:129`
- **_create_new_log** (function) in `utils/files.py:771`

