"""Pipeline-wide and stage-specific exception types."""


class PipelineError(Exception):
    """Base for all pipeline errors."""


class ConfigError(PipelineError):
    """Configuration loading or validation failed."""


class IngestError(PipelineError):
    """Failure during ingest stage (hashing, S3 upload, DB upsert)."""


class StorageError(PipelineError):
    """S3 or DB I/O failure."""


class ManifestError(PipelineError):
    """Manifest JSON missing, malformed, or schema-invalid."""


class PreprocessError(PipelineError):
    """Image preprocessing failure (deskew, threshold, etc.)."""


class OCRError(PipelineError):
    """OCR engine failure or unrecoverable low-confidence result."""


class StructureError(PipelineError):
    """Layout analysis or entity extraction failure."""


class PersistError(PipelineError):
    """Failure persisting to Qdrant, Neo4j, or Postgres."""
