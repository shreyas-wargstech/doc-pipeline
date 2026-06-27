 Reality check — what's actually deployed, and the trap

  You have two AWS infra definitions in the repo:
  - SAM (cloud/infrastructure/sam/template.yaml) → stack docintel-production in ap-south-1. This is the live one (per PROJECT_MEMORY).
  - Terraform (infra/*.tf) → an alternate dev design (Neptune + pgvector). May or may not be applied.

  The trap: sam delete / terraform destroy will NOT delete everything, and what they do delete includes your processed-document data. Specifically:

  ┌───────────────────────────────────────┬────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────┬───────────────────────────────┐
  │                 Thing                 │                         In the stack?                          │               What deletes it               │          Data loss?           │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ S3 documents bucket (versioned)       │ SAM                                                            │ sam delete (but versioned bucket won't      │ YES — all original PDFs +     │
  │                                       │                                                                │ empty automatically)                        │ page PNGs                     │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ RDS Postgres                          │ NO — externally managed (docintel-production-postgres-public,  │ separate aws rds delete-db-instance         │ YES — all extractions,        │
  │                                       │ created by CLI)                                                │                                             │ matches, registry             │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ Neptune (graph)                       │ Terraform only                                                 │ terraform destroy                           │ YES if TF applied             │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ Qdrant Cloud                          │ SaaS (separate account/billing)                                │ cancel in Qdrant console                    │ YES                           │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ Neo4j Aura                            │ SaaS (separate billing)                                        │ delete in Aura console                      │ YES                           │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ ECR image repos                       │ NO — created by deploy.py                                      │ separate aws ecr delete-repository          │ no (just images)              │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ Terraform state bucket + DynamoDB     │ bootstrap, outside both                                        │ manual                                      │ no                            │
  │ lock                                  │                                                                │                                             │                               │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────┤
  │ ElastiCache Redis, SQS, Lambda, ECS,  │ SAM                                                            │ sam delete                                  │ no (just compute)             │
  │ ALB, KMS, Secrets                     │                                                                │                                             │                               │
  └───────────────────────────────────────┴────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────┴───────────────────────────────┘

  So if you delete AWS first, you lose all processed data unless you migrate it to the NAS first. The correct order is: build NAS → migrate data → then tear down AWS.

  The good news — your NAS target already exists

  Your repo's docker-compose.yml is the Synology deployment. Every AWS managed service has a self-hosted equivalent already wired:

  ┌───────────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │           AWS (now)           │           Synology container (already in your compose)           │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ S3                            │ MinIO                                                            │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ RDS Postgres                  │ postgres:16-alpine                                               │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Qdrant Cloud                  │ qdrant/qdrant                                                    │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Neo4j Aura                    │ neo4j:5-community                                                │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ SQS                           │ ElasticMQ (softwaremill/elasticmq-native)                        │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ ECS Fargate API               │ api container                                                    │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Lambda stage workers          │ local make stage-worker consumers (run as long-lived containers) │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ ElastiCache Redis             │ add one redis:7-alpine container                                 │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ EventBridge (sweeper/monitor) │ DSM Task Scheduler cron, or a small loop container               │
  ├───────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ OpenRouter VLM/LLM            │ stays external — unchanged                                       │
  └───────────────────────────────┴──────────────────────────────────────────────────────────────────┘

  Critical sizing insight: your heavy AI (handwriting VLM + structure LLM) is offloaded to OpenRouter. The NAS only runs Tesseract OCR + a 384-dim MiniLM embedding
  (sentence-transformers/torch CPU). That's light — you do not need a GPU. A DS923+/DS1522+ with 16–32 GB RAM handles this comfortably (Postgres + Neo4j + Qdrant + embeddings are the RAM
  consumers; bump to 32 GB if you batch heavily).

  ---
  Before I write the exact runbooks and execute anything, two decisions are genuinely yours and they change the plan:

● User answered Claude's questions:
  ⎿  · Is there production data in AWS (processed PDFs in S3, extractions/matches in RDS Postgres, graph in Neo4j Aura, vectors in Qdrant) that must survive the move to the NAS? → No — it's
     throwaway
     · Who runs the destructive AWS teardown commands (sam delete, rds delete, SaaS cancellation)? → I run them, you guide
     · Which Synology model is the target (drives hardware sizing in the guide)? → I own a DS925

● Good — that simplifies everything: no migration, delete AWS now, rebuild empty on the NAS, re-ingest source PDFs. Let me confirm DS925+ specs so sizing is accurate, then I'll give you both
  runbooks.

● Web Search("Synology DS925+ specs CPU AMD Ryzen RAM maximum ECC 2.5GbE Container Manager")
  ⎿  Did 1 search in 8s

● DS925+ confirmed: AMD Ryzen V1500B (4-core/8-thread, AVX2), 2× 2.5GbE, ships 4 GB ECC, max 32 GB, no GPU. Perfect fit for this stack — the V1500B's AVX2 handles the MiniLM embeddings fine,
  and the AI heavy-lifting stays on OpenRouter.

  #1 hardware action: upgrade RAM to 32 GB (2×16 GB ECC). 4 GB will not run Postgres + Neo4j + Qdrant + MinIO + embeddings together. This is the single most important prerequisite.

  Here are both runbooks.

  ---
  Part 1 — Tear down AWS (you run these; data is throwaway)

  ▎ Order matters only because a versioned S3 bucket blocks stack deletion until emptied. Account ID 082688269612, region ap-south-1, SAM stack docintel-production.

  1. Empty the versioned documents bucket (required before stack delete)

  BUCKET=docintel-documents-082688269612-production
  # delete all object versions + delete-markers, then the bucket empties
  aws s3api delete-objects --bucket "$BUCKET" --region ap-south-1 \
    --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --region ap-south-1 \
      --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null
  aws s3api delete-objects --bucket "$BUCKET" --region ap-south-1 \
    --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --region ap-south-1 \
      --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null
  (If you have many objects, repeat until list-object-versions returns empty.)

  2. Delete the SAM/CloudFormation stack (Lambda, ECS, ALB, SQS, Redis, KMS, Secrets, S3)

  sam delete --stack-name docintel-production --region ap-south-1 --no-prompts
  # or: aws cloudformation delete-stack --stack-name docintel-production --region ap-south-1
  aws cloudformation wait stack-delete-complete --stack-name docintel-production --region ap-south-1

  3. Delete the externally-managed RDS (NOT in the stack — survives step 2)

  aws rds delete-db-instance \
    --db-instance-identifier docintel-production-postgres-public \
    --skip-final-snapshot --delete-automated-backups --region ap-south-1

  4. Delete ECR repos (created by deploy.py — survive step 2)

  for r in $(aws ecr describe-repositories --region ap-south-1 \
      --query "repositories[?starts_with(repositoryName,'docintel-')].repositoryName" --output text); do
    aws ecr delete-repository --repository-name "$r" --force --region ap-south-1
  done

  5. Terraform stack — only if it was ever applied

  cd infra
  terraform state list            # if this errors or is empty → nothing applied, skip destroy
  terraform destroy               # this removes Neptune, pgvector RDS, etc.
  Then optionally remove the TF backend:
  aws s3 rb s3://terraform-state-docintel-082688269612 --force --region ap-south-1
  aws dynamodb delete-table --table-name terraform-state-lock --region ap-south-1

  6. Cancel the SaaS (separate billing — AWS deletion does nothing here)

  - Qdrant Cloud → console → delete the cluster.
  - Neo4j Aura → console → delete the instance.

  7. Force-delete leftovers (Secrets Manager keeps a recovery window; logs linger)

  aws secretsmanager delete-secret --secret-id docintel/production/credentials \
    --force-delete-without-recovery --region ap-south-1
  # KMS keys: stack schedules them; nothing to do. CloudWatch log groups:
  aws logs describe-log-groups --region ap-south-1 \
    --log-group-name-prefix /aws/ --query "logGroups[?contains(logGroupName,'docintel')].logGroupName" --output text
  # delete any returned with: aws logs delete-log-group --log-group-name <name> --region ap-south-1

  8. Verify nothing tagged remains (and watch the next bill)

  aws resourcegroupstaggingapi get-resources --region ap-south-1 \
    --tag-filters Key=Project,Values=DocIntel,doc-pipeline --query 'ResourceTagMappingList[].ResourceARN'

  ⚠️ Urgent regardless of teardown — leaked secrets

  infra/terraform.tfvars (committed to git, 68 commits of history) contains a live OpenRouter API key, the RDS password, and the session secret. The RDS password/session secret die with AWS,
  but:
  - Rotate the OpenRouter key now at openrouter.ai (revoke sk-or-v1-fa53…, generate a new one). You'll reuse OpenRouter on the NAS — do not carry the leaked key forward.
  - Move all secrets to an untracked .env on the NAS; add infra/terraform.tfvars to .gitignore. (Git history still holds the old one — rotation is the real fix.)

  ---
  Part 2 — Rebuild on the Synology DS925+

  The key fact: your repo's docker-compose.yml already is the NAS deployment. Every AWS managed service maps to a container you already run locally. You're not rebuilding — you're promoting
  your dev compose to production.

  Step 0 — DS925+ prep

  1. Install 32 GB ECC RAM (2×16 GB). Non-negotiable for this stack.
  2. Drives in SHR/RAID-1+ (don't trust a single disk with the only copy of your data).
  3. DSM 7.2+ → install Container Manager (Package Center).
  4. Create shared folder docpipe and a non-admin DSM user docpipe-svc; run containers under it, not root.
  5. Put the repo on the NAS: git clone into /volume1/docpipe/doc-pipeline (or copy via File Station).

  Step 1 — What changes from your dev compose

  The AWS architecture used Lambda fan-out + SQS + EventBridge schedules. On the NAS you replace those three with long-lived worker containers + DSM Task Scheduler. Everything else
  (Postgres, MinIO, Qdrant, Neo4j, ElasticMQ, api, web) is unchanged from your compose. Additions:

  # add to your existing docker-compose.yml services:

    redis:                              # replaces ElastiCache (suggestions/cache)
      image: redis:7-alpine
      container_name: docpipe-redis
      volumes: [redis_data:/data]
      restart: unless-stopped

    # One long-lived worker per stage = the local equivalent of each Lambda.
    # These drain the ElasticMQ queues exactly like the SQS-triggered Lambdas did.
    ocr-worker:
      build: { context: ., dockerfile: infra/docker/Dockerfile.ocr }
      env_file: .env
      environment:
        SQS_ENDPOINT_URL: http://elasticmq:9324
        S3_ENDPOINT_URL: http://minio:9000
        DATABASE_URL: postgresql+asyncpg://pipeline:pipeline@postgres:5432/doc_pipeline
      command: uv run make stage-worker STAGE=ocr      # adapt to your worker entrypoint
      depends_on: [postgres, minio, elasticmq]
      deploy: { replicas: 2 }                          # concurrency = replicas (Lambda did 40; 2–4 here)
      restart: unless-stopped
    # …repeat structure/match/persist/index workers, smaller replica counts…

  volumes:
    postgres_data:
    minio_data:
    qdrant_data:
    neo4j_data:
    redis_data:

  For the two scheduled Lambdas (sweeper rate(1m), monitor rate(5m)): use DSM → Control Panel → Task Scheduler → Scheduled Task → User-defined script, e.g. every minute:
  docker exec docpipe-api uv run python -m cloud.orchestration.sweeper
  and every 5 minutes for cloud.lambda.monitor. (Or a tiny restart: unless-stopped loop container if you prefer it in-compose.)

  Step 2 — Production .env (NAS values)

  Point everything at the local containers; the only external call is OpenRouter:
  DATABASE_URL=postgresql+asyncpg://pipeline:<strong-pw>@postgres:5432/doc_pipeline
  S3_ENDPOINT_URL=http://minio:9000
  S3_BUCKET=documents
  QDRANT_URL=http://qdrant:6333
  NEO4J_URI=bolt://neo4j:7687
  SQS_ENDPOINT_URL=http://elasticmq:9324
  REDIS_HOST=redis
  OPENROUTER_API_KEY=<your NEWLY ROTATED key>
  OPENROUTER_MODEL=google/gemini-2.5-flash
  DASHBOARD_SESSION_SECRET=<new random>
  Change the default minioadmin/minioadmin and neo4j/pipeline-dev creds before this is reachable from your LAN.

  Step 3 — Verify the OCR image carries the languages

  Tesseract must have eng+mar+hin+osd baked in (your locked decision). Confirm the worker image installs tesseract-ocr-mar tesseract-ocr-hin tesseract-ocr-osd, then:
  docker exec docpipe-ocr-worker tesseract --list-langs   # must show eng, mar, hin, osd

  Step 4 — Bring it up + initialize

  docker compose up -d
  docker exec docpipe-api uv run python -m scripts.init_all          # postgres/minio/qdrant/neo4j schemas
  docker exec docpipe-api uv run python -m scripts.load_reference_data  # the ~92K practitioner registry
  # RBAC/feature tables your PROJECT_MEMORY lists as one-time:
  docker exec docpipe-api uv run python -m scripts.apply_admin_rbac
  docker exec docpipe-api uv run python -m scripts.add_dashboard_user <you> --role administrator
  # (also apply_bookmarks, apply_cost_events, apply_consistency, apply_pipeline_runs, seed_tuning_defaults)

  Step 5 — Re-ingest from scratch

  Since AWS data was throwaway, point the NAS batch uploader at your source PDFs:
  docker exec docpipe-api uv run python -m scripts.batch_upload --src /volume1/docpipe/incoming
  This is the correct scale path (NAS uploader → MinIO manifest → ElasticMQ → workers fan out), per your locked decision — not the sequential folder runner.

  Step 6 — Access + HTTPS

  - DSM built-in reverse proxy (Control Panel → Login Portal → Advanced → Reverse Proxy) or Nginx Proxy Manager container → map docintel.yourdomain → web:3000 and /api → api:8000. Enable
  HSTS.
  - Only expose the web/api ports externally; keep Postgres/Neo4j/Qdrant/MinIO LAN-internal (separate them into their own Container Manager project/network).

  Step 7 — Backups (the part people skip and regret)

  - Hyper Backup the bind-mount/volume data — especially postgres_data and neo4j_data — to a second location, encrypted.
  - For Postgres, prefer a logical dump in the schedule too: docker exec docpipe-postgres pg_dump -U pipeline doc_pipeline | gzip > /volume1/docpipe/backups/pg_$(date +%F).sql.gz.
  - Test a restore before you trust it.

  ---
  Cost & trade-off summary

  - Gone: ALB + Fargate + Lambda + RDS + ElastiCache + Neptune/Qdrant-Aura monthly bill → ~$0 recurring. Only running cost left = OpenRouter API usage (unchanged) + electricity.
  - Lost: AWS auto-scaling and managed HA. Your throughput is now bounded by the V1500B (4c/8t) — fine for minutes-per-doc batch latency (your stated assumption), not for bursty real-time.
  Tune worker replicas to taste.
  - Gained: full data locality (good for the practitioner PII), one docker compose file as the entire deployment, trivial rebuild.

  I kept this as guidance per your request. If you want, I can generate the concrete docker-compose.nas.yml (with all 5 workers + redis + healthchecks) and a documentation/NAS_DEPLOYMENT.md
  runbook committed to the repo — say the word and I'll write them.

  Sources:
  - Synology DS925+ product spec (https://www.synology.com/en-us/products/DS925+)
  - Marius Hosting — DS925+ specs (https://mariushosting.com/synology-ds925-release-date-and-specs/)
  - AI on Synology NAS: Docker setup (2026) (https://localaimaster.com/blog/ai-synology-nas-setup)
  - n8n + Qdrant compose for Synology (https://github.com/litio2001/docker-n8n)
  - How to install MinIO on Synology Docker (https://yarboroughtechnologies.com/how-to-install-minio-on-synology-docker/)
  - Neo4j Docker operations manual (https://neo4j.com/docs/operations-manual/current/docker/)
  - Container Manager backup & recovery guide (https://www.synoforum.com/threads/container-manager-a-definitive-guide-for-backup-recovery.15461/)
  - Docker best practices on Synology (https://www.epistechnology.com/docker-best-practices-on-synology-for-developers-and-power-users/)
  - Nginx Proxy Manager on Synology (https://www.wundertech.net/nginx-proxy-manager-synology-nas-setup-instructions/)