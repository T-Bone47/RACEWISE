"""Manifest Generator: creates dataset manifest for reproducibility."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ManifestGenerator:
    """Generates dataset manifest for reproducibility and verification."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        if data_dir is None:
            data_dir = os.environ.get("RACEWISE_DATA_DIR", str(Path.cwd() / "data"))
        self.data_dir = Path(data_dir)
        self.manifests_dir = self.data_dir / "manifests"
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _collect_files(self, root: Path, pattern: str = "**/*") -> list[dict]:
        """Collect all files matching pattern with metadata."""
        files = []
        for path in root.glob(pattern):
            if path.is_file():
                stat = path.stat()
                files.append({
                    "path": str(path.relative_to(self.data_dir)),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "sha256": self._hash_file(path),
                })
        return files

    def generate_manifest(
        self,
        include_raw: bool = True,
        include_canonical: bool = True,
        output_path: Optional[str] = None,
    ) -> dict:
        """Generate full dataset manifest."""
        manifest = {
            "generated_at": datetime.utcnow().isoformat(),
            "generator": "RACEWISE ManifestGenerator",
            "schema_version": "1.0",
            "data_directory": str(self.data_dir),
            "files": {},
            "summary": {
                "total_files": 0,
                "total_size_bytes": 0,
                "by_category": {},
            },
        }

        categories = []
        if include_raw:
            categories.append(("raw", self.data_dir / "raw"))
        if include_canonical:
            categories.append(("canonical", self.data_dir / "canonical"))

        for category, path in categories:
            if path.exists():
                files = self._collect_files(path)
                manifest["files"][category] = files
                manifest["summary"]["by_category"][category] = {
                    "count": len(files),
                    "total_size_bytes": sum(f["size_bytes"] for f in files),
                }
                manifest["summary"]["total_files"] += len(files)
                manifest["summary"]["total_size_bytes"] += sum(f["size_bytes"] for f in files)

        # Add manifest hash
        manifest_json = json.dumps(manifest, sort_keys=True).encode()
        manifest["manifest_sha256"] = hashlib.sha256(manifest_json).hexdigest()

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"Manifest written to {output_path}")

        return manifest

    def verify_manifest(self, manifest_path: str) -> dict:
        """Verify a manifest against actual files."""
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        results = {
            "verified": True,
            "missing_files": [],
            "hash_mismatches": [],
            "extra_files": [],
            "checked_count": 0,
        }

        for category, files in manifest.get("files", {}).items():
            for file_info in files:
                path = self.data_dir / file_info["path"]
                results["checked_count"] += 1

                if not path.exists():
                    results["verified"] = False
                    results["missing_files"].append(file_info["path"])
                    continue

                if file_info.get("sha256"):
                    actual_hash = self._hash_file(path)
                    if actual_hash != file_info["sha256"]:
                        results["verified"] = False
                        results["hash_mismatches"].append({
                            "path": file_info["path"],
                            "expected": file_info["sha256"],
                            "actual": actual_hash,
                        })

        return results


def generate_dataset_manifest(data_dir: Optional[str] = None, output: Optional[str] = None) -> dict:
    """Convenience function to generate manifest."""
    generator = ManifestGenerator(data_dir)
    return generator.generate_manifest(output_path=output)


def verify_dataset_manifest(manifest_path: str, data_dir: Optional[str] = None) -> dict:
    """Convenience function to verify manifest."""
    generator = ManifestGenerator(data_dir)
    return generator.verify_manifest(manifest_path)