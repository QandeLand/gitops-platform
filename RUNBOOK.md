# GitOps Platform — Runbook

Personal reference for running, debugging, and understanding this project.
Written after building it so I remember what I actually did.

---

## Daily startup

```bash
k3d cluster start gitops-cluster && sleep 30
kubectl config use-context k3d-gitops-cluster

# Port-forwards
kubectl port-forward svc/argocd-server -n argocd 9090:443 &
kubectl port-forward svc/monitoring-grafana -n monitoring 3000:80 &
```

## Daily shutdown

```bash
k3d cluster stop gitops-cluster
kill $(lsof -t -i:9090) $(lsof -t -i:3000) $(lsof -t -i:8081) 2>/dev/null
```

---

## Access

| Service | URL | Credentials |
|---|---|---|
| ArgoCD | https://localhost:9090 | admin / get with command below |
| Grafana | http://localhost:3000 | admin / admin123 |
| Backend dev | http://backend.local:8080 | — |
| Backend prod | http://backend-prod.local:8080 | — |
| Frontend | http://frontend.local:8080 | — |

```bash
# Get ArgoCD password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

---

## Issues I hit and how I fixed them

### Wrong kubectl context
Was accidentally connected to an AKS cluster from another project instead of the local k3d cluster. All commands were running against the wrong cluster.

Fix:
```bash
kubectl config current-context   # always check this first
kubectl config use-context k3d-gitops-cluster
```

### argocd-repo-server stuck in Unknown
After cluster restart, the repo-server pod gets stuck in Unknown state and ArgoCD can't sync.

Fix:
```bash
kubectl delete pod -n argocd -l app.kubernetes.io/name=argocd-repo-server --force --grace-period=0
```

### Missing ApplicationSet CRD
argocd-applicationset-controller was in CrashLoopBackOff with error "no matches for kind ApplicationSet".

Fix:
```bash
kubectl apply -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.4/manifests/crds/applicationset-crd.yaml
```

### Frontend ImagePullBackOff
Kubernetes could not pull the frontend image from GHCR — 403 Forbidden.

Fix: create imagePullSecret in the dev namespace and add it to the Helm deployment template:
```bash
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=QandeLand \
  --docker-password=<token> \
  -n dev
```

### Wrong YAML indentation in deployment template
imagePullSecrets was placed inside the containers block instead of at the spec level. Pod kept failing silently.

Fix: move imagePullSecrets to the correct level in helm/frontend/templates/deployment.yaml

### ArgoCD Image Updater not updating pods

Image Updater was running but `images_updated=0` every cycle.

**Root causes and fixes:**

1. Wrong args order — container was showing help text instead of running. Fixed by patching args to put `run` before flags:
```bash
kubectl patch deployment argocd-image-updater-controller -n argocd --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/args", "value": ["run", "--metrics-bind-address=:8443"]}]'
```

2. Liveness probe killing the pod too fast — `timeoutSeconds` was 1 second. Fixed by removing the liveness probe on local cluster.

3. Wrong credential secret format — secret needed `credentials` field with `username:password` format:
```bash
kubectl create secret generic ghcr-secret \
  --from-literal=credentials=QandeLand:<token> \
  -n argocd
```

4. Wrong update strategy — `alphabetical` was picking `v1` tag instead of SHA tags. Fixed by restricting to SHA tags only:
```yaml
allowTags: "regexp:^[0-9a-f]{7}$"
```

---

## What each file does

### apps/backend/
- `app.py` — Flask app with 3 endpoints: `/` returns version info, `/health` returns ok, `/items` returns a list
- `Dockerfile` — builds the backend into a container image using Python Alpine

### apps/frontend/
- `index.html` — HTML page that fetches from the backend API and displays status and items
- `nginx.conf` — Nginx config that serves the HTML and proxies `/api/` to the backend service
- `Dockerfile` — builds the frontend into a container image using Nginx Alpine

### helm/backend/
- `Chart.yaml` — metadata about the Helm chart (name, version)
- `values.yaml` — dev settings: 2 replicas, resource limits, image tag, ingress host
- `values-prod.yaml` — prod overrides: 3 replicas, stricter limits, prod ingress host
- `templates/deployment.yaml` — Kubernetes Deployment template
- `templates/service.yaml` — Kubernetes Service template
- `templates/ingress.yaml` — Traefik ingress rule template

### helm/frontend/
- Same structure as backend chart but for the Nginx frontend

### argocd/applications/
- `backend-dev.yaml` — tells ArgoCD to deploy helm/backend to the dev namespace using values.yaml
- `backend-prod.yaml` — tells ArgoCD to deploy helm/backend to the prod namespace using values.yaml + values-prod.yaml
- `frontend-dev.yaml` — tells ArgoCD to deploy helm/frontend to the dev namespace
- `image-updater-backend.yaml` — tells Image Updater to watch GHCR for new backend images and update backend-dev automatically

### .github/workflows/
- `ci.yaml` — two jobs: builds backend image on push to apps/backend/, builds frontend image on push to apps/frontend/. Both push to GHCR with SHA tag and latest tag

---

## What each component does

**k3d** — runs a real Kubernetes cluster inside Docker on your laptop. No cloud needed.

**ArgoCD** — watches your GitHub repo every 3 minutes. If anything in git changed, it applies those changes to the cluster automatically. If someone manually changes something in the cluster, ArgoCD reverses it.

**Helm** — instead of writing raw Kubernetes YAML, you write templates with variables. values.yaml = dev settings, values-prod.yaml = prod settings. Same template, different environments.

**ArgoCD Image Updater** — watches GHCR for new image tags. When CI pushes a new image, Image Updater tells ArgoCD to redeploy. No git commit needed from CI.

**GitHub Actions** — builds Docker images on every push and pushes them to GHCR. Two jobs: one for backend, one for frontend.

**Prometheus** — scrapes metrics from every pod and node every 15 seconds and stores them.

**Grafana** — reads from Prometheus and shows dashboards. Pre-built dashboards for node and pod metrics.

**Traefik** — ingress controller. Routes traffic from backend.local and frontend.local to the correct service inside the cluster.

**Nginx (frontend)** — serves the HTML dashboard and proxies /api/ calls to the backend Flask service. The browser never talks to the backend directly.

