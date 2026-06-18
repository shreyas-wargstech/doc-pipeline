
from __future__ import annotations

import boto3
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

def build_and_deploy_lambda_images():
    """Build Docker images for Lambda stages and deploy them to ECR."""
    region = "ap-south-1"
    account = "082688269612"
    env = "production"
    
    ecr = boto3.client("ecr", region_name=region)
    lambda_client = boto3.client("lambda", region_name=region)
    
    # Create ECR repos if they don't exist
    repos = [f"docintel-{env}-ocr", f"docintel-{env}-light", f"docintel-{env}-persist-index"]
    for repo in repos:
        try:
            ecr.describe_repositories(repositoryNames=[repo])
            print(f"ECR repo exists: {repo}")
        except ecr.exceptions.RepositoryNotFoundException:
            ecr.create_repository(
                repositoryName=repo,
                imageScanningConfiguration={"scanOnPush": True},
            )
            print(f"Created ECR repo: {repo}")
    
    # Build images using Docker
    docker_path = "/c/Program Files/Docker/Docker/resources/bin"
    os.environ["PATH"] = docker_path + os.pathsep + os.environ.get("PATH", "")
    
    # Generate requirements.txt
    print("Generating requirements.txt...")
    subprocess.run(["uv", "export", "--no-dev", "--no-hashes", "-o", "requirements.txt"], check=True)
    
    # Build OCR image
    print("Building OCR image...")
    subprocess.run([
        "docker", "build",
        "--platform", "linux/amd64",
        "-f", "infra/docker/Dockerfile.ocr",
        "-t", f"{account}.dkr.ecr.{region}.amazonaws.com/docintel-{env}-ocr:latest",
        ".",
    ], check=True)
    
    # Login to ECR and push
    print("Pushing OCR image...")
    login_password = subprocess.run(
        ["aws", "ecr", "get-login-password", "--region", region],
        capture_output=True, text=True, check=True,
    ).stdout
    subprocess.run(
        ["docker", "login", "--username", "AWS", "--password-stdin", f"{account}.dkr.ecr.{region}.amazonaws.com"],
        input=login_password, text=True, capture_output=True, check=True,
    )
    subprocess.run(
        ["docker", "push", f"{account}.dkr.ecr.{region}.amazonaws.com/docintel-{env}-ocr:latest"],
        check=True,
    )
    
    # Update Lambda functions to use container images
    image_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/docintel-{env}-ocr:latest"
    
    functions = {
        f"docintel-{env}-ocr": {"Command": ["cloud.ocr.consumer.handler"]},
        f"docintel-{env}-vlm": {"Command": ["cloud.lambda.vlm.handler.lambda_handler"]},
        f"docintel-{env}-structure": {"Command": ["cloud.lambda.structure.handler.lambda_handler"]},
        f"docintel-{env}-match": {"Command": ["cloud.lambda.match.handler.lambda_handler"]},
        f"docintel-{env}-persist": {"Command": ["cloud.lambda.persist.handler.lambda_handler"]},
        f"docintel-{env}-index": {"Command": ["cloud.lambda.index.handler.lambda_handler"]},
    }
    
    for func_name, image_config in functions.items():
        print(f"Updating {func_name} to use container image...")
        lambda_client.update_function_code(
            FunctionName=func_name,
            ImageUri=image_uri,
            Publish=False,
        )
        lambda_client.update_function_configuration(
            FunctionName=func_name,
            ImageConfig={"Command": image_config["Command"]},
        )
        print(f"  Updated {func_name}")
    
    print("All Lambda functions updated to use container images")

if __name__ == "__main__":
    build_and_deploy_lambda_images()
