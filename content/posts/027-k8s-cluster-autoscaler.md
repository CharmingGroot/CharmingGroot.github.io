---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "027. Kubernetes Cluster Autoscaler — 파드가 올라갈 노드를 자동으로 늘리고 줄이기"
date: 2026-06-12
tags: [kubernetes, k8s, cluster-autoscaler, karpenter, node, scaling, hpa, cost-optimization]
summary: "HPA가 파드 수를 조절하면, 새 파드를 올릴 노드가 부족해지는 상황이 생긴다. Cluster Autoscaler는 Pending 상태인 파드를 감지해 노드를 추가하고, 유휴 노드를 제거해 비용을 절감한다. HPA와 어떻게 협력하는지, 노드를 어떻게 선택하는지, 스케일 인 중 파드 안전성을 어떻게 보장하는지, 그리고 차세대 도구인 Karpenter와의 차이를 설명한다."
slug: "027-k8s-cluster-autoscaler"
categories: ["쿠버네티스"]
---

HPA가 트래픽에 따라 파드를 10개로 늘렸는데, 클러스터 노드가 3대뿐이고 이미 가득 찼다면 새 파드들은 Pending 상태로 머문다. 자원이 없으니 스케줄이 안 된다. 반대로 새벽에 트래픽이 없어 파드가 2개뿐인데 노드 10대가 켜져 있다면 비용 낭비다.

Cluster Autoscaler(CA)는 이 두 문제를 해결한다. Pending 파드가 생기면 노드를 추가하고, 노드 자원 사용률이 낮으면 노드를 줄인다. HPA가 파드 수를 조절하는 수평 확장이라면, CA는 파드가 올라갈 인프라를 조절하는 **인프라 레벨 확장**이다.

## HPA와 CA의 협력 구조

```
트래픽 증가
    ↓
HPA: CPU 사용률 초과 감지 → 파드 수 증가 결정
    ↓
스케줄러: 새 파드를 노드에 배치 시도
    ↓
자원 부족 → 파드 Pending 상태
    ↓
CA: Pending 파드 감지 → 노드 추가 (클라우드 API 호출)
    ↓
새 노드 준비 완료 → 파드 스케줄
```

이 과정은 직렬로 일어나므로 **노드가 추가되는 데 수 분이 걸린다**. 노드 이미지 부팅, k8s 컴포넌트 시작, 노드 등록, 파드 이미지 풀까지 합산하면 보통 2~5분이다. HPA가 스케일 아웃을 결정하고 실제로 트래픽을 처리할 때까지 공백이 생긴다. `minReplicas`를 충분히 잡아두거나, 트래픽 폭증이 예상되면 미리 노드를 확보해두는 것이 이 공백을 줄이는 방법이다.

## 설치와 설정

CA는 클라우드 프로바이더별로 다르게 설치한다. AWS EKS 기준으로는 Node Group(Auto Scaling Group)을 만들고, CA가 그 그룹의 최소/최대 노드 수를 조정한다.

```yaml
# CA Deployment의 핵심 설정 (일부)
command:
- ./cluster-autoscaler
- --cloud-provider=aws
- --nodes=2:20:my-node-group    # 최소:최대:그룹이름
- --scale-down-enabled=true
- --scale-down-utilization-threshold=0.5   # 사용률 50% 미만 노드는 제거 후보
- --scale-down-unneeded-time=10m           # 10분 이상 불필요한 노드를 제거
- --skip-nodes-with-local-storage=true     # emptyDir 같은 로컬 스토리지 파드가 있으면 제거 안 함
- --skip-nodes-with-system-pods=true       # 시스템 파드가 있는 노드는 제거 안 함
```

## 스케일 인 — 노드 제거의 조건

CA가 노드를 제거하려면 여러 조건을 확인한다.

노드 사용률이 임계값(`scale-down-utilization-threshold`, 기본 50%) 미만이어야 한다. 그 노드의 파드들이 다른 노드로 이동 가능해야 한다. `--skip-nodes-with-local-storage`가 설정돼 있으면 emptyDir 볼륨을 쓰는 파드가 있는 노드는 제거하지 않는다. PodDisruptionBudget을 위반하지 않아야 한다.

노드를 제거할 때는 먼저 **drain** 처리를 한다. 그 노드의 파드들을 정상적으로 종료하고 다른 노드로 이동시킨 뒤 노드를 삭제한다. 이 과정에서 PDB가 중요하다. `minAvailable: 2`인 Deployment에서 2개의 파드가 모두 이 노드에 있다면, 드레인 중 두 파드가 동시에 내려가는 것을 PDB가 막아 CA가 그 노드를 제거하지 못한다. PDB와 파드 분산(anti-affinity)을 함께 설정하면 스케일 인 중에도 가용성이 유지된다.

## 노드 그룹(Node Group) 설계

CA는 노드 그룹 단위로 스케일한다. 다양한 워크로드를 처리하려면 목적에 맞는 노드 그룹을 여러 개 두는 것이 일반적이다.

```
일반 워크로드용: m5.xlarge × 2~20
메모리 집약형: r5.2xlarge × 0~10
GPU 워크로드용: p3.2xlarge × 0~5 (평소 0개, 필요 시 추가)
```

GPU 노드 그룹을 평소 0개로 유지하다가 필요할 때만 켜면 비용이 크게 줄어든다. Taint & Toleration을 함께 써서 GPU 파드만 GPU 노드에 스케줄되도록 강제한다.

## Karpenter — CA의 대안

AWS가 개발한 **Karpenter**는 CA의 몇 가지 한계를 개선한 도구다. 지금은 AWS 외 환경도 지원하기 시작했다.

CA와 가장 다른 점은 노드 그룹 없이 파드의 요구사항을 직접 보고 최적의 인스턴스 타입을 선택한다는 것이다. 파드가 요청한 CPU/메모리에 가장 잘 맞는 인스턴스를 즉시 프로비저닝한다. 또한 Spot 인스턴스를 자동으로 활용해 비용을 최적화하고, 필요 없어진 노드를 더 공격적으로 통합(consolidation)해 낭비를 줄인다.

| | Cluster Autoscaler | Karpenter |
|---|---|---|
| 노드 선택 | 미리 정의된 노드 그룹 | 파드 요구사항 보고 최적 타입 선택 |
| 반응 속도 | 상대적으로 느림 | 빠름 |
| 비용 최적화 | 수동 설정 필요 | Spot 자동 활용, 통합 적극적 |
| 설정 복잡도 | 노드 그룹 관리 필요 | 더 단순 |
| 클라우드 지원 | 멀티 클라우드 | AWS 중심 (확장 중) |

AWS EKS 환경이라면 Karpenter가 더 권장된다. 다른 클라우드나 온프레미스라면 CA가 여전히 표준이다.

## 트레이드오프

CA의 가장 큰 단점은 **노드 추가에 걸리는 시간**이다. 트래픽이 갑자기 몰리는 상황에서는 CA가 반응하기 전에 기존 노드들이 과부하를 감당해야 한다. 이를 완화하려면 오버프로비저닝(여유 노드 유지), 파드 Pending 알림 설정, HPA의 `minReplicas` 충분히 확보 같은 보완책이 필요하다.

스케일 인은 보수적으로 동작한다. 이는 의도된 설계지만, 낮은 트래픽이 지속되는 시간대에도 노드가 천천히 줄어 일시적 비용 낭비가 생길 수 있다. `scale-down-unneeded-time`을 짧게 하면 더 빠르게 줄어들지만, 트래픽이 다시 오를 때 새 노드를 기다려야 하는 지연이 생긴다.
