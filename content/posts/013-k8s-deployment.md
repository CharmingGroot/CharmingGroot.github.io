---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "013. Kubernetes Deployment — 파드 배포와 업데이트를 관리하는 오브젝트"
date: 2026-06-12
tags: [kubernetes, k8s, deployment, rolling-update, rollback, replicaset, strategy, revision]
summary: "Deployment는 파드를 직접 만드는 대신 '몇 개를 유지할지, 어떻게 업데이트할지'를 선언하는 오브젝트다. 내부적으로 ReplicaSet을 통해 파드를 관리하고, 롤링 업데이트로 무중단 배포를 하며, 문제가 생기면 이전 버전으로 롤백한다. 이 과정이 어떻게 동작하는지, 전략 파라미터를 어떻게 조절하는지를 설명한다."
slug: "013-k8s-deployment"
categories: ["쿠버네티스"]
---

파드를 직접 만들면 그 파드가 죽었을 때 아무도 다시 살려주지 않는다. Deployment는 이 문제를 해결하는 오브젝트다. "이 파드를 3개 유지하라"를 선언하면 파드가 죽을 때마다 새로 만들어 항상 3개를 유지하고, 새 버전으로 업데이트할 때는 트래픽을 끊지 않고 하나씩 교체한다. k8s에서 웹 서버, API 서버처럼 상시 실행되는 거의 모든 서비스는 Deployment로 배포된다.

## Deployment, ReplicaSet, Pod의 관계

Deployment는 파드를 직접 만들지 않는다. 중간에 **ReplicaSet**이 있다.

```
Deployment
    └── ReplicaSet (버전 A)  ← 현재 활성
            ├── Pod
            ├── Pod
            └── Pod
    └── ReplicaSet (버전 B)  ← 이전 버전 (롤백용으로 보존)
```

ReplicaSet이 파드 개수를 유지하는 실제 컨트롤러다. Deployment는 ReplicaSet들을 관리하면서 업데이트와 롤백을 조율하는 한 층 위의 오브젝트다.

버전을 올리면 Deployment가 새 ReplicaSet을 만들고, 거기서 새 파드를 하나씩 띄우면서 이전 ReplicaSet의 파드를 하나씩 줄인다. 이전 ReplicaSet은 파드 수 0으로 보존되므로, 롤백 시 그 ReplicaSet의 파드 수를 다시 올리면 된다.

## 기본 구조

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app       # 이 레이블을 가진 파드를 이 Deployment가 관리한다
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1         # 업데이트 중 원하는 수보다 최대 몇 개 더 만들어도 되는가
      maxUnavailable: 0   # 업데이트 중 최대 몇 개까지 동시에 내려도 되는가
  template:               # 만들 파드의 템플릿
    metadata:
      labels:
        app: my-app       # selector의 matchLabels와 일치해야 한다
    spec:
      containers:
      - name: my-app
        image: my-app:1.0.0
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
```

`selector.matchLabels`와 `template.metadata.labels`가 일치해야 한다. Deployment는 이 레이블로 자신이 관리해야 할 파드를 찾는다.

## 롤링 업데이트 — 무중단 배포

이미지 버전을 바꾸면 Deployment가 롤링 업데이트(Rolling Update)를 시작한다. 모든 파드를 한 번에 교체하지 않고, 일부씩 교체하면서 서비스를 유지한다.

롤링 업데이트의 진행은 두 파라미터로 제어한다.

`maxSurge`는 업데이트 도중 desired 수보다 얼마나 더 만들어도 되는지다. `replicas: 3`, `maxSurge: 1`이면 업데이트 중 최대 4개까지 파드가 동시에 실행될 수 있다.

`maxUnavailable`은 업데이트 도중 몇 개가 동시에 내려가도 되는지다. `maxUnavailable: 0`이면 새 파드가 Ready 상태가 되기 전까지 이전 파드를 내리지 않는다. 이 설정이 무중단 배포를 보장한다.

```
초기 상태:     [v1] [v1] [v1]
maxSurge=1, maxUnavailable=0

step 1:        [v1] [v1] [v1] [v2]  새 파드 1개 추가 (surge)
step 2:        [v1] [v1] [v2]       v2 Ready → v1 하나 종료
step 3:        [v1] [v1] [v2] [v2]  새 파드 1개 추가
step 4:        [v1] [v2] [v2]       v2 Ready → v1 하나 종료
step 5:        [v1] [v2] [v2] [v2]  새 파드 1개 추가
step 6:        [v2] [v2] [v2]       v2 Ready → 마지막 v1 종료
```

maxSurge와 maxUnavailable은 절대값(1, 2) 또는 퍼센트(25%)로 지정할 수 있다. 기본값은 둘 다 25%다. 파드가 4개라면 1개씩 교체한다는 뜻이다.

## Recreate 전략

`type: Recreate`를 쓰면 모든 이전 파드를 다 내리고 새 파드를 올린다. 그 사이에 서비스가 잠깐 중단된다. DB 스키마 변경처럼 이전 버전과 새 버전이 동시에 실행되면 안 되는 경우에 쓴다.

## 롤백

배포 후 문제가 발견되면 이전 버전으로 되돌릴 수 있다.

```bash
# 직전 버전으로 롤백
kubectl rollout undo deployment/my-app

# 특정 리비전으로 롤백
kubectl rollout undo deployment/my-app --to-revision=2

# 리비전 히스토리 확인
kubectl rollout history deployment/my-app

# 현재 롤아웃 상태 확인
kubectl rollout status deployment/my-app
```

Deployment는 기본적으로 최근 10개의 ReplicaSet 히스토리를 보존한다(`revisionHistoryLimit`, 기본값 10). 이 덕분에 특정 리비전으로 롤백이 가능하다. 히스토리를 너무 많이 쌓으면 사용하지 않는 ReplicaSet이 많아지므로, 실무에서는 3~5 정도로 줄이는 경우가 많다.

## 배포 일시 정지와 재개

큰 변경사항을 여러 번 업데이트하면서 한꺼번에 적용하고 싶을 때, 롤아웃을 일시 정지할 수 있다.

```bash
# 배포 일시 정지 (이후 변경사항이 바로 적용되지 않는다)
kubectl rollout pause deployment/my-app

# 이미지 변경
kubectl set image deployment/my-app my-app=my-app:2.0.0

# 환경변수 변경
kubectl set env deployment/my-app ENV=staging

# 준비됐으면 재개 (위의 모든 변경이 한꺼번에 롤아웃된다)
kubectl rollout resume deployment/my-app
```

## minReadySeconds — 성급한 롤아웃 방지

```yaml
spec:
  minReadySeconds: 10
```

새 파드가 Ready 상태가 된 후 이 초만큼 기다렸다가 다음 파드를 교체한다. 파드가 Ready 직후 크래시하는 경우, 이 설정이 없으면 롤아웃이 너무 빨리 진행돼 모든 파드가 크래시하는 상태가 될 수 있다. 10~30초 정도를 주면 새 파드가 안정적으로 동작하는지 짧게 검증하는 여유가 생긴다.

## 트레이드오프

롤링 업데이트의 핵심 감수 사항은 **업데이트 중에 이전 버전과 새 버전이 동시에 트래픽을 받는다**는 것이다. API가 하위 호환이 안 되거나, DB 스키마가 새 버전에만 맞는 구조라면 롤링 업데이트 중에 오류가 난다. 이를 피하려면 API 변경 시 하위 호환을 유지하거나, 스키마를 먼저 배포하고 앱을 나중에 배포하는 단계적 접근이 필요하다.

또한 롤백은 파드만 되돌린다. DB 마이그레이션은 함께 롤백되지 않는다. 배포 후 롤백이 필요한 상황에서 DB 변경이 있었다면, 파드 롤백과 DB 롤백을 별도로 처리해야 한다.
