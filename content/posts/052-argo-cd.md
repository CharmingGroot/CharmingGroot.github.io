---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "052. Argo CD — GitOps 기반 k8s 배포 도구"
date: 2026-06-13
tags: [argocd, gitops, kubernetes, cd, deployment, sync, app-of-apps, helm, kustomize]
summary: "Argo CD는 GitOps 방식으로 k8s 배포를 관리하는 도구다. Git 저장소의 매니페스트를 감시하고, 클러스터 상태와 diff를 보여주며, 자동 또는 수동으로 동기화한다. Application 정의 방식, Sync 전략, App of Apps 패턴, 실무에서 자주 쓰는 설정을 설명한다."
slug: "052-argo-cd"
categories: ["IaC · 플랫폼"]
---

Argo CD는 GitOps 원칙을 k8s에 구현한 CD(Continuous Delivery) 도구다. Git 저장소의 선언된 상태와 클러스터의 실제 상태를 계속 비교하고, 차이가 생기면 동기화한다. Helm, Kustomize, 순수 YAML 모두 지원한다.

## 핵심 개념

### Application

Argo CD에서 배포의 단위다. "이 Git 저장소의 이 경로에 있는 매니페스트를 이 클러스터의 이 네임스페이스에 배포하라"를 정의한다.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/my-org/my-gitops
    targetRevision: main           # 브랜치, 태그, 커밋 SHA
    path: apps/production/my-app   # 저장소 내 경로
  destination:
    server: https://kubernetes.default.svc  # 배포할 클러스터
    namespace: production
  syncPolicy:
    automated:
      prune: true        # Git에서 삭제된 리소스를 클러스터에서도 삭제
      selfHeal: true     # 클러스터가 직접 수정되면 Git 상태로 복원
    syncOptions:
    - CreateNamespace=true
```

`syncPolicy.automated`를 설정하면 Git push 시 자동 동기화된다. 설정하지 않으면 Argo CD UI에서 수동으로 Sync 버튼을 눌러야 한다. 프로덕션은 수동 승인, 스테이징은 자동 동기화로 구성하는 경우가 많다.

### Sync 상태

Argo CD는 Application의 상태를 두 차원으로 표시한다.

**Sync Status**: Git과 클러스터가 일치하는가
- `Synced`: 일치
- `OutOfSync`: 불일치 (Git에 변경이 있거나, 클러스터가 직접 수정됐거나)

**Health Status**: 리소스가 정상인가
- `Healthy`: 모든 리소스가 정상
- `Progressing`: 롤아웃 진행 중
- `Degraded`: 일부 리소스 비정상

## Helm + Argo CD

Helm Chart를 Argo CD로 관리하면 values를 Git에서 관리할 수 있다.

```yaml
spec:
  source:
    repoURL: https://prometheus-community.github.io/helm-charts
    chart: kube-prometheus-stack
    targetRevision: "55.0.0"
    helm:
      releaseName: prometheus
      valuesObject:
        grafana:
          enabled: true
          adminPassword: "${GRAFANA_ADMIN_PASSWORD}"
        prometheus:
          prometheusSpec:
            retention: 30d
            storageSpec:
              volumeClaimTemplate:
                spec:
                  resources:
                    requests:
                      storage: 100Gi
```

외부 Helm 저장소의 Chart를 버전 고정해 배포한다. `targetRevision`으로 Chart 버전을 명시하면 의도치 않은 업그레이드가 없다.

## App of Apps 패턴

클러스터에 수십 개의 Application이 있으면 하나하나 만들기 번거롭다. App of Apps는 Application들을 관리하는 상위 Application을 만드는 패턴이다.

```
root-app (Application)
  → apps/ 디렉토리를 감시
    → monitoring-app (Application)
    → ingress-controller-app (Application)
    → my-service-app (Application)
```

```yaml
# root-app
spec:
  source:
    path: apps/               # 이 경로의 모든 Application YAML을 배포
  destination:
    namespace: argocd
```

`apps/` 디렉토리에 새 Application YAML을 추가하면 root-app이 감지해 자동으로 Argo CD에 등록한다. 새 서비스 추가가 파일 하나 추가로 끝난다.

## ApplicationSet

App of Apps보다 발전된 방식이다. 클러스터 목록, 브랜치 목록, Git 디렉토리 구조 등을 기반으로 Application을 자동 생성한다.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: cluster-apps
spec:
  generators:
  - git:
      repoURL: https://github.com/my-org/my-gitops
      revision: main
      directories:
      - path: apps/*          # apps/ 아래 각 디렉토리마다 Application 생성
  template:
    metadata:
      name: '{{path.basename}}'
    spec:
      source:
        repoURL: https://github.com/my-org/my-gitops
        targetRevision: main
        path: '{{path}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{path.basename}}'
```

`apps/my-service`, `apps/monitoring` 디렉토리를 만들면 각각 Application이 자동 생성된다.

## Sync Wave와 배포 순서

의존 관계가 있는 리소스는 순서가 중요하다. Namespace가 먼저 만들어져야 그 안에 Deployment를 배포할 수 있다. `sync-wave` 어노테이션으로 순서를 제어한다.

```yaml
# 먼저 실행 (wave -1)
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
# → Namespace, CRD

# 그 다음 (wave 0, 기본값)
# → Deployment, Service

# 마지막 (wave 1)
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"
# → Ingress, HPA
```

낮은 번호가 먼저 실행된다. 같은 wave 안에서는 병렬로 적용된다.

## 트레이드오프

Argo CD UI가 직관적이어서 도입 장벽이 낮다. 하지만 클러스터별로 Argo CD를 따로 설치해야 하고, 여러 클러스터를 하나의 Argo CD로 관리하려면 클러스터를 등록해 외부에서 API를 호출하는 구조가 된다. 대규모 멀티클러스터 환경에서는 Argo CD 자체의 고가용성과 성능이 중요해진다.

`selfHeal: true`를 켜두면 긴급 패치를 위해 클러스터를 직접 수정해도 자동으로 원래 상태로 복원된다. 의도치 않은 변경을 막는 것이 목적이지만, 긴급 상황에서 이 동작이 방해가 될 수 있다. 운영팀과 긴급 시 절차를 사전에 합의해둬야 한다.
