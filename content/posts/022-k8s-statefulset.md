---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "022. Kubernetes StatefulSet — 순서와 신원이 필요한 파드를 위한 오브젝트"
date: 2026-06-12
tags: [kubernetes, k8s, statefulset, stateful, database, persistent-storage, headless-service, ordered-deployment]
summary: "Deployment는 파드를 교환 가능한 존재로 다루지만, DB나 메시지 큐처럼 파드마다 고유한 신원과 안정적인 스토리지가 필요한 경우가 있다. StatefulSet이 무엇인지, Deployment와 어떻게 다른지, 안정적인 네트워크 신원과 영구 스토리지를 어떻게 보장하는지, 언제 써야 하는지를 설명한다."
slug: "022-k8s-statefulset"
categories: ["쿠버네티스"]
---

Deployment는 파드를 **교환 가능(interchangeable)** 한 존재로 다룬다. 파드가 죽으면 새 파드를 만드는데, 이름도 다르고 IP도 다르고 저장소도 새것이다. 어떤 파드가 어떤 요청을 처리하든 결과가 같아야 한다. 이 전제가 무상태(stateless) 앱에는 완벽히 맞는다.

하지만 DB는 다르다. MySQL 레플리카는 자신이 primary인지 replica인지 알아야 하고, 재시작 후에도 같은 데이터를 가져야 하며, 다른 노드들이 이 노드를 이름으로 찾을 수 있어야 한다. Kafka 브로커, Redis Cluster, Elasticsearch 노드도 마찬가지다. **StatefulSet**은 이런 "신원이 있는 파드"를 위한 오브젝트다.

## Deployment와의 핵심 차이

| | Deployment | StatefulSet |
|---|---|---|
| 파드 이름 | 랜덤 접미사 (`my-app-7d8f9c-xk2p`) | 순서 번호 (`my-app-0`, `my-app-1`) |
| 파드 신원 | 교환 가능, 신원 없음 | 고유하고 안정적인 신원 |
| 스토리지 | 파드와 함께 사라짐 | 파드가 재생성돼도 같은 PVC가 재연결 |
| 시작/종료 순서 | 병렬 (순서 보장 없음) | 순서대로 (0→1→2, 역방향 종료) |
| 네트워크 이름 | Service IP로 접근 | 파드마다 안정적인 DNS 이름 |

## 안정적인 네트워크 신원

StatefulSet의 파드는 `<sts이름>-<순서번호>` 형태의 이름을 갖는다. `my-db-0`, `my-db-1`, `my-db-2`처럼. 이 이름은 파드가 재생성돼도 바뀌지 않는다. `my-db-0`이 죽으면 새로 만들어지는 파드도 이름이 `my-db-0`이다.

이 안정적인 이름을 DNS로 접근하려면 **헤드리스 서비스(Headless Service)** 가 필요하다.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-db
spec:
  clusterIP: None           # 헤드리스: 가상 IP를 할당하지 않는다
  selector:
    app: my-db
  ports:
  - port: 5432
```

헤드리스 서비스와 StatefulSet을 결합하면 각 파드에 안정적인 DNS 이름이 생긴다.

```
<파드이름>.<서비스이름>.<네임스페이스>.svc.cluster.local

my-db-0.my-db.default.svc.cluster.local
my-db-1.my-db.default.svc.cluster.local
my-db-2.my-db.default.svc.cluster.local
```

DB 클러스터 내부에서 노드들이 서로를 이 DNS 이름으로 참조한다. 파드가 재시작돼 IP가 바뀌어도 DNS 이름은 그대로이므로 클러스터 구성이 유지된다.

## 안정적인 스토리지

StatefulSet은 `volumeClaimTemplates`로 파드마다 별도의 PVC를 자동으로 만든다.

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-db
spec:
  serviceName: my-db          # 헤드리스 서비스 이름
  replicas: 3
  selector:
    matchLabels:
      app: my-db
  template:
    metadata:
      labels:
        app: my-db
    spec:
      containers:
      - name: postgres
        image: postgres:16
        env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:         # 파드마다 PVC를 자동 생성
  - metadata:
      name: data
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: fast
      resources:
        requests:
          storage: 20Gi
```

이 StatefulSet을 만들면 다음 PVC가 자동으로 생성된다.

```
data-my-db-0    (my-db-0 파드 전용)
data-my-db-1    (my-db-1 파드 전용)
data-my-db-2    (my-db-2 파드 전용)
```

`my-db-0`이 죽고 새로 만들어지면, 새 파드가 기존 `data-my-db-0` PVC에 다시 연결된다. 데이터가 그대로 살아있다.

StatefulSet을 삭제해도 PVC는 자동으로 삭제되지 않는다. 의도치 않은 데이터 삭제를 막기 위한 설계다. PVC는 수동으로 삭제해야 한다.

## 순서 보장

StatefulSet은 파드의 시작과 종료 순서를 보장한다.

**시작**: 0번부터 순서대로 생성된다. 0번이 Running + Ready가 될 때까지 1번을 만들지 않는다.

**종료**: 역순으로 종료된다. 2→1→0 순서로 내려간다.

**업데이트**: 기본적으로 역순(가장 높은 번호부터)으로 하나씩 교체한다.

이 순서 보장이 DB 클러스터 초기화에서 중요하다. primary 노드(`my-db-0`)가 먼저 완전히 뜬 뒤에 replica 노드들이 뜨면서 primary에 붙어 데이터를 동기화한다. primary가 준비되기 전에 replica가 시도하면 실패한다.

`podManagementPolicy: Parallel`로 설정하면 순서를 무시하고 병렬로 파드를 관리한다. 순서가 중요하지 않지만 StatefulSet의 다른 기능(안정적 이름, PVC 연결)이 필요할 때 쓴다.

## 언제 StatefulSet을 쓰나

k8s 위에서 DB를 직접 운영하는 것은 복잡한 일이다. 스토리지 관리, 백업, 레플리케이션, 장애 복구 모두 손이 많이 간다. 그래서 프로덕션에서는 RDS, Cloud SQL, Mongo Atlas 같은 매니지드 서비스를 쓰고 k8s 안에 DB를 두지 않는 경우도 많다.

StatefulSet이 실용적인 경우는 다음과 같다.

- 규제 등 이유로 클라우드 매니지드 DB를 못 쓰는 경우
- Redis, Kafka처럼 비교적 운영이 단순한 상태 저장 시스템
- 개발·스테이징 환경의 DB (비용 절감)
- Operator 패턴을 쓰는 경우: MongoDB Operator, PostgreSQL Operator(Zalando PGO) 같은 도구가 StatefulSet 위에 DB 운영의 복잡성을 자동화한다

## 트레이드오프

StatefulSet의 순서 보장은 안전하지만 느리다. 파드 3개를 업데이트하면 하나씩 순서대로 진행되므로 Deployment의 롤링 업데이트보다 오래 걸린다. 하나가 실패하면 업데이트가 거기서 멈춘다.

PVC는 StatefulSet이 삭제돼도 남는다. 이는 데이터 보호의 의도이지만, 클러스터를 정리하거나 테스트 환경을 재구성할 때 잊어버린 PVC가 비용을 계속 쓰는 문제가 된다. StatefulSet 삭제 후 PVC를 명시적으로 정리하는 습관이 필요하다.
