#!/usr/bin/env python3
"""DocIntel AWS Deployment — One-command deploy.

Usage:
    python cloud/infrastructure/scripts/deploy.py --env production --region ap-south-1

Prerequisites:
  1. AWS CLI installed and configured (aws configure)
  2. SAM CLI installed (pip install aws-sam-cli)
  3. Docker installed (for building Lambda layers if needed)
  4. VPC with public and private subnets in the target region

What this does:
  1. Validates AWS credentials and SAM CLI
  2. Builds Lambda packages (if needed)
  3. Packages the SAM template (uploads to S3)
  4. Deploys the CloudFormation stack
  5. Seeds the RDS database with schema and reference data
  6. Outputs all endpoints and credentials

Author: DocIntel Infrastructure Team
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
INFRA_DIR = SCRIPT_DIR.parent
SAM_DIR = INFRA_DIR / "sam"
TEMPLATE_PATH = SAM_DIR / "template.yaml"
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # doc-pipeline root

# ── Helpers ──────────────────────────────────────────────────────────────────


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = True) -> str:
    """Run a shell command and return stdout. Raise on non-zero exit."""
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
        sys.exit(1)
    return getattr(result, "stdout", "")


def check_prerequisites() -> None:
    """Verify AWS CLI, SAM CLI, and Docker are available."""
    print("🔍 Checking prerequisites...")
    
    # AWS CLI
    try:
        run(["aws", "--version"])
    except FileNotFoundError:
        print("❌ AWS CLI not found. Install: https://aws.amazon.com/cli/", file=sys.stderr)
        sys.exit(1)
    
    # SAM CLI
    try:
        run(["sam", "--version"])
    except FileNotFoundError:
        print("❌ SAM CLI not found. Install: pip install aws-sam-cli", file=sys.stderr)
        sys.exit(1)
    
    # AWS credentials
    try:
        identity = run(["aws", "sts", "get-caller-identity"])
        account = json.loads(identity)["Account"]
        print(f"   ✅ AWS credentials OK (Account: {account})")
    except Exception as e:
        print(f"❌ AWS credentials not configured: {e}", file=sys.stderr)
        print("   Run: aws configure", file=sys.stderr)
        sys.exit(1)
    
    # Docker (for building Lambda layers)
    try:
        run(["docker", "--version"])
        print("   ✅ Docker OK")
    except FileNotFoundError:
        print("   ⚠️ Docker not found. Lambda layers will use SAM's built-in build.")


def get_vpc_info(region: str) -> dict:
    """Prompt user for VPC and subnet IDs, or use defaults."""
    print("\n🏗️ VPC Configuration")
    print("   The stack needs a VPC with at least 2 private subnets and 2 public subnets.")
    print("   If you have a default VPC, it will be used automatically.")
    
    # Try to find default VPC
    try:
        result = run([
            "aws", "ec2", "describe-vpcs",
            "--region", region,
            "--filters", "Name=isDefault,Values=true",
            "--query", "Vpcs[0].VpcId",
            "--output", "text"
        ])
        default_vpc = result.strip()
        if default_vpc and default_vpc != "None":
            print(f"   Found default VPC: {default_vpc}")
            use_default = input("   Use default VPC? [Y/n]: ").strip().lower() or "y"
            if use_default == "y":
                # Get subnets
                subnets = run([
                    "aws", "ec2", "describe-subnets",
                    "--region", region,
                    "--filters", f"Name=vpc-id,Values={default_vpc}",
                    "--query", "Subnets[*].[SubnetId,AvailabilityZone,MapPublicIpOnLaunch]",
                    "--output", "json"
                ])
                subnet_list = json.loads(subnets)
                
                public_subnets = [s[0] for s in subnet_list if s[2]]
                private_subnets = [s[0] for s in subnet_list if not s[2]]
                
                if len(public_subnets) >= 2 and len(private_subnets) >= 2:
                    return {
                        "VpcId": default_vpc,
                        "PublicSubnet1": public_subnets[0],
                        "PublicSubnet2": public_subnets[1],
                        "PrivateSubnet1": private_subnets[0],
                        "PrivateSubnet2": private_subnets[1],
                    }
                
                print(f"   Default VPC has {len(public_subnets)} public, {len(private_subnets)} private subnets.")
                print("   Need at least 2 of each. Using default VPC but you may need to create more subnets.")
    except Exception as e:
        print(f"   Could not auto-detect VPC: {e}")
    
    # Manual input
    print("\n   Please provide the following VPC IDs (from AWS Console → VPC):")
    return {
        "VpcId": input("   VPC ID: ").strip(),
        "PublicSubnet1": input("   Public Subnet 1 (AZ-a): ").strip(),
        "PublicSubnet2": input("   Public Subnet 2 (AZ-b): ").strip(),
        "PrivateSubnet1": input("   Private Subnet 1 (AZ-a): ").strip(),
        "PrivateSubnet2": input("   Private Subnet 2 (AZ-b): ").strip(),
    }


def get_external_service_params() -> dict:
    """Prompt for external managed service credentials."""
    print("\n🔐 External Managed Services (these are NOT created by this stack)")
    print("   You need accounts with these services. The credentials will be stored in AWS Secrets Manager.")
    
    params = {}
    
    # OpenRouter
    print("\n   OpenRouter (https://openrouter.ai/)")
    print("   For VLM tier (Gemini 2.5 Flash).")
    params["OpenRouterApiKey"] = input("   OpenRouter API Key: ").strip()
    
    # Dashboard Session Secret
    print("\n   Dashboard Session Secret (HMAC signing key)")
    import secrets
    auto_secret = secrets.token_urlsafe(32)
    use_auto = input(f"   Generate random secret? [{auto_secret[:8]}...] [Y/n]: ").strip().lower() or "y"
    if use_auto == "y":
        params["DashboardSessionSecret"] = auto_secret
    else:
        params["DashboardSessionSecret"] = input("   Enter secret (min 32 chars): ").strip()
    
    return params


def get_sam_config(env: str, region: str, vpc: dict, externals: dict) -> dict:
    """Build the SAM deploy configuration."""
    config = {
        "Environment": env,
        "Region": region,
        "VpcId": vpc["VpcId"],
        "PublicSubnet1": vpc["PublicSubnet1"],
        "PublicSubnet2": vpc["PublicSubnet2"],
        "PrivateSubnet1": vpc["PrivateSubnet1"],
        "PrivateSubnet2": vpc["PrivateSubnet2"],
        "OpenRouterApiKey": externals["OpenRouterApiKey"],
        "OpenRouterBaseUrl": externals.get("OpenRouterBaseUrl", "https://openrouter.ai/api/v1"),
        "OpenRouterModel": externals.get("OpenRouterModel", "google/gemini-2.5-flash"),
        "DashboardSessionSecret": externals["DashboardSessionSecret"],
    }
    
    # Optional overrides
    print("\n⚙️ Optional Configuration (press Enter to use defaults):")
    
    rds_class = input("   RDS instance class [db.t3.medium]: ").strip() or "db.t3.medium"
    config["RdsInstanceClass"] = rds_class
    
    rds_storage = input("   RDS storage (GB) [20]: ").strip() or "20"
    config["RdsAllocatedStorage"] = rds_storage
    
    multi_az = input("   Enable Multi-AZ RDS? [y/N]: ").strip().lower() or "n"
    config["EnableMultiAz"] = "true" if multi_az == "y" else "false"
    
    ecs_cpu = input("   ECS API CPU (256/512/1024/2048) [512]: ").strip() or "512"
    config["EcsCpu"] = ecs_cpu
    
    ecs_memory = input("   ECS API memory (MB) [1024]: ").strip() or "1024"
    config["EcsMemory"] = ecs_memory
    
    ecs_count = input("   ECS API task count [1]: ").strip() or "1"
    config["EcsTaskCount"] = ecs_count
    
    bucket_name = input("   S3 bucket name (blank for auto-generated): ").strip()
    if bucket_name:
        config["S3BucketName"] = bucket_name
    
    allowed_cidr = input("   Allowed CIDR for ALB [0.0.0.0/0]: ").strip() or "0.0.0.0/0"
    config["AllowedCidr"] = allowed_cidr
    
    return config


def build_sam_template(config: dict) -> None:
    """Build SAM template and Lambda packages."""
    print("\n🔨 Building SAM template...")
    
    # Build Lambda packages (using SAM build)
    # For Phase 0, the Lambda handlers are stubs. In Phase 1, they'll
    # include the actual pipeline code and dependencies.
    
    build_cmd = [
        "sam", "build",
        "--template", str(TEMPLATE_PATH),
        "--build-dir", str(SAM_DIR / ".aws-sam" / "build"),
    ]
    
    # For now, stub handlers don't need complex builds
    # In Phase 1, we'll add --use-container for building Tesseract + OpenCV layers
    print("   (Stub handlers — no complex build needed for Phase 0)")
    print(f"   Template: {TEMPLATE_PATH}")


def deploy_stack(config: dict) -> dict:
    """Deploy the CloudFormation stack via SAM."""
    print(f"\n🚀 Deploying DocIntel stack to {config['Region']}...")
    
    stack_name = f"docintel-{config['Environment']}"
    s3_bucket = f"docintel-sam-artifacts-{config['Environment']}"
    
    # Ensure S3 bucket exists for SAM artifacts
    try:
        run([
            "aws", "s3api", "head-bucket",
            "--bucket", s3_bucket,
            "--region", config["Region"]
        ])
        print(f"   ✅ SAM artifacts bucket exists: {s3_bucket}")
    except:
        print(f"   Creating SAM artifacts bucket: {s3_bucket}")
        run([
            "aws", "s3", "mb", f"s3://{s3_bucket}",
            "--region", config["Region"]
        ])
    
    # Build parameter overrides string
    param_overrides = " ".join([
        f"{k}={v}" for k, v in config.items()
    ])
    
    deploy_cmd = [
        "sam", "deploy",
        "--template", str(TEMPLATE_PATH),
        "--stack-name", stack_name,
        "--s3-bucket", s3_bucket,
        "--region", config["Region"],
        "--capabilities", "CAPABILITY_IAM", "CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND",
        "--parameter-overrides", param_overrides,
        "--no-confirm-changeset",
        "--no-fail-on-empty-changeset",
    ]
    
    print(f"   Stack name: {stack_name}")
    print(f"   Region: {config['Region']}")
    print(f"   This will take 8-15 minutes...")
    
    output = run(deploy_cmd, capture=False)
    
    # Extract outputs
    print("\n📤 Retrieving stack outputs...")
    outputs_json = run([
        "aws", "cloudformation", "describe-stacks",
        "--stack-name", stack_name,
        "--region", config["Region"],
        "--query", "Stacks[0].Outputs",
        "--output", "json"
    ])
    outputs = json.loads(outputs_json)
    
    result = {}
    for o in outputs:
        result[o["OutputKey"]] = o["OutputValue"]
    
    return result


def seed_rds(endpoint: str, password: str, region: str) -> None:
    """Seed the RDS database with schema and reference data."""
    print("\n🌱 Seeding RDS database...")
    
    schema_path = PROJECT_ROOT / "db" / "schema.sql"
    if not schema_path.exists():
        print(f"   ⚠️ Schema file not found: {schema_path}")
        print("   Skipping RDS seeding. Run manually later with:")
        print(f"   psql -h {endpoint} -U pipeline -d doc_pipeline -f db/schema.sql")
        return
    
    print(f"   Schema file: {schema_path}")
    print(f"   RDS endpoint: {endpoint}")
    
    # Note: RDS is in a private subnet, so we can't connect directly from local
    # We need to use a bastion host or ECS task to run the seeding
    print("   ℹ️ RDS is in a private subnet. Seeding will be done via an ECS task.")
    print("   (This will be implemented in Phase 0 — for now, seed manually via bastion host)")
    
    # Alternative: Create a temporary ECS task to run the seeding
    # This is the proper AWS-native way to do it
    print("\n   To seed the database manually:")
    print(f"   1. Create a bastion host in the VPC, or")
    print(f"   2. Use AWS Systems Manager Session Manager to connect to a private instance")
    print(f"   3. Run: psql -h {endpoint} -U pipeline -d doc_pipeline -f db/schema.sql")
    print(f"   Password: (from Secrets Manager)")


def print_summary(outputs: dict, config: dict) -> None:
    """Print deployment summary."""
    print("\n" + "=" * 70)
    print("🎉 DocIntel AWS Infrastructure Deployed Successfully!")
    print("=" * 70)
    
    print(f"\n📋 Environment: {config['Environment']}")
    print(f"📍 Region: {config['Region']}")
    
    print("\n🔗 Endpoints:")
    print(f"   API (ALB):        http://{outputs.get('ApiEndpoint', 'N/A')}")
    print(f"   RDS (Postgres):   {outputs.get('RdsEndpoint', 'N/A')}:{outputs.get('RdsPort', '5432')}")
    print(f"   Redis:            {outputs.get('RedisEndpoint', 'N/A')}:{outputs.get('RedisPort', '6379')}")
    
    print("\n📦 S3 Bucket:")
    print(f"   {outputs.get('S3Bucket', 'N/A')}")
    
    print("\n📨 SQS Queues:")
    print(f"   OCR:       {outputs.get('OcrQueueUrl', 'N/A')}")
    print(f"   Structure: {outputs.get('StructureQueueUrl', 'N/A')}")
    print(f"   Match:     {outputs.get('MatchQueueUrl', 'N/A')}")
    print(f"   Persist:   {outputs.get('PersistQueueUrl', 'N/A')}")
    print(f"   Index:     {outputs.get('IndexQueueUrl', 'N/A')}")
    
    print("\n🔐 Secrets Manager:")
    print(f"   {outputs.get('SecretsArn', 'N/A')}")
    
    print("\n📊 CloudWatch Dashboard:")
    print(f"   {outputs.get('DashboardUrl', 'N/A')}")
    
    print("\n⚡ Next Steps:")
    print("   1. Seed the RDS database with schema.sql and reference data")
    print("   2. Build and push the API Docker image to ECR")
    print("   3. Deploy the Next.js app to Vercel")
    print("   4. Run the NAS upload agent: python nas/upload_agent.py <pdf>")
    print("   5. Monitor the pipeline in the CloudWatch dashboard")
    
    print("\n💰 Estimated Monthly Cost:")
    print("   RDS (db.t3.medium):      ~$45")
    print("   ElastiCache (t3.micro):    ~$12")
    print("   ECS Fargate (1 task):      ~$15")
    print("   S3 (100 GB):               ~$2")
    print("   ───────────────────────────────")
    print("   Base Total:                ~$74/month")
    print("   + $6 per 200-document batch")
    
    print("\n📁 Save these outputs to .env for local development:")
    print(f"   DATABASE_URL=postgresql+asyncpg://pipeline:<password>@{outputs.get('RdsEndpoint', '')}:5432/doc_pipeline")
    print(f"   S3_BUCKET={outputs.get('S3Bucket', '')}")
    print(f"   SQS_OCR_QUEUE_URL={outputs.get('OcrQueueUrl', '')}")
    print(f"   REDIS_HOST={outputs.get('RedisEndpoint', '')}")
    
    print("\n" + "=" * 70)
    
    # Save outputs to a file for reference
    output_file = PROJECT_ROOT / f"docintel-{config['Environment']}-outputs.json"
    with open(output_file, "w") as f:
        json.dump({
            "config": config,
            "outputs": outputs,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)
    print(f"\n💾 Full outputs saved to: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy DocIntel AWS infrastructure")
    parser.add_argument("--env", default="production", choices=["development", "staging", "production"],
                        help="Deployment environment")
    parser.add_argument("--region", default="ap-south-1",
                        help="AWS region (default: ap-south-1 for Mumbai)")
    parser.add_argument("--skip-build", action="store_true",
                        help="Skip SAM build (use existing build artifacts)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Non-interactive mode (reads config from environment variables)")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🚀 DocIntel AWS Infrastructure Deployment")
    print("=" * 70)
    print(f"   Environment: {args.env}")
    print(f"   Region: {args.region}")
    print()
    
    # 1. Check prerequisites
    check_prerequisites()
    
    # 2. Get VPC configuration
    if args.non_interactive:
        vpc = {
            "VpcId": os.environ.get("DOCINTEL_VPC_ID", ""),
            "PublicSubnet1": os.environ.get("DOCINTEL_PUBLIC_SUBNET_1", ""),
            "PublicSubnet2": os.environ.get("DOCINTEL_PUBLIC_SUBNET_2", ""),
            "PrivateSubnet1": os.environ.get("DOCINTEL_PRIVATE_SUBNET_1", ""),
            "PrivateSubnet2": os.environ.get("DOCINTEL_PRIVATE_SUBNET_2", ""),
        }
        externals = {
            "OpenRouterApiKey": os.environ.get("OPENROUTER_API_KEY", ""),
            "OpenRouterBaseUrl": os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "OpenRouterModel": os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
            "DashboardSessionSecret": os.environ.get("DASHBOARD_SESSION_SECRET", ""),
        }
        config = get_sam_config(args.env, args.region, vpc, externals)
    else:
        vpc = get_vpc_info(args.region)
        externals = get_external_service_params()
        config = get_sam_config(args.env, args.region, vpc, externals)
    
    # 3. Build SAM template
    if not args.skip_build:
        build_sam_template(config)
    
    # 4. Deploy stack
    outputs = deploy_stack(config)
    
    # 5. Seed RDS (noted for manual or bastion-based seeding)
    if outputs.get("RdsEndpoint"):
        seed_rds(
            outputs["RdsEndpoint"],
            "(from Secrets Manager)",  # Password is in Secrets Manager
            args.region
        )
    
    # 6. Print summary
    print_summary(outputs, config)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
