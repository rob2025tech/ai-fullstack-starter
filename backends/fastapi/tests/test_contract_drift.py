from pathlib import Path

import yaml

from app.main import create_app

SPEC_PATH = Path(__file__).resolve().parents[3] / "packages" / "api-contract" / "openapi.yaml"
# Contract-only schemas that document SSE payloads; FastAPI never emits them
# because the streaming endpoints return StreamingResponse with no typed model.
DOC_ONLY_SCHEMAS = {"SseDeltaEvent", "AgentSseEvent"}


def _canonical() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text())


def _emitted() -> dict:
    return create_app().openapi()


def test_spec_file_exists():
    assert SPEC_PATH.is_file(), f"canonical contract spec missing at {SPEC_PATH}"


def test_contract_version_matches():
    assert _emitted()["info"]["version"] == _canonical()["info"]["version"]


def test_endpoints_and_methods_match():
    def operations(spec: dict) -> dict[str, set[str]]:
        return {path: set(ops) for path, ops in spec["paths"].items()}

    assert operations(_canonical()) == operations(_emitted())


def test_status_codes_match_per_operation():
    canonical, emitted = _canonical(), _emitted()
    for path, ops in canonical["paths"].items():
        for method, op in ops.items():
            assert set(op["responses"]) == set(
                emitted["paths"][path][method]["responses"]
            ), f"{method.upper()} {path}"


def test_schema_shapes_match():
    canonical_schemas = _canonical()["components"]["schemas"]
    emitted_schemas = _emitted()["components"]["schemas"]
    assert set(emitted_schemas) == set(canonical_schemas) - DOC_ONLY_SCHEMAS
    for name, emitted in emitted_schemas.items():
        canonical = canonical_schemas[name]
        assert set(emitted.get("properties", {})) == set(
            canonical.get("properties", {})
        ), f"{name} properties"
        assert set(emitted.get("required", [])) == set(canonical.get("required", [])), (
            f"{name} required"
        )


def test_error_code_registry_matches():
    canonical_enum = _canonical()["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
    emitted_enum = _emitted()["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
    assert sorted(emitted_enum) == sorted(canonical_enum)
