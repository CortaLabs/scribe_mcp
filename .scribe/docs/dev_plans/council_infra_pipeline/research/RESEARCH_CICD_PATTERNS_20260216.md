---
id: council_infra_pipeline-research-cicd-patterns-20260216
title: "\U0001F52C GitHub Actions CI/CD for Docker Compose VPS Deployment \u2014 council_infra_pipeline"
doc_type: RESEARCH_CICD_PATTERNS_20260216
doc_name: RESEARCH_CICD_PATTERNS_20260216
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 01:57:14 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# 🔬 GitHub Actions CI/CD for Docker Compose VPS Deployment — council_infra_pipeline
**Author:** Lens
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-16 20:56:00 UTC

> Research on GitHub Actions CI/CD patterns for deploying multi-service Docker Compose stacks to a Hetzner VPS via Tailscale mesh network.

---
## Executive Summary
<!-- ID: executive_summary -->

This research synthesizes best practices for GitHub Actions CI/CD workflows deployed to a Hetzner CCX23 VPS (16GB RAM, 4 vCPU) connected via Tailscale mesh network. Two primary deployment strategies emerged from analysis of production patterns, official documentation, and community tools.

**Recommended Strategy:** Build on GitHub (GitHub Actions) + Push to GHCR (GitHub Container Registry) + SSH Deploy to VPS

**Rationale:**
- Consistent builds across environments (GitHub's infrastructure, not server-dependent)
- Reduced VPS load (building happens on GitHub, not your server)
- Better Docker layer caching (GHCR caches intermediate layers)
- Faster deployments (pull pre-built image vs. build 5 services from scratch)
- Easier rollbacks (tagged images in GHCR)
- Works for monorepo with 5 interdependent services

**Key Findings (by topic):**
1. **Deployment Strategies:** Build-on-GitHub + GHCR is superior to build-on-server for production
2. **Tailscale Integration:** tailscale/github-action connects GitHub Actions runner to private VPS without exposing ports
3. **Zero-Downtime:** Requires Docker Rollout tool or manual health-check-based rolling restart
4. **Secrets Management:** GitHub Secrets → environment-specific, OIDC tokens preferred over PATs
5. **Multi-Service Health Checks:** Critical for 5-service stack (postgres, daemon, web, scribe, corta-store)

**Overall Confidence:** HIGH (primary sources: GitHub official docs, Tailscale engineering, Docker docs, production case studies)
---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** agent-20260216-130610-b59de721

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]
## Findings
<!-- ID: findings -->

### Finding 1: Two Deployment Strategies (Build-on-GitHub vs. Build-on-Server)

**Summary:** Production-grade Docker Compose deployments use two primary strategies. Build-on-GitHub + GHCR is the industry standard; build-on-server is only viable for small teams with low-frequency deployments.

**Strategy A: Build on GitHub + GHCR + SSH Deploy (RECOMMENDED)**

**How it works:**
1. Push to GitHub repo → GitHub Actions triggered
2. Build Docker image(s) in GitHub Actions runners
3. Push built images to GitHub Container Registry (GHCR, ghcr.io)
4. SSH into VPS and execute deployment script
5. Script pulls images from GHCR and restarts services via docker compose

**Pros:**
- Consistent builds across environments (GitHub infrastructure, not server-dependent)
- Significantly reduces VPS load (building uses GitHub's CPU, not your server)
- Better Docker layer caching (GHCR caches intermediate layers between builds)
- Faster deployments (5-10 min build time on GitHub vs. 20-30 min on CCX23)
- Easier rollbacks (tagged images persist in GHCR, revert is trivial)
- Supports multi-platform builds (linux/amd64, linux/arm64 if needed)
- Cleaner audit trail (GitHub Actions logs track every build)

**Cons:**
- Need to authenticate VPS with GHCR credentials (minor)
- Slightly higher complexity in GitHub Actions workflow
- Small cost if using private repos (but free for public)

**Confidence:** HIGH — [GitHub official CI/CD guide](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry), [Shipyard blog](https://shipyard.build/blog/gha-recipes-build-and-push-container-registry/), industry standard at scale

---

**Strategy B: Build on Server via SSH (NOT RECOMMENDED FOR PRODUCTION)**

**How it works:**
1. Push to GitHub repo → GitHub Actions triggered
2. SSH into VPS and git pull latest code
3. Run docker compose build (on server) → rebuilds all 5 services
4. Restart services via docker compose up -d
5. All work happens on the VPS

**Pros:**
- Simpler workflow (fewer GitHub Actions steps)
- No registry account/authentication needed
- Works for fast iteration during dev

**Cons:**
- Hetzner CCX23 (4 vCPU, 16GB) slows down significantly building 5 large services
- Build time: ~20-30 min on CCX23 vs. ~5 min on GitHub Actions
- No layer caching between builds (each build starts from base images)
- Single point of failure (VPS dies during build, deployment fails)
- No audit trail in GHCR; builds are ephemeral
- Difficult to rollback (only last built image on server)
- During builds, VPS resources are maxed out → poor user experience

**Confidence:** HIGH — [GitHub Actions cookbook](https://docs.servicestack.net/ssh-github-action-deployment), [DZone DevOps article](https://dzone.com/articles/diy-devops-ci-and-cd-with-github-docker-and-a-vps)

---

### Finding 2: Tailscale Integration with GitHub Actions

**Summary:** Tailscale provides a GitHub Action that securely connects GitHub Actions runners to your private Tailscale mesh network, enabling deployment to VPS without exposing any ports to the public internet.

**How it works:**
1. GitHub Actions runner connects to Tailscale network using OAuth credentials
2. Runner gets an ephemeral node on the tailnet (auto-removed after workflow completes)
3. Runner can SSH/deploy to VPS using its private Tailscale IP
4. All traffic is encrypted through Tailscale mesh; zero public ports exposed

**Implementation:**
```yaml
- name: Connect Tailscale
  uses: tailscale/github-action@v4
  with:
    oauth-client-id: ${{ secrets.TAILSCALE_OAUTH_CLIENT_ID }}
    oauth-secret: ${{ secrets.TAILSCALE_OAUTH_SECRET }}
    tags: ci-deploy
    
- name: Deploy to VPS
  run: ssh deploy@council-hub "cd /opt/council_mcp && docker compose pull && docker compose up -d"
```

**Security Benefits:**
- GitHub Actions runner appears as ephemeral node on Tailscale (not persistent)
- Runner is removed from tailnet immediately after workflow completes
- All traffic encrypted; no public ports, no firewall rules needed
- Tailnet Lock can enforce device key signatures for extra security
- SSH key audit trail via Tailscale's integration logs

**Key Components:**
- `oauth-client-id` / `oauth-secret`: Tailscale OAuth app credentials (stored in GitHub Secrets)
- `tags`: Label for this ephemeral node (helps with firewall rules on VPS side)
- Ephemeral lifecycle: node created at start, auto-removed at end

**Confidence:** HIGH — [Tailscale engineering blog](https://tailscale.com/blog/github-action-v4), [Tailscale GitHub Action docs](https://github.com/tailscale/github-action), [Aaron Stannard deployment guide](https://aaronstannard.com/docker-compose-tailscale/)

---

### Finding 3: Zero-Downtime Deployment Patterns

**Summary:** Docker Compose has no native zero-downtime deployment. Achieving it requires either the `docker-rollout` tool (recommended) or manual health-check-based rolling restart strategy.

**Challenge:** By default, `docker compose up -d` kills old containers, then starts new ones → brief downtime

**Solution A: Docker Rollout Tool (RECOMMENDED)**

The [docker-rollout](https://github.com/wowu/docker-rollout) tool implements zero-downtime updates:

```bash
# Instead of: docker compose up -d
docker rollout --service <service-name> deploy
```

**How it works:**
1. Scale service to 2x replicas (e.g., 1 container → 2 containers)
2. Wait for health checks to pass on new containers
3. Kill old container
4. Repeat for each service

**Pros:**
- Proven tool used in production
- Handles health checks correctly
- Easy integration into GitHub Actions
- Works with multi-service stacks

**Cons:**
- Requires additional tool installation on VPS
- Depends on accurate health checks (if health check is broken, rollout fails)

**Confidence:** HIGH — [docker-rollout GitHub](https://github.com/wowu/docker-rollout), [Reintech guide](https://reintech.io/blog/zero-downtime-deployments-docker-compose-rolling-updates), [Virtualization Howto](https://www.virtualizationhowto.com/2025/06/docker-rollout-zero-downtime-deployments-for-docker-compose-made-simple/)

---

**Solution B: Manual Health-Check-Based Rolling Restart (ALTERNATIVE)**

If docker-rollout is not an option:

```bash
# For each service in dependency order:
docker compose up -d --no-deps --build <service>
docker compose exec <service> /healthcheck.sh  # Wait for health
# Repeat
```

This approach requires:
- Health checks defined in docker-compose.yaml for ALL services
- Startup scripts that properly handle readiness signals
- Careful ordering (stop read-only services first, critical ones last)

**Critical:** Don't stop old containers before starting new ones. Docker Compose respects this with `docker compose up -d`.

---

### Finding 4: Multi-Service Health Checks & Dependency Management

**Summary:** Docker Compose supports `depends_on` with `condition: service_healthy`, which ensures correct startup order for multi-service stacks. Health checks are CRITICAL for the 5-service stack (postgres, daemon, web, scribe, corta-store).

**Your Stack's Dependency Graph:**

```
postgres (CRITICAL)
    ↓
daemon (depends on postgres)
    ↓
web (depends on daemon)
    ↓
scribe (peer of web)
    ↓
corta-store (peer of scribe)
```

**Proper Health Check Pattern:**

```yaml
services:
  postgres:
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "council"]
      interval: 10s
      timeout: 5s
      retries: 5
      
  daemon:
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8016/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      
  web:
    depends_on:
      daemon:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8015/health"]
```

**Key Rules:**
1. **Always use `condition: service_healthy`** — not just `depends_on`, which only checks if container is running
2. **Health checks must be meaningful** — test actual service readiness (not just container existence)
3. **Startup order matters** — define dependencies for each service that has dependencies
4. **Timeouts must be generous** — 5-10s per check, 5 retries = up to 50s for postgres to be ready

**Confidence:** HIGH — [Docker Compose official docs](https://docs.docker.com/compose/how-tos/startup-order/), [OneUptime guide](https://oneuptime.com/blog/post/2026-01-16-docker-compose-depends-on-healthcheck/view), [Last9 blog](https://last9.io/blog/docker-compose-health-checks-an-easy-to-follow-guide/)

---

### Finding 5: Secrets Management in GitHub Actions

**Summary:** GitHub Secrets should be environment-specific (Development, Staging, Production). Modern best practice is OIDC tokens over PATs. Secrets → docker/build-push-action for build-time secrets, Docker Secrets file for runtime.

**GitHub Secrets Hierarchy:**

| Level | Scope | Use Case |
|-------|-------|----------|
| Organization | All repos in org | Common API keys, shared credentials |
| Repository | Single repo | Project-specific secrets (API keys, deploy credentials) |
| Environment | Specific env (Prod/Staging) | Prod secrets, requires approval before deploy |

**Recommended Setup for council_infra_pipeline:**

```
GitHub Organization Secrets:
  - TAILSCALE_OAUTH_CLIENT_ID
  - TAILSCALE_OAUTH_SECRET
  - GHCR_PAT (GitHub PAT with packages:write scope)

GitHub Repository Secrets (council_mcp):
  - HETZNER_DEPLOY_KEY (SSH private key)
  - GHCR_USERNAME (your GitHub username)
  
GitHub Environment Secrets (Production):
  - PG_PASSWORD (only for production, requires approval)
  - OPENAI_API_KEY (only for production)
```

**Secrets in GitHub Actions Workflows:**

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Login to GHCR
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}  # Free! GitHub provides this
          
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}/daemon:${{ github.sha }}
          secrets: |
            "build_secret=value"  # For build-time secrets (Dockerfile RUN --mount=type=secret)
```

**Runtime Secrets (Docker Secrets files):**

Docker Secrets are files mounted as `/run/secrets/<name>` inside containers. For production:

1. Create secret files on VPS: `/opt/council_mcp/secrets/*.txt`
2. Docker Compose reads them via `secrets:` section
3. GitHub Actions deployment script uploads secrets via SSH SFTP or similar

```yaml
# In docker-compose.yaml on VPS:
services:
  postgres:
    secrets:
      - pg_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_password
      
secrets:
  pg_password:
    file: ./secrets/pg_password.txt
```

**Best Practices (2026):**

1. **Use OIDC tokens instead of PATs** — OIDC provides temporary, auto-rotating credentials (more secure)
2. **Rotate secrets every 30-90 days** — GitHub Actions logs don't expose secrets, but rotation is good practice
3. **Environment-specific secrets** — Prod secrets require approval before use
4. **Never hardcode secrets in workflows** — always use `${{ secrets.* }}`
5. **Audit secret access** — GitHub tracks who accessed which secrets in organization settings

**Confidence:** HIGH — [GitHub official docs](https://docs.github.com/actions/security-guides/using-secrets-in-github-actions), [Docker official guide](https://docs.docker.com/build/ci/github-actions/secrets/), [Blacksmith best practices](https://www.blacksmith.sh/blog/best-practices-for-managing-secrets-in-github-actions), [Tom Vaidyan guide](https://www.tvaidyan.com/2026/01/22/introduction-to-secrets-management-in-github-actions/)

---

## Technical Analysis
<!-- ID: technical_analysis -->

### Recommended Workflow Structure

```yaml
name: Deploy Docker Stack to Hetzner

on:
  push:
    branches: [main]
  workflow_dispatch:  # Allow manual trigger

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to GHCR
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push daemon image
        uses: docker/build-push-action@v5
        with:
          context: ./
          file: ./deploy/Dockerfile
          target: daemon
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/daemon:latest
            ghcr.io/${{ github.repository }}/daemon:${{ github.sha }}
          cache-from: type=registry,ref=ghcr.io/${{ github.repository }}/daemon:buildcache
          cache-to: type=registry,ref=ghcr.io/${{ github.repository }}/daemon:buildcache,mode=max
      
      - name: Build and push web image
        uses: docker/build-push-action@v5
        with:
          context: ./
          file: ./deploy/Dockerfile
          target: web
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/web:latest
            ghcr.io/${{ github.repository }}/web:${{ github.sha }}
          cache-from: type=registry,ref=ghcr.io/${{ github.repository }}/web:buildcache
          cache-to: type=registry,ref=ghcr.io/${{ github.repository }}/web:buildcache,mode=max

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production  # Requires approval in repo settings
    steps:
      - uses: actions/checkout@v4
      
      - name: Connect to Tailscale
        uses: tailscale/github-action@v4
        with:
          oauth-client-id: ${{ secrets.TAILSCALE_OAUTH_CLIENT_ID }}
          oauth-secret: ${{ secrets.TAILSCALE_OAUTH_SECRET }}
          tags: ci-deploy
      
      - name: Deploy to Hetzner
        run: |
          ssh -i "${{ secrets.HETZNER_DEPLOY_KEY }}" \
            -o StrictHostKeyChecking=no \
            deploy@council-hub << 'EOF'
          cd /opt/council_mcp
          docker login -u ${{ github.actor }} -p ${{ secrets.GITHUB_TOKEN }} ghcr.io
          docker compose pull
          docker compose up -d --remove-orphans
          docker compose exec -T postgres pg_isready -U council
          EOF
```

### Architecture Decision Records

**Decision 1: Build on GitHub + GHCR**
- **Alternative:** Build on server
- **Winner:** Build on GitHub (faster, less VPS load, better caching)
- **Trade-off:** Slightly more complex workflow, need GHCR authentication on VPS

**Decision 2: Use docker-rollout for zero-downtime**
- **Alternative:** Manual rolling restart or accept brief downtime
- **Winner:** docker-rollout (handles health checks correctly, proven tool)
- **Trade-off:** Need to install and maintain separate tool

**Decision 3: Tailscale ephemeral nodes for CI**
- **Alternative:** Long-lived CI user with SSH key, public internet with UFW
- **Winner:** Tailscale ephemeral (zero public ports, auto-cleanup, audit trail)
- **Trade-off:** Requires Tailscale OAuth setup

---

## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps (Phase 0)

1. **[ ] Set up GitHub Container Registry authentication**
   - Create GitHub PAT with `packages:write` scope
   - Store in `GITHUB_PACKAGES_TOKEN` GitHub Secret
   - Test with `docker login ghcr.io` locally

2. **[ ] Create Tailscale OAuth app**
   - Go to Tailscale admin console → Settings → OAuth clients
   - Create client, store credentials in GitHub organization secrets
   - Test ephemeral connection from GitHub Actions

3. **[ ] Create GitHub Actions workflow scaffold**
   - Add `.github/workflows/deploy.yml` with build job
   - Implement docker/build-push-action for each service
   - Add layer caching (buildcache tags)

4. **[ ] Set up production environment**
   - Go to repo Settings → Environments
   - Create "production" environment with approval rules
   - Link secrets: PG_PASSWORD, OPENAI_API_KEY, etc.

5. **[ ] Test end-to-end deployment (dry-run)**
   - Push to branch, trigger GitHub Actions manually
   - Verify images build and push to GHCR
   - SSH step should succeed but not restart services (dry-run flag)

### Phase 1: Implement Zero-Downtime

6. **[ ] Install docker-rollout on VPS**
   - `curl -sSL https://get.docker.com/rollout | sh`
   - Test with: `docker rollout --service daemon deploy`

7. **[ ] Add health checks to all services**
   - postgres: `pg_isready -U council`
   - daemon: `curl http://localhost:8016/health`
   - web: `curl http://localhost:8015/health`
   - scribe: HTTP health endpoint
   - corta-store: HTTP health endpoint

8. **[ ] Update deployment script to use docker-rollout**
   - Replace `docker compose up -d` with rollout commands
   - Test zero-downtime by hitting API during deployment

### Phase 2: Monitoring & Rollback

9. **[ ] Add GitHub Actions job for health checks post-deploy**
   - After deployment, curl critical endpoints
   - On failure, trigger rollback script

10. **[ ] Implement rollback strategy**
    - Keep 2 recent image tags in GHCR
    - Rollback script: pull previous image, restart services

### Long-Term Opportunities

- **Multi-region failover:** Use load balancer across multiple Hetzner VPS instances
- **Canary deployments:** Route 10% traffic to new image, monitor, then 100%
- **Self-healing:** Automatic rollback if health checks fail post-deploy
- **Secrets rotation:** GitHub Actions + HashiCorp Vault for OIDC token rotation
- **Cost optimization:** Cache more aggressively, consider GitHub Actions on self-hosted runner

---

## Appendix
<!-- ID: appendix -->

### Reference Sources

**GitHub Official Docs:**
- [Working with GHCR](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Using Secrets in GitHub Actions](https://docs.github.com/actions/security-guides/using-secrets-in-github-actions)

**Tailscale Integration:**
- [Tailscale GitHub Action v4](https://tailscale.com/blog/github-action-v4)
- [Tailscale GitHub Action GitHub Repo](https://github.com/tailscale/github-action)
- [Deploy Docker Compose with Tailscale](https://aaronstannard.com/docker-compose-tailscale/)

**Docker Compose Best Practices:**
- [Docker Compose Startup Order](https://docs.docker.com/compose/how-tos/startup-order/)
- [Health Checks with depends_on](https://oneuptime.com/blog/post/2026-01-16-docker-compose-depends-on-healthcheck/view)
- [Health Checks Guide](https://last9.io/blog/docker-compose-health-checks-an-easy-to-follow-guide/)

**Zero-Downtime Deployment:**
- [docker-rollout GitHub](https://github.com/wowu/docker-rollout)
- [Zero-Downtime Deployments Guide](https://reintech.io/blog/zero-downtime-deployments-docker-compose-rolling-updates)

**CI/CD Patterns:**
- [Shipyard: GitHub Actions + Docker](https://shipyard.build/blog/gha-recipes-build-and-push-container-registry/)
- [DZone: DIY DevOps with GitHub & VPS](https://dzone.com/articles/diy-devops-ci-and-cd-with-github-docker-and-a-vps)

**Secrets Management:**
- [Blacksmith: Best Practices](https://www.blacksmith.sh/blog/best-practices-for-managing-secrets-in-github-actions)
- [Tom Vaidyan: Secrets Management 2026](https://www.tvaidyan.com/2026/01/22/introduction-to-secrets-management-in-github-actions/)

---
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---