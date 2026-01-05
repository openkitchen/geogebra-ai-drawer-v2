# Deployment / Runtime Guide (v2)

## Local Development

- Start both: `./scripts/v2_dev.sh`
- Build/compile: `./scripts/v2_build.sh`

## Environment

- Web defaults: `WEB_PORT=3000`
- API defaults: `API_PORT=3002`

API LLM config: see `apps/api/README.md` (`V2_LLM_API_KEY`, etc.).

## Notes

This quick-scan did not detect containerization or infrastructure manifests (Docker/K8s/etc.).
If deployment automation is required, add a dedicated deployment spec and update this doc.
