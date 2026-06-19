---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "041. VPN vs Direct Connect — 온프렘과 클라우드를 연결하는 두 가지 방법"
date: 2026-06-13
tags: [network, aws, vpn, direct-connect, hybrid-cloud, ipsec, latency, bandwidth, on-premises]
summary: "온프렘 데이터센터와 AWS VPC를 연결할 때 AWS Site-to-Site VPN 또는 AWS Direct Connect를 쓴다. VPN은 인터넷 위에 암호화 터널을 만드는 방식으로 빠르게 설정할 수 있고, Direct Connect는 AWS와 전용 물리 회선을 연결하는 방식으로 안정적인 대역폭과 낮은 레이턴시를 제공한다. 둘의 차이와 선택 기준을 설명한다."
slug: "041-vpn-direct-connect"
categories: ["클라우드 인프라"]
---

클라우드로 완전히 이전하지 않은 조직은 온프렘 데이터센터와 AWS가 공존한다. ERP나 레거시 DB는 온프렘에, 새 서비스는 AWS에 있는 식이다. 이 둘이 사설 IP로 안전하게 통신하려면 연결이 필요하다.

## Site-to-Site VPN

인터넷을 통해 암호화된 터널을 만드는 방식이다. 온프렘 네트워크 장비(Customer Gateway)와 AWS의 Virtual Private Gateway 사이에 IPSec 터널을 구성한다.

```
온프렘 데이터센터
  [Customer Gateway (라우터/방화벽)]
      ↕ IPSec 암호화 터널 (인터넷 경유)
  [Virtual Private Gateway]
  AWS VPC
```

### 특징

설정이 빠르다. AWS 콘솔에서 Customer Gateway(온프렘 장비 IP 등록)와 Virtual Private Gateway를 만들고, 다운로드되는 설정 파일을 온프렘 장비에 적용하면 수 시간 안에 연결된다.

기본적으로 **2개의 터널**을 만든다. 하나가 끊겨도 다른 하나로 이어진다. 단, 두 터널이 같은 인터넷 경로를 타면 ISP 장애 시 동시에 끊길 수 있다.

**대역폭이 제한적이다.** AWS VPN의 최대 처리량은 터널당 약 1.25Gbps다. 인터넷을 거치므로 실제 레이턴시와 처리량은 인터넷 상태에 따라 변동된다.

### 비용

시간당 연결 비용 + 데이터 아웃바운드 비용. 설치 비용이 없고 Direct Connect에 비해 훨씬 싸다.

## Direct Connect

AWS 데이터센터와 온프렘 데이터센터를 **물리 전용 회선**으로 연결하는 방식이다. 인터넷을 거치지 않는다.

```
온프렘 데이터센터
  [Customer Router]
      ↕ 전용 광케이블 (Direct Connect Location 경유)
  [AWS Direct Connect Router]
  AWS VPC
```

Direct Connect Location은 AWS와 협력하는 코로케이션 데이터센터(Equinix, Megaport 등)다. 온프렘 회선을 이 시설까지 끌고, AWS는 이 시설에서 자체 회선을 운영한다.

### 특징

**일관된 레이턴시**: 인터넷을 거치지 않으므로 레이턴시 변동이 적다. 금융 거래, 실시간 데이터 동기화처럼 레이턴시에 민감한 워크로드에 적합하다.

**높은 대역폭**: 1Gbps, 10Gbps, 100Gbps 옵션이 있다.

**데이터 전송 비용 절감**: Direct Connect를 통한 데이터 아웃바운드 비용이 인터넷 경유보다 저렴하다. 대용량 데이터를 지속적으로 전송하는 경우 비용 절감 효과가 크다.

### 비용과 구축 기간

Direct Connect Location까지 회선을 끌어오는 비용, AWS 포트 비용(시간당), 데이터 전송 비용이 발생한다. 초기 구축 비용이 크고 실제 연결이 완료되기까지 수 주에서 수 개월이 걸린다.

## 비교

| | Site-to-Site VPN | Direct Connect |
|---|---|---|
| 경로 | 인터넷 (암호화) | 전용 회선 |
| 설정 기간 | 수 시간 | 수 주 ~ 수 개월 |
| 초기 비용 | 낮음 | 높음 |
| 대역폭 | ~1.25Gbps (터널당) | 최대 100Gbps |
| 레이턴시 | 변동 있음 | 일관적 |
| 가용성 | 인터넷 의존 | 전용 회선 의존 |
| 암호화 | IPSec 기본 | 별도 설정 필요 |

## 조합 패턴

Direct Connect는 전용 회선이므로 그 회선 자체가 단일 장애점이 될 수 있다. 중요한 환경에서는 **Direct Connect + VPN 조합**을 쓴다.

```
평상시: Direct Connect (메인 경로, 낮은 레이턴시)
Direct Connect 장애 시: VPN으로 자동 페일오버
```

라우팅 우선순위를 Direct Connect가 높게 설정하면, 장애 시 VPN으로 자동 전환된다. Direct Connect의 안정성과 VPN의 인터넷 백업을 결합한 패턴이다.

## 선택 기준

VPN으로 시작하고 Direct Connect를 검토하는 것이 일반적이다. 다음 조건에 해당하면 Direct Connect를 고려한다.

- 온프렘 ↔ AWS 간 데이터 전송량이 매달 수 TB 이상
- 레이턴시 변동이 서비스 품질에 영향을 주는 경우
- 인터넷 의존 VPN의 가용성이 SLA를 충족하지 못하는 경우
- 규제나 보안 정책상 트래픽이 인터넷을 경유하면 안 되는 경우
