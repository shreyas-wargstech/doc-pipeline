#!/usr/bin/env python3
"""DocIntel AWS Teardown — One-command destroy all resources.

Usage:
    python cloud/infrastructure/scripts/destroy.py --env production --region ap-south-1

⚠️ WARNING: This DESTROYS all DocIntel infrastructure in the target environment.
All data in S3, RDS, SQS, ElastiCache, and Lambda will be DELETED.
This is IRREVERSIBLE. Use with caution.

Author: DocIntel Infrastructure Team
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = True) -> str:
    """Run a shell command and return stdout."""
    kwargs = {}
    if cwd:
        kwargs["cwd"] = str(cwd)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        stderr = getattr(result, "stderr", "")
        stdout = getattr(result, "stdout", "")
        print(f"\n❌ Command failed: {' '.join(cmd)}", file=sys.stderr)
        if stderr:
            print(f"stderr:\n{stderr}", file=sys.stderr)
        if stdout:
            print(f"stdout:\n{stdout}", file=sys.stderr)
    return getattr(result, "stdout", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Destroy DocIntel AWS infrastructure")
    parser.add_argument("--env", default="production", choices=["development", "staging", "production"],
                        help="Environment to destroy")
    parser.add_argument("--region", default="ap-south-1",
                        help="AWS region")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmation prompt (USE WITH CAUTION)")
    
    args = parser.parse_args()
    
    stack_name = f"docintel-{args.env}"
    
    print("=" * 70)
    print("🗑️ DocIntel AWS Infrastructure Teardown")
    print("=" * 70)
    print(f"   Stack: {stack_name}")
    print(f"   Region: {args.region}")
    print()
    
    # Get stack info before deletion
    try:
        outputs_json = run([
            "aws", "cloudformation", "describe-stacks",
            "--stack-name", stack_name,
            "--region", args.region,
            "--query", "Stacks[0].Outputs",
            "--output", "json"
        ])
        outputs = json.loads(outputs_json)
        print("📋 Resources that will be destroyed:")
        for o in outputs:
            print(f"   {o['OutputKey']}: {o['OutputValue']}")
    except:
        print("⚠️ Could not retrieve stack info. It may not exist.")
    
    # Confirmation
    if not args.force:
        print()
        print("⚠️ WARNING: This will PERMANENTLY DELETE:")
        print("   - All S3 documents and their versions")
        print("   - All RDS PostgreSQL data (including reference_data)")
        print("   - All SQS messages and dead-letter queues")
        print("   - All ElastiCache Redis data")
        print("   - All Lambda functions and logs")
        print("   - All ECS services and tasks")
        print("   - All CloudWatch dashboards and alarms")
        print("   - All Secrets (except the KMS key, which is scheduled for deletion)")
        print()
        confirm = input(f"   Type '{stack_name}' to confirm destruction: ").strip()
        if confirm != stack_name:
            print("❌ Confirmation mismatch. Aborting.")
            return 1
    
    print(f"\n🗑️ Deleting stack: {stack_name}...")
    print("   This will take 5-10 minutes...")
    
    run([
        "aws", "cloudformation", "delete-stack",
        "--stack-name", stack_name,
        "--region", args.region
    ], capture=False)
    
    print(f"\n   Waiting for stack deletion to complete...")
    run([
        "aws", "cloudformation", "wait", "stack-delete-complete",
        "--stack-name", stack_name,
        "--region", args.region
    ], capture=False)
    
    print(f"\n✅ Stack '{stack_name}' deleted successfully.")
    
    # Clean up SAM artifacts bucket
    artifact_bucket = f"docintel-sam-artifacts-{args.env}"
    try:
        print(f"\n🧹 Cleaning up SAM artifacts bucket: {artifact_bucket}")
        run([
            "aws", "s3", "rb", f"s3://{artifact_bucket}",
            "--force"
        ], capture=False)
        print(f"   ✅ SAM artifacts bucket deleted.")
    except:
        print(f"   ⚠️ Could not delete SAM artifacts bucket (may not exist or not empty)")
    
    # Clean up ECR repository (if exists)
    ecr_repo = f"docintel-{args.env}-api"
    try:
        print(f"\n🧹 Cleaning up ECR repository: {ecr_repo}")
        run([
            "aws", "ecr", "delete-repository",
            "--repository-name", ecr_repo,
            "--region", args.region,
            "--force"
        ], capture=False)
        print(f"   ✅ ECR repository deleted.")
    except:
        print(f"   ⚠️ Could not delete ECR repository (may not exist)")
    
    # Remove output file
    output_file = PROJECT_ROOT / f"docintel-{args.env}-outputs.json"
    if output_file.exists():
        output_file.unlink()
        print(f"   ✅ Removed output file: {output_file}")
    
    print("\n" + "=" * 70)
    print("🗑️ DocIntel AWS Infrastructure Destroyed")
    print("=" * 70)
    print("\n   All resources have been deleted. To redeploy:")
    print(f"   python cloud/infrastructure/scripts/deploy.py --env {args.env} --region {args.region}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
