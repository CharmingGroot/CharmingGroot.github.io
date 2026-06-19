---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "053. Argo CD + Crossplane — Git 선언에서 AWS 인프라까지"
date: 2026-06-13
tags: [argocd, crossplane, gitops, kubernetes, aws, platform-engineering, iac, composition]
summary: "Argo CD와 Crossplane을 결합하면 Git 하나로 k8s 앱 배포와 AWS 인프라 프로비저닝을 모두 관리할 수 있다. 개발자가 Git에 Claim을 올리면 Argo CD가 k8s에 적용하고, Crossplane이 실제 AWS 리소스를 만든다. 이 파이프라인이 어떻게 구성되는지, 그리고 실제 운영에서 어떤 점을 주의해야 하는지 설명한다."
slug: "053-argocd-crossplane"
categories: ["IaC · 플랫폼"]
---

Argo CD는 Git → k8s 동기화를 담당한다. Crossplane은 k8s CR → AWS 인프라 프로비저닝을 담당한다. 이 둘을 결합하면 Git이 k8s 앱과 AWS 인프라 모두의 단일 진실 원천이 된다.

```
Git 저장소
  ├── apps/production/order-service/
  │   ├── deployment.yaml
  │   ├── service.yaml
  │   └── db-claim.yaml              ← PostgreSQLInstance Claim
  └── infrastructure/
      ├── composition.yaml           ← Crossplane Composition
      └── provider-config.yaml
        ↓ (Argo CD가 감시 → 적용)
k8s 클러스터
  ├── Deployment, Service (앱)
  └── PostgreSQLInstance CR (Crossplane Claim)
        ↓ (Crossplane Operator가 처리)
AWS
  └── RDS 인스턴스
```

개발자는 Git에 코드와 Claim YAML을 올린다. 이후 인프라 프로비저닝까지 자동이다.

## 실제 파이프라인

### 1. Git 저장소 구조

```
my-gitops/
├── platform/                        # 인프라 팀 관리
│   ├── crossplane/
│   │   ├── provider-aws.yaml
│   │   ├── provider-config.yaml
│   │   └── compositions/
│   │       └── postgresql.yaml      # Composition 정의
│   └── argocd/
│       └── root-app.yaml
└── apps/
    └── production/
        └── order-service/
            ├── deployment.yaml
            ├── service.yaml
            ├── ingress.yaml
            └── db-claim.yaml        # 앱 팀이 요청하는 DB
```

### 2. 앱 팀의 DB 요청

```yaml
# apps/production/order-service/db-claim.yaml
apiVersion: platform.example.com/v1alpha1
kind: PostgreSQLInstance
metadata:
  name: order-db
  namespace: order-service
spec:
  parameters:
    size: medium
    storageGB: 100
  writeConnectionSecretToRef:
    name: order-db-credentials
```

앱 팀은 이 파일을 추가하고 PR을 올린다. 인프라 팀이 리뷰하고 merge하면 자동으로 진행된다.

### 3. Argo CD 동기화

Argo CD가 `apps/production/order-service/` 변경을 감지하고 k8s에 적용한다.

```bash
# Argo CD UI에서 또는
kubectl get applications -n argocd order-service
# STATUS: Synced

kubectl get postgresqlinstances -n order-service
# NAME       READY   SYNCED
# order-db   False   True    ← 아직 프로비저닝 중
```

### 4. Crossplane 프로비저닝

Crossplane이 `PostgreSQLInstance` CR을 감지하고 Composition을 실행한다.

```bash
# 프로비저닝 완료 후
kubectl get postgresqlinstances -n order-service
# NAME       READY   SYNCED
# order-db   True    True

# 연결 정보가 Secret에 자동 저장됨
kubectl get secret order-db-credentials -n order-service
# NAME                   TYPE     DATA   AGE
# order-db-credentials   Opaque   5      2m
```

앱 Deployment가 이 Secret을 환경변수로 마운트해 DB에 접근한다.

## 프로비저닝 시간 처리

RDS 인스턴스는 만드는 데 수 분이 걸린다. 앱 Deployment가 DB 연결을 시도하는 시점에 DB가 아직 준비 중일 수 있다.

두 가지 방법으로 처리한다.

**Init Container로 DB 대기**: 앱 컨테이너가 시작하기 전에 DB 연결이 될 때까지 기다린다.

```yaml
initContainers:
- name: wait-for-db
  image: busybox
  command:
  - sh
  - -c
  - |
    until nc -z $DB_HOST 5432; do
      echo "DB 대기 중..."
      sleep 5
    done
  env:
  - name: DB_HOST
    valueFrom:
      secretKeyRef:
        name: order-db-credentials
        key: host
```

**Crossplane readiness를 Argo CD Sync Wave에 연결**: DB Claim을 먼저 배포하고(wave 0), DB가 Ready 상태가 된 이후 앱을 배포(wave 1)한다.

```yaml
# db-claim.yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "0"

# deployment.yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"
```

Argo CD는 wave 0의 모든 리소스가 Healthy가 된 후 wave 1을 배포한다. Crossplane CR의 `READY: True`가 Healthy 기준이다.

## 환경 분리

여러 환경을 같은 패턴으로 관리한다.

```
apps/
├── staging/
│   └── order-service/
│       └── db-claim.yaml    # size: small, storageGB: 20
└── production/
    └── order-service/
        └── db-claim.yaml    # size: large, storageGB: 500
```

환경별 값만 다르고 구조는 동일하다. Kustomize로 공통 base에 환경별 overlay를 적용하는 방식으로 중복을 줄일 수 있다.

## 트레이드오프

Crossplane Composition이 있는 k8s 클러스터와 앱이 배포되는 클러스터를 분리하는 것이 일반적이다. **Management Cluster** (Crossplane 운영)와 **Workload Cluster** (앱 운영)를 나누면 인프라 프로비저닝 실패가 앱 클러스터에 영향을 주지 않는다.

Crossplane으로 만든 리소스를 삭제할 때 주의가 필요하다. Claim을 삭제하면 Crossplane이 실제 AWS 리소스를 삭제한다. Argo CD의 `prune: true`가 켜져 있으면 Git에서 Claim을 제거했을 때 RDS가 삭제된다. 프로덕션 데이터베이스가 PR merge 한 번으로 사라질 수 있다. `deletionPolicy: Orphan`을 설정해 k8s CR 삭제 시 실제 AWS 리소스는 보존하는 것이 안전하다.

```yaml
spec:
  forProvider:
    ...
  managementPolicies: ["Observe", "Create", "Update"]  # Delete 제외
```
