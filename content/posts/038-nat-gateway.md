---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "038. NAT Gateway — private 서브넷의 아웃바운드 인터넷 출구"
date: 2026-06-13
tags: [network, nat-gateway, vpc, private-subnet, aws, elastic-ip, snat, outbound]
summary: "private 서브넷의 서버는 인터넷에서 직접 접근할 수 없지만, 외부 API 호출이나 패키지 설치를 위해 아웃바운드 인터넷 접근은 필요하다. NAT Gateway는 이 단방향 출구를 제공한다. 동작 원리, 비용 구조, 고가용성 설계, 그리고 EKS에서의 주의사항을 설명한다."
slug: "038-nat-gateway"
categories: ["클라우드 인프라"]
---

private 서브넷에 있는 앱 서버가 외부 API를 호출하거나 OS 패키지를 업데이트하려면 인터넷에 나갈 수 있어야 한다. 하지만 인터넷에서 직접 들어오는 것은 막아야 한다. NAT Gateway는 이 비대칭 요구사항을 해결한다. **아웃바운드는 허용, 인바운드는 차단**.

## 동작 원리

```
private 서브넷 (10.0.11.5)
  → 라우팅 테이블: 0.0.0.0/0 → nat-gateway
  → NAT Gateway (public 서브넷, Elastic IP: 203.0.113.1)
      출발지 IP를 10.0.11.5 → 203.0.113.1:포트 로 SNAT
  → Internet Gateway
  → 외부 서버 (api.github.com)

응답:
  외부 서버 → 203.0.113.1:포트
  → NAT Gateway: conntrack 테이블 보고 10.0.11.5 로 복원
  → private 서브넷 서버
```

외부에서 먼저 `203.0.113.1`로 연결을 시도해도 NAT Gateway는 conntrack 항목이 없으니 어느 내부 서버로 보낼지 모른다. 연결이 성립되지 않는다. 이것이 private 서브넷이 외부에서 "보이지 않는" 이유다.

## 배치 위치

NAT Gateway는 **public 서브넷**에 위치해야 한다. 자체 Elastic IP(고정 공인 IP)를 가진다. private 서브넷의 라우팅 테이블에서 `0.0.0.0/0 → nat-gateway-id`를 지정하면 연결된다.

```
[private subnet] → route table → [NAT Gateway in public subnet] → [IGW] → Internet
```

NAT Gateway가 인터넷에 나가려면 public 서브넷에 IGW 라우팅이 있어야 한다. NAT Gateway 자체가 IGW를 거쳐 나가는 구조다.

## 고가용성 — AZ별 NAT Gateway

NAT Gateway는 단일 AZ 안에서만 동작한다. AZ-a의 NAT Gateway는 AZ-a의 private 서브넷 트래픽만 처리한다.

```
# 잘못된 설계 (NAT Gateway 하나 공유)
private-AZ-a: 0.0.0.0/0 → nat-gateway-AZ-a
private-AZ-b: 0.0.0.0/0 → nat-gateway-AZ-a  ← AZ-a 장애 시 AZ-b도 아웃바운드 끊김
```

```
# 올바른 설계 (AZ별 NAT Gateway)
private-AZ-a: 0.0.0.0/0 → nat-gateway-AZ-a
private-AZ-b: 0.0.0.0/0 → nat-gateway-AZ-b
```

비용이 2배가 되지만, 한 AZ 장애가 다른 AZ 아웃바운드를 끊지 않는다.

## 비용 구조

NAT Gateway는 두 가지 비용이 발생한다.

**시간당 요금**: 존재하는 것만으로도 시간당 과금된다 (약 $0.045/hr, 리전마다 다름). 한 달이면 약 $32.

**데이터 처리 요금**: NAT Gateway를 통과하는 데이터 GB당 과금된다 (약 $0.045/GB). 트래픽이 많으면 이 비용이 지배적이 된다.

데이터 처리 비용은 **AZ를 넘는 트래픽**에서 배가된다. AZ-a의 서버가 AZ-b의 NAT Gateway를 쓰면 AZ 간 데이터 전송 비용도 추가된다. AZ별로 NAT Gateway를 두는 것이 고가용성뿐 아니라 비용 측면에서도 맞다.

S3, DynamoDB 같은 AWS 서비스는 **VPC Endpoint**를 쓰면 NAT Gateway를 거치지 않는다. 이 서비스들을 많이 쓰는 환경에서는 VPC Endpoint 설정으로 NAT 비용을 크게 줄일 수 있다.

## EKS에서의 주의사항

EKS에서 파드 IP가 VPC IP를 직접 쓰는 경우(AWS VPC CNI), 파드에서 외부로 나가는 트래픽도 NAT Gateway를 거친다. 파드가 많으면 NAT Gateway 트래픽이 예상보다 훨씬 많아질 수 있다.

아웃바운드 IP를 고정해야 하는 경우(외부 시스템 IP 화이트리스트 등), NAT Gateway의 Elastic IP가 그 고정 IP가 된다. AZ별로 NAT Gateway가 있으면 Elastic IP도 여러 개가 되므로, IP 화이트리스트에 모두 등록해야 한다.

## 트레이드오프

NAT Gateway는 AWS가 관리하는 완전 관리형 서비스다. 가용성, 스케일링을 AWS가 처리한다. 대안으로 EC2 인스턴스에 NAT를 직접 구성하는 **NAT Instance** 방식이 있는데, 비용은 절감되지만 가용성과 성능 관리를 직접 해야 한다. 트래픽이 적은 개발 환경에서 비용 절감 목적으로 쓰는 경우가 있다.
