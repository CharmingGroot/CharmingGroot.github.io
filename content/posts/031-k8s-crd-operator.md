---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "031. Kubernetes CRD & Operator 패턴 — k8s를 플랫폼으로 확장하기"
date: 2026-06-12
tags: [kubernetes, k8s, crd, custom-resource, operator, controller, reconciliation, kubebuilder, cert-manager, postgres-operator]
summary: "k8s는 Deployment, Service, ConfigMap 같은 기본 리소스 외에 사용자 정의 리소스(CRD)를 추가할 수 있다. Operator 패턴은 CRD로 새 리소스를 정의하고, 컨트롤러가 그 리소스의 desired state를 실현하는 구조다. cert-manager, Postgres Operator처럼 복잡한 운영 지식을 자동화하는 데 쓰인다."
slug: "031-k8s-crd-operator"
categories: ["쿠버네티스"]
---

k8s의 선언형 모델은 강력하다. Deployment에 `replicas: 5`를 선언하면 컨트롤러가 알아서 파드를 유지한다. 이 모델을 기본 리소스(Deployment, Service 등)만이 아니라 **도메인 특화 리소스**에도 적용할 수 있다면 어떨까.

CRD(Custom Resource Definition)는 k8s에 새 리소스 타입을 추가하는 메커니즘이다. `PostgresCluster`나 `Certificate` 같은 리소스를 정의하면 `kubectl get postgresclusters` 처럼 기본 리소스처럼 다룰 수 있다. Operator 패턴은 이 CRD와 컨트롤러를 결합해, 복잡한 운영 작업을 자동화하는 방법이다.

## CRD — 새 리소스 타입 정의

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: widgets.example.com      # <복수명>.<그룹>
spec:
  group: example.com
  versions:
  - name: v1
    served: true
    storage: true
    schema:
      openAPIV3Schema:
        type: object
        properties:
          spec:
            type: object
            properties:
              color:
                type: string
              size:
                type: integer
                minimum: 1
                maximum: 100
          status:
            type: object
            properties:
              ready:
                type: boolean
              message:
                type: string
  scope: Namespaced              # 또는 Cluster
  names:
    plural: widgets
    singular: widget
    kind: Widget
    shortNames:
    - wg
```

CRD를 클러스터에 적용하면 이제 `Widget` 오브젝트를 만들 수 있다.

```yaml
apiVersion: example.com/v1
kind: Widget
metadata:
  name: my-widget
spec:
  color: blue
  size: 42
```

```bash
kubectl get widgets
kubectl describe widget my-widget
```

CRD만 있으면 리소스를 저장하고 읽을 수 있다. 하지만 이 리소스가 실제로 무언가를 **하게** 만들려면 컨트롤러가 필요하다.

## Operator — 컨트롤러와 CRD의 결합

Operator 패턴은 CoreOS(현 Red Hat)가 제안한 개념이다. 운영자(Operator)가 수동으로 하던 작업 — DB 클러스터 확장, 백업, 장애 복구, 버전 업그레이드 — 을 소프트웨어로 자동화한다.

구조는 단순하다.

1. CRD로 원하는 상태를 선언하는 리소스를 정의한다.
2. 컨트롤러가 그 리소스를 감시하고, desired state와 actual state의 차이를 없애는 **Reconcile 루프**를 실행한다.

```
사용자: Widget CR 생성/수정/삭제
    ↓
API Server에 이벤트 발생
    ↓
Controller: Watch → Reconcile 함수 호출
    ↓
현재 상태 확인 (k8s 리소스, 외부 시스템)
    ↓
desired state와 diff 계산
    ↓
필요한 작업 수행 (파드 생성, DB 설정 변경 등)
    ↓
status 업데이트
```

Reconcile 함수는 **멱등성**을 가져야 한다. 같은 상태를 여러 번 적용해도 결과가 같아야 한다. 컨트롤러는 오류가 생기면 재시도하고, 재시작 후에도 상태를 보고 올바른 방향으로 수렴한다.

## 실제 사례: cert-manager

cert-manager는 TLS 인증서 발급과 갱신을 자동화하는 Operator다.

```yaml
# cert-manager가 제공하는 CRD: Certificate
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: api-tls
  namespace: production
spec:
  secretName: api-tls-secret       # 인증서를 저장할 Secret 이름
  duration: 2160h                  # 90일
  renewBefore: 360h                # 만료 15일 전에 갱신
  dnsNames:
  - api.example.com
  - www.example.com
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
```

이 YAML을 적용하면 cert-manager 컨트롤러가:
1. Let's Encrypt에 인증서 발급 요청
2. ACME 챌린지 수행 (HTTP-01 또는 DNS-01)
3. 발급된 인증서를 `api-tls-secret` Secret에 저장
4. 만료 15일 전에 자동으로 갱신

기존에는 Certbot을 cron으로 돌리고 nginx를 재시작하는 등의 수동 작업이었다. cert-manager는 이 모든 것을 `Certificate` 리소스 하나로 선언적으로 관리한다.

## 실제 사례: Postgres Operator (CrunchyData PGO)

```yaml
apiVersion: postgres-operator.crunchydata.com/v1beta1
kind: PostgresCluster
metadata:
  name: my-postgres
  namespace: production
spec:
  postgresVersion: 15
  instances:
  - name: instance1
    replicas: 3                    # Primary 1 + Standby 2
    dataVolumeClaimSpec:
      accessModes:
      - ReadWriteOnce
      resources:
        requests:
          storage: 100Gi
  backups:
    pgbackrest:
      repos:
      - name: repo1
        s3:
          bucket: my-postgres-backups
          endpoint: s3.amazonaws.com
          region: ap-northeast-2
        schedules:
          full: "0 2 * * 0"       # 매주 일요일 새벽 2시 풀 백업
          incremental: "0 2 * * 1-6"  # 평일 새벽 2시 증분 백업
```

이 선언 하나로 Operator가:
- Primary + Standby PostgreSQL 클러스터 구성
- Replication 설정
- S3 자동 백업 스케줄
- Standby 장애 시 자동 Failover
- 버전 업그레이드 시 Rolling 방식으로 처리

수십 줄의 쉘 스크립트와 cron 작업이 YAML 선언 하나로 대체된다.

## Kubebuilder — Operator 개발 도구

직접 Operator를 만들 때는 **Kubebuilder** 또는 **Operator SDK**를 쓴다. Kubebuilder는 Go 기반 스캐폴딩을 제공한다.

```bash
# 프로젝트 초기화
kubebuilder init --domain example.com --repo github.com/my-org/my-operator

# API (CRD + Controller) 생성
kubebuilder create api --group apps --version v1 --kind Widget
```

이 명령이 CRD 스캐폴드, 컨트롤러 파일, 테스트 파일을 자동 생성한다. 개발자는 `Reconcile` 함수만 채우면 된다.

```go
func (r *WidgetReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    widget := &appsv1.Widget{}
    if err := r.Get(ctx, req.NamespacedName, widget); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // desired state 구현: 필요한 Deployment, Service 생성/수정
    // ...

    // status 업데이트
    widget.Status.Ready = true
    r.Status().Update(ctx, widget)

    return ctrl.Result{}, nil
}
```

## 트레이드오프

Operator는 강력하지만 복잡도 비용이 있다. 컨트롤러 코드가 버그를 가지면 리소스가 잘못된 상태로 수렴할 수 있다. Reconcile이 외부 시스템(DB, 클라우드 API)을 변경하는 경우 롤백이 어렵다.

오픈소스 Operator를 쓸 때는 버전과 CRD 스키마 변경을 주의해야 한다. CRD의 `spec` 구조가 버전마다 달라지는 경우가 있고, 업그레이드 시 기존 CR이 새 스키마와 호환되지 않으면 문제가 된다. 업그레이드 전 마이그레이션 가이드를 반드시 확인한다.

단순한 배포 자동화는 Helm이나 Kustomize로 충분하다. Operator는 **운영 지식(장애 복구, 백업, 버전 업그레이드 절차)** 을 자동화해야 할 때 가치가 있다. 상태가 없는 단순 서비스에 Operator를 만드는 것은 과한 복잡도다.
