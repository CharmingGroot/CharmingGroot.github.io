---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "028. Kubernetes Taint, Toleration, Affinity — 파드가 어떤 노드에 올라갈지 제어하기"
date: 2026-06-12
tags: [kubernetes, k8s, taint, toleration, affinity, node-affinity, pod-affinity, anti-affinity, scheduling, topology]
summary: "기본적으로 스케줄러는 자원이 충분한 노드에 파드를 자유롭게 배치한다. Taint와 Toleration은 노드를 특수 목적으로 예약하고, Affinity는 파드가 특정 노드에 또는 특정 파드 근처에 배치되도록 유도한다. GPU 노드 예약, 파드 고가용성 분산, 같이 실행해야 하는 파드 모으기를 어떻게 구현하는지 설명한다."
slug: "028-k8s-taint-affinity"
categories: ["쿠버네티스"]
---

스케줄러는 기본적으로 자원이 충분한 노드를 골라 파드를 올린다. 이 기본 동작으로 충분한 경우가 많지만, 운영하다 보면 더 세밀하게 제어해야 하는 상황이 생긴다. GPU가 있는 노드에는 GPU 작업 파드만 올려야 한다, DB 파드들이 같은 노드에 모이지 않도록 분산해야 한다, 같이 쓰는 두 서비스는 같은 노드에 올려 네트워크 지연을 줄여야 한다 같은 경우다.

이를 제어하는 메커니즘이 **Taint/Toleration**과 **Affinity**다.

## Taint와 Toleration — 노드 출입 허가

Taint는 노드에 붙이는 거부 표시다. "이 노드는 허가받은 파드만 올 수 있다"고 선언한다. Toleration은 파드에 붙이는 허가증이다. "나는 이 Taint를 감수할 수 있다"고 선언한다. 두 조건이 맞으면 스케줄이 허용된다.

```bash
# 노드에 Taint 추가
kubectl taint nodes gpu-node-1 dedicated=gpu:NoSchedule
```

```yaml
# 파드에 Toleration 설정
spec:
  tolerations:
  - key: "dedicated"
    operator: "Equal"
    value: "gpu"
    effect: "NoSchedule"
```

`effect`는 세 종류다.

`NoSchedule`: 이 Taint를 감수하지 못하는 파드는 이 노드에 스케줄되지 않는다. 이미 실행 중인 파드는 영향받지 않는다.

`PreferNoSchedule`: 가능하면 이 노드를 피하지만, 다른 선택지가 없으면 스케줄된다. 소프트 규칙이다.

`NoExecute`: 새 파드를 스케줄하지 않으며, 이미 실행 중인 파드도 감수하지 못하면 **축출(evict)** 한다. 노드 장애 시 k8s가 자동으로 이 Taint를 붙여 파드를 다른 노드로 옮기는 데도 쓰인다.

### GPU 노드 전용 예약 패턴

```bash
# GPU 노드에 Taint
kubectl taint nodes gpu-node-1 gpu=true:NoSchedule
kubectl taint nodes gpu-node-2 gpu=true:NoSchedule
```

```yaml
# GPU 작업 파드에만 Toleration + 노드 선택
spec:
  tolerations:
  - key: "gpu"
    operator: "Exists"
    effect: "NoSchedule"
  nodeSelector:
    gpu: "true"
  containers:
  - name: ml-training
    resources:
      limits:
        nvidia.com/gpu: 1
```

Taint만 있으면 GPU 파드가 GPU 노드에도 갈 수 있고 일반 노드에도 갈 수 있다. `nodeSelector`나 Affinity로 GPU 파드를 GPU 노드로 당겨야 온전히 예약된다.

## Node Affinity — 파드를 특정 노드로 유도

Affinity는 Taint와 반대 방향이다. 노드가 파드를 거부하는 게 아니라, 파드가 특정 노드를 선호(또는 요구)한다.

`requiredDuringSchedulingIgnoredDuringExecution`: **필수** 조건. 맞는 노드가 없으면 파드가 Pending 상태로 기다린다. (nodeSelector의 강화판)

`preferredDuringSchedulingIgnoredDuringExecution`: **선호** 조건. 가능하면 이 노드를 선호하지만, 없으면 다른 노드에 스케줄된다. `weight`로 여러 선호도에 우선순위를 줄 수 있다.

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: kubernetes.io/arch
            operator: In
            values:
            - amd64              # AMD64 아키텍처 노드에서만 실행
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
          - key: topology.kubernetes.io/zone
            operator: In
            values:
            - ap-northeast-2a    # 가능하면 이 AZ 선호
      - weight: 20
        preference:
          matchExpressions:
          - key: node-type
            operator: In
            values:
            - spot               # 2순위로 Spot 인스턴스 선호
```

## Pod Affinity와 Anti-Affinity — 파드 간 배치 관계

Node Affinity가 "어떤 노드에 올라갈지"라면, Pod Affinity/Anti-Affinity는 "어떤 파드와 같은 노드(또는 같은 AZ)에 배치될지"를 제어한다.

**Pod Affinity**: 특정 파드와 **가까운 곳**에 배치되길 원할 때. 같은 노드 배치로 네트워크 지연을 줄이거나 같은 AZ에 두어 데이터 전송 비용을 절감할 때 쓴다.

**Pod Anti-Affinity**: 특정 파드와 **멀리 배치**되길 원할 때. 고가용성을 위해 같은 서비스의 파드들이 서로 다른 노드나 AZ에 분산되도록 강제하는 데 가장 많이 쓴다.

```yaml
spec:
  affinity:
    podAntiAffinity:
      # 필수: 같은 hostname(= 같은 노드)에 app=my-app 파드가 있으면 스케줄 안 함
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: my-app
        topologyKey: kubernetes.io/hostname
      # 선호: 가능하면 다른 AZ에 분산
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: my-app
          topologyKey: topology.kubernetes.io/zone
```

`topologyKey`가 중요하다. 분산의 기준이 되는 노드 레이블이다. `kubernetes.io/hostname`이면 노드 단위, `topology.kubernetes.io/zone`이면 AZ 단위로 분산된다.

위 설정은 "같은 노드에는 절대 두 파드가 올라가지 않고(required), 가능하면 다른 AZ에 분산(preferred)"이다. DB나 API 서버처럼 단일 노드 장애로 전체가 다운되면 안 되는 서비스에 필수적인 설정이다.

## 세 메커니즘의 관계

셋은 독립적이지만 함께 써서 세밀한 스케줄링을 구현한다.

```
Taint/Toleration: 노드 접근 허가 (방어적, 노드 주도)
Node Affinity:    파드가 원하는 노드 (능동적, 파드 주도)
Pod Affinity:     파드 간 배치 관계 (상대적)
```

GPU 노드에 GPU 작업만 올리는 완전한 구성은 이렇다.
1. GPU 노드에 Taint → 일반 파드가 GPU 노드에 못 들어옴
2. GPU 파드에 Toleration → GPU 노드에 들어올 수 있음
3. GPU 파드에 Node Affinity (required) → GPU 노드에만 스케줄됨

## 트레이드오프

Anti-Affinity를 `requiredDuringScheduling`으로 설정하면 스케줄러가 조건을 만족하는 노드를 못 찾으면 파드가 Pending 상태로 멈춘다. 예를 들어 파드 3개를 서로 다른 노드에 강제하는데 노드가 2개뿐이면 3번째 파드가 영원히 Pending이다. 클러스터 노드 수와 Affinity 조건의 현실적 조합을 확인해야 한다.

`preferredDuringScheduling`은 조건이 안 맞아도 스케줄이 진행돼 유연하지만, 보장이 없어 고가용성을 실제로 달성했는지 확인하기 어렵다. 중요한 서비스의 분산 보장은 `required`를 쓰고 클러스터 용량을 충분히 확보하는 것이 맞다.
