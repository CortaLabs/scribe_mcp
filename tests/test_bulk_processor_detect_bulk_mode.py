from scribe_mcp.utils.bulk_processor import BulkProcessor


def test_detect_bulk_mode_true_for_items_json():
    assert BulkProcessor.detect_bulk_mode(message="x", items="[]") is True


def test_detect_bulk_mode_true_for_items_list():
    assert BulkProcessor.detect_bulk_mode(message="x", items_list=[{"message": "a"}]) is True


def test_detect_bulk_mode_true_for_multiline_message():
    assert BulkProcessor.detect_bulk_mode(message="a\nb") is True


def test_detect_bulk_mode_false_for_long_single_line_message():
    long_message = "x" * 10_000
    assert BulkProcessor.detect_bulk_mode(message=long_message) is False


def test_detect_bulk_mode_false_for_pipe_characters():
    assert BulkProcessor.detect_bulk_mode(message="a | b | c") is False

