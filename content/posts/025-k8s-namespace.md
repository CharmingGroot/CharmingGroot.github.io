---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "025. Kubernetes Namespace — 클러스터 안의 논리적 격리 단위"
date: 2026-06-12
tags: [kubernetes, k8s, namespace, isolation, rbac, resource-quota, limit-range, multi-tenancy]
summary: "Namespace는 하나의 클러스터를 여러 논리적 공간으로 나누는 메커니즘이다. 팀별, 환경별, 서비스 도메인별로 나눌 수 있고, RBAC과 NetworkPolicy, ResourceQuota와 결합해 진짜 격리를 구현한다. 언제 Namespace로 나누고 언제 클러스터를 아예 분리해야 하는지, 기본 Namespace들이 어떤 역할인지를 설명한다."
slug: "025-k8s-namespace"
categories: ["쿠버네티스"]
---

k8s 클러스터는 기본적으로 하나의 평평한 공간이다. 모든 파드가 같은 네트워크에 있고, 이름 충돌이 없는 한 어디서든 다 보인다. 팀이 하나이고 서비스가 몇 개 없다면 이것으로 충분하다. 하지만 여러 팀이 같은 클러스터를 쓰거나, 개발·스테이징·프로덕션을 같은 클러스터에서 운영하거나, 서비스 규모가 커지면 구획이 필요해진다.

Namespace는 클러스터 안의 **논리적 격리 단위**다. 같은 이름의 오브젝트도 다른 Namespace에는 따로 존재할 수 있고, RBAC과 NetworkPolicy, ResourceQuota를 Namespace 단위로 적용해 격리와 권한 제어를 구현한다.

## 기본 Namespace

클러스터를 처음 만들면 네 가지 Namespace가 있다.

`default`: Namespace를 지정하지 않으면 오브젝트가 여기 들어간다. 처음엔 편하지만 모든 것이 섞여 관리가 어려워진다. 실제 워크로드는 여기에 두지 않는 것이 좋다.

`kube-system`: k8s 시스템 컴포넌트가 있는 곳. kube-dns(CoreDNS), kube-proxy, metrics-server, Ingress Controller 등이 여기 돌아간다. 직접 수정하지 않는 것이 원칙이다.

`kube-public`: 모든 사용자가 읽을 수 있는 공개 정보. 클러스터 정보 같은 것이 여기 있다.

`kube-node-lease`: 각 노드가 heartbeat를 저장하는 곳. 노드 상태 감지에 쓰인다.

## Namespace 만들기

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    env: production              # NetworkPolicy의 namespaceSelector에서 쓰인다
    team: platform
```

또는

```bash
kubectl create namespace production
```

오브젝트를 만들 때 Namespace를 지정한다.

```bash
kubectl apply -f deployment.yaml -n production
kubectl get pods -n production
kubectl get pods --all-namespaces    # 또는 -A
```

## RBAC과 결합: 팀별 접근 제어

Namespace의 가장 강력한 쓰임새는 RBAC과 결합한 팀별 접근 제어다.

```yaml
# 팀 A는 자기 Namespace만 관리할 수 있다
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-a-admin
  namespace: team-a           # 이 Namespace 안에서만 유효
subjects:
- kind: Group
  name: team-a                # 팀 A의 사용자 그룹
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: admin                 # k8s 기본 제공 역할
  apiGroup: rbac.authorization.k8s.io
```

팀 A는 `team-a` Namespace에서 admin 권한을 갖지만, `team-b`나 `production` Namespace에는 접근할 수 없다. 팀들이 서로의 리소스를 건드리지 않고 독립적으로 작업할 수 있다.

## ResourceQuota — Namespace별 자원 제한

여러 팀이 같은 클러스터를 쓸 때, 한 팀이 자원을 과도하게 쓰면 다른 팀에 영향을 준다. ResourceQuota로 Namespace가 쓸 수 있는 자원 총량을 제한한다.

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-a-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "10"          # 이 Namespace 전체 CPU requests 합계 10코어 이하
    requests.memory: 20Gi       # 전체 메모리 requests 20Gi 이하
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "50"                  # 파드 수 50개 이하
    services: "10"
    persistentvolumeclaims: "20"
    services.loadbalancers: "2" # LoadBalancer 타입 Service 2개 이하 (비용 제한)
```

ResourceQuota가 있는 Namespace에서는 파드에 `resources.requests`와 `resources.limits`를 반드시 설정해야 한다. 안 하면 파드가 생성되지 않는다.

## LimitRange — 기본값과 최솟값 설정

ResourceQuota가 Namespace 전체 총량을 제한한다면, LimitRange는 개별 파드·컨테이너의 최솟값, 최댓값, 기본값을 정한다.

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: team-a
spec:
  limits:
  - type: Container
    default:                  # requests/limits를 안 쓴 컨테이너에 적용되는 기본값
      cpu: "200m"
      memory: "256Mi"
    defaultRequest:
      cpu: "100m"
      memory: "128Mi"
    max:                      # 이 이상은 못 쓴다
      cpu: "2"
      memory: "2Gi"
    min:                      # 이 이하로는 못 설정한다
      cpu: "50m"
      memory: "64Mi"
```

LimitRange가 있으면 requests/limits를 명시하지 않은 파드에 기본값이 자동 적용된다. ResourceQuota와 함께 쓰면 파드마다 requests를 강제하지 않아도 Namespace 전체 자원이 관리된다.

## 어떻게 나눌 것인가

Namespace 분리 기준은 정답이 없고, 조직과 운영 방식에 따라 다르다.

**환경 기준**: `dev`, `staging`, `production`. 가장 흔한 패턴. 환경별로 RBAC, ResourceQuota, NetworkPolicy를 달리 적용하기 좋다. 하지만 프로덕션과 개발이 같은 클러스터에 있으면 개발 환경의 문제가 클러스터 자원을 잡아먹어 프로덕션에 영향을 줄 수 있다.

**팀 기준**: `team-payments`, `team-orders`. 팀 자율성을 주고 서로 간섭을 줄이는 방식. 팀 간 공유 서비스(모니터링, 인프라)는 별도 Namespace에 둔다.

**도메인 기준**: `payments`, `orders`, `users`. 마이크로서비스가 많으면 도메인 단위로 묶는 것이 관리하기 좋다.

실무에서는 환경과 팀을 결합한 방식도 많다. `payments-production`, `payments-staging`처럼 쓰거나, 프로덕션은 아예 별도 클러스터로 분리하고 개발·스테이징만 같은 클러스터에 두는 경우도 흔하다.

## Namespace는 완전한 격리가 아니다

중요한 한계를 이해해야 한다. Namespace는 **논리적** 격리다. 물리적·강한 격리가 아니다.

- 기본적으로 다른 Namespace의 파드와 네트워크 통신이 가능하다. 완전히 막으려면 NetworkPolicy가 필요하다.
- Node, PersistentVolume, StorageClass, ClusterRole처럼 Namespace에 속하지 않는 **클러스터 레벨 오브젝트**는 Namespace로 분리되지 않는다.
- 파드가 노드를 공유한다. 한 Namespace의 파드가 노이지 네이버(noisy neighbor) 문제로 노드 자원을 과점하면 다른 Namespace에도 영향을 준다. ResourceQuota로 완화할 수 있지만 완벽하지 않다.

강한 격리가 필요하다면 — 보안 요구사항이 엄격하거나, 다른 고객의 워크로드를 완전히 분리해야 하는 경우 — 클러스터 자체를 분리하는 것이 더 확실하다.

## 트레이드오프

Namespace를 많이 나누면 관리 오브젝트도 선형으로 늘어난다. 네임스페이스마다 RBAC, ResourceQuota, LimitRange, NetworkPolicy를 만들어야 한다. 새 팀이 생기거나 환경이 추가될 때마다 이 설정들을 복사하고 맞춰야 한다. 이 반복 작업을 줄이려면 Namespace 프로비저닝을 자동화하는 도구(Helm chart, Argo CD Application, Namespace 템플릿)를 쓰는 것이 현실적이다.

반대로 너무 적게 나누면 팀들이 같은 공간에 오브젝트를 만들다가 이름 충돌, 권한 관리 어려움, 자원 과점 문제를 겪는다. default Namespace 하나에 모든 것을 몰아넣는 것은 클러스터가 작을 때만 통한다.
