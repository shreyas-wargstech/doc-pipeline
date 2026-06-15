"""DocIntel NAS Upload Agent — Zero Docker.

Usage:
    python nas/upload_agent.py <path-to-pdf> [--category practitioner]
    python nas/upload_agent.py <folder-with-pdfs> [--category practitioner] [--batch]
    python nas/upload_agent.py --batch <folder> [--category practitioner] [--workers 4]

This script runs on the local NAS (or any machine) and:
  1. Renders PDF pages to PNG (PyMuPDF)
  2. Preprocesses images (OpenCV: grayscale, denoise, deskew, threshold)
  3. Classifies page type and content type (Tesseract triage)
  4. Uploads original PDF + page PNGs + manifest.json to S3
  5. The manifest.json upload (LAST) triggers the S3 event → SQS → Lambda pipeline

Requirements:
  - Python 3.11+
  - Tesseract OCR (with eng, mar, hin traineddata)
  - OpenCV (cv2)
  - PyMuPDF (fitz)
  - boto3 (AWS SDK)
  - pytesseract
  - Pillow (PIL)
  - numpy

Install: pip install -r nas/requirements.txt

AWS Credentials:
  - Run `aws configure` once, or
  - Set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
  - The IAM user/role needs S3 PutObject permissions on the DocIntel bucket.

Author: DocIntel Infrastructure Team
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from shared.aws_clients import get_s3
from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

DEFAULT_DPI = 300
PREPROCESS_DENOISE = True
PREPROCESS_DESKEW = True
PREPROCESS_THRESHOLD = True

# ── PDF Rendering ────────────────────────────────────────────────────────────


def render_page_to_image(doc: fitz.Document, page_num: int, dpi: int = DEFAULT_DPI) -> np.ndarray:
    """Render a PDF page to a grayscale numpy array (OpenCV format)."""
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 DPI is PDF default
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # Convert to numpy array
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    
    # Convert to grayscale (1 channel)
    if img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
    else:
        img = img[:, :, 0]
    
    return img


# ── Preprocessing ────────────────────────────────────────────────────────────


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Apply the full preprocessing pipeline."""
    img = image.copy()
    
    # 1. Denoise
    if PREPROCESS_DENOISE:
        img = cv2.fastNlMeansDenoising(img, None, h=10, templateWindowSize=7, searchWindowSize=21)
    
    # 2. Deskew (simple projection profile method)
    if PREPROCESS_DESKEW:
        img = deskew_image(img)
    
    # 3. Adaptive threshold (Sauvola / Otsu)
    if PREPROCESS_THRESHOLD:
        img = adaptive_threshold(img)
    
    return img


def deskew_image(image: np.ndarray) -> np.ndarray:
    """Detect and correct skew using Hough transform."""
    # Detect edges
    edges = cv2.Canny(image, 50, 150, apertureSize=3)
    
    # Hough line transform
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)
    
    if lines is None or len(lines) == 0:
        return image
    
    # Calculate median angle of detected lines
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Normalize to [-45, 45] range
        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90
        angles.append(angle)
    
    median_angle = np.median(angles)
    
    if abs(median_angle) < 0.5:  # Already straight
        return image
    
    # Rotate image
    (h, w) = image.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    log.debug("upload_agent.deskewed", angle=median_angle)
    return rotated


def adaptive_threshold(image: np.ndarray) -> np.ndarray:
    """Apply adaptive thresholding (Sauvola or Gaussian)."""
    # Use Gaussian adaptive threshold for simplicity and speed
    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    return binary


# ── Triage (Page Classification) ───────────────────────────────────────────────


def classify_page_type(image: np.ndarray) -> str:
    """Classify page type using Tesseract OCR as a quick pass."""
    import pytesseract
    
    try:
        # Quick OCR to get text content
        text = pytesseract.image_to_string(image, lang="eng+mar+hin", config="--psm 6")
        text_lower = text.lower()
        
        # Keyword-based classification (same as shared/page_type.py)
        if any(k in text_lower for k in ["application", "form", "registration", "amr-mch"]):
            return "form"
        elif any(k in text_lower for k in ["aadhaar", "uid", "uidai"]):
            return "aadhaar"
        elif any(k in text_lower for k in ["ssc", "secondary school", "s.s.c"]):
            return "ssc"
        elif any(k in text_lower for k in ["hsc", "higher secondary", "h.s.c"]):
            return "hsc"
        elif any(k in text_lower for k in ["marks", "statement of marks", "university"]):
            return "marks_statement"
        elif any(k in text_lower for k in ["degree", "bachelor", "bhms", "b.a.m.s", "passing"]):
            return "passing_cert"
        elif any(k in text_lower for k in ["internship", "training"]):
            return "internship_cert"
        elif any(k in text_lower for k in ["provisional", "temporary registration"]):
            return "provisional_reg"
        elif any(k in text_lower for k in ["form e", "name change", "renewal"]):
            return "form_e"
        elif any(k in text_lower for k in ["marriage", "married"]):
            return "marriage_cert"
        elif any(k in text_lower for k in ["receipt", "challan", "sbi", "payment"]):
            return "sbi_receipt"
        elif any(k in text_lower for k in ["birth certificate", "birth"]):
            return "birth_certificate"
        
        # Check if blank (low variance)
        variance = np.var(image)
        if variance < 100:
            return "blank"
        
        return "other"
    except Exception as exc:
        log.warning("upload_agent.page_type_failed", error=str(exc))
        return "other"


def classify_content_type(image: np.ndarray) -> str:
    """Classify content type: typed, handwritten, or unknown."""
    # Simple heuristic: compute stroke density and height variance
    # (Full implementation would use the triage logic from nas/preprocess/triage.py)
    
    # Edge detection
    edges = cv2.Canny(image, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size
    
    # Contour analysis
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return "unknown"
    
    # Compute height variance of contours
    heights = [cv2.boundingRect(c)[3] for c in contours if cv2.boundingRect(c)[3] > 5]
    if not heights:
        return "unknown"
    
    height_cv = np.std(heights) / np.mean(heights) if np.mean(heights) > 0 else 0
    
    # Simple thresholds (these should be calibrated)
    if height_cv > 1.10 and edge_density > 0.01:
        return "handwritten"
    elif edge_density > 0.01:
        return "typed"
    else:
        return "unknown"


# ── Upload ───────────────────────────────────────────────────────────────────


async def upload_pdf_bundle(pdf_path: Path, category: str = "practitioner") -> str:
    """Process a single PDF and upload to S3.
    
    Returns the document_id (first 16 chars of SHA-256).
    """
    s = get_settings()
    bucket = s.s3_bucket
    
    if not bucket:
        raise ValueError("S3_BUCKET not configured in .env")
    
    # 1. Compute document_id
    file_bytes = pdf_path.read_bytes()
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    doc_id = sha256[:16]  # Shortened ID for readability
    prefix = f"documents/{doc_id}"
    
    log.info("upload_agent.start", document_id=doc_id, path=str(pdf_path), category=category)
    
    # 2. Upload original PDF
    s3 = get_s3()
    original_key = f"{prefix}/original.pdf"
    s3.put_object(Bucket=bucket, Key=original_key, Body=file_bytes)
    log.info("upload_agent.pdf_uploaded", key=original_key, size=len(file_bytes))
    
    # 3. Render and process pages
    doc = fitz.open(str(pdf_path))
    page_manifests = []
    
    for page_num in range(len(doc)):
        page_idx = page_num + 1  # 1-indexed
        
        # Render
        img = render_page_to_image(doc, page_num)
        
        # Preprocess
        processed = preprocess_image(img)
        
        # Classify
        page_type = classify_page_type(processed)
        content_type = classify_content_type(processed)
        
        # Save to temp file for upload
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            cv2.imwrite(str(tmp_path), processed)
        
        # Upload page image
        page_key = f"{prefix}/pages/page_{page_idx:03d}.png"
        with open(tmp_path, "rb") as f:
            s3.put_object(Bucket=bucket, Key=page_key, Body=f.read())
        
        tmp_path.unlink()
        
        page_manifests.append({
            "page_num": page_idx,
            "s3_key": page_key,
            "page_type": page_type,
            "content_type": content_type,
            "language_hint": "mixed",  # Simplified for now
        })
        
        log.info("upload_agent.page_uploaded", page=page_idx, page_type=page_type, content_type=content_type)
    
    doc.close()
    
    # 4. Build and upload manifest (THIS TRIGGERS THE PIPELINE)
    manifest = {
        "schema_version": 1,
        "document_id": doc_id,
        "original_s3_key": original_key,
        "document_category": category,
        "pages": page_manifests,
    }
    
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    manifest_key = f"{prefix}/manifest.json"
    
    # Upload manifest LAST — this is the trigger for the S3 event → SQS → Lambda
    s3.put_object(Bucket=bucket, Key=manifest_key, Body=manifest_bytes)
    
    log.info("upload_agent.complete", document_id=doc_id, pages=len(page_manifests), 
             manifest_key=manifest_key, bucket=bucket)
    
    return doc_id


async def batch_upload(folder: Path, category: str, workers: int = 4) -> list[str]:
    """Upload all PDFs in a folder concurrently."""
    pdf_files = list(folder.glob("*.pdf"))
    
    if not pdf_files:
        log.warning("upload_agent.no_pdfs", folder=str(folder))
        return []
    
    log.info("upload_agent.batch_start", folder=str(folder), files=len(pdf_files), workers=workers)
    
    # Use asyncio semaphore to limit concurrency
    semaphore = asyncio.Semaphore(workers)
    
    async def upload_with_limit(pdf_path: Path) -> str:
        async with semaphore:
            return await upload_pdf_bundle(pdf_path, category)
    
    tasks = [upload_with_limit(pdf) for pdf in pdf_files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    doc_ids = []
    errors = []
    for pdf, result in zip(pdf_files, results):
        if isinstance(result, Exception):
            log.error("upload_agent.failed", path=str(pdf), error=str(result))
            errors.append((pdf, result))
        else:
            doc_ids.append(result)
    
    log.info("upload_agent.batch_complete", total=len(pdf_files), success=len(doc_ids), failed=len(errors))
    
    if errors:
        print(f"\n⚠️ {len(errors)} files failed:")
        for pdf, exc in errors:
            print(f"   {pdf.name}: {exc}")
    
    return doc_ids


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="DocIntel NAS Upload Agent — Upload PDFs to S3 and trigger cloud pipeline")
    parser.add_argument("path", type=Path, help="Path to PDF file or folder containing PDFs")
    parser.add_argument("--category", default="practitioner", choices=["practitioner", "letter", "receipt", "record", "other"],
                        help="Document category")
    parser.add_argument("--batch", action="store_true", help="Upload all PDFs in the folder")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent upload workers (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")
    
    args = parser.parse_args()
    
    if not args.path.exists():
        print(f"❌ Path not found: {args.path}", file=sys.stderr)
        return 1
    
    # Configure logging
    configure_logging(level="INFO", fmt="console")
    
    # Check settings
    s = get_settings()
    if not s.s3_bucket:
        print("❌ S3_BUCKET not configured. Set it in .env or environment variables.", file=sys.stderr)
        return 1
    
    print(f"📤 DocIntel Upload Agent")
    print(f"   S3 Bucket: {s.s3_bucket}")
    print(f"   Category: {args.category}")
    
    if args.dry_run:
        print("\n🏃 DRY RUN — no uploads will be performed.")
    
    if args.batch or args.path.is_dir():
        # Batch upload
        if not args.path.is_dir():
            print(f"❌ --batch requires a folder, not a file: {args.path}", file=sys.stderr)
            return 1
        
        pdf_files = list(args.path.glob("*.pdf"))
        print(f"\n   Folder: {args.path}")
        print(f"   PDFs found: {len(pdf_files)}")
        
        if args.dry_run:
            for pdf in pdf_files:
                print(f"   Would upload: {pdf.name}")
            return 0
        
        doc_ids = asyncio.run(batch_upload(args.path, args.category, args.workers))
        
        print(f"\n✅ Uploaded {len(doc_ids)} documents.")
        print(f"   Pipeline triggered automatically via S3 event notifications.")
        print(f"   Monitor progress: CloudWatch Dashboard or AWS Console → SQS")
        
    else:
        # Single file upload
        if not args.path.is_file() or args.path.suffix.lower() != ".pdf":
            print(f"❌ Not a PDF file: {args.path}", file=sys.stderr)
            return 1
        
        print(f"\n   File: {args.path.name}")
        print(f"   Size: {args.path.stat().st_size / 1024:.1f} KB")
        
        if args.dry_run:
            print(f"   Would upload: {args.path.name}")
            return 0
        
        doc_id = asyncio.run(upload_pdf_bundle(args.path, args.category))
        
        print(f"\n✅ Document uploaded successfully.")
        print(f"   Document ID: {doc_id}")
        print(f"   S3 Prefix: s3://{s.s3_bucket}/documents/{doc_id}/")
        print(f"   Pipeline triggered automatically.")
        print(f"   Monitor: AWS Console → S3 → Events or CloudWatch → SQS")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
