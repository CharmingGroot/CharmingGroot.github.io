---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "016. Kubernetes ServiceAccount & RBAC — 파드의 신원과 권한 제어"
date: 2026-06-12
tags: [kubernetes, k8s, serviceaccount, rbac, role, clusterrole, rolebinding, least-privilege, security]
summary: "ServiceAccount는 파드가 k8s API를 호출할 때 쓰는 신원(identity)이다. RBAC은 그 신원에 어떤 리소스에 어떤 작업을 허용할지 정하는 권한 체계다. Role, ClusterRole, RoleBinding, ClusterRoleBinding이 어떻게 조합되는지, 최소 권한 원칙을 어떻게 적용하는지를 설명한다."
slug: "016-k8s-serviceaccount"
categories: ["쿠버네티스"]
---

파드가 k8s API Server에 요청을 보낼 때 — ConfigMap을 읽거나, 다른 파드 목록을 조회하거나, Deployment를 수정하는 등 — 그 요청이 허용되는지 판단하려면 "이 요청을 보낸 게 누구인가"를 알아야 한다. 사람에게 사용자 계정이 있듯, 파드에는 **ServiceAccount**가 있다.

## ServiceAccount가 필요한 이유

많은 서비스는 API Server를 직접 호출하지 않는다. 하지만 다음 경우에는 반드시 필요하다.

- CI/CD 파이프라인이 Deployment를 업데이트한다
- Operator나 컨트롤러가 파드나 서비스를 감시하고 수정한다
- 앱이 자신이 실행 중인 노드 정보를 조회한다
- Prometheus가 파드의 메트릭 엔드포인트 목록을 k8s API에서 가져온다
- Vault Agent가 API Server에서 파드의 신원을 검증한다

파드에 ServiceAccount를 명시하지 않으면 네임스페이스의 `default` ServiceAccount가 자동 할당된다. 이 기본 ServiceAccount는 권한이 없으므로 대부분의 API 호출이 차단된다.

## ServiceAccount 토큰

파드가 시작되면 ServiceAccount에 연결된 **JWT 토큰**이 파드 안의 고정 경로(`/var/run/secrets/kubernetes.io/serviceaccount/token`)에 자동 마운트된다. API Server에 요청할 때 이 토큰을 `Authorization: Bearer <token>` 헤더에 담아 보내면 API Server가 신원을 확인한다.

```
파드 → API Server 요청 → API Server가 토큰 검증
                              ↓
                    RBAC: 이 ServiceAccount에
                    이 작업이 허용돼 있나?
                              ↓
                    허용 → 응답 / 거부 → 403
```

## RBAC — 역할 기반 접근 제어

RBAC(Role-Based Access Control)은 "누가 어떤 리소스에 어떤 작업을 할 수 있는가"를 정의하는 체계다. 네 가지 오브젝트로 구성된다.

**Role**: 특정 네임스페이스 안에서 허용할 권한을 정의한다.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: production
rules:
- apiGroups: [""]          # "" = core API 그룹
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get"]
```

`verbs`는 허용할 동작이다. `get`, `list`, `watch`, `create`, `update`, `patch`, `delete`가 있다. `"*"`는 전체 허용.

**ClusterRole**: Role과 같지만 특정 네임스페이스가 아니라 **클러스터 전체** 또는 네임스페이스가 없는 리소스(Node, PersistentVolume 등)에 대한 권한을 정의한다.

**RoleBinding**: Role을 특정 대상(ServiceAccount, 사용자, 그룹)에 연결한다. "이 네임스페이스에서 이 Role을 이 ServiceAccount에게 준다"는 것이다.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-pods
  namespace: production
subjects:
- kind: ServiceAccount
  name: my-app
  namespace: production
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

**ClusterRoleBinding**: ClusterRole을 클러스터 전체 범위로 대상에 연결한다.

## 전체 구성 예시

```yaml
# 1. ServiceAccount 생성
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-app
  namespace: production

---
# 2. 필요한 권한을 Role로 정의
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: my-app-role
  namespace: production
rules:
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["secrets"]
  resourceNames: ["my-app-secret"]   # 특정 Secret만 접근 허용
  verbs: ["get"]

---
# 3. Role을 ServiceAccount에 연결
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: my-app-rolebinding
  namespace: production
subjects:
- kind: ServiceAccount
  name: my-app
  namespace: production
roleRef:
  kind: Role
  name: my-app-role
  apiGroup: rbac.authorization.k8s.io

---
# 4. Deployment에서 ServiceAccount 지정
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      serviceAccountName: my-app    # 이 파드는 my-app ServiceAccount로 실행된다
      containers:
      - name: app
        image: my-app:1.0.0
```

## 최소 권한 원칙

RBAC 설계의 핵심 원칙은 **최소 권한(least privilege)** 이다. 파드가 실제로 필요한 것만 정확히 허용하고, 나머지는 차단한다.

흔한 실수는 편의를 위해 `cluster-admin` 권한을 주거나, `"*"` 와일드카드로 모든 리소스에 모든 권한을 주는 것이다. 그 파드가 침해되면 공격자가 클러스터 전체를 제어할 수 있다.

`resourceNames`로 특정 오브젝트만 지정할 수도 있다. "이 파드는 이 Secret 하나만 읽을 수 있다"처럼 리소스 종류뿐 아니라 특정 인스턴스까지 제한하는 것이 더 엄격한 권한 제어다.

## automountServiceAccountToken 비활성화

API Server를 전혀 호출하지 않는 파드라면 토큰 마운트 자체를 꺼두는 것이 좋다.

```yaml
spec:
  automountServiceAccountToken: false
```

토큰이 없으면 파드가 침해되어도 공격자가 API Server에 접근할 수 없다. Deployment의 `spec.template.spec`에 설정하면 해당 파드에 적용되고, ServiceAccount에 설정하면 그 계정을 쓰는 모든 파드에 적용된다.

## 트레이드오프

RBAC을 제대로 설정하면 파드 침해의 폭발 반경(blast radius)을 줄일 수 있다. 반면 서비스마다 ServiceAccount와 Role과 RoleBinding을 만들고 관리하는 것은 번거롭다. 서비스가 많아질수록 이 오브젝트들이 쌓여 관리 부담이 된다.

현실적인 전략은 최소한 두 가지를 지키는 것이다. 첫째, API Server를 호출하지 않는 파드는 `automountServiceAccountToken: false`. 둘째, API Server를 호출하는 파드는 `default` ServiceAccount가 아닌 전용 ServiceAccount를 만들고, 필요한 권한만 정확히 정의한다. 이 두 가지만 지켜도 기본 보안 수준이 크게 올라간다.
