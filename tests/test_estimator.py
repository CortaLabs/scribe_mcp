#!/usr/bin/env python3
"""
Comprehensive tests for estimation utilities.

Tests all estimation algorithms extracted from tools to ensure
identical behavior and proper edge case handling.
"""

import pytest
import tempfile
import math
import hashlib
import io
import os
import json
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any

from scribe_mcp.utils.estimator import (
    EntryCountEstimate,
    PaginationInfo,
    ChunkCalculation,
    FileSizeEstimator,
    ThresholdEstimator,
    PaginationCalculator,
    BulkProcessingCalculator,
    TokenEstimator,
    EstimatorUtilities
)
import scribe_mcp.utils.tokens as token_utils
from scribe_mcp.utils.tokens import TokenEstimator as MetricsTokenEstimator, TokenMetrics

pytestmark = pytest.mark.usefixtures("test_agent")


@pytest.mark.core
@pytest.mark.regression
def test_packaged_exact_count_never_enters_upstream_io(monkeypatch):
    import tiktoken
    import tiktoken.model
    import tiktoken.registry

    def forbidden(*args, **kwargs):
        pytest.fail("subject entered upstream tokenizer registry/cache/network")

    monkeypatch.setattr(tiktoken.registry, "get_encoding", forbidden)
    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)
    monkeypatch.setattr(tiktoken.model, "get_encoding", forbidden)
    estimator = MetricsTokenEstimator()
    assert estimator.estimate_tokens("alpha beta gamma", exact=False) == 4
    assert estimator.estimate_tokens("alpha beta gamma") == 3
    assert isinstance(estimator.encoder, tiktoken.Encoding)


_NATIVE_CORPUS = [
    "", "alpha beta gamma", "  \t  \n\n", "line1\r\nline2\r\n", "!?:;-- ()[]{}",
    "def f(x):\n    return x ** 2  # café\n", "café 漢字 العربية русский हिन्दी",
    "e\u0301 a\u0308", "😀👩🏽‍💻🇨🇦", "long text: 漢😀\r\n" * 256, "a\ud800b\udfff",
]
_RECIPES = ("gpt2", "r50k_base", "p50k_base", "p50k_edit", "cl100k_base", "o200k_base", "o200k_harmony")
_SPECIAL_CORPUS = [
    "lead <|endofprompt|> middle <|reserved_200018|> tail",
    "<|endoftext|>A<|reserved_200018|>B<|endofprompt|>",
]


def _deny_upstream(monkeypatch):
    """Count attempted upstream registry, loader, HTTP and socket use by subject."""
    import requests
    import tiktoken
    import tiktoken.load
    import tiktoken.model
    import tiktoken.registry
    import tiktoken_ext.openai_public as recipes

    seen = []

    def forbidden(*args, **kwargs):
        seen.append("forbidden upstream I/O")
        raise AssertionError("subject entered upstream tokenizer registry/cache/network")

    for module, names in [
        (tiktoken, ["get_encoding", "encoding_for_model"]),
        (tiktoken.model, ["get_encoding"]),
        (tiktoken.registry, ["get_encoding"]),
        (tiktoken.load, ["read_file", "read_file_cached", "load_tiktoken_bpe", "data_gym_to_mergeable_bpe_ranks"]),
        (recipes, list(_RECIPES)),
        (requests, ["get"]), (requests.sessions.Session, ["request"]),
        (socket.socket, ["connect", "connect_ex"]), (socket, ["create_connection"]),
    ]:
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    return tiktoken, seen


def _run_native_oracle(directory):
    """Separate unmodified upstream process; cache exclusively from approved bytes."""
    directory.mkdir()
    resources = Path(token_utils.__file__).parent / "token_data"
    fixed = {
        "vocab.bpe": ("gpt-2/encodings/main/vocab.bpe", "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5"),
        "encoder.json": ("gpt-2/encodings/main/encoder.json", "196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783"),
        "r50k_base.tiktoken": ("encodings/r50k_base.tiktoken", "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930"),
        "p50k_base.tiktoken": ("encodings/p50k_base.tiktoken", "94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069"),
        "cl100k_base.tiktoken": ("encodings/cl100k_base.tiktoken", "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"),
        "o200k_base.tiktoken": ("encodings/o200k_base.tiktoken", "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"),
    }
    for filename, (suffix, digest) in fixed.items():
        data = (resources / filename).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
        url = "https://openaipublic.blob.core.windows.net/" + suffix
        (directory / hashlib.sha1(url.encode()).hexdigest()).write_bytes(data)
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    script = r'''
import json, socket, sys
def denied(*a, **k):
    raise AssertionError("oracle attempted network")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
import requests
requests.sessions.Session.request = denied
import tiktoken, tiktoken.model
assert tiktoken.__version__ == "0.14.0"
corpus, names, special_corpus = json.load(sys.stdin)
result = {"origin": tiktoken.__file__, "version": tiktoken.__version__, "encodings": {}}
for name in names:
    enc = tiktoken.get_encoding(name)
    ids = [enc.encode(text) for text in corpus]
    specials = dict(enc._special_tokens)
    result["encodings"][name] = {
        "ids": ids, "decoded": [enc.decode_bytes(row).hex() for row in ids],
        "specials": specials, "special_ids": {s: enc.encode(s, allowed_special={s}, disallowed_special=()) for s in specials},
        "literal_specials": enc.encode("|".join(specials), disallowed_special=()),
        "special_text_ids": [enc.encode(text, allowed_special="all") for text in special_corpus],
        "pattern": enc._pat_str, "n_vocab": enc.n_vocab,
    }
models = dict(tiktoken.model.MODEL_TO_ENCODING)
models.update({p + "FAKE-20261102": tiktoken.encoding_name_for_model(p + "FAKE-20261102") for p in tiktoken.model.MODEL_PREFIX_TO_ENCODING})
result["models"] = models
result["concrete"] = tiktoken.model.MODEL_TO_ENCODING
result["prefixes"] = tiktoken.model.MODEL_PREFIX_TO_ENCODING
print(json.dumps(result))
'''
    child_env = dict(os.environ, TIKTOKEN_CACHE_DIR=str(directory), DATA_GYM_CACHE_DIR=str(directory), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", script], input=json.dumps([_NATIVE_CORPUS, _RECIPES, _SPECIAL_CORPUS]), text=True, capture_output=True, env=child_env, timeout=60)
    assert result.returncode == 0, result.stderr
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def native_oracle(tmp_path_factory):
    return _run_native_oracle(tmp_path_factory.mktemp("independent-native") / "cache")


@pytest.fixture
def isolated_tiktoken(monkeypatch):
    tiktoken, seen = _deny_upstream(monkeypatch)
    monkeypatch.setattr(token_utils, "TIKTOKEN_AVAILABLE", None)
    yield tiktoken
    assert seen == []


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("name", _RECIPES)
def test_seven_native_recipes_match_independent_upstream(name, isolated_tiktoken, native_oracle):
    model = {"gpt2": "gpt2", "r50k_base": "davinci", "p50k_base": "text-davinci-003", "p50k_edit": "text-davinci-edit-001", "cl100k_base": "gpt-4", "o200k_base": "gpt-4o", "o200k_harmony": "gpt-oss-20b"}[name]
    estimator = MetricsTokenEstimator(model=model)
    encoder = estimator._get_encoder()
    expected = native_oracle["encodings"][name]
    assert isinstance(encoder, isolated_tiktoken.Encoding)
    assert encoder.name == name
    assert encoder._pat_str == expected["pattern"]
    assert encoder.n_vocab == expected["n_vocab"]
    if name == "o200k_harmony":
        assert encoder.n_vocab == 201088
    assert encoder._special_tokens == expected["specials"]
    for text, ids, decoded in zip(_NATIVE_CORPUS, expected["ids"], expected["decoded"]):
        assert encoder.encode(text) == ids
        assert len(encoder.encode(text)) == len(ids)
        assert encoder.decode_bytes(ids).hex() == decoded
        if not any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            assert encoder.decode(ids) == text
    for special, ids in expected["special_ids"].items():
        assert encoder.encode(special, allowed_special={special}, disallowed_special=()) == ids
        with pytest.raises(ValueError, match="disallowed special token"):
            estimator.estimate_tokens(special)
    assert encoder.encode("|".join(expected["specials"]), disallowed_special=()) == expected["literal_specials"]
    for text, ids in zip(_SPECIAL_CORPUS, expected["special_text_ids"]):
        assert encoder.encode(text, allowed_special="all") == ids
        assert len(encoder.encode(text, allowed_special="all")) == len(ids)
        if any(special in text for special in expected["specials"]):
            with pytest.raises(ValueError, match="disallowed special token"):
                estimator.estimate_tokens(text)
        else:
            assert estimator.estimate_tokens(text) == len(ids)
    assert isinstance(encoder.__getstate__(), dict)


@pytest.mark.core
@pytest.mark.regression
def test_complete_native_model_and_prefix_resolution(isolated_tiktoken, native_oracle):
    import tiktoken.model
    assert tiktoken.model.MODEL_TO_ENCODING == native_oracle["concrete"]
    assert tiktoken.model.MODEL_PREFIX_TO_ENCODING == native_oracle["prefixes"]
    models = dict(native_oracle["models"], **{
        "unknown-model": "cl100k_base", "cl100k_base": "cl100k_base",
        "gpt-4o-FAKE": "o200k_base", "ft:gpt-4o:custom": "o200k_base",
        "ft:gpt-4:custom": "cl100k_base",
    })
    for model, encoding in models.items():
        estimator = MetricsTokenEstimator(model=model)
        expected = native_oracle["encodings"][encoding]["ids"][1]
        assert estimator.estimate_tokens(_NATIVE_CORPUS[1]) == len(expected), model
        assert isinstance(estimator.encoder, isolated_tiktoken.Encoding)
        assert estimator.encoder.name == encoding, model
        assert estimator.encoder.encode(_NATIVE_CORPUS[1]) == expected, model
        with pytest.raises(ValueError, match="disallowed special token"):
            estimator.estimate_tokens("<|endoftext|>")
    assert MetricsTokenEstimator().model == "gpt-4"


@pytest.mark.core
@pytest.mark.regression
def test_mixed_native_instances_and_serialization(isolated_tiktoken, native_oracle):
    estimators = [MetricsTokenEstimator(model=m) for m in ["gpt-4", "gpt-4", "gpt-4o", "gpt2"]]
    def count(index):
        return estimators[index % len(estimators)].estimate_tokens(_NATIVE_CORPUS[1])
    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(pool.map(count, range(16)))
    assert len({id(e.encoder) for e in estimators}) == len(estimators)
    for i, result in enumerate(counts):
        encoder = estimators[i % 4].encoder
        assert result == len(native_oracle["encodings"][encoder.name]["ids"][1])
    for payload in ["café", {"text": "漢😀"}, ["é", "😀"], 1234, None]:
        serialized = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload)
        cheap = payload if isinstance(payload, str) else json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
        assert estimators[0].estimate_tokens(payload) == len(estimators[0].encoder.encode(serialized))
        assert estimators[0].estimate_tokens(payload, exact=False) == len(cheap) // 4


def _resource_streams(monkeypatch, replacements):
    from importlib import resources
    real_files = resources.files
    calls = []
    class Resource:
        def joinpath(self, *parts):
            assert parts[:2] == ("utils", "token_data")
            self.filename = parts[2]
            return self
        def open(self, mode):
            assert mode == "rb"
            filename = self.filename
            if filename not in replacements:
                return real_files("scribe_mcp").joinpath("utils", "token_data", filename).open(mode)
            data = replacements[filename]
            if data is None:
                raise FileNotFoundError(filename)
            class Stream(io.BytesIO):
                def read(self, size=-1):
                    calls.append((filename, size))
                    return super().read(size)
            return Stream(data)
    monkeypatch.setattr(resources, "files", lambda package: Resource() if package == "scribe_mcp" else pytest.fail(package))
    return calls


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("filename", ["vocab.bpe", "encoder.json", "r50k_base.tiktoken", "p50k_base.tiktoken", "cl100k_base.tiktoken", "o200k_base.tiktoken"])
@pytest.mark.parametrize("damage", ["missing", "flip", "truncate", "append", "crlf"])
def test_resource_integrity_precedes_all_parsing(monkeypatch, isolated_tiktoken, filename, damage):
    data = (Path(token_utils.__file__).parent / "token_data" / filename).read_bytes()
    changed = {"missing": None, "flip": bytes([data[0] ^ 1]) + data[1:], "truncate": data[:-1], "append": data + b"x", "crlf": data.replace(b"\n", b"\r\n") if b"\n" in data else data + b"\r\n"}[damage]
    calls = _resource_streams(monkeypatch, {filename: changed})
    entered = []
    def forbidden(*args, **kwargs):
        entered.append(True)
        pytest.fail("integrity failure entered parser/native constructor")
    monkeypatch.setattr(token_utils, "_parse_token_ranks", forbidden)
    monkeypatch.setattr(token_utils, "_parse_gpt2_ranks", forbidden)
    monkeypatch.setattr(isolated_tiktoken, "Encoding", forbidden)
    name = "gpt2" if filename in {"vocab.bpe", "encoder.json"} else filename.removesuffix(".tiktoken")
    with pytest.raises(FileNotFoundError if damage == "missing" else ValueError, match=filename):
        token_utils._load_packaged_encoder(name, isolated_tiktoken)
    assert entered == []
    assert calls == ([] if damage == "missing" else [(filename, len(data) + 1)])


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("name", ["unknown", "cl100k_base/escape", "https://host/data", ""])
def test_closed_recipe_and_version_precede_io(monkeypatch, isolated_tiktoken, name):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid recipe/version attempted resource I/O")
    monkeypatch.setattr(token_utils, "_read_token_resource", forbidden)
    with pytest.raises(ValueError, match="unsupported packaged encoding"):
        token_utils._load_packaged_encoder(name, isolated_tiktoken)
    monkeypatch.setattr(isolated_tiktoken, "__version__", "0.14.1")
    with pytest.raises(RuntimeError, match="0.14.0"):
        token_utils._load_packaged_encoder("cl100k_base", isolated_tiktoken)
    with pytest.raises(RuntimeError, match="0.14.0"):
        MetricsTokenEstimator().estimate_tokens("text")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("data", [
    b"! 0\n", b"YQ== +5\n", b"YQ== 1_000\n", "YQ== ٥\n".encode(),
    b"YQ== 0 extra\n", b" 0\n", b"YQ== -1\n", b"YQ== 0\nYQ== 1\n",
    b"YQ== 0\nYg== 0\n", b"", b"\n", b"YQ== 0\n", b"YQ==\t0\n",
])
def test_malformed_ranks_never_reach_native(monkeypatch, isolated_tiktoken, data):
    monkeypatch.setattr(token_utils, "_read_token_resource", lambda *a: data)
    native_calls = []
    monkeypatch.setattr(isolated_tiktoken, "Encoding", lambda **kw: native_calls.append(kw) or pytest.fail("invalid data reached native"))
    estimator = MetricsTokenEstimator()
    for _ in range(2):
        with pytest.raises(ValueError, match="cl100k_base.tiktoken"):
            estimator.estimate_tokens("text")
        assert estimator.encoder is None and not estimator._encoder_initialized
    assert native_calls == []


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("error", [ImportError, KeyError])
def test_post_import_adapter_errors_recover(monkeypatch, isolated_tiktoken, error):
    original = token_utils._load_packaged_encoder
    calls = []
    def transient(name, module):
        calls.append(name)
        if len(calls) <= 2:
            raise error("adapter failure")
        return original(name, module)
    monkeypatch.setattr(token_utils, "_load_packaged_encoder", transient)
    estimator = MetricsTokenEstimator()
    for _ in range(2):
        with pytest.raises(error, match="adapter failure"):
            estimator.estimate_tokens(_NATIVE_CORPUS[1])
        assert not estimator._encoder_initialized
    assert estimator.estimate_tokens(_NATIVE_CORPUS[1]) == 3
    assert isinstance(estimator.encoder, isolated_tiktoken.Encoding)
    assert len(calls) == 3


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("damage", ["utf8", "header", "fields", "character", "duplicate_merge", "json_utf8", "json_array", "duplicate_key", "bool", "negative", "duplicate_rank", "json_character", "consistency"])
def test_gpt2_parser_controls_never_enter_native(monkeypatch, isolated_tiktoken, damage):
    root = Path(token_utils.__file__).parent / "token_data"
    vocab = (root / "vocab.bpe").read_bytes()
    encoder = (root / "encoder.json").read_bytes()
    if damage == "utf8":
        vocab = b"\xff"
    elif damage == "header":
        vocab = vocab.replace(b"#version: 0.2", b"#version: 0.1", 1)
    elif damage in {"fields", "character", "duplicate_merge"}:
        lines = vocab.decode().split("\n")
        if damage == "fields":
            lines[1] = "a b c"
        elif damage == "character":
            lines[1] = "☃ a"
        else:
            lines[2] = lines[1]
        vocab = "\n".join(lines).encode()
    elif damage == "json_utf8":
        encoder = b"\xff"
    elif damage == "json_array":
        encoder = b"[]"
    elif damage == "duplicate_key":
        encoder = b'{"a": 0, "a": 1}'
    else:
        obj = json.loads(encoder)
        first, second = list(obj)[:2]
        if damage == "bool":
            obj[first] = True
        elif damage == "negative":
            obj[first] = -1
        elif damage == "duplicate_rank":
            obj[second] = obj[first]
        elif damage == "json_character":
            obj["☃"] = obj.pop(first)
        else:
            obj[first], obj[second] = obj[second], obj[first]
        encoder = json.dumps(obj).encode()
    replacements = {"vocab.bpe": vocab, "encoder.json": encoder}
    monkeypatch.setattr(token_utils, "_read_token_resource", lambda filename, name: replacements[filename])
    native_calls = []
    monkeypatch.setattr(isolated_tiktoken, "Encoding", lambda **kw: native_calls.append(kw) or pytest.fail("invalid GPT2 reached native"))
    estimator = MetricsTokenEstimator(model="gpt2")
    for _ in range(2):
        with pytest.raises(ValueError, match="gpt2: (vocab.bpe|encoder.json)"):
            estimator.estimate_tokens("text")
        assert estimator.encoder is None and not estimator._encoder_initialized
    assert native_calls == []


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("damage", ["special_rank_collision", "duplicate_special_id", "negative_special", "bool_special", "vocab_size", "vocab_max", "duplicate_rank"])
def test_recipe_checks_precede_native_constructor(monkeypatch, isolated_tiktoken, damage):
    original_recipe = token_utils._token_recipe
    def recipe(name):
        result = original_recipe(name)
        if damage == "special_rank_collision":
            result["special_tokens"][0] = ("<|endoftext|>", 0)
        elif damage == "duplicate_special_id":
            result["special_tokens"].append(("duplicate", 50256))
        elif damage in {"negative_special", "bool_special"}:
            result["special_tokens"].append(("bad", -1 if damage == "negative_special" else True))
        elif damage == "vocab_size":
            result["explicit_n_vocab"] += 1
        elif damage == "vocab_max":
            result["special_tokens"][0] = ("<|endoftext|>", 60000)
        return result
    monkeypatch.setattr(token_utils, "_token_recipe", recipe)
    if damage == "duplicate_rank":
        monkeypatch.setattr(token_utils, "_parse_token_ranks", lambda *a: {b"a": 0, b"b": 0})
    native_calls = []
    monkeypatch.setattr(isolated_tiktoken, "Encoding", lambda **kw: native_calls.append(kw) or pytest.fail("invalid recipe reached native"))
    with pytest.raises(ValueError):
        token_utils._load_packaged_encoder("r50k_base", isolated_tiktoken)
    assert native_calls == []


@pytest.mark.core
@pytest.mark.regression
def test_optimized_python_keeps_vocabulary_and_gpt2_consistency_checks():
    script = r'''
import json
from pathlib import Path
from scribe_mcp.utils import tokens as t
recipe = t._token_recipe("r50k_base")
try:
    t._validate_token_recipe(recipe, {b"a": 0})
except ValueError as e:
    if "vocabulary mismatch" not in str(e): raise
else:
    raise RuntimeError("optimized Python dropped vocabulary check")
root = Path(t.__file__).parent / "token_data"
obj = json.loads((root / "encoder.json").read_bytes())
a, b = list(obj)[:2]
obj[a], obj[b] = obj[b], obj[a]
try:
    t._parse_gpt2_ranks((root / "vocab.bpe").read_bytes(), json.dumps(obj).encode())
except ValueError as e:
    if "consistency mismatch" not in str(e): raise
else:
    raise RuntimeError("optimized Python dropped GPT2 consistency check")
print("optimized validation: 2 rejected")
'''
    result = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "optimized validation: 2 rejected"


@pytest.mark.core
@pytest.mark.regression
def test_subject_no_cache_env_network_or_metrics_effects(monkeypatch, tmp_path, isolated_tiktoken):
    import tiktoken.registry
    env_before = dict(os.environ)
    registry_before = dict(tiktoken.registry.ENCODINGS)
    opened = []
    original_open = io.open
    def observe_open(file, mode="r", *args, **kwargs):
        path = os.fspath(file) if not isinstance(file, int) else str(file)
        opened.append((path, mode))
        return original_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(io, "open", observe_open)
    estimator = MetricsTokenEstimator()
    estimator.metrics_dir = tmp_path / "metrics"
    estimator.metrics_file = estimator.metrics_dir / "usage.json"
    original_read = token_utils._read_token_resource
    calls = []
    def transient(filename, name):
        calls.append(filename)
        if len(calls) == 1:
            raise FileNotFoundError("test-local missing resource")
        return original_read(filename, name)
    monkeypatch.setattr(token_utils, "_read_token_resource", transient)
    with pytest.raises(FileNotFoundError):
        estimator.estimate_tokens("alpha beta gamma")
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(estimator.estimate_tokens, ["alpha beta gamma"] * 16)) == [3] * 16
    assert dict(os.environ) == env_before
    assert tiktoken.registry.ENCODINGS == registry_before
    assert not list(tmp_path.iterdir())
    assert opened and all(path.endswith("/utils/token_data/cl100k_base.tiktoken") and mode == "rb" for path, mode in opened)
    assert estimator.metrics_history == []


@pytest.mark.core
@pytest.mark.regression
def test_exact_resource_uses_one_buffer_and_length_before_hash(monkeypatch, isolated_tiktoken):
    filename = "cl100k_base.tiktoken"
    data = (Path(token_utils.__file__).parent / "token_data" / filename).read_bytes()
    hashed, parsed = [], []
    original_hash = hashlib.sha256
    original_parse = token_utils._parse_token_ranks
    def observe_hash(buffer):
        hashed.append(id(buffer))
        return original_hash(buffer)
    def observe_parse(buffer, *args):
        parsed.append(id(buffer))
        return original_parse(buffer, *args)
    with pytest.MonkeyPatch.context() as patch:
        calls = _resource_streams(patch, {filename: data})
        patch.setattr(hashlib, "sha256", observe_hash)
        patch.setattr(token_utils, "_parse_token_ranks", observe_parse)
        encoder = token_utils._load_packaged_encoder("cl100k_base", isolated_tiktoken)
        assert len(encoder.encode("alpha beta gamma")) == 3
        assert calls == [(filename, len(data) + 1)]
    assert hashed == parsed and len(hashed) == 1
    for damaged in [data[:-1], data + b"x", data + b"x" * 10000]:
        with pytest.MonkeyPatch.context() as patch:
            calls = _resource_streams(patch, {filename: damaged})
            patch.setattr(hashlib, "sha256", lambda *a: pytest.fail("length mismatch reached hash"))
            with pytest.raises(ValueError, match="length mismatch"):
                token_utils._load_packaged_encoder("cl100k_base", isolated_tiktoken)
            assert calls == [(filename, len(data) + 1)]


@pytest.mark.core
@pytest.mark.regression
def test_rank_parser_preserves_upstream_blank_line_semantics():
    filename = "r50k_base.tiktoken"
    data = (Path(token_utils.__file__).parent / "token_data" / filename).read_bytes()
    assert token_utils._parse_token_ranks(b"\n" + data + b"\n", filename, "r50k_base") == token_utils._parse_token_ranks(data, filename, "r50k_base")


@pytest.mark.core
@pytest.mark.regression
def test_genuine_dependency_unavailable_fallback_is_cached():
    script = r'''
import importlib.abc, sys
class Unavailable(importlib.abc.MetaPathFinder):
    calls = 0
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "tiktoken":
            self.calls += 1
            raise ModuleNotFoundError("tiktoken intentionally unavailable")
finder = Unavailable()
sys.meta_path.insert(0, finder)
from scribe_mcp.utils.tokens import TokenEstimator
estimator = TokenEstimator()
if "tiktoken" in sys.modules or finder.calls:
    raise RuntimeError("constructor imported tokenizer")
if estimator.estimate_tokens("alpha beta gamma") != 4:
    raise RuntimeError("genuine missing dependency lost fallback")
if estimator.estimate_tokens("alpha beta gamma") != 4 or finder.calls != 1:
    raise RuntimeError("missing import fallback was not cached")
if estimator.encoder is not None or not estimator._encoder_initialized:
    raise RuntimeError("missing dependency published invalid state")
print("genuine import unavailable: cached")
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "genuine import unavailable: cached"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("name", _RECIPES)
def test_qualified_special_aliases_are_exact_for_each_recipe(name):
    pairs = token_utils._token_recipe(name)["special_tokens"]
    assert len({key for key, value in pairs}) == len(pairs)
    grouped = {}
    for key, value in pairs:
        grouped.setdefault(value, set()).add(key)
    aliases = {value: keys for value, keys in grouped.items() if len(keys) > 1}
    expected = {200018: {"<|endofprompt|>", "<|reserved_200018|>"}} if name == "o200k_harmony" else {}
    assert aliases == expected
    assert token_utils._ALLOWED_SPECIAL_ID_ALIASES.get(name, {}) == expected
    if name == "o200k_harmony":
        assert len(pairs) == 1091 and len(grouped) == 1090
        assert set(grouped) == set(range(199998, 201088))
        assert "explicit_n_vocab" not in token_utils._token_recipe(name)
        assert pairs.count(("<|endoftext|>", 199999)) == 1


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("damage", [
    "third_alias", "pair_in_base", "missing_reserved", "missing_endofprompt",
    "another_duplicate_id", "duplicate_string", "rank_collision", "moved_endofprompt",
    "missing_nonalias", "extra_unique", "shifted_range",
])
def test_qualified_harmony_alias_negative_controls_before_native(monkeypatch, isolated_tiktoken, damage):
    original_recipe = token_utils._token_recipe
    original_parse = token_utils._parse_token_ranks
    def recipe(name):
        result = original_recipe(name)
        pairs = result["special_tokens"]
        if damage == "third_alias":
            pairs.append(("<|third_alias|>", 200018))
        elif damage == "pair_in_base":
            pairs.append(("<|reserved_200018|>", 200018))
        elif damage == "missing_reserved":
            pairs.remove(("<|reserved_200018|>", 200018))
        elif damage == "missing_endofprompt":
            pairs.remove(("<|endofprompt|>", 200018))
        elif damage == "another_duplicate_id":
            pairs[pairs.index(("<|reserved_200019|>", 200019))] = ("<|reserved_200019|>", 200017)
        elif damage == "duplicate_string":
            # Repeating the identical pair would disappear if converted to dict.
            pairs.append(("<|endoftext|>", 199999))
        elif damage == "moved_endofprompt":
            pairs[pairs.index(("<|endofprompt|>", 200018))] = ("<|endofprompt|>", 210000)
        elif damage == "missing_nonalias":
            pairs.remove(("<|reserved_200019|>", 200019))
        elif damage == "extra_unique":
            pairs.append(("<|extra_unique|>", 210000))
        elif damage == "shifted_range":
            pairs[pairs.index(("<|reserved_200019|>", 200019))] = ("<|reserved_200019|>", 210000)
        return result
    def ranks(*args):
        result = original_parse(*args)
        if damage == "rank_collision":
            result[next(iter(result))] = 200018
        return result
    monkeypatch.setattr(token_utils, "_token_recipe", recipe)
    monkeypatch.setattr(token_utils, "_parse_token_ranks", ranks)
    native_calls = []
    monkeypatch.setattr(isolated_tiktoken, "Encoding", lambda **kw: native_calls.append(kw) or pytest.fail("invalid alias map reached native"))
    estimator = MetricsTokenEstimator(model="gpt-4o" if damage == "pair_in_base" else "gpt-oss-20b")
    for _ in range(2):
        with pytest.raises(ValueError, match="o200k_(harmony|base): o200k_base.tiktoken"):
            estimator.estimate_tokens("alpha beta gamma")
        assert estimator.encoder is None
        assert not estimator._encoder_initialized
        assert estimator.estimate_tokens("alpha beta gamma", exact=False) == 4
    assert native_calls == []


@pytest.mark.core
@pytest.mark.regression
def test_optimized_python_keeps_exact_harmony_alias_and_spelling_validation():
    script = r'''
from scribe_mcp.utils import tokens as t
for damage in ("duplicate_string", "missing_alias", "rank_collision"):
    recipe = t._token_recipe("o200k_harmony")
    ranks = {b"a": 0}
    if damage == "duplicate_string":
        recipe["special_tokens"].append(("<|endoftext|>", 199999))
    elif damage == "missing_alias":
        recipe["special_tokens"].remove(("<|endofprompt|>", 200018))
    else:
        ranks = {b"a": 200018}
    try:
        t._validate_token_recipe(recipe, ranks)
    except ValueError:
        pass
    else:
        raise RuntimeError("optimized Python dropped harmony validation: " + damage)
print("optimized harmony validation: 3 rejected")
'''
    result = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "optimized harmony validation: 3 rejected"


class TestEntryCountEstimate:
    """Test EntryCountEstimate dataclass."""

    def test_entry_count_estimate_creation(self):
        """Test EntryCountEstimate creation and attributes."""
        estimate = EntryCountEstimate(
            count=100,
            approximate=True,
            method="test",
            details={"test": "data"}
        )

        assert estimate.count == 100
        assert estimate.approximate is True
        assert estimate.method == "test"
        assert estimate.details["test"] == "data"


class TestPaginationInfo:
    """Test PaginationInfo dataclass."""

    def test_pagination_info_creation(self):
        """Test PaginationInfo creation and to_dict method."""
        info = PaginationInfo(
            page=2,
            page_size=50,
            total_count=150,
            has_next=True,
            has_prev=True
        )

        assert info.page == 2
        assert info.page_size == 50
        assert info.total_count == 150
        assert info.has_next is True
        assert info.has_prev is True

        result_dict = info.to_dict()
        expected = {
            "page": 2,
            "page_size": 50,
            "total_count": 150,
            "has_next": True,
            "has_prev": True
        }
        assert result_dict == expected


class TestChunkCalculation:
    """Test ChunkCalculation dataclass."""

    def test_chunk_calculation_creation(self):
        """Test ChunkCalculation creation."""
        calc = ChunkCalculation(
            total_items=150,
            chunk_size=50,
            total_chunks=3,
            remaining_items=0
        )

        assert calc.total_items == 150
        assert calc.chunk_size == 50
        assert calc.total_chunks == 3
        assert calc.remaining_items == 0


class TestFileSizeEstimator:
    """Test FileSizeEstimator class."""

    def test_estimator_initialization(self):
        """Test FileSizeEstimator initialization with custom values."""
        estimator = FileSizeEstimator(
            default_bytes_per_line=100.0,
            min_bytes_per_line=20.0,
            max_bytes_per_line=600.0,
            tail_sample_bytes=2_000_000
        )

        assert estimator.default_bytes_per_line == 100.0
        assert estimator.min_bytes_per_line == 20.0
        assert estimator.max_bytes_per_line == 600.0
        assert estimator.tail_sample_bytes == 2_000_000

    def test_clamp_bytes_per_line(self):
        """Test bytes-per-line clamping within bounds."""
        estimator = FileSizeEstimator()

        # Below minimum
        result = estimator.clamp_bytes_per_line(10.0)
        assert result == estimator.min_bytes_per_line

        # Above maximum
        result = estimator.clamp_bytes_per_line(1000.0)
        assert result == estimator.max_bytes_per_line

        # Within bounds
        result = estimator.clamp_bytes_per_line(100.0)
        assert result == 100.0

    def test_estimate_entry_count_basic(self):
        """Test basic entry count estimation."""
        estimator = FileSizeEstimator()

        # Zero size
        result = estimator.estimate_entry_count_basic(0)
        assert result.count == 0
        assert result.approximate is False
        assert result.method == "empty"

        # Negative size
        result = estimator.estimate_entry_count_basic(-100)
        assert result.count == 0
        assert result.method == "empty"

        # Normal size with default bytes-per-line
        result = estimator.estimate_entry_count_basic(8000)  # 8000 bytes / 80 = 100 entries
        assert result.count == 100
        assert result.approximate is True
        assert result.method == "basic"

        # Custom bytes-per-line
        result = estimator.estimate_entry_count_basic(8000, bytes_per_line=100.0)
        assert result.count == 80
        assert result.details["bytes_per_line"] == 100.0

    def test_estimate_entry_count_with_cache(self):
        """Test entry count estimation with cache support."""
        estimator = FileSizeEstimator()

        # No cache
        result = estimator.estimate_entry_count_with_cache(8000)
        assert result.count == 100
        assert result.method == "ema"
        assert result.details["source"] == "initial_estimate"

        # Valid cache hit
        cache_stats = {
            "size_bytes": 8000,
            "mtime_ns": 12345,
            "line_count": 100,
            "source": "test_cache"
        }
        result = estimator.estimate_entry_count_with_cache(8000, cache_stats, 12345)
        assert result.count == 100
        assert result.approximate is False
        assert result.method == "cache"
        assert result.details["cache_hit"] is True

        # Cache miss due to size change
        result = estimator.estimate_entry_count_with_cache(9000, cache_stats, 12345)
        assert result.method == "ema"
        assert result.details.get("cache_hit") is not True

        # Cache with EMA
        cache_stats_ema = {
            "ema_bytes_per_line": 90.0
        }
        result = estimator.estimate_entry_count_with_cache(9000, cache_stats_ema)
        assert result.count == 100  # 9000 / 90 = 100
        assert result.details["ema_bytes_per_line"] == 90.0

    def test_refine_estimate_with_sampling(self):
        """Test estimate refinement using tail sampling."""
        estimator = FileSizeEstimator()

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            # Write 100 lines with approximately 80 bytes each
            for i in range(100):
                f.write(f"Test log entry {i:03d} with some content to make it longer\n")
            temp_path = Path(f.name)

        try:
            # Non-approximate estimate should be returned unchanged
            exact_estimate = EntryCountEstimate(100, False, "exact", {})
            result = estimator.refine_estimate_with_sampling(temp_path, 8000, exact_estimate)
            assert result == exact_estimate

            # Approximate estimate should be refined
            approx_estimate = EntryCountEstimate(50, True, "basic", {})
            result = estimator.refine_estimate_with_sampling(temp_path, temp_path.stat().st_size, approx_estimate)

            assert result is not None
            assert result.method in ["tail", "full_tail", "basic+tail"]
            assert result.count > 0
            assert "tail_sample_bytes" in result.details
            assert "refined_bytes_per_line" in result.details

        finally:
            temp_path.unlink()

        # Non-existent file should return None
        result = estimator.refine_estimate_with_sampling(
            Path("/non/existent/file.log"), 8000, approx_estimate
        )
        assert result is None

    def test_compute_bytes_per_line(self):
        """Test bytes-per-line computation."""
        estimator = FileSizeEstimator()

        # Valid inputs
        result = estimator.compute_bytes_per_line(8000, 100)
        assert result == 80.0

        # Zero values
        result = estimator.compute_bytes_per_line(0, 100)
        assert result is None

        result = estimator.compute_bytes_per_line(8000, 0)
        assert result is None

        # None values
        result = estimator.compute_bytes_per_line(None, 100)
        assert result is None

        result = estimator.compute_bytes_per_line(8000, None)
        assert result is None

        # Value outside bounds should be clamped
        result = estimator.compute_bytes_per_line(100000, 100)  # 1000 BPL, above max
        assert result == estimator.max_bytes_per_line


class TestThresholdEstimator:
    """Test ThresholdEstimator class."""

    def test_compute_estimation_band(self):
        """Test estimation band calculation."""
        estimator = ThresholdEstimator()

        # No threshold
        result = estimator.compute_estimation_band(None)
        assert result is None

        # Normal threshold
        result = estimator.compute_estimation_band(1000)
        expected = max(int(1000 * estimator.ESTIMATION_BAND_RATIO), estimator.ESTIMATION_BAND_MIN)
        assert result == expected

        # Small threshold
        result = estimator.compute_estimation_band(100)
        assert result >= estimator.ESTIMATION_BAND_MIN

    def test_classify_estimate(self):
        """Test estimate classification."""
        estimator = ThresholdEstimator()

        # No band
        result = estimator.classify_estimate(150, 100, None)
        assert result == "above_threshold"

        result = estimator.classify_estimate(50, 100, None)
        assert result == "below_threshold"

        # With band
        band = 50
        result = estimator.classify_estimate(150, 100, band)
        assert result == "well_above_threshold"

        result = estimator.classify_estimate(80, 100, band)
        assert result == "near_threshold"

        result = estimator.classify_estimate(30, 100, band)
        assert result == "well_below_threshold"


class TestPaginationCalculator:
    """Test PaginationCalculator class."""

    def test_create_pagination_info(self):
        """Test pagination info creation."""
        calc = PaginationCalculator()

        # First page
        result = calc.create_pagination_info(1, 50, 150)
        assert result.page == 1
        assert result.page_size == 50
        assert result.total_count == 150
        assert result.has_next is True
        assert result.has_prev is False

        # Middle page
        result = calc.create_pagination_info(2, 50, 150)
        assert result.has_next is True
        assert result.has_prev is True

        # Last page
        result = calc.create_pagination_info(3, 50, 150)
        assert result.has_next is False
        assert result.has_prev is True

        # Single page
        result = calc.create_pagination_info(1, 50, 30)
        assert result.has_next is False
        assert result.has_prev is False

    def test_calculate_pagination_indices(self):
        """Test pagination index calculation."""
        calc = PaginationCalculator()

        # First page
        start, end = calc.calculate_pagination_indices(1, 50, 150)
        assert start == 0
        assert end == 50

        # Middle page
        start, end = calc.calculate_pagination_indices(2, 50, 150)
        assert start == 50
        assert end == 100

        # Last page (partial)
        start, end = calc.calculate_pagination_indices(3, 50, 120)
        assert start == 100
        assert end == 120

    def test_calculate_total_pages(self):
        """Test total pages calculation."""
        calc = PaginationCalculator()

        # Exact division
        result = calc.calculate_total_pages(100, 50)
        assert result == 2

        # Partial last page
        result = calc.calculate_total_pages(120, 50)
        assert result == 3

        # Zero items
        result = calc.calculate_total_pages(0, 50)
        assert result == 1

        # Single item
        result = calc.calculate_total_pages(1, 50)
        assert result == 1


class TestBulkProcessingCalculator:
    """Test BulkProcessingCalculator class."""

    def test_calculate_chunks(self):
        """Test chunk calculation."""
        calc = BulkProcessingCalculator()

        # Exact division
        result = calc.calculate_chunks(100, 50)
        assert result.total_items == 100
        assert result.chunk_size == 50
        assert result.total_chunks == 2
        assert result.remaining_items == 0

        # Partial last chunk
        result = calc.calculate_chunks(120, 50)
        assert result.total_chunks == 3
        assert result.remaining_items == 20

        # Single item chunks
        result = calc.calculate_chunks(5, 10)
        assert result.total_chunks == 1
        assert result.remaining_items == 5

        # Zero chunk size
        result = calc.calculate_chunks(100, 0)
        assert result.total_chunks == 1
        assert result.remaining_items == 100

    def test_calculate_optimal_chunk_size(self):
        """Test optimal chunk size calculation."""
        calc = BulkProcessingCalculator()

        # Small total items
        result = calc.calculate_optimal_chunk_size(5)
        assert result == 5

        # Normal case
        result = calc.calculate_optimal_chunk_size(100)
        assert result == 25  # 100 / 4 target chunks

        # Large total items
        result = calc.calculate_optimal_chunk_size(1000)
        assert result == 100  # hits max_chunk_size limit

        # Custom parameters
        result = calc.calculate_optimal_chunk_size(
            200, target_chunks=5, min_chunk_size=20, max_chunk_size=60
        )
        assert result == 40  # 200 / 5 = 40


class TestApproximateTokenEstimator:
    """Test the lightweight estimator used by response formatting."""

    def test_estimate_tokens_string(self):
        """Test token estimation for strings."""
        estimator = TokenEstimator()

        # Short string
        result = estimator.estimate_tokens("Hello world")
        assert result > 0
        assert isinstance(result, int)

        # Empty string
        result = estimator.estimate_tokens("")
        assert result == 0

        # Long string
        long_text = "word " * 100
        result = estimator.estimate_tokens(long_text)
        assert result > 0

    def test_estimate_tokens_dict_list(self):
        """Test token estimation for dictionaries and lists."""
        estimator = TokenEstimator()

        # Dictionary
        data = {"key1": "value1", "key2": "value2"}
        result = estimator.estimate_tokens(data)
        assert result > 0

        # List
        data = ["item1", "item2", "item3"]
        result = estimator.estimate_tokens(data)
        assert result > 0

        # Complex structure
        data = {"nested": {"list": [1, 2, 3]}}
        result = estimator.estimate_tokens(data)
        assert result > 0

    def test_estimate_response_tokens(self):
        """Test token estimation for response data."""
        estimator = TokenEstimator()

        entries = [
            {"message": "First message", "timestamp": "2023-01-01"},
            {"message": "Second message", "timestamp": "2023-01-02"}
        ]

        # With metadata
        result = estimator.estimate_response_tokens(entries, include_metadata=True)
        assert result > 0

        # Without metadata
        result = estimator.estimate_response_tokens(entries, include_metadata=False)
        assert result > 0

        # Empty list
        result = estimator.estimate_response_tokens([])
        assert result == 0


@pytest.mark.core
@pytest.mark.regression
class TestTokenEstimator:
    """Permanent guards for lazy token metrics estimation and utility exports."""

    def test_construction_and_cheap_estimation_are_encoder_and_filesystem_free(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("HOME", str(tmp_path))
        import_calls = []

        def fail_import(name):
            import_calls.append(name)
            raise AssertionError("cheap estimation must not import tiktoken")

        monkeypatch.setattr(token_utils.importlib, "import_module", fail_import)

        estimator = MetricsTokenEstimator()
        assert estimator.encoder is None
        assert estimator.estimate_tokens_cheap("abcdefgh") == 2
        assert estimator.estimate_tokens({"key": "value"}, exact=False) == (
            len(token_utils.json.dumps({"key": "value"})) // 4
        )
        assert estimator.estimate_tokens([1, 2, 3], exact=False) == (
            len(token_utils.json.dumps([1, 2, 3])) // 4
        )
        assert import_calls == []
        assert not (tmp_path / ".scribe_metrics").exists()

    def test_exact_estimation_initializes_one_reusable_encoder(self, monkeypatch, isolated_tiktoken):
        monkeypatch.setattr(token_utils, "TIKTOKEN_AVAILABLE", None)
        calls = {"import": 0, "model": 0}
        original = isolated_tiktoken.encoding_name_for_model
        def encoding_name_for_model(model):
            calls["model"] += 1
            assert model == "gpt-4"
            return original(model)
        monkeypatch.setattr(isolated_tiktoken, "encoding_name_for_model", encoding_name_for_model)
        original_import = token_utils.importlib.import_module

        def import_module(name):
            if name != "tiktoken":
                return original_import(name)
            calls["import"] += 1
            assert name == "tiktoken"
            return isolated_tiktoken

        monkeypatch.setattr(token_utils.importlib, "import_module", import_module)
        estimator = MetricsTokenEstimator()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(estimator.estimate_tokens, ["one two"] * 16))

        assert results == [2] * 16
        encoder = estimator.encoder
        assert isinstance(encoder, isolated_tiktoken.Encoding)
        assert estimator.estimate_tokens("three four") == 2
        assert estimator.encoder is encoder
        assert calls == {"import": 1, "model": 1}

    @pytest.mark.regression
    @pytest.mark.parametrize("model", ["gpt-4", "unknown-model"])
    @pytest.mark.parametrize("failure", [FileNotFoundError, ValueError, ImportError, KeyError])
    def test_exact_initialization_failure_never_becomes_cheap_success(
        self, monkeypatch, isolated_tiktoken, model, failure
    ):
        attempts = []
        def fail_resource(filename, encoding_name):
            attempts.append(filename)
            raise failure("token data unavailable")
        monkeypatch.setattr(token_utils, "_read_token_resource", fail_resource)
        estimator = MetricsTokenEstimator(model=model)
        for _ in range(2):
            with pytest.raises(failure, match="token data unavailable"):
                estimator.estimate_tokens("alpha beta gamma", exact=True)

        assert len(attempts) == 2
        assert estimator.encoder is None
        assert not estimator._encoder_initialized
        assert estimator.estimate_tokens("alpha beta gamma", exact=False) == 4

    @pytest.mark.regression
    @pytest.mark.parametrize("model", ["gpt-4", "unknown-model"])
    def test_exact_initialization_recovers_with_genuine_packaged_encoder(
        self, monkeypatch, isolated_tiktoken, model
    ):
        tiktoken = isolated_tiktoken
        attempts = []
        original = token_utils._read_token_resource
        def transient_read(filename, encoding_name):
            attempts.append(filename)
            if len(attempts) == 1:
                raise FileNotFoundError("transient token data failure")
            return original(filename, encoding_name)
        monkeypatch.setattr(token_utils, "_read_token_resource", transient_read)
        estimator = MetricsTokenEstimator(model=model)
        text = "alpha beta gamma"
        with pytest.raises(FileNotFoundError, match="transient token data failure"):
            estimator.estimate_tokens(text, exact=True)

        # Competing recovery calls must all use the same real encoder.
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(estimator.estimate_tokens, [text] * 16))
        encoder = estimator.encoder
        assert isinstance(encoder, tiktoken.Encoding)
        assert encoder.name == "cl100k_base"
        assert results == [len(encoder.encode(text))] * 16
        assert results[0] != estimator.estimate_tokens(text, exact=False)
        payload = {"text": "café 漢字 😀"}
        assert estimator.estimate_tokens(payload, exact=True) == len(
            encoder.encode(token_utils.json.dumps(payload, ensure_ascii=False))
        )
        assert estimator.encoder is encoder
        assert attempts == ["cl100k_base.tiktoken"] * 2

    def test_exact_estimation_preserves_unknown_model_and_import_fallbacks(
        self, monkeypatch, isolated_tiktoken
    ):
        monkeypatch.setattr(token_utils, "TIKTOKEN_AVAILABLE", None)
        unknown_model = MetricsTokenEstimator(model="unknown-model")
        assert unknown_model.estimate_tokens("value") == 1
        assert unknown_model.encoder.name == "cl100k_base"
        assert isinstance(unknown_model.encoder, isolated_tiktoken.Encoding)

        unavailable = MetricsTokenEstimator()
        monkeypatch.setattr(
            token_utils.importlib,
            "import_module",
            lambda name: (_ for _ in ()).throw(ImportError(name)),
        )
        assert unavailable.estimate_tokens("abcdefgh") == 2
        assert unavailable.encoder is None
        assert unavailable._encoder_initialized
        monkeypatch.setattr(token_utils.importlib, "import_module", lambda name: pytest.fail("cached missing import retried"))
        assert unavailable.estimate_tokens("abcdefgh") == 2

    def test_metrics_persistence_and_result_shapes_remain_compatible(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("HOME", str(tmp_path))
        estimator = MetricsTokenEstimator()
        estimator.metrics_history.append(TokenMetrics("probe", 1, 2, 3))

        assert not estimator.metrics_dir.exists()
        estimator.save_metrics()
        assert estimator.metrics_file.exists()

        restored = MetricsTokenEstimator()
        restored.load_metrics()
        assert [metric.total_tokens for metric in restored.metrics_history] == [3]
        assert set(restored.get_usage_stats()) == {
            "total_operations",
            "total_tokens_used",
            "average_tokens_per_operation",
            "compact_mode_average",
            "full_mode_average",
            "recent_average",
            "compact_savings",
            "daily_usage",
            "daily_limit",
            "operation_limit",
            "model",
            "tiktoken_available",
        }

    def test_utils_package_defers_export_modules_until_attribute_access(self):
        script = """
import json
import sys
import scribe_mcp.utils as utils

deferred = {
    "scribe_mcp.utils.files",
    "scribe_mcp.utils.slug",
    "scribe_mcp.utils.time",
    "scribe_mcp.utils.response",
    "scribe_mcp.utils.tokens",
}
assert deferred.isdisjoint(sys.modules)
assert callable(utils.append_line)
assert "scribe_mcp.utils.files" in sys.modules
assert "scribe_mcp.utils.response" not in sys.modules
assert "scribe_mcp.utils.tokens" not in sys.modules
print(json.dumps(utils.__all__))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert token_utils.json.loads(result.stdout) == [
            "append_line",
            "ensure_parent",
            "read_tail",
            "rotate_file",
            "slugify_project_name",
            "slugify_filename",
            "format_utc",
            "utcnow",
            "ResponseFormatter",
            "default_formatter",
            "create_pagination_info",
            "PaginationInfo",
            "TokenEstimator",
            "TokenMetrics",
            "TokenBudget",
            "token_estimator",
        ]


class TestEstimatorUtilities:
    """Test EstimatorUtilities high-level interface."""

    def test_utilities_initialization(self):
        """Test EstimatorUtilities initialization."""
        utilities = EstimatorUtilities()

        assert isinstance(utilities.file_size, FileSizeEstimator)
        assert isinstance(utilities.threshold, ThresholdEstimator)
        assert isinstance(utilities.pagination, PaginationCalculator)
        assert isinstance(utilities.bulk, BulkProcessingCalculator)
        assert isinstance(utilities.tokens, TokenEstimator)

    def test_estimate_file_operations_nonexistent(self):
        """Test file operation estimation for non-existent file."""
        utilities = EstimatorUtilities()

        result = utilities.estimate_file_operations(Path("/non/existent/file.log"))

        assert result["exists"] is False
        assert result["size_bytes"] == 0
        assert result["entry_estimate"].method == "file_not_found"
        assert result["entry_estimate"].count == 0

    def test_estimate_file_operations_existing(self):
        """Test file operation estimation for existing file."""
        utilities = EstimatorUtilities()

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            # Write 50 lines
            for i in range(50):
                f.write(f"Test log entry {i:03d}\n")
            temp_path = Path(f.name)

        try:
            result = utilities.estimate_file_operations(temp_path)

            assert result["exists"] is True
            assert result["size_bytes"] > 0
            assert result["size_mb"] > 0
            assert result["mtime_ns"] > 0

            # Check estimates
            assert isinstance(result["entry_estimate"], EntryCountEstimate)
            assert isinstance(result["basic_estimate"], EntryCountEstimate)
            assert isinstance(result["cached_estimate"], EntryCountEstimate)

            # Entry count should be reasonable (around 50)
            assert 1 <= result["entry_estimate"].count <= 200

        finally:
            temp_path.unlink()

    def test_estimate_file_operations_with_cache(self):
        """Test file operation estimation with cache."""
        utilities = EstimatorUtilities()

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            for i in range(30):
                f.write(f"Cached entry {i:03d}\n")
            temp_path = Path(f.name)

        try:
            file_stat = temp_path.stat()
            cache_stats = {
                "size_bytes": file_stat.st_size,
                "mtime_ns": file_stat.st_mtime_ns,
                "line_count": 30,
                "source": "test_cache"
            }

            result = utilities.estimate_file_operations(temp_path, cache_stats)

            # Should use cache
            assert result["cached_estimate"].method == "cache"
            assert result["cached_estimate"].approximate is False
            assert result["cached_estimate"].count == 30

        finally:
            temp_path.unlink()


class TestIntegration:
    """Integration tests for estimator utilities."""

    def test_end_to_end_estimation_workflow(self):
        """Test complete estimation workflow."""
        utilities = EstimatorUtilities()

        # Create test data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            for i in range(75):
                f.write(f"Integration test entry {i:03d} with varying content lengths\n")
            temp_path = Path(f.name)

        try:
            # File operations estimation
            file_result = utilities.estimate_file_operations(temp_path)

            # Threshold estimation
            threshold = 50
            band = utilities.threshold.compute_estimation_band(threshold)
            classification = utilities.threshold.classify_estimate(
                file_result["entry_estimate"].count, threshold, band
            )

            # Pagination calculation
            total_items = file_result["entry_estimate"].count
            page_size = 20
            pagination_info = utilities.pagination.create_pagination_info(
                1, page_size, total_items
            )

            # Bulk processing calculation
            chunk_calc = utilities.bulk.calculate_chunks(total_items, 25)

            # Token estimation
            sample_entries = [
                {"message": f"Entry {i}", "timestamp": "2023-01-01"}
                for i in range(min(10, total_items))
            ]
            token_estimate = utilities.tokens.estimate_response_tokens(sample_entries)

            # Verify all components work together
            assert file_result["exists"] is True
            assert file_result["entry_estimate"].count > 0
            assert isinstance(band, int)
            assert classification in ["well_above_threshold", "near_threshold", "well_below_threshold"]
            assert isinstance(pagination_info, PaginationInfo)
            assert isinstance(chunk_calc, ChunkCalculation)
            assert token_estimate > 0

            # Verify consistency
            assert total_items == file_result["entry_estimate"].count
            assert pagination_info.total_count == total_items
            assert chunk_calc.total_items == total_items

        finally:
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__])
