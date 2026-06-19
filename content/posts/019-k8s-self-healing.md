---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "019. Kubernetes 셀프힐링 — 파드가 스스로 회복하는 구조"
date: 2026-06-12
tags: [kubernetes, k8s, self-healing, liveness-probe, readiness-probe, startup-probe, restart-policy, pdb, pod-disruption-budget]
summary: "k8s의 셀프힐링은 선언적 모델과 세 가지 프로브로 구현된다. Liveness probe가 죽은 컨테이너를 재시작하고, Readiness probe가 준비 안 된 파드를 트래픽에서 제외하며, Startup probe가 시작이 느린 앱을 보호한다. 각 프로브가 언제 무엇을 해야 하는지, 잘못 설정했을 때 어떤 문제가 생기는지를 설명한다."
slug: "019-k8s-self-healing"
categories: ["쿠버네티스"]
---

k8s가 자주 언급되는 강점 중 하나가 셀프힐링(self-healing)이다. 파드가 죽으면 다시 살리고, 노드가 꺼지면 파드를 다른 노드로 옮기며, 컨테이너가 응답을 못 하면 재시작한다. 이 동작들은 마법이 아니라 선언적 모델의 자연스러운 결과다. 컨트롤러가 desired state와 actual state를 끊임없이 비교하면서 차이가 생기면 바로잡는다.

이 구조 위에 세 가지 프로브(probe)가 더 정교한 자가 회복을 가능하게 한다.

## Liveness Probe — 죽은 컨테이너를 재시작한다

Liveness probe는 **컨테이너가 살아있는지** 확인한다. 검사에 실패하면 kubelet이 해당 컨테이너를 재시작한다.

이것이 필요한 이유는 프로세스는 살아있지만 실제로는 동작하지 않는 상태가 있기 때문이다. 데드락에 빠진 스레드, 무한 루프에 갇힌 코드, 응답을 못 하는 상태 등이 그렇다. 이 경우 컨테이너가 살아있으니 k8s는 정상으로 보지만, 실제로는 요청을 처리 못 하고 있다. Liveness probe가 이를 감지해 재시작을 유도한다.

```yaml
livenessProbe:
  httpGet:
    path: /healthz        # 앱이 노출하는 헬스체크 엔드포인트
    port: 8080
  initialDelaySeconds: 10 # 컨테이너 시작 후 10초 기다렸다가 첫 검사
  periodSeconds: 10       # 10초마다 검사
  failureThreshold: 3     # 3번 연속 실패해야 재시작 (기본값)
  timeoutSeconds: 5       # 응답을 5초 내에 받아야 함
```

검사 방식은 세 가지다.

`httpGet`: 지정한 경로로 HTTP GET 요청을 보내 2xx 또는 3xx 응답을 받으면 성공이다.

`exec`: 컨테이너 안에서 명령을 실행해 exit code 0이면 성공이다.

`tcpSocket`: 지정한 포트로 TCP 연결을 시도해 연결되면 성공이다.

## Readiness Probe — 준비 안 된 파드를 트래픽에서 제외한다

Readiness probe는 **컨테이너가 트래픽을 받을 준비가 됐는지** 확인한다. 검사에 실패하면 재시작하지 않고, 그 파드를 Service의 엔드포인트 목록에서 **제외**한다. 즉, 살아는 있지만 트래픽을 주지 않는다.

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 1     # 1번만 실패해도 트래픽 제외 (빠른 반응)
  successThreshold: 1     # 다시 1번 성공하면 트래픽 재개
```

이것이 유용한 상황은 여러 가지다.

**시작 중인 파드**: 앱이 완전히 초기화되기 전에는 트래픽을 받으면 안 된다. DB 연결 풀을 열거나, 캐시를 워밍업하거나, 설정 파일을 로드하는 동안 요청이 들어오면 오류가 난다. Readiness probe가 준비 완료 전까지 트래픽을 막아준다.

**일시적 과부하**: 파드가 살아있지만 일시적으로 처리 용량이 찼다면, ready 상태를 false로 내려 새 요청이 들어오지 않게 하고 기존 요청을 먼저 처리할 수 있다.

**의존 서비스 장애**: DB나 외부 API가 내려가 이 서비스도 동작을 못 한다면, readiness를 false로 내려 트래픽을 다른 파드로 우회시킬 수 있다.

## Liveness vs Readiness — 무엇이 다른가

둘을 혼동하면 문제가 생긴다.

| | Liveness | Readiness |
|---|---|---|
| 검사 실패 시 | 컨테이너 재시작 | 트래픽에서 제외 (재시작 없음) |
| 용도 | 죽은 컨테이너 감지 | 트래픽 받을 준비 확인 |
| 엔드포인트 | `/healthz` (최소 검사) | `/ready` (의존성 포함 검사) |

Liveness probe에 의존 서비스(DB) 연결 확인을 넣으면 안 된다. DB가 잠깐 내려갔을 때 Liveness가 실패해 파드를 재시작하면, 재시작한 파드도 같은 이유로 실패하는 재시작 폭풍(CrashLoopBackOff)이 생긴다. Liveness는 "이 프로세스가 동작 가능한 상태인가"만 확인하고, 의존성은 Readiness에서 확인한다.

Readiness probe를 너무 공격적으로 설정하면(failureThreshold를 1로, 외부 의존성을 모두 포함) 작은 지연에도 파드가 트래픽에서 빠져 과부하가 다른 파드로 몰리는 연쇄 장애가 생길 수 있다.

## Startup Probe — 시작이 느린 앱 보호

Java 앱이나 머신러닝 모델처럼 시작 시간이 수십 초 이상 걸리는 앱이 있다. 이때 Liveness probe의 `initialDelaySeconds`를 그 시간보다 길게 잡으면 해결될 것 같지만, 운영 중에 앱이 실제로 먹통이 됐을 때도 그만큼 기다린 뒤에야 재시작한다.

Startup probe는 이 딜레마를 해결한다. **시작 완료 여부를 따로 검사**해 시작이 끝날 때까지 Liveness와 Readiness probe의 실행을 미룬다.

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  failureThreshold: 30    # 최대 30번 시도 (30 × 10초 = 5분)
  periodSeconds: 10       # 10초마다 검사
# startupProbe가 성공하기 전까지 아래 둘은 실행되지 않음
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  periodSeconds: 5
```

startupProbe가 성공하면 그 이후부터 Liveness와 Readiness probe가 동작한다. 시작 중에는 최대 `failureThreshold × periodSeconds`초를 기다리고, 시작 후에는 빠르게 이상 감지가 가능하다.

## CrashLoopBackOff — 재시작 폭풍

컨테이너가 계속 실패해 재시작을 반복하면 k8s가 재시작 간격을 점점 늘린다. 처음엔 즉시, 다음엔 10초, 20초, 40초로 늘어나 최대 5분까지 늘어난다. `kubectl get pods`에서 `CrashLoopBackOff` 상태로 표시된다.

이 상태는 k8s가 잘못 동작하는 것이 아니라 의도된 보호 장치다. 계속 재시작하며 리소스를 낭비하지 않도록 백오프(backoff)를 건다. 원인은 보통 앱 자체의 버그, 잘못된 환경변수나 설정, 의존 서비스 미준비 등이다. `kubectl logs <파드이름> --previous`로 이전 컨테이너의 로그를 보면 원인을 찾을 수 있다.

## PodDisruptionBudget — 자발적 중단 중 가용성 보장

셀프힐링과 반대로, 운영자가 의도적으로 파드를 중단시키는 상황도 있다. 노드 업그레이드, 클러스터 축소 같은 경우다. 이때 동시에 너무 많은 파드가 내려가면 서비스가 중단된다. PodDisruptionBudget(PDB)이 이를 막는다.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  selector:
    matchLabels:
      app: my-app
  minAvailable: 2       # 항상 최소 2개는 살아있어야 한다
  # 또는
  # maxUnavailable: 1   # 동시에 최대 1개까지만 내려도 된다
```

노드를 drain(파드를 안전하게 내보내는 작업)할 때 k8s가 PDB를 확인한다. minAvailable이 지켜지지 않으면 drain을 진행하지 않는다. 롤링 업데이트 중에도 PDB가 적용돼 업데이트 중에도 최소 가용 파드 수가 보장된다.

## 트레이드오프

프로브를 너무 공격적으로 설정하면 안정적인 앱도 계속 재시작되거나 트래픽에서 빠지는 오탐(false positive)이 생긴다. 너무 느슨하게 설정하면 진짜 문제가 있는 파드가 오랫동안 트래픽을 받는다. 적절한 값은 앱의 실제 응답 시간 분포와 시작 시간을 측정해 결정해야 한다. "표준 설정값"이 모든 앱에 맞지는 않는다.
