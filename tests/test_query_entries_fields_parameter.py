from scribe_mcp.tools.query_entries import _validate_search_parameters


def test_validate_search_parameters_accepts_fields_list():
    config, info = _validate_search_parameters(
        project=None,
        start=None,
        end=None,
        message="x",
        message_mode="substring",
        case_sensitive=False,
        emoji=None,
        status=None,
        agents=None,
        meta_filters=None,
        limit=50,
        page=1,
        page_size=5,
        compact=True,
        fields=["ts", "emoji"],
        include_metadata=False,
        search_scope="project",
        document_types=None,
        include_outdated=True,
        verify_code_references=False,
        time_range=None,
        relevance_threshold=0.0,
        max_results=None,
        config=None,
    )

    assert config.fields == ["ts", "emoji"]
    assert info["healing_applied"] in (True, False)


def test_correct_intelligent_parameter_search_scope_returns_string():
    from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector

    value = BulletproofParameterCorrector.correct_intelligent_parameter(
        "search_scope", ["project"], {"tool_name": "query_entries", "operation_type": "query_entries"}
    )
    assert isinstance(value, str)

