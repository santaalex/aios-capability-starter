from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .task_bundle import (
    TaskBundleError,
    capability_identity_from_task,
    create_capability_result,
    ensure_task_matches_source,
    load_result,
    load_task,
    sha256_file,
    validate_result,
    validate_task,
    write_json_atomic,
)

PACK_SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "AIOS_CAPABILITY_PACK"
RUNTIME_API = "aios-capability-runtime.v1"
SIGNATURE_SCHEME = "ED25519_DETACHED_V1"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
COMPONENT_KINDS = {
    "RUNTIME": "runtime/",
    "ADAPTER": "adapters/",
    "INPUT_SCHEMA": "schemas/",
    "CONFIRMATION_SCHEMA": "schemas/",
    "RESULT_SCHEMA": "schemas/",
    "UI_SCHEMA": "ui/",
    "SKILL": "skills/",
    "GOLDEN_CASE": "golden/",
    "DOCUMENTATION": "docs/",
}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".md",
    ".ps1",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}


class CapabilityPackError(ValueError):
    """Raised when a Capability Pack source or artifact is invalid."""


def init_pack_source(
    capability_id: str,
    *,
    display_name: str,
    version: str = "0.1.0",
    repo_root: Path,
) -> dict[str, Any]:
    """Create one repository-local Capability Pack source from the starter."""

    identity = {"capability_id": capability_id, "version": version}
    capability_id = _capability_id(identity)
    version = _semantic_version(identity, "version")
    if not isinstance(display_name, str) or not display_name.strip():
        raise CapabilityPackError("display_name must be a non-empty string")
    display_name = display_name.strip()
    if len(display_name) > 48 or any(ord(character) < 32 for character in display_name):
        raise CapabilityPackError(
            "display_name must be at most 48 characters without control characters"
        )

    repo_root = repo_root.resolve()
    template_root = repo_root / "template"
    if not template_root.is_dir():
        raise CapabilityPackError("Capability Pack template is missing: template")
    target = repo_root / "capabilities" / capability_id / version
    if target.exists():
        raise CapabilityPackError(f"Capability Pack source already exists: {target}")

    source_root = target.relative_to(repo_root).as_posix()
    replacements = {
        "__CAPABILITY_ID__": capability_id,
        "__DISPLAY_NAME__": display_name,
        "__DISPLAY_NAME_JSON__": json.dumps(display_name, ensure_ascii=False)[1:-1],
        "__VERSION__": version,
        "__SOURCE_ROOT__": source_root,
    }
    template_files = sorted(path for path in template_root.rglob("*") if path.is_file())
    if not template_files:
        raise CapabilityPackError("Capability Pack starter contains no files")

    target.mkdir(parents=True)
    source_manifest = target / "capability.source.json"
    try:
        for source in template_files:
            relative = source.relative_to(template_root).as_posix()
            for token, replacement in replacements.items():
                relative = relative.replace(token, replacement)
            destination = target / Path(*PurePosixPath(relative).parts)
            try:
                text = source.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise CapabilityPackError(
                    f"cannot read starter file: {source}"
                ) from error
            for token, replacement in replacements.items():
                text = text.replace(token, replacement)
            if "__" in text and any(
                token in text
                for token in (
                    "__CAPABILITY_ID__",
                    "__DISPLAY_NAME__",
                    "__DISPLAY_NAME_JSON__",
                    "__VERSION__",
                    "__SOURCE_ROOT__",
                )
            ):
                raise CapabilityPackError(f"starter token was not replaced: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8", newline="\n")
        _validate_source_manifest(_load_json_object(source_manifest))
    except Exception:
        for path in sorted(target.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        target.rmdir()
        raise

    return {
        "capability_id": capability_id,
        "version": version,
        "display_name": display_name,
        "source_directory": str(target),
        "source_manifest": str(source_manifest),
        "next_command": (
            "aios-capability build "
            f"{source_manifest.relative_to(repo_root).as_posix()} --repo-root ."
        ),
    }


def build_pack(
    source_manifest_path: Path,
    *,
    repo_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source_manifest_path = source_manifest_path.resolve()
    source = _load_json_object(source_manifest_path)
    capability, release, validation, signature_policy = _validate_source_manifest(
        source
    )
    if output_path is None:
        output_path = (
            repo_root
            / "dist"
            / "capability-packs"
            / f"{capability['capability_id']}-{capability['version']}.zip"
        )
    output_path = output_path.resolve()

    payloads: dict[str, bytes] = {}
    inventory: list[dict[str, Any]] = []
    component_kinds: dict[str, str] = {}
    for component in source["components"]:
        destination = _safe_archive_path(component["path"])
        if (
            destination in {"manifest.json", "capability.json"}
            or destination in payloads
        ):
            raise CapabilityPackError(
                f"duplicate or reserved component path: {destination}"
            )
        kind = component["kind"]
        expected_root = COMPONENT_KINDS[kind]
        if not destination.startswith(expected_root):
            raise CapabilityPackError(
                f"{kind} component must be stored below {expected_root}: {destination}"
            )
        source_file = _source_file(repo_root, component["source"])
        data = _normalize_component_content(destination, source_file.read_bytes())
        payloads[destination] = data
        component_kinds[destination] = kind
        inventory.append(
            {
                "kind": kind,
                "id": component["id"],
                "path": destination,
                "size_bytes": len(data),
                "sha256": _sha256_bytes(data),
            }
        )

    _validate_capability_references(capability, component_kinds)
    capability_data = _canonical_json(capability)
    manifest = {
        "schema_version": PACK_SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "capability_id": capability["capability_id"],
        "version": capability["version"],
        "display_name": capability["display_name"],
        "release": release,
        "compatibility": capability["compatibility"],
        "validation": validation,
        "signature_policy": signature_policy,
        "capability_contract": {
            "path": "capability.json",
            "size_bytes": len(capability_data),
            "sha256": _sha256_bytes(capability_data),
        },
        "components": sorted(inventory, key=lambda item: item["path"]),
    }
    manifest_data = _canonical_json(manifest)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            _write_entry(archive, "manifest.json", manifest_data)
            _write_entry(archive, "capability.json", capability_data)
            for destination in sorted(payloads):
                _write_entry(archive, destination, payloads[destination])
        verified = verify_pack(temporary_path)
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    artifact_sha256 = _sha256_file(output_path)
    return {
        **verified,
        "path": str(output_path),
        "artifact_sha256": artifact_sha256,
        "signature_payload": f"sha256:{artifact_sha256}",
    }


def verify_pack(pack_path: Path) -> dict[str, Any]:
    pack_path = pack_path.resolve()
    try:
        with zipfile.ZipFile(pack_path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise CapabilityPackError("Capability Pack contains duplicate files")
            if "manifest.json" not in names or "capability.json" not in names:
                raise CapabilityPackError(
                    "Capability Pack requires manifest.json and capability.json"
                )
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            capability = json.loads(archive.read("capability.json").decode("utf-8"))
            identity = _validate_artifact_manifest(manifest)
            _validate_capability_contract(capability)
            if (
                capability["capability_id"] != identity["capability_id"]
                or capability["version"] != identity["version"]
            ):
                raise CapabilityPackError(
                    "manifest and capability identity do not match"
                )
            if capability["compatibility"] != manifest["compatibility"]:
                raise CapabilityPackError(
                    "manifest and capability compatibility do not match"
                )

            capability_data = archive.read("capability.json")
            contract = manifest["capability_contract"]
            _verify_bytes("capability.json", capability_data, contract)
            component_kinds: dict[str, str] = {}
            expected_names = {"manifest.json", "capability.json"}
            for component in manifest["components"]:
                path = _safe_archive_path(component["path"])
                expected_names.add(path)
                component_kinds[path] = component["kind"]
                try:
                    data = archive.read(path)
                except KeyError as error:
                    raise CapabilityPackError(
                        f"component is missing: {path}"
                    ) from error
                _verify_bytes(path, data, component)
                _validate_component_content(path, data)
            extras = set(names) - expected_names
            if extras:
                extra_names = ", ".join(sorted(extras))
                raise CapabilityPackError(
                    f"Capability Pack contains undeclared files: {extra_names}"
                )
            _validate_capability_references(capability, component_kinds)
    except (
        OSError,
        zipfile.BadZipFile,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise CapabilityPackError(f"cannot read Capability Pack: {error}") from error

    artifact_sha256 = _sha256_file(pack_path)
    return {
        **identity,
        "components": len(manifest["components"]),
        "artifact_sha256": artifact_sha256,
        "signature_scheme": manifest["signature_policy"]["scheme"],
        "signature_required_for_activation": manifest["signature_policy"][
            "required_for_activation"
        ],
        "signature_payload": f"sha256:{artifact_sha256}",
        "trust_status": "DETACHED_SIGNATURE_NOT_CHECKED",
    }


def _validate_source_manifest(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], dict[str, Any]]:
    allowed = {
        "schema_version",
        "capability_id",
        "version",
        "display_name",
        "release",
        "compatibility",
        "execution",
        "contracts",
        "ui",
        "skills",
        "golden_cases",
        "validation",
        "signature_policy",
        "components",
    }
    unknown = set(value) - allowed
    if unknown:
        raise CapabilityPackError(
            f"unknown source manifest fields: {', '.join(sorted(unknown))}"
        )
    capability = _capability_from_source(value)
    release = _validate_release(value.get("release"))
    validation = _validate_validation(value.get("validation"))
    signature_policy = _validate_signature_policy(value.get("signature_policy"))
    components = value.get("components")
    if not isinstance(components, list) or not components:
        raise CapabilityPackError("components must be a non-empty array")
    for component in components:
        if not isinstance(component, Mapping):
            raise CapabilityPackError("every component must be an object")
        if set(component) != {"kind", "id", "source", "path"}:
            raise CapabilityPackError(
                "source components require exactly kind, id, source, and path"
            )
        kind = _required_text(component, "kind")
        if kind not in COMPONENT_KINDS:
            raise CapabilityPackError(f"unsupported component kind: {kind}")
        for field in ("id", "source", "path"):
            _required_text(component, field)
    return capability, release, validation, signature_policy


def _capability_from_source(value: Mapping[str, Any]) -> dict[str, Any]:
    capability = {
        "schema_version": PACK_SCHEMA_VERSION,
        "capability_id": _capability_id(value),
        "version": _semantic_version(value, "version"),
        "display_name": _required_text(value, "display_name"),
        "compatibility": value.get("compatibility"),
        "execution": value.get("execution"),
        "contracts": value.get("contracts"),
        "ui": value.get("ui"),
        "skills": value.get("skills"),
        "golden_cases": value.get("golden_cases"),
    }
    _validate_capability_contract(capability)
    return capability


def _validate_capability_contract(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise CapabilityPackError("capability.json must contain an object")
    expected = {
        "schema_version",
        "capability_id",
        "version",
        "display_name",
        "compatibility",
        "execution",
        "contracts",
        "ui",
        "skills",
        "golden_cases",
    }
    if set(value) != expected:
        raise CapabilityPackError("capability contract fields are invalid")
    if value.get("schema_version") != PACK_SCHEMA_VERSION:
        raise CapabilityPackError(f"schema_version must be {PACK_SCHEMA_VERSION}")
    _capability_id(value)
    _semantic_version(value, "version")
    _required_text(value, "display_name")

    compatibility = value.get("compatibility")
    if not isinstance(compatibility, Mapping) or set(compatibility) != {
        "core_min",
        "core_max_exclusive",
        "runtime_api",
    }:
        raise CapabilityPackError("compatibility fields are invalid")
    _semantic_version(compatibility, "core_min")
    _semantic_version(compatibility, "core_max_exclusive")
    if compatibility.get("runtime_api") != RUNTIME_API:
        raise CapabilityPackError(f"runtime_api must be {RUNTIME_API}")

    execution = value.get("execution")
    if not isinstance(execution, Mapping) or set(execution) != {
        "kind",
        "entrypoint",
    }:
        raise CapabilityPackError("execution fields are invalid")
    if execution.get("kind") != "PYTHON_SUBPROCESS":
        raise CapabilityPackError("execution.kind must be PYTHON_SUBPROCESS")
    _safe_archive_path(_required_text(execution, "entrypoint"))

    contracts = value.get("contracts")
    if not isinstance(contracts, Mapping) or set(contracts) != {
        "input",
        "confirmation",
        "result",
    }:
        raise CapabilityPackError("contracts fields are invalid")
    for field in ("input", "confirmation", "result"):
        _safe_archive_path(_required_text(contracts, field))

    ui = value.get("ui")
    if not isinstance(ui, Mapping) or set(ui) != {"form", "result"}:
        raise CapabilityPackError("ui fields are invalid")
    for field in ("form", "result"):
        _safe_archive_path(_required_text(ui, field))
    _path_array(value.get("skills"), "skills")
    _path_array(value.get("golden_cases"), "golden_cases")


def _validate_capability_references(
    capability: Mapping[str, Any], component_kinds: Mapping[str, str]
) -> None:
    references = {
        capability["execution"]["entrypoint"]: "RUNTIME",
        capability["contracts"]["input"]: "INPUT_SCHEMA",
        capability["contracts"]["confirmation"]: "CONFIRMATION_SCHEMA",
        capability["contracts"]["result"]: "RESULT_SCHEMA",
        capability["ui"]["form"]: "UI_SCHEMA",
        capability["ui"]["result"]: "UI_SCHEMA",
        **{path: "SKILL" for path in capability["skills"]},
        **{path: "GOLDEN_CASE" for path in capability["golden_cases"]},
    }
    for path, expected_kind in references.items():
        actual_kind = component_kinds.get(path)
        if actual_kind != expected_kind:
            actual_label = actual_kind or "missing"
            raise CapabilityPackError(
                f"capability reference {path} requires {expected_kind}, "
                f"got {actual_label}"
            )


def _validate_artifact_manifest(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise CapabilityPackError("manifest.json must contain an object")
    expected = {
        "schema_version",
        "artifact_type",
        "capability_id",
        "version",
        "display_name",
        "release",
        "compatibility",
        "validation",
        "signature_policy",
        "capability_contract",
        "components",
    }
    if set(value) != expected:
        raise CapabilityPackError("manifest fields are invalid")
    if value.get("schema_version") != PACK_SCHEMA_VERSION:
        raise CapabilityPackError(f"schema_version must be {PACK_SCHEMA_VERSION}")
    if value.get("artifact_type") != ARTIFACT_TYPE:
        raise CapabilityPackError(f"artifact_type must be {ARTIFACT_TYPE}")
    identity = {
        "capability_id": _capability_id(value),
        "version": _semantic_version(value, "version"),
        "display_name": _required_text(value, "display_name"),
    }
    _validate_release(value.get("release"))
    _validate_validation(value.get("validation"))
    _validate_signature_policy(value.get("signature_policy"))
    contract = value.get("capability_contract")
    if not isinstance(contract, Mapping) or set(contract) != {
        "path",
        "size_bytes",
        "sha256",
    }:
        raise CapabilityPackError("capability_contract fields are invalid")
    if contract.get("path") != "capability.json":
        raise CapabilityPackError("capability_contract.path must be capability.json")
    _validate_file_record(contract, "capability.json")
    components = value.get("components")
    if not isinstance(components, list) or not components:
        raise CapabilityPackError("manifest components must be a non-empty array")
    seen: set[str] = set()
    for component in components:
        if not isinstance(component, Mapping) or set(component) != {
            "kind",
            "id",
            "path",
            "size_bytes",
            "sha256",
        }:
            raise CapabilityPackError("manifest component fields are invalid")
        kind = _required_text(component, "kind")
        if kind not in COMPONENT_KINDS:
            raise CapabilityPackError(f"unsupported component kind: {kind}")
        _required_text(component, "id")
        path = _safe_archive_path(component["path"])
        if path in seen:
            raise CapabilityPackError(f"duplicate manifest component path: {path}")
        seen.add(path)
        if not path.startswith(COMPONENT_KINDS[kind]):
            raise CapabilityPackError(f"component kind/path mismatch: {path}")
        _validate_file_record(component, path)
    return identity


def _validate_release(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"stage", "channel"}:
        raise CapabilityPackError("release requires exactly stage and channel")
    stage = _required_text(value, "stage")
    if stage not in {"DRAFT", "CANDIDATE", "RELEASED"}:
        raise CapabilityPackError("release.stage is invalid")
    return {"stage": stage, "channel": _required_text(value, "channel")}


def _validate_validation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "golden_case_ids",
        "required_checks",
    }:
        raise CapabilityPackError(
            "validation requires exactly golden_case_ids and required_checks"
        )
    golden_case_ids = _text_array(value.get("golden_case_ids"), "golden_case_ids")
    required_checks = _text_array(value.get("required_checks"), "required_checks")
    return {"golden_case_ids": golden_case_ids, "required_checks": required_checks}


def _validate_signature_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "scheme",
        "required_for_activation",
    }:
        raise CapabilityPackError(
            "signature_policy requires exactly scheme and required_for_activation"
        )
    if value.get("scheme") != SIGNATURE_SCHEME:
        raise CapabilityPackError(f"signature scheme must be {SIGNATURE_SCHEME}")
    if value.get("required_for_activation") is not True:
        raise CapabilityPackError("Capability Pack activation must require a signature")
    return {"scheme": SIGNATURE_SCHEME, "required_for_activation": True}


def _validate_file_record(value: Mapping[str, Any], path: str) -> None:
    size = value.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise CapabilityPackError(f"invalid component size: {path}")
    digest = value.get("sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise CapabilityPackError(f"invalid component sha256: {path}")


def _verify_bytes(path: str, data: bytes, record: Mapping[str, Any]) -> None:
    if len(data) != record["size_bytes"]:
        raise CapabilityPackError(f"component size mismatch: {path}")
    if _sha256_bytes(data) != record["sha256"]:
        raise CapabilityPackError(f"component hash mismatch: {path}")


def _path_array(value: Any, field: str) -> list[str]:
    values = _text_array(value, field)
    for item in values:
        _safe_archive_path(item)
    return values


def _text_array(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CapabilityPackError(f"{field} must be a non-empty array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CapabilityPackError(f"{field} items must be non-empty strings")
        result.append(item.strip())
    if len(result) != len(set(result)):
        raise CapabilityPackError(f"{field} must not contain duplicates")
    return result


def _capability_id(value: Mapping[str, Any]) -> str:
    item = _required_text(value, "capability_id")
    if not CAPABILITY_ID.fullmatch(item):
        raise CapabilityPackError("capability_id must be lowercase kebab-case")
    return item


def _semantic_version(value: Mapping[str, Any], field: str) -> str:
    item = _required_text(value, field)
    if not SEMVER.fullmatch(item):
        raise CapabilityPackError(f"{field} must be MAJOR.MINOR.PATCH")
    return item


def _required_text(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise CapabilityPackError(f"{field} must be a non-empty string")
    return item.strip()


def _source_file(repo_root: Path, relative_path: str) -> Path:
    safe_path = _safe_archive_path(relative_path)
    resolved = (repo_root / Path(*PurePosixPath(safe_path).parts)).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as error:
        raise CapabilityPackError(
            f"component source leaves repo root: {relative_path}"
        ) from error
    if not resolved.is_file():
        raise CapabilityPackError(f"component source does not exist: {relative_path}")
    return resolved


def _safe_archive_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CapabilityPackError("component path must be a POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CapabilityPackError(f"unsafe component path: {value}")
    return path.as_posix()


def _validate_component_content(path: str, data: bytes) -> None:
    if path.endswith(".json"):
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CapabilityPackError(f"invalid JSON component: {path}") from error
        if not isinstance(value, Mapping):
            raise CapabilityPackError(f"JSON component must contain an object: {path}")
    if path.endswith("/SKILL.md"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CapabilityPackError(f"SKILL.md must be UTF-8: {path}") from error
        if text.startswith("\ufeff") or not text.startswith("---\n"):
            raise CapabilityPackError(
                f"SKILL.md must be UTF-8 without BOM and start with frontmatter: {path}"
            )


def _normalize_component_content(path: str, data: bytes) -> bytes:
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix in TEXT_SUFFIXES or path.endswith("/SKILL.md"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CapabilityPackError(
                f"text component must be UTF-8: {path}"
            ) from error
        if text.startswith("\ufeff"):
            raise CapabilityPackError(
                f"text component must be UTF-8 without BOM: {path}"
            )
        data = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if path.endswith(".json"):
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CapabilityPackError(f"invalid JSON component: {path}") from error
        if not isinstance(value, Mapping):
            raise CapabilityPackError(f"JSON component must contain an object: {path}")
        data = _canonical_json(value)
    _validate_component_content(path, data)
    return data


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityPackError(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise CapabilityPackError(f"JSON file must contain an object: {path}")
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(_canonical_json(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_entry(archive: zipfile.ZipFile, path: str, data: bytes) -> None:
    info = zipfile.ZipInfo(path, ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aios-capability")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser(
        "init", help="create a Capability Pack source from the repository starter"
    )
    init.add_argument("capability_id", nargs="?")
    init.add_argument("--display-name")
    init.add_argument("--version")
    init.add_argument("--task", type=Path)
    init.add_argument("--repo-root", type=Path, default=Path.cwd())
    build = subparsers.add_parser("build", help="build a deterministic Capability Pack")
    build.add_argument("source_manifest", nargs="?", type=Path)
    build.add_argument("--repo-root", type=Path, default=Path.cwd())
    build.add_argument("--output", type=Path)
    build.add_argument("--task", type=Path)
    build.add_argument("--result-output", type=Path)
    verify = subparsers.add_parser("verify", help="verify one Capability Pack artifact")
    verify.add_argument("pack", type=Path)
    verify.add_argument("--task", type=Path)
    task_validate = subparsers.add_parser(
        "task-validate", help="validate one AIOS Task Bundle"
    )
    task_validate.add_argument("task", type=Path)
    result_validate = subparsers.add_parser(
        "result-validate", help="validate one AIOS Task Result"
    )
    result_validate.add_argument("result", type=Path)
    result_validate.add_argument("--task", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            if args.task is not None:
                if (
                    args.capability_id is not None
                    or args.display_name is not None
                    or args.version is not None
                ):
                    raise TaskBundleError(
                        "init --task derives capability identity; do not also pass "
                        "capability_id, --display-name, or --version"
                    )
                task = load_task(args.task)
                capability = capability_identity_from_task(task)
                capability_id = capability["capability_id"]
                display_name = capability["display_name"]
                version = capability["version"]
                expected_source = (
                    f"capabilities/{capability_id}/{version}/capability.source.json"
                )
                if capability["source_manifest"] != expected_source:
                    raise TaskBundleError(
                        "init --task requires spec.capability.source_manifest to be "
                        f"{expected_source}"
                    )
            else:
                if args.capability_id is None or args.display_name is None:
                    raise CapabilityPackError(
                        "init requires capability_id and --display-name, or --task"
                    )
                capability_id = args.capability_id
                display_name = args.display_name
                version = args.version or "0.1.0"
            result = init_pack_source(
                capability_id,
                display_name=display_name,
                version=version,
                repo_root=args.repo_root,
            )
            if args.task is not None:
                source_path = Path(result["source_manifest"])
                ensure_task_matches_source(
                    task,
                    source_manifest_path=source_path,
                    source=_load_json_object(source_path),
                    repo_root=args.repo_root,
                )
                task_summary = validate_task(task)
                result["task_id"] = task_summary["task_id"]
                result["task_generation"] = task_summary["generation"]
        elif args.command == "build":
            task = None
            source = None
            if args.result_output is not None and args.task is None:
                raise TaskBundleError("--result-output requires --task")
            if args.task is not None:
                task = load_task(args.task)
                capability = capability_identity_from_task(task)
                task_source_path = (
                    args.repo_root
                    / Path(*PurePosixPath(capability["source_manifest"]).parts)
                ).resolve()
                if args.source_manifest is not None:
                    source_path = args.source_manifest.resolve()
                    if source_path != task_source_path:
                        raise TaskBundleError(
                            "build source manifest does not match task"
                        )
                else:
                    source_path = task_source_path
                source = _load_json_object(source_path)
                ensure_task_matches_source(
                    task,
                    source_manifest_path=source_path,
                    source=source,
                    repo_root=args.repo_root,
                )
            elif args.source_manifest is None:
                raise CapabilityPackError(
                    "build requires source_manifest, or --task"
                )
            else:
                source_path = args.source_manifest.resolve()
            result = build_pack(
                source_path,
                repo_root=args.repo_root,
                output_path=args.output,
            )
            if task is not None and source is not None:
                task_summary = validate_task(task)
                result_output = args.result_output or (
                    args.repo_root
                    / "dist"
                    / "task-results"
                    / f"{task_summary['task_id']}.result.json"
                )
                task_result = create_capability_result(
                    task,
                    artifact_path=Path(result["path"]),
                    artifact_sha256=result["artifact_sha256"],
                    artifact_size=Path(result["path"]).stat().st_size,
                    source_manifest_path=source_path,
                    source_manifest_sha256=sha256_file(source_path),
                    repo_root=args.repo_root,
                )
                write_json_atomic(result_output.resolve(), task_result)
                result["task_id"] = task_summary["task_id"]
                result["task_generation"] = task_summary["generation"]
                result["task_result"] = str(result_output.resolve())
        elif args.command == "verify":
            result = verify_pack(args.pack)
            if args.task is not None:
                task = load_task(args.task)
                capability = capability_identity_from_task(task)
                for field in ("capability_id", "version", "display_name"):
                    if result[field] != capability[field]:
                        raise TaskBundleError(
                            f"verified artifact {field} does not match task"
                        )
                task_summary = validate_task(task)
                result["task_id"] = task_summary["task_id"]
                result["task_generation"] = task_summary["generation"]
        elif args.command == "task-validate":
            task = load_task(args.task)
            summary = validate_task(task)
            result = {
                "task_id": summary["task_id"],
                "generation": summary["generation"],
                "kind": summary["kind"],
                "impact": summary["impact"],
                "status": "VALID",
            }
        elif args.command == "result-validate":
            task = load_task(args.task) if args.task is not None else None
            result = load_result(args.result, task=task)
            result = {**validate_result(result, task=task), "status": "VALID"}
    except (CapabilityPackError, TaskBundleError) as error:
        raise SystemExit(f"AIOS Starter error: {error}") from error
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
