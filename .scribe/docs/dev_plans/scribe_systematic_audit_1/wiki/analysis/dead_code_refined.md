# Dead Code Analysis - Refined Report

**Date**: 2026-01-05
**Agent**: ResearchAgent-Phase4-DeadCode
**Status**: Filtered for false positives

## Executive Summary

- **Total Files Analyzed**: 209
- **True Unused Imports**: 238
- **False Positive Imports**: 197 (annotations, type hints)
- **Production Unreferenced**: 81
- **Test Unreferenced**: 949 (expected - pytest fixtures/helpers)

## True Unused Imports (Action Required)

These imports should be removed as they serve no purpose:

### .scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/dead_code_analyzer.py

- Line 8: `os` - **SAFE TO REMOVE**

### .scribe/temp_circular_dep_analyzer.py

- Line 7: `os` - **SAFE TO REMOVE**

### config/__init__.py

- Line 5: `settings` - **SAFE TO REMOVE**

### config/repo_config.py

- Line 10: `os` - **SAFE TO REMOVE**

### db/__init__.py

- Line 3: `ops` - **SAFE TO REMOVE**
- Line 3: `pool` - **SAFE TO REMOVE**

### demo/demo_global_scribe.py

- Line 99: `RepoConfig` - **SAFE TO REMOVE**

### doc_management/__init__.py

- Line 3: `apply_doc_change` - **SAFE TO REMOVE**

### doc_management/diff_visualizer.py

- Line 14: `ChangeRecord` - **SAFE TO REMOVE**
- Line 14: `DiffResult` - **SAFE TO REMOVE**

### doc_management/file_watcher.py

- Line 22: `utcnow` - **SAFE TO REMOVE**

### doc_management/integrity_verifier.py

- Line 7: `json` - **SAFE TO REMOVE**

### doc_management/manager.py

- Line 7: `difflib` - **SAFE TO REMOVE**
- Line 27: `ToolValidator` - **SAFE TO REMOVE**

### doc_management/sync_manager.py

- Line 7: `json` - **SAFE TO REMOVE**

### plugins/registry.py

- Line 16: `importlib.util` - **SAFE TO REMOVE**
- Line 23: `Type` - **SAFE TO REMOVE**
- Line 27: `settings` - **SAFE TO REMOVE**

### plugins/vector_indexer.py

- Line 40: `settings` - **SAFE TO REMOVE**
- Line 42: `VectorIndexRecord` - **SAFE TO REMOVE**
- Line 836: `concurrent.futures` - **SAFE TO REMOVE**

### scripts/migrate_database.py

- Line 13: `json` - **SAFE TO REMOVE**

### scripts/scribe_cli.py

- Line 9: `asyncio` - **SAFE TO REMOVE**
- Line 17: `RepoConfig` - **SAFE TO REMOVE**
- Line 17: `reload_repo_config` - **SAFE TO REMOVE**
- Line 18: `get_plugin_security_info` - **SAFE TO REMOVE**
- Line 19: `check_permission` - **SAFE TO REMOVE**

### security/sandbox.py

- Line 10: `os` - **SAFE TO REMOVE**

### server.py

- Line 458: `tools` - **SAFE TO REMOVE**
- Line 510: `load_active_project` - **SAFE TO REMOVE**

### shared/__init__.py

- Line 3: `LoggingContext` - **SAFE TO REMOVE**
- Line 3: `ProjectResolutionError` - **SAFE TO REMOVE**
- Line 3: `clean_list` - **SAFE TO REMOVE**
- Line 3: `compose_log_line` - **SAFE TO REMOVE**
- Line 3: `default_status_emoji` - **SAFE TO REMOVE**
- Line 3: `ensure_metadata_requirements` - **SAFE TO REMOVE**
- Line 3: `normalize_metadata` - **SAFE TO REMOVE**
- Line 3: `normalize_meta_filters` - **SAFE TO REMOVE**
- Line 3: `resolve_log_definition` - **SAFE TO REMOVE**
- Line 3: `resolve_logging_context` - **SAFE TO REMOVE**
- Line 15: `LoggingToolMixin` - **SAFE TO REMOVE**
- Line 16: `ProjectInfo` - **SAFE TO REMOVE**
- Line 16: `ProjectRegistry` - **SAFE TO REMOVE**

### state/__init__.py

- Line 3: `StateManager` - **SAFE TO REMOVE**

### state/agent_identity.py

- Line 5: `hashlib` - **SAFE TO REMOVE**
- Line 6: `json` - **SAFE TO REMOVE**

### state/agent_manager.py

- Line 10: `ConflictError` - **SAFE TO REMOVE**

### storage/sqlite.py

- Line 16: `MilestoneRecord` - **SAFE TO REMOVE**
- Line 16: `ChecklistRecord` - **SAFE TO REMOVE**
- Line 16: `DocumentSectionRecord` - **SAFE TO REMOVE**
- Line 16: `CustomTemplateRecord` - **SAFE TO REMOVE**
- Line 16: `DocumentChangeRecord` - **SAFE TO REMOVE**
- Line 16: `SyncStatusRecord` - **SAFE TO REMOVE**

### template_engine/__init__.py

- Line 3: `Jinja2TemplateEngine` - **SAFE TO REMOVE**
- Line 3: `TemplateEngineError` - **SAFE TO REMOVE**
- Line 3: `TemplateNotFoundError` - **SAFE TO REMOVE**
- Line 3: `TemplateValidationError` - **SAFE TO REMOVE**
- Line 3: `TemplateRenderError` - **SAFE TO REMOVE**
- Line 3: `DEFAULT_VARIABLES` - **SAFE TO REMOVE**
- Line 3: `RESTRICTED_BUILTINS` - **SAFE TO REMOVE**

### template_engine/engine.py

- Line 12: `Template` - **SAFE TO REMOVE**

### tests/debug_vector_processing.py

- Line 20: `faiss` - **SAFE TO REMOVE**
- Line 21: `np` - **SAFE TO REMOVE**
- Line 22: `SentenceTransformer` - **SAFE TO REMOVE**

### tests/test_append_entry_config.py

- Line 6: `json` - **SAFE TO REMOVE**

### tests/test_append_entry_priority.py

- Line 18: `LogPriority` - **SAFE TO REMOVE**
- Line 18: `LogCategory` - **SAFE TO REMOVE**

### tests/test_base_logging_tool.py

- Line 5: `asyncio` - **SAFE TO REMOVE**

### tests/test_bulletproof_corrector_enhancements.py

- Line 9: `json` - **SAFE TO REMOVE**

### tests/test_db_activation.py

- Line 16: `asyncio` - **SAFE TO REMOVE**
- Line 17: `time` - **SAFE TO REMOVE**
- Line 18: `json` - **SAFE TO REMOVE**
- Line 19: `Path` - **SAFE TO REMOVE**
- Line 29: `validate_session_isolation` - **SAFE TO REMOVE**

### tests/test_doc_management.py

- Line 8: `timedelta` - **SAFE TO REMOVE**

### tests/test_doc_management_basic.py

- Line 7: `asyncio` - **SAFE TO REMOVE**
- Line 9: `time` - **SAFE TO REMOVE**

### tests/test_dual_parameter_integration.py

- Line 11: `json` - **SAFE TO REMOVE**
- Line 22: `server` - **SAFE TO REMOVE**

### tests/test_dual_parameter_logic.py

- Line 7: `asyncio` - **SAFE TO REMOVE**

### tests/test_dual_parameter_support.py

- Line 19: `append_entry` - **SAFE TO REMOVE**

### tests/test_enhanced_append_entry.py

- Line 33: `Settings` - **SAFE TO REMOVE**

### tests/test_estimator.py

- Line 11: `math` - **SAFE TO REMOVE**

### tests/test_exception_healer.py

- Line 19: `BulletproofParameterCorrector` - **SAFE TO REMOVE**

### tests/test_failure_priority.py

- Line 15: `asyncio` - **SAFE TO REMOVE**
- Line 26: `reminders` - **SAFE TO REMOVE**

### tests/test_function_decomposition_integration.py

- Line 22: `RotateLogConfig` - **SAFE TO REMOVE**

### tests/test_get_project_integration.py

- Line 14: `get_project` - **SAFE TO REMOVE**

### tests/test_health_check.py

- Line 18: `scribe_mcp.storage.sqlite` - **SAFE TO REMOVE**
- Line 19: `scribe_mcp.state.manager` - **SAFE TO REMOVE**
- Line 20: `scribe_mcp.state.agent_manager` - **SAFE TO REMOVE**
- Line 21: `scribe_mcp.tools.health_check` - **SAFE TO REMOVE**
- Line 22: `scribe_mcp.server` - **SAFE TO REMOVE**

### tests/test_jinja2_engine.py

- Line 10: `TemplateEngineError` - **SAFE TO REMOVE**

### tests/test_list_projects_integration.py

- Line 11: `json` - **SAFE TO REMOVE**

### tests/test_mcp_tools_enhancements.py

- Line 8: `tempfile` - **SAFE TO REMOVE**
- Line 9: `json` - **SAFE TO REMOVE**
- Line 18: `apply_doc_change` - **SAFE TO REMOVE**
- Line 27: `ToolValidator` - **SAFE TO REMOVE**
- Line 27: `BulletproofParameterCorrector` - **SAFE TO REMOVE**

### tests/test_migration_priority_columns.py

- Line 11: `json` - **SAFE TO REMOVE**
- Line 18: `ProjectRecord` - **SAFE TO REMOVE**

### tests/test_parameter_validator.py

- Line 10: `json` - **SAFE TO REMOVE**

### tests/test_performance.py

- Line 32: `append_entry` - **SAFE TO REMOVE**
- Line 35: `slugify_project_name` - **SAFE TO REMOVE**

### tests/test_project_registry.py

- Line 9: `pytest` - **SAFE TO REMOVE**

### tests/test_query_entries_config.py

- Line 15: `VALID_DOCUMENT_TYPES` - **SAFE TO REMOVE**

### tests/test_read_file_readable.py

- Line 5: `Path` - **SAFE TO REMOVE**

### tests/test_reminder_hash_session.py

- Line 3: `pytest` - **SAFE TO REMOVE**
- Line 6: `settings` - **SAFE TO REMOVE**

### tests/test_reminder_storage.py

- Line 16: `timedelta` - **SAFE TO REMOVE**

### tests/test_rotation_utils.py

- Line 10: `json` - **SAFE TO REMOVE**
- Line 14: `time` - **SAFE TO REMOVE**
- Line 29: `store_rotation_metadata` - **SAFE TO REMOVE**
- Line 29: `get_rotation_history` - **SAFE TO REMOVE**
- Line 29: `verify_rotation_integrity` - **SAFE TO REMOVE**
- Line 29: `get_audit_summary` - **SAFE TO REMOVE**
- Line 38: `get_project_state` - **SAFE TO REMOVE**
- Line 38: `update_project_state` - **SAFE TO REMOVE**
- Line 38: `get_next_sequence_number` - **SAFE TO REMOVE**
- Line 38: `generate_rotation_id` - **SAFE TO REMOVE**

### tests/test_sandbox_bypass.py

- Line 4: `os` - **SAFE TO REMOVE**

### tests/test_tool_logger.py

- Line 12: `mock_open` - **SAFE TO REMOVE**

### tests/test_vector_complete_integration.py

- Line 33: `initialize_plugins` - **SAFE TO REMOVE**
- Line 33: `get_plugin_registry` - **SAFE TO REMOVE**
- Line 37: `VectorIndexRecord` - **SAFE TO REMOVE**
- Line 37: `VectorShardMetadata` - **SAFE TO REMOVE**

### tests/test_vector_entry_ids.py

- Line 3: `pytest` - **SAFE TO REMOVE**
- Line 4: `tempfile` - **SAFE TO REMOVE**
- Line 5: `Path` - **SAFE TO REMOVE**

### tests/test_vector_performance.py

- Line 318: `threading` - **SAFE TO REMOVE**
- Line 319: `concurrent.futures` - **SAFE TO REMOVE**

### tools/__init__.py

- Line 3: `append_entry` - **SAFE TO REMOVE**
- Line 4: `delete_project` - **SAFE TO REMOVE**
- Line 5: `generate_doc_templates` - **SAFE TO REMOVE**
- Line 6: `get_project` - **SAFE TO REMOVE**
- Line 7: `list_projects` - **SAFE TO REMOVE**
- Line 8: `query_entries` - **SAFE TO REMOVE**
- Line 9: `read_recent` - **SAFE TO REMOVE**
- Line 10: `read_file` - **SAFE TO REMOVE**
- Line 11: `sentinel_tools` - **SAFE TO REMOVE**
- Line 12: `rotate_log` - **SAFE TO REMOVE**
- Line 13: `set_project` - **SAFE TO REMOVE**
- Line 14: `manage_docs` - **SAFE TO REMOVE**
- Line 15: `vector_search` - **SAFE TO REMOVE**
- Line 16: `manage_docs_validation` - **SAFE TO REMOVE**
- Line 17: `doctor` - **SAFE TO REMOVE**

### tools/append_entry.py

- Line 22: `ensure_agent_session` - **SAFE TO REMOVE**
- Line 22: `validate_agent_session` - **SAFE TO REMOVE**
- Line 30: `ensure_metadata_requirements` - **SAFE TO REMOVE**
- Line 39: `LogPriority` - **SAFE TO REMOVE**
- Line 39: `LogCategory` - **SAFE TO REMOVE**
- Line 53: `_manage_docs_validation` - **SAFE TO REMOVE**

### tools/base/__init__.py

- Line 3: `BaseTool` - **SAFE TO REMOVE**
- Line 4: `ToolResult` - **SAFE TO REMOVE**
- Line 5: `normalize_dict_param` - **SAFE TO REMOVE**
- Line 5: `normalize_list_param` - **SAFE TO REMOVE**
- Line 6: `ToolMetadata` - **SAFE TO REMOVE**
- Line 6: `ToolParameter` - **SAFE TO REMOVE**
- Line 6: `ToolExample` - **SAFE TO REMOVE**
- Line 6: `get_tool_metadata` - **SAFE TO REMOVE**
- Line 6: `list_tools_by_category` - **SAFE TO REMOVE**
- Line 6: `list_deprecated_tools` - **SAFE TO REMOVE**
- Line 6: `get_tool_examples` - **SAFE TO REMOVE**
- Line 6: `validate_tool_parameters` - **SAFE TO REMOVE**
- Line 6: `generate_tool_help` - **SAFE TO REMOVE**
- Line 6: `TOOL_METADATA` - **SAFE TO REMOVE**

### tools/base/base_tool.py

- Line 7: `Awaitable` - **SAFE TO REMOVE**
- Line 7: `Callable` - **SAFE TO REMOVE**

### tools/config/append_entry_config.py

- Line 17: `ConfigManager` - **SAFE TO REMOVE**
- Line 17: `resolve_fallback_chain` - **SAFE TO REMOVE**
- Line 18: `ErrorHandler` - **SAFE TO REMOVE**

### tools/config/query_entries_config.py

- Line 10: `re` - **SAFE TO REMOVE**
- Line 16: `ErrorHandler` - **SAFE TO REMOVE**
- Line 16: `HealingErrorHandler` - **SAFE TO REMOVE**

### tools/config/rotate_log_config.py

- Line 18: `json` - **SAFE TO REMOVE**

### tools/delete_project.py

- Line 12: `ensure_agent_session` - **SAFE TO REMOVE**
- Line 12: `validate_agent_session` - **SAFE TO REMOVE**
- Line 16: `slugify_project_name` - **SAFE TO REMOVE**

### tools/health_check.py

- Line 57: `asyncio` - **SAFE TO REMOVE**

### tools/manage_docs.py

- Line 17: `SECTION_MARKER` - **SAFE TO REMOVE**

### tools/query_entries.py

- Line 17: `validate_enum_value` - **SAFE TO REMOVE**
- Line 17: `validate_range` - **SAFE TO REMOVE**
- Line 25: `ErrorHandler` - **SAFE TO REMOVE**
- Line 26: `ToolValidator` - **SAFE TO REMOVE**
- Line 28: `ProjectResolutionError` - **SAFE TO REMOVE**

### tools/read_file.py

- Line 5: `asyncio` - **SAFE TO REMOVE**

### tools/read_recent.py

- Line 18: `resolve_logging_context` - **SAFE TO REMOVE**

### tools/rotate_log.py

- Line 8: `uuid` - **SAFE TO REMOVE**
- Line 12: `Sequence` - **SAFE TO REMOVE**
- Line 21: `BulkProcessor` - **SAFE TO REMOVE**
- Line 23: `shared_resolve_log_definition` - **SAFE TO REMOVE**
- Line 23: `resolve_logging_context` - **SAFE TO REMOVE**
- Line 36: `normalize_dict_param` - **SAFE TO REMOVE**
- Line 37: `ToolValidator` - **SAFE TO REMOVE**
- Line 46: `get_audit_manager` - **SAFE TO REMOVE**
- Line 49: `compute_file_hash` - **SAFE TO REMOVE**
- Line 54: `get_state_manager` - **SAFE TO REMOVE**
- Line 61: `reminders` - **SAFE TO REMOVE**

### tools/set_project.py

- Line 367: `uuid` - **SAFE TO REMOVE**

### tools/vector_search.py

- Line 13: `get_agent_project_data` - **SAFE TO REMOVE**

### utils/__init__.py

- Line 3: `append_line` - **SAFE TO REMOVE**
- Line 3: `ensure_parent` - **SAFE TO REMOVE**
- Line 3: `read_tail` - **SAFE TO REMOVE**
- Line 3: `rotate_file` - **SAFE TO REMOVE**
- Line 4: `format_utc` - **SAFE TO REMOVE**
- Line 4: `utcnow` - **SAFE TO REMOVE**
- Line 5: `ResponseFormatter` - **SAFE TO REMOVE**
- Line 5: `default_formatter` - **SAFE TO REMOVE**
- Line 5: `create_pagination_info` - **SAFE TO REMOVE**
- Line 5: `PaginationInfo` - **SAFE TO REMOVE**
- Line 6: `TokenEstimator` - **SAFE TO REMOVE**
- Line 6: `TokenMetrics` - **SAFE TO REMOVE**
- Line 6: `TokenBudget` - **SAFE TO REMOVE**
- Line 6: `token_estimator` - **SAFE TO REMOVE**
- Line 7: `get_response_formatter` - **SAFE TO REMOVE**
- Line 7: `get_token_estimator` - **SAFE TO REMOVE**
- Line 7: `get_configured_response_formatter` - **SAFE TO REMOVE**
- Line 7: `get_configured_token_estimator` - **SAFE TO REMOVE**
- Line 7: `configured_formatter` - **SAFE TO REMOVE**
- Line 7: `configured_token_estimator` - **SAFE TO REMOVE**
- Line 7: `reset_configured_instances` - **SAFE TO REMOVE**

### utils/audit.py

- Line 9: `os` - **SAFE TO REMOVE**
- Line 10: `uuid` - **SAFE TO REMOVE**

### utils/bulk_processor.py

- Line 13: `re` - **SAFE TO REMOVE**

### utils/estimator.py

- Line 23: `NamedTuple` - **SAFE TO REMOVE**

### utils/files.py

- Line 10: `tempfile` - **SAFE TO REMOVE**
- Line 16: `Iterable` - **SAFE TO REMOVE**

### utils/integrity.py

- Line 12: `json` - **SAFE TO REMOVE**

### utils/optimization.py

- Line 11: `_default_formatter` - **SAFE TO REMOVE**
- Line 12: `_default_token_estimator` - **SAFE TO REMOVE**

### utils/reminder_engine.py

- Line 15: `os` - **SAFE TO REMOVE**
- Line 16: `time` - **SAFE TO REMOVE**

### utils/reminder_monitoring.py

- Line 25: `timedelta` - **SAFE TO REMOVE**

### utils/reminder_validator.py

- Line 9: `json` - **SAFE TO REMOVE**
- Line 10: `Path` - **SAFE TO REMOVE**
- Line 13: `ReminderInstance` - **SAFE TO REMOVE**

### utils/response.py

- Line 10: `dataclass` - **SAFE TO REMOVE**

## False Positive Imports (Intentional)

These imports appear unused but serve legitimate purposes:

- **`annotations` imports**: 101 files (PEP 563 - required for postponed type hint evaluation)
- **Type hint imports**: ~96 (Dict, List, Any, etc. - used in type annotations)

## Production Code - Unreferenced Definitions

### Likely False Positives (Do Not Remove)

- **_log_async_error** (function) in `plugins/vector_indexer.py:212` - *Private helper - may be called internally*
- **_start_background_loop** (function) in `plugins/vector_indexer.py:381` - *Private helper - may be called internally*
- **_build_config** (function) in `reminders.py:292` - *Private helper - may be called internally*
- **_apply_tone** (function) in `reminders.py:350` - *Private helper - may be called internally*
- **_make_reminder** (function) in `reminders.py:356` - *Private helper - may be called internally*
- **_iter_doc_files** (function) in `scripts/reindex_vector.py:95` - *Private helper - may be called internally*
- **_write_json** (function) in `state/manager.py:231` - *Private helper - may be called internally*
- **_write_json_atomic** (function) in `state/manager.py:239` - *Private helper - may be called internally*
- **_migrate_document_sections_sync** (function) in `storage/sqlite.py:1110` - *Private helper - may be called internally*
- **_ensure_column_sync** (function) in `storage/sqlite.py:1164` - *Private helper - may be called internally*
- **_migrate_agent_sessions_schema_sync** (function) in `storage/sqlite.py:1179` - *Private helper - may be called internally*
- **_ensure_index_sync** (function) in `storage/sqlite.py:1204` - *Private helper - may be called internally*
- **_execute_sync** (function) in `storage/sqlite.py:1215` - *Private helper - may be called internally*
- **_execute_many_sync** (function) in `storage/sqlite.py:1226` - *Private helper - may be called internally*
- **_fetchone_sync** (function) in `storage/sqlite.py:1238` - *Private helper - may be called internally*
- **_fetchall_sync** (function) in `storage/sqlite.py:1250` - *Private helper - may be called internally*
- **_add_healing_info_to_response** (function) in `tools/manage_docs.py:296` - *Private helper - may be called internally*
- **_resolve_emojis** (function) in `tools/query_entries.py:1987` - *Private helper - may be called internally*
- **_clean_list** (function) in `tools/query_entries.py:2010` - *Private helper - may be called internally*
- **_normalise_boundary** (function) in `tools/query_entries.py:2014` - *Private helper - may be called internally*
- **_heal_rotate_log_parameters** (function) in `tools/rotate_log.py:141` - *Private helper - may be called internally*
- **_add_healing_info_to_rotate_response** (function) in `tools/rotate_log.py:350` - *Private helper - may be called internally*
- **_merge_single_rotation_response** (function) in `tools/rotate_log.py:1892` - *Private helper - may be called internally*
- **_overlaps** (function) in `tools/set_project.py:789` - *Private helper - may be called internally*
- **_get_priority_sort_key** (function) in `utils/entry_limit.py:129` - *Private helper - may be called internally*
- **_create_new_log** (function) in `utils/files.py:771` - *Private helper - may be called internally*

### Needs Investigation (Verify Before Removal)

- **reload_repo_config** (function) in `config/repo_config.py:380` - *Potentially unused*
- **on_any_event** (function) in `doc_management/file_watcher.py:114` - *Potentially unused*
- **DefaultDict** (class) in `doc_management/manager.py:2418` - *Potentially unused*
- **register_metric_callback** (function) in `doc_management/performance_monitor.py:245` - *Potentially unused*
- **get_plugin_security_info** (function) in `plugins/registry.py:511` - *Potentially unused*
- **parse_entry** (function) in `plugins/registry.py:105` - *Potentially unused*
- **execute_hook_pre_append** (function) in `plugins/registry.py:435` - *Potentially unused*
- **execute_hook_post_append** (function) in `plugins/registry.py:445` - *Potentially unused*
- **execute_hook_pre_rotate** (function) in `plugins/registry.py:453` - *Potentially unused*
- **execute_hook_post_rotate** (function) in `plugins/registry.py:461` - *Potentially unused*
- **get_reminder_engine** (function) in `reminders.py:380` - *Potentially unused*
- **reload_reminders** (function) in `reminders.py:395` - *Potentially unused*
- **get_safe_relative_path** (function) in `security/sandbox.py:126` - *Potentially unused*
- **cleanup_repository** (function) in `security/sandbox.py:319` - *Potentially unused*
- **run_stdio** (function) in `server.py:52` - *Potentially unused*
- **set_status** (function) in `shared/project_registry.py:170` - *Potentially unused*
- **with_project** (function) in `state/manager.py:49` - *Potentially unused*
- **MilestoneRecord** (class) in `storage/models.py:48` - *Potentially unused*
- **ChecklistRecord** (class) in `storage/models.py:78` - *Potentially unused*
- **DocumentSectionRecord** (class) in `storage/models.py:111` - *Potentially unused*
- **CustomTemplateRecord** (class) in `storage/models.py:124` - *Potentially unused*
- **DocumentChangeRecord** (class) in `storage/models.py:136` - *Potentially unused*
- **SyncStatusRecord** (class) in `storage/models.py:149` - *Potentially unused*
- **AgentReportCardRecord** (class) in `storage/models.py:163` - *Potentially unused*
- **VectorIndexRecord** (class) in `storage/models.py:179` - *Potentially unused*
- **record_tool_call_sync** (function) in `storage/sqlite.py:2032` - *Potentially unused*
- **BaseTool** (class) in `tools/base/base_tool.py:13` - *Potentially unused*
- **safe_get_nested** (function) in `tools/base/parameter_normalizer.py:119` - *Potentially unused*
- **list_tools_by_category** (function) in `tools/base/tool_metadata.py:396` - *Potentially unused*
- **list_deprecated_tools** (function) in `tools/base/tool_metadata.py:401` - *Potentially unused*
- **get_tool_examples** (function) in `tools/base/tool_metadata.py:406` - *Potentially unused*
- **validate_tool_parameters** (function) in `tools/base/tool_metadata.py:412` - *Potentially unused*
- **generate_tool_help** (function) in `tools/base/tool_metadata.py:437` - *Potentially unused*
- **parameter_error** (function) in `tools/base/tool_result.py:80` - *Potentially unused*
- **heal_and_validate** (function) in `tools/config/query_entries_config.py:137` - *Potentially unused*
- **copy_with** (function) in `tools/config/rotate_log_config.py:415` - *Potentially unused*
- **load_project_config_by_path** (function) in `tools/project_utils.py:120` - *Potentially unused*
- **load_config_project** (function) in `tools/project_utils.py:127` - *Potentially unused*
- **RotationTarget** (class) in `tools/rotate_log.py:365` - *Potentially unused*
- **parse_json_items** (function) in `utils/bulk_processor.py:327` - *Potentially unused*
- **validate_bulk_items** (function) in `utils/bulk_processor.py:348` - *Potentially unused*
- **prepare_parallel_bulk_items** (function) in `utils/bulk_processor.py:383` - *Potentially unused*
- **create_processing_chunks** (function) in `utils/bulk_processor.py:444` - *Potentially unused*
- **optimize_for_performance** (function) in `utils/bulk_processor.py:506` - *Potentially unused*
- **apply_token_budget_to_response** (function) in `utils/config_manager.py:674` - *Potentially unused*
- **suggest_pagination** (function) in `utils/context_safety.py:181` - *Potentially unused*
- **heal_and_execute** (function) in `utils/error_handler.py:471` - *Potentially unused*
- **create_healing_response** (function) in `utils/error_handler.py:557` - *Potentially unused*
- **auto_heal_parameter_type** (function) in `utils/estimator.py:722` - *Potentially unused*
- **reset_configured_instances** (function) in `utils/optimization.py:102` - *Potentially unused*
- **get_optimization_suggestion** (function) in `utils/tokens.py:222` - *Potentially unused*
- **get_usage_stats** (function) in `utils/tokens.py:251` - *Potentially unused*
- **get_tokenizer_info** (function) in `utils/tokens.py:297` - *Potentially unused*
- **save_metrics** (function) in `utils/tokens.py:321` - *Potentially unused*
- **load_metrics** (function) in `utils/tokens.py:342` - *Potentially unused*

## Test Code - Unreferenced Definitions

**Total**: 949 test functions/classes

**Analysis**: Test files contain many helper functions and fixtures that pytest discovers dynamically.
These are NOT dead code - they're invoked by pytest's test discovery mechanism.

Top test files with 'unreferenced' functions:

- `tests/test_response_formatter_readable.py`: 68 functions (pytest test functions/fixtures)
- `tests/test_rotate_log_config.py`: 47 functions (pytest test functions/fixtures)
- `tests/test_log_enums.py`: 46 functions (pytest test functions/fixtures)
- `tests/test_exception_healer.py`: 46 functions (pytest test functions/fixtures)
- `tests/test_parameter_validator.py`: 42 functions (pytest test functions/fixtures)
- `tests/test_config_manager.py`: 41 functions (pytest test functions/fixtures)
- `tests/test_query_entries_config.py`: 40 functions (pytest test functions/fixtures)
- `tests/test_bulletproof_fallback_manager.py`: 39 functions (pytest test functions/fixtures)
- `tests/test_error_handler.py`: 38 functions (pytest test functions/fixtures)
- `tests/test_append_entry_config.py`: 37 functions (pytest test functions/fixtures)

## Recommendations

### Immediate Actions

1. Remove 238 true unused imports (safe, automated cleanup)
2. Review 55 production unreferenced definitions
3. Validate private helper functions are actually called (grep verification)

### No Action Required

1. 101 `annotations` imports (PEP 563 requirement)
2. 949 test function 'unreferenced' findings (pytest discovery)
3. 26 __init__ exports and private helpers

