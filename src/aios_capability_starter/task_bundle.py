from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

TASK_API_VERSION = "task.aios.fuinno.cn/v0.1alpha1"
RESULT_API_VERSION = "task-result.aios.fuinno.cn/v0.1alpha1"
TASK_KINDS = {
    "CapabilityDevelopment",
    "AdapterDevelopment",
    "DeviceDeployment",
    "DesktopUpdate",
}
RESULT_KINDS = {f"{kind}Result" for kind in TASK_KINDS}
IMPACT_LEVELS = {
    "pack-only",
    "customer-pack-only",
    "plugin-required",
    "desktop-required",
    "bootstrap-required",
    "control-plane-required",
}
RESULT_OUTCOMES = {"COMPLETED", "NEEDS_ATTENTION", "BLOCKED", "FAILED"}
CONDITION_STATUSES = {"True", "False", "Unknown"}
ENVIRONMENTS = {"development", "test", "customer"}
TASK_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TaskBundleError(ValueError):
    """Raised when an AIOS Task Bundle contract is invalid."""


def load_task(path: Path) -> dict[str, Any]:
    task = _load_json_object(path, "Task Bundle")
    validate_task(task)
    return task


def load_result(path: Path, *, task: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = _load_json_object(path, "Task Result")
    validate_result(result, task=task)
    return result


def validate_task(task: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(task, {"api_version", "kind", "metadata", "spec"}, "task")
    if task.get("api_version") != TASK_API_VERSION:
        raise TaskBundleError(f"api_version must be {TASK_API_VERSION}")
    kind = _enum(task, "kind", TASK_KINDS)

    metadata = _mapping(task.get("metadata"), "metadata")
    _allow_fields(
        metadata,
        {"task_id", "generation", "created_at", "expires_at"},
        {"task_id", "generation", "created_at"},
        "metadata",
    )
    task_id = _identifier(metadata, "task_id", TASK_ID)
    generation = metadata.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
    ):
        raise TaskBundleError("metadata.generation must be a positive integer")
    created_at = _timestamp(metadata, "created_at")
    expires_at = None
    if "expires_at" in metadata:
        expires_at = _timestamp(metadata, "expires_at")
        if expires_at <= created_at:
            raise TaskBundleError("metadata.expires_at must be after created_at")

    spec = _mapping(task.get("spec"), "spec")
    _allow_fields(
        spec,
        {
            "objective",
            "non_goals",
            "impact",
            "target",
            "capability",
            "artifacts",
            "human_actions",
            "acceptance",
            "secrets_policy",
        },
        {
            "objective",
            "non_goals",
            "impact",
            "target",
            "acceptance",
            "secrets_policy",
        },
        "spec",
    )
    _text(spec, "objective")
    _text_array(spec.get("non_goals"), "spec.non_goals", allow_empty=True)
    impact = _enum(spec, "impact", IMPACT_LEVELS)
    target = _validate_target(spec.get("target"))
    artifacts = _validate_artifacts(spec.get("artifacts", []), "spec.artifacts")
    human_actions = _validate_human_actions(spec.get("human_actions", []))
    acceptance = _validate_acceptance(spec.get("acceptance"))
    secrets_policy = _validate_secrets_policy(spec.get("secrets_policy"))

    capability = None
    if "capability" in spec:
        capability = _validate_capability(spec.get("capability"))
    if kind == "CapabilityDevelopment":
        if capability is None:
            raise TaskBundleError(
                "CapabilityDevelopment requires spec.capability"
            )
        if target["environment"] != "development":
            raise TaskBundleError(
                "CapabilityDevelopment target.environment must be development"
            )
        if impact not in {"pack-only", "plugin-required", "desktop-required"}:
            raise TaskBundleError(
                "CapabilityDevelopment impact must be pack-only, "
                "plugin-required, or desktop-required"
            )
    if kind in {"DeviceDeployment", "DesktopUpdate"} and "device_id" not in target:
        raise TaskBundleError(f"{kind} requires spec.target.device_id")

    return {
        "task_id": task_id,
        "generation": generation,
        "created_at": created_at,
        "expires_at": expires_at,
        "kind": kind,
        "impact": impact,
        "target": target,
        "capability": capability,
        "artifacts": artifacts,
        "human_actions": human_actions,
        "acceptance": acceptance,
        "secrets_policy": secrets_policy,
    }


def validate_result(
    result: Mapping[str, Any], *, task: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    _require_fields(
        result,
        {"api_version", "kind", "metadata", "status", "delivery"},
        "result",
    )
    if result.get("api_version") != RESULT_API_VERSION:
        raise TaskBundleError(f"api_version must be {RESULT_API_VERSION}")
    kind = _enum(result, "kind", RESULT_KINDS)

    metadata = _mapping(result.get("metadata"), "metadata")
    _require_fields(
        metadata,
        {"task_id", "observed_generation", "completed_at"},
        "result.metadata",
    )
    task_id = _identifier(metadata, "task_id", TASK_ID)
    observed_generation = metadata.get("observed_generation")
    if (
        not isinstance(observed_generation, int)
        or isinstance(observed_generation, bool)
        or observed_generation < 1
    ):
        raise TaskBundleError(
            "result.metadata.observed_generation must be a positive integer"
        )
    completed_at = _timestamp(metadata, "completed_at")

    status = _mapping(result.get("status"), "status")
    _require_fields(status, {"outcome", "summary", "conditions"}, "status")
    outcome = _enum(status, "outcome", RESULT_OUTCOMES)
    _text(status, "summary")
    conditions = status.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise TaskBundleError("status.conditions must be a non-empty array")
    condition_types: set[str] = set()
    for index, condition_value in enumerate(conditions):
        label = f"status.conditions[{index}]"
        condition = _mapping(condition_value, label)
        _require_fields(
            condition,
            {"type", "status", "reason", "message"},
            label,
        )
        condition_type = _text(condition, "type", label)
        if condition_type in condition_types:
            raise TaskBundleError("status.conditions types must be unique")
        condition_types.add(condition_type)
        _enum(condition, "status", CONDITION_STATUSES, label)
        _text(condition, "reason", label)
        _text(condition, "message", label)

    delivery = _mapping(result.get("delivery"), "delivery")
    _allow_fields(
        delivery,
        {
            "capability",
            "artifacts",
            "source",
            "validation",
            "adapter_required",
            "known_limitations",
        },
        {"artifacts", "validation", "known_limitations"},
        "delivery",
    )
    artifacts = _validate_artifacts(delivery.get("artifacts"), "delivery.artifacts")
    known_limitations = _text_array(
        delivery.get("known_limitations"),
        "delivery.known_limitations",
        allow_empty=True,
    )
    validation = _validate_result_validation(delivery.get("validation"))
    passed_checks = {
        check["name"]
        for check in validation["performed_checks"]
        if check["status"] == "PASS"
    }
    pending_checks = [
        check
        for check in validation["declared_required_checks"]
        if check not in passed_checks
    ]
    if outcome == "COMPLETED" and pending_checks:
        raise TaskBundleError(
            "COMPLETED requires every declared required check to PASS: "
            + ", ".join(pending_checks)
        )
    capability = None
    if "capability" in delivery:
        capability = _validate_result_capability(delivery.get("capability"))
    if "adapter_required" in delivery and not isinstance(
        delivery.get("adapter_required"), bool
    ):
        raise TaskBundleError("delivery.adapter_required must be boolean")
    if "source" in delivery:
        _validate_source(delivery.get("source"))
    if kind == "CapabilityDevelopmentResult" and capability is None:
        raise TaskBundleError(
            "CapabilityDevelopmentResult requires delivery.capability"
        )

    if task is not None:
        task_summary = validate_task(task)
        expected_kind = f"{task_summary['kind']}Result"
        if kind != expected_kind:
            raise TaskBundleError(
                f"result kind {kind} does not match task kind {task_summary['kind']}"
            )
        if task_id != task_summary["task_id"]:
            raise TaskBundleError("result task_id does not match task")
        if observed_generation != task_summary["generation"]:
            raise TaskBundleError("result observed_generation does not match task")
        if completed_at < task_summary["created_at"]:
            raise TaskBundleError("result completed_at is before task created_at")
        if (
            task_summary["expires_at"] is not None
            and completed_at > task_summary["expires_at"]
        ):
            raise TaskBundleError("result completed_at is after task expires_at")
        if (
            validation["declared_required_checks"]
            != task_summary["acceptance"]["required_checks"]
        ):
            raise TaskBundleError(
                "result declared_required_checks do not match task acceptance"
            )
        if capability is not None and task_summary["capability"] is not None:
            expected = task_summary["capability"]
            for field in ("capability_id", "version", "display_name"):
                if capability[field] != expected[field]:
                    raise TaskBundleError(
                        f"result capability.{field} does not match task"
                    )
            if "adapter_required" not in delivery:
                raise TaskBundleError(
                    "CapabilityDevelopmentResult requires delivery.adapter_required"
                )
            if delivery["adapter_required"] != expected["adapter_required"]:
                raise TaskBundleError(
                    "result adapter_required does not match task capability"
                )
            omitted_limitations = [
                limitation
                for limitation in expected["known_limitations"]
                if limitation not in known_limitations
            ]
            if omitted_limitations:
                raise TaskBundleError(
                    "result omitted task known_limitations: "
                    + ", ".join(omitted_limitations)
                )

    return {
        "task_id": task_id,
        "observed_generation": observed_generation,
        "kind": kind,
        "outcome": outcome,
        "conditions": len(conditions),
        "artifacts": len(artifacts),
        "known_limitations": known_limitations,
        "validation": validation,
    }


def capability_identity_from_task(task: Mapping[str, Any]) -> dict[str, Any]:
    summary = validate_task(task)
    if summary["kind"] != "CapabilityDevelopment":
        raise TaskBundleError(
            "only CapabilityDevelopment tasks can initialize or build a Capability Pack"
        )
    capability = summary["capability"]
    assert capability is not None
    return capability


def ensure_task_matches_source(
    task: Mapping[str, Any],
    *,
    source_manifest_path: Path,
    source: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    capability = capability_identity_from_task(task)
    expected_source = _repo_file(
        repo_root, capability["source_manifest"], "spec.capability.source_manifest"
    )
    if expected_source != source_manifest_path.resolve():
        raise TaskBundleError("build source manifest does not match task")
    for field in ("capability_id", "version", "display_name"):
        if source.get(field) != capability[field]:
            raise TaskBundleError(f"source {field} does not match task")
    return capability


def create_capability_result(
    task: Mapping[str, Any],
    *,
    artifact_path: Path,
    artifact_sha256: str,
    artifact_size: int,
    source_manifest_path: Path,
    source_manifest_sha256: str,
    repo_root: Path,
) -> dict[str, Any]:
    summary = validate_task(task)
    capability = capability_identity_from_task(task)
    performed_checks = [
        {"name": "task-contract", "status": "PASS"},
        {"name": "pack-build", "status": "PASS"},
        {"name": "pack-verify", "status": "PASS"},
    ]
    passed_checks = {check["name"] for check in performed_checks}
    required_checks = summary["acceptance"]["required_checks"]
    pending_checks = [check for check in required_checks if check not in passed_checks]
    if pending_checks:
        outcome = "NEEDS_ATTENTION"
        result_summary = (
            "Capability Pack built and structurally verified; required checks remain: "
            + ", ".join(pending_checks)
            + ". Signing, publishing, device assignment, and Windows HIL were not "
            "performed."
        )
        acceptance_condition = {
            "type": "AcceptanceComplete",
            "status": "False",
            "reason": "RequiredChecksPending",
            "message": "Required checks not reported as PASS: "
            + ", ".join(pending_checks),
        }
    else:
        outcome = "COMPLETED"
        result_summary = (
            "Capability Pack built and structurally verified; signing, publishing, "
            "device assignment, and Windows HIL were not performed."
        )
        acceptance_condition = {
            "type": "AcceptanceComplete",
            "status": "True",
            "reason": "AllRequiredChecksPassed",
            "message": "Every declared required check was reported as PASS.",
        }
    try:
        artifact_location = (
            artifact_path.resolve().relative_to(repo_root.resolve()).as_posix()
        )
    except ValueError:
        artifact_location = str(artifact_path.resolve())
    try:
        source_location = (
            source_manifest_path.resolve().relative_to(repo_root.resolve()).as_posix()
        )
    except ValueError:
        source_location = str(source_manifest_path.resolve())
    revision, dirty = _git_state(repo_root)
    result = {
        "api_version": RESULT_API_VERSION,
        "kind": "CapabilityDevelopmentResult",
        "metadata": {
            "task_id": summary["task_id"],
            "observed_generation": summary["generation"],
            "completed_at": _now_utc(),
        },
        "status": {
            "outcome": outcome,
            "summary": result_summary,
            "conditions": [
                {
                    "type": "TaskContractValid",
                    "status": "True",
                    "reason": "Validated",
                    "message": (
                        "task.json passed AIOS Task Bundle v0.1alpha1 validation."
                    ),
                },
                {
                    "type": "PackBuilt",
                    "status": "True",
                    "reason": "DeterministicBuilderCompleted",
                    "message": "The Capability Pack builder completed successfully.",
                },
                {
                    "type": "PackVerified",
                    "status": "True",
                    "reason": "ArtifactStructureVerified",
                    "message": (
                        "The final ZIP structure, sizes, and component hashes match."
                    ),
                },
                acceptance_condition,
            ],
        },
        "delivery": {
            "capability": {
                "capability_id": capability["capability_id"],
                "version": capability["version"],
                "display_name": capability["display_name"],
            },
            "artifacts": [
                {
                    "role": "capability-pack",
                    "media_type": "application/zip",
                    "location": artifact_location,
                    "size_bytes": artifact_size,
                    "sha256": artifact_sha256,
                }
            ],
            "source": {
                "revision": revision,
                "dirty": dirty,
                "source_manifest": source_location,
                "source_manifest_sha256": source_manifest_sha256,
            },
            "validation": {
                "performed_checks": performed_checks,
                "declared_required_checks": required_checks,
            },
            "adapter_required": capability["adapter_required"],
            "known_limitations": capability["known_limitations"],
        },
    }
    validate_result(result, task=task)
    return result


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_target(value: Any) -> dict[str, Any]:
    target = _mapping(value, "spec.target")
    _allow_fields(
        target,
        {"environment", "repository", "device_id", "assignment_id"},
        {"environment"},
        "spec.target",
    )
    environment = _enum(target, "environment", ENVIRONMENTS, "spec.target")
    result: dict[str, Any] = {"environment": environment}
    for field in ("repository", "device_id", "assignment_id"):
        if field in target:
            result[field] = _text(target, field, "spec.target")
    if "repository" not in result and "device_id" not in result:
        raise TaskBundleError(
            "spec.target requires repository or device_id"
        )
    return result


def _validate_capability(value: Any) -> dict[str, Any]:
    capability = _mapping(value, "spec.capability")
    _allow_fields(
        capability,
        {
            "capability_id",
            "version",
            "display_name",
            "source_manifest",
            "adapter_required",
            "known_limitations",
        },
        {
            "capability_id",
            "version",
            "display_name",
            "source_manifest",
            "adapter_required",
            "known_limitations",
        },
        "spec.capability",
    )
    capability_id = _identifier(
        capability, "capability_id", CAPABILITY_ID, "spec.capability"
    )
    version = _identifier(capability, "version", SEMVER, "spec.capability")
    display_name = _text(capability, "display_name", "spec.capability")
    source_manifest = _relative_path(
        _text(capability, "source_manifest", "spec.capability"),
        "spec.capability.source_manifest",
    )
    adapter_required = capability.get("adapter_required")
    if not isinstance(adapter_required, bool):
        raise TaskBundleError("spec.capability.adapter_required must be boolean")
    known_limitations = _text_array(
        capability.get("known_limitations"),
        "spec.capability.known_limitations",
        allow_empty=True,
    )
    return {
        "capability_id": capability_id,
        "version": version,
        "display_name": display_name,
        "source_manifest": source_manifest,
        "adapter_required": adapter_required,
        "known_limitations": known_limitations,
    }


def _validate_result_capability(value: Any) -> dict[str, Any]:
    capability = _mapping(value, "delivery.capability")
    _require_fields(
        capability,
        {"capability_id", "version", "display_name"},
        "delivery.capability",
    )
    return {
        "capability_id": _identifier(
            capability,
            "capability_id",
            CAPABILITY_ID,
            "delivery.capability",
        ),
        "version": _identifier(
            capability, "version", SEMVER, "delivery.capability"
        ),
        "display_name": _text(
            capability, "display_name", "delivery.capability"
        ),
    }


def _validate_artifacts(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TaskBundleError(f"{label} must be an array")
    result: list[dict[str, Any]] = []
    for index, artifact_value in enumerate(value):
        item_label = f"{label}[{index}]"
        artifact = _mapping(artifact_value, item_label)
        _require_fields(
            artifact,
            {"role", "media_type", "location", "size_bytes", "sha256"},
            item_label,
        )
        size = artifact.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise TaskBundleError(f"{item_label}.size_bytes must be non-negative")
        digest = _text(artifact, "sha256", item_label)
        if not SHA256.fullmatch(digest):
            raise TaskBundleError(f"{item_label}.sha256 must be lowercase SHA-256")
        result.append(
            {
                "role": _text(artifact, "role", item_label),
                "media_type": _text(artifact, "media_type", item_label),
                "location": _text(artifact, "location", item_label),
                "size_bytes": size,
                "sha256": digest,
            }
        )
    return result


def _validate_human_actions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TaskBundleError("spec.human_actions must be an array")
    result: list[dict[str, Any]] = []
    for index, action_value in enumerate(value):
        label = f"spec.human_actions[{index}]"
        action = _mapping(action_value, label)
        _allow_fields(
            action,
            {"type", "required", "component", "instructions"},
            {"type", "required"},
            label,
        )
        required = action.get("required")
        if not isinstance(required, bool):
            raise TaskBundleError(f"{label}.required must be boolean")
        item: dict[str, Any] = {
            "type": _text(action, "type", label),
            "required": required,
        }
        for field in ("component", "instructions"):
            if field in action:
                item[field] = _text(action, field, label)
        result.append(item)
    return result


def _validate_acceptance(value: Any) -> dict[str, list[str]]:
    acceptance = _mapping(value, "spec.acceptance")
    _require_fields(
        acceptance,
        {"required_checks", "deliverables", "forbidden_changes"},
        "spec.acceptance",
    )
    return {
        field: _text_array(
            acceptance.get(field), f"spec.acceptance.{field}", allow_empty=False
        )
        for field in ("required_checks", "deliverables", "forbidden_changes")
    }


def _validate_secrets_policy(value: Any) -> dict[str, list[str]]:
    policy = _mapping(value, "spec.secrets_policy")
    _require_fields(
        policy,
        {"bundle_must_not_contain"},
        "spec.secrets_policy",
    )
    return {
        "bundle_must_not_contain": _text_array(
            policy.get("bundle_must_not_contain"),
            "spec.secrets_policy.bundle_must_not_contain",
            allow_empty=False,
        )
    }


def _validate_result_validation(value: Any) -> dict[str, Any]:
    validation = _mapping(value, "delivery.validation")
    _require_fields(
        validation,
        {"performed_checks", "declared_required_checks"},
        "delivery.validation",
    )
    checks = validation.get("performed_checks")
    if not isinstance(checks, list) or not checks:
        raise TaskBundleError(
            "delivery.validation.performed_checks must be a non-empty array"
        )
    names: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, check_value in enumerate(checks):
        label = f"delivery.validation.performed_checks[{index}]"
        check = _mapping(check_value, label)
        _require_fields(check, {"name", "status"}, label)
        name = _text(check, "name", label)
        if name in names:
            raise TaskBundleError(
                "delivery.validation.performed_checks names must be unique"
            )
        names.add(name)
        status = _enum(check, "status", {"PASS", "FAIL", "NOT_RUN"}, label)
        normalized.append({"name": name, "status": status})
    return {
        "performed_checks": normalized,
        "declared_required_checks": _text_array(
            validation.get("declared_required_checks"),
            "delivery.validation.declared_required_checks",
            allow_empty=True,
        ),
    }


def _validate_source(value: Any) -> dict[str, Any]:
    source = _mapping(value, "delivery.source")
    _require_fields(
        source,
        {"revision", "dirty", "source_manifest", "source_manifest_sha256"},
        "delivery.source",
    )
    dirty = source.get("dirty")
    if not isinstance(dirty, bool):
        raise TaskBundleError("delivery.source.dirty must be boolean")
    digest = _text(source, "source_manifest_sha256", "delivery.source")
    if not SHA256.fullmatch(digest):
        raise TaskBundleError(
            "delivery.source.source_manifest_sha256 must be lowercase SHA-256"
        )
    return {
        "revision": _text(source, "revision", "delivery.source"),
        "dirty": dirty,
        "source_manifest": _text(source, "source_manifest", "delivery.source"),
        "source_manifest_sha256": digest,
    }


def _repo_file(repo_root: Path, path: str, label: str) -> Path:
    relative = _relative_path(path, label)
    resolved = (repo_root.resolve() / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as error:
        raise TaskBundleError(f"{label} leaves repo root") from error
    return resolved


def _relative_path(value: str, label: str) -> str:
    if not value or "\\" in value:
        raise TaskBundleError(f"{label} must be a POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TaskBundleError(f"{label} must be a safe POSIX relative path")
    return path.as_posix()


def _git_state(repo_root: Path) -> tuple[str, bool]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE", True
    return revision, dirty


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TaskBundleError(f"{label} must be an object")
    return value


def _require_fields(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        missing = sorted(fields - set(value))
        unknown = sorted(set(value) - fields)
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise TaskBundleError(f"{label} fields are invalid: {'; '.join(details)}")


def _allow_fields(
    value: Mapping[str, Any],
    allowed: set[str],
    required: set[str],
    label: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown {', '.join(sorted(unknown))}")
        raise TaskBundleError(f"{label} fields are invalid: {'; '.join(details)}")


def _text(value: Mapping[str, Any], field: str, prefix: str = "") -> str:
    item = value.get(field)
    label = f"{prefix}.{field}" if prefix else field
    if not isinstance(item, str) or not item.strip():
        raise TaskBundleError(f"{label} must be a non-empty string")
    return item.strip()


def _identifier(
    value: Mapping[str, Any],
    field: str,
    pattern: re.Pattern[str],
    prefix: str = "",
) -> str:
    item = _text(value, field, prefix)
    label = f"{prefix}.{field}" if prefix else field
    if not pattern.fullmatch(item):
        raise TaskBundleError(f"{label} has an invalid format")
    return item


def _enum(
    value: Mapping[str, Any],
    field: str,
    choices: set[str],
    prefix: str = "",
) -> str:
    item = _text(value, field, prefix)
    label = f"{prefix}.{field}" if prefix else field
    if item not in choices:
        raise TaskBundleError(f"{label} must be one of {', '.join(sorted(choices))}")
    return item


def _text_array(value: Any, label: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise TaskBundleError(f"{label} must be {qualifier}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TaskBundleError(f"{label} items must be non-empty strings")
        result.append(item.strip())
    if len(result) != len(set(result)):
        raise TaskBundleError(f"{label} must not contain duplicates")
    return result


def _timestamp(value: Mapping[str, Any], field: str) -> datetime:
    prefix = "metadata" if field != "completed_at" else "result.metadata"
    raw = _text(value, field, prefix)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise TaskBundleError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise TaskBundleError(f"{field} must include a timezone")
    return parsed


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TaskBundleError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise TaskBundleError(f"{label} must contain a JSON object")
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
