---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "040. VPC Peering vs Transit Gateway — VPC 간 연결 방식"
date: 2026-06-13
tags: [network, aws, vpc-peering, transit-gateway, tgw, routing, multi-vpc, hub-spoke]
summary: "VPC는 기본적으로 격리된 네트워크다. 여러 VPC를 연결하려면 VPC Peering 또는 Transit Gateway를 쓴다. Peering은 두 VPC를 직접 연결하는 단순한 방식이고, Transit Gateway는 여러 VPC를 허브-스포크 구조로 연결하는 중앙 라우터다. 각각의 동작 방식과 어떤 상황에 무엇을 쓰는지 설명한다."
slug: "040-vpc-peering-transit-gateway"
categories: ["클라우드 인프라"]
---

개발 VPC와 프로덕션 VPC, 또는 팀별로 분리된 VPC들이 서로 통신해야 할 때가 있다. VPC는 기본적으로 격리돼 있으므로 연결을 직접 설정해야 한다. AWS에서는 VPC Peering과 Transit Gateway 두 가지 방식을 제공한다.

## VPC Peering — 1:1 직접 연결

두 VPC를 직접 연결하는 방식이다. 피어링이 성립되면 두 VPC의 리소스가 사설 IP로 통신할 수 있다. 트래픽이 인터넷을 타지 않는다.

```
VPC A (10.1.0.0/16) ←→ VPC B (10.2.0.0/16)
```

설정 방법:
1. 피어링 연결 요청 생성
2. 반대편 VPC에서 수락
3. **양쪽** VPC의 라우팅 테이블에 상대방 CIDR 추가
4. Security Group 규칙에 상대방 CIDR 허용 추가

```
VPC A 라우팅 테이블:
10.2.0.0/16 → pcx-xxxxx (피어링 연결)

VPC B 라우팅 테이블:
10.1.0.0/16 → pcx-xxxxx (피어링 연결)
```

### Peering의 한계: 전이적 라우팅 불가

VPC Peering은 **전이적 라우팅(transitive routing)을 지원하지 않는다.** A-B 피어링과 B-C 피어링이 있어도 A에서 C로 B를 거쳐 통신할 수 없다.

```
A ←→ B ←→ C

A에서 C로 통신하려면 A-C 피어링을 별도로 만들어야 한다.
```

VPC가 늘어나면 피어링 수가 폭발적으로 늘어난다. N개의 VPC를 모두 연결하려면 N*(N-1)/2개의 피어링이 필요하다.

```
VPC 5개 → 10개 피어링
VPC 10개 → 45개 피어링
```

각 피어링마다 양쪽 라우팅 테이블을 관리해야 한다. 조직이 커지면 관리 불가 수준이 된다.

## Transit Gateway — 중앙 라우터

Transit Gateway(TGW)는 여러 VPC와 온프렘 네트워크를 연결하는 **중앙 허브**다. 허브-스포크(Hub-Spoke) 구조로, 모든 VPC를 TGW에 연결하면 서로 통신할 수 있다.

```
VPC A ─┐
VPC B ─┼─ Transit Gateway ─── 온프렘 (VPN/Direct Connect)
VPC C ─┘
```

각 VPC에서 TGW로 가는 라우팅만 추가하면 된다. VPC끼리 직접 피어링할 필요가 없다.

```
VPC A 라우팅 테이블:
10.0.0.0/8  → tgw-xxxxx   ← 모든 내부 트래픽을 TGW로

TGW 라우팅 테이블:
10.1.0.0/16 → VPC A attachment
10.2.0.0/16 → VPC B attachment
10.3.0.0/16 → VPC C attachment
10.10.0.0/16 → VPN attachment (온프렘)
```

TGW는 전이적 라우팅을 지원한다. A → TGW → C 경로가 가능하다.

### TGW 라우팅 테이블로 격리

TGW에 여러 라우팅 테이블을 만들어 VPC 간 접근을 세밀하게 제어할 수 있다.

```
# 공유 서비스(모니터링, 로깅)는 모든 VPC에서 접근 가능
# 개발 VPC와 프로덕션 VPC는 서로 직접 통신 불가

라우팅 테이블 A (개발용):
  10.1.0.0/16 → dev-vpc         (자기 자신)
  10.100.0.0/16 → shared-vpc    (공유 서비스)

라우팅 테이블 B (프로덕션용):
  10.2.0.0/16 → prod-vpc        (자기 자신)
  10.100.0.0/16 → shared-vpc    (공유 서비스)
  # dev-vpc 경로 없음 → 프로덕션 ↔ 개발 통신 차단
```

## 비교

| | VPC Peering | Transit Gateway |
|---|---|---|
| 연결 방식 | 1:1 직접 | 허브-스포크 |
| 전이적 라우팅 | 불가 | 가능 |
| 관리 복잡도 | VPC 증가 시 기하급수적 | 중앙 집중 관리 |
| 비용 | 데이터 전송 비용만 | 연결 시간당 + 데이터 전송 비용 |
| 리전 간 | 가능 (Inter-region Peering) | 가능 (Inter-region TGW Peering) |
| 대역폭 | 제한 없음 | 최대 50Gbps/AZ |

## 언제 무엇을 쓰는가

VPC가 2~3개이고 연결 구조가 단순하다면 Peering이 싸고 간단하다. TGW는 시간당 비용이 발생하므로 VPC가 적을 때는 오버엔지니어링이다.

VPC가 4개 이상이거나, 온프렘과 연결이 필요하거나, 환경별 격리 정책이 필요하다면 TGW가 낫다. 나중에 Peering에서 TGW로 마이그레이션하는 것보다 처음부터 TGW로 설계하는 것이 덜 고통스럽다.
