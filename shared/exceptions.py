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


class ClassifierError(PipelineError):
    """Document classification failed (rules engine or LLM fallback)."""


class TriageError(PipelineError):
    """Page triage failure (OSD, content-type detection)."""


class PreprocessError(PipelineError):
    """Image preprocessing failure (deskew, threshold, etc.)."""


class UploaderError(PipelineError):
    """NAS uploader failure (PDF render, PNG encode, or S3 upload)."""


class OCRError(PipelineError):
    """OCR engine failure or unrecoverable low-confidence result."""


class StructureError(PipelineError):
    """Layout analysis or entity extraction failure."""


class PersistError(PipelineError):
    """Failure persisting to Qdrant, Neo4j, or Postgres."""


class MatchError(PipelineError):
    """Reference-data matching failure (lookup or scoring)."""


class OrchestrationError(PipelineError):
    """Raised by the inter-stage orchestration (sweeper / stage chaining)."""


class IndexingError(PipelineError):
    """Base for all index-stage errors."""


class IndexSummarizationError(IndexingError):
    """LLM summarisation failed or is unavailable."""


class IndexKeywordError(IndexingError):
    """Keyword extraction failed (LLM mode only — TF-IDF path never raises)."""


class IndexEntityError(IndexingError):
    """Entity extraction LLM call failed."""


class IndexWriteError(IndexingError):
    """Failed to write index results to a datastore (Qdrant, Postgres, Neo4j)."""
