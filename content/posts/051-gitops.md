---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "051. GitOps — Git을 배포의 단일 진실 원천으로"
date: 2026-06-13
tags: [gitops, git, cd, deployment, argo-cd, flux, pull-based, declarative, drift, kubernetes]
summary: "GitOps는 Git 저장소를 인프라와 애플리케이션의 desired state를 담는 단일 진실 원천으로 사용하는 운영 모델이다. 배포는 Git 커밋으로 시작하고, 클러스터 상태가 항상 Git과 일치하도록 유지한다. 전통적인 push 방식 CI/CD와의 차이, 핵심 원칙, 그리고 왜 k8s에 자연스럽게 맞는지 설명한다."
slug: "051-gitops"
categories: ["IaC · 플랫폼"]
---

전통적인 배포 파이프라인은 이렇다. 코드를 push → CI가 빌드 → CD가 `kubectl apply`를 실행 → 클러스터가 변경됨. CI/CD 시스템이 클러스터에 직접 접근해 변경을 밀어 넣는 **push 방식**이다.

GitOps는 방향을 뒤집는다. CI/CD가 클러스터에 push하는 대신, **클러스터 안의 에이전트가 Git을 계속 감시해 당겨온다(pull)**. Git이 항상 "이 클러스터는 이 상태여야 한다"는 선언을 담고, 에이전트가 이를 실현한다.

## 핵심 원칙

**선언적 설정**: 모든 인프라와 앱 설정이 선언형 YAML로 Git에 있다. `kubectl run`처럼 명령형으로 직접 실행하지 않는다.

**Git이 단일 진실 원천**: Git의 특정 브랜치(또는 태그)가 특정 환경의 desired state를 정의한다. "지금 프로덕션이 어떤 상태인지"는 Git을 보면 안다.

**변경은 Git을 통해서만**: 클러스터를 직접 `kubectl apply`로 수정하지 않는다. PR을 만들고 리뷰하고 merge하면 자동으로 반영된다.

**자동 동기화와 드리프트 감지**: 에이전트가 클러스터 상태와 Git을 비교한다. 누군가 클러스터를 직접 수정하면 드리프트가 감지되고, 자동으로 Git 상태로 복원하거나 알림을 보낸다.

## Push vs Pull 방식

```
# Push (전통 CI/CD)
개발자 → git push → CI 빌드 → CD가 kubectl apply → 클러스터
                                ↑
                     클러스터 접근 자격증명이 CI/CD에 있음

# Pull (GitOps)
개발자 → git push → CI 빌드 → 이미지 저장소
                              Git 매니페스트 업데이트
클러스터 안의 에이전트 → Git 폴링 → 변경 감지 → kubectl apply
```

Pull 방식의 보안 이점이 크다. 클러스터 접근 자격증명이 외부 CI/CD 시스템에 없어도 된다. 에이전트가 클러스터 안에 있으므로 외부에 자격증명을 노출하지 않는다.

## Git 저장소 구조

배포 매니페스트를 어떻게 구조화하느냐에 따라 여러 패턴이 있다.

### 앱 코드와 배포 설정 분리

```
# app 저장소 (소스 코드)
my-app/
├── src/
└── Dockerfile

# gitops 저장소 (배포 설정)
my-gitops/
├── apps/
│   ├── production/
│   │   ├── my-app/
│   │   │   ├── deployment.yaml   # image: my-app:2.5.1
│   │   │   └── service.yaml
│   └── staging/
│       └── my-app/
│           └── deployment.yaml   # image: my-app:2.6.0-rc1
└── infrastructure/
    ├── monitoring/
    └── ingress-controller/
```

앱 코드와 배포 설정이 분리되면 배포 이력과 인프라 변경이 별도 PR로 관리된다. 앱 CI가 빌드 후 gitops 저장소의 이미지 태그를 업데이트하는 PR을 자동으로 만든다.

### 환경 프로모션

```
feature 브랜치 → staging 브랜치 → production 브랜치
       ↓                ↓                  ↓
   스테이징 클러스터   스테이징        프로덕션 클러스터
```

PR merge가 배포 트리거다. 코드 리뷰가 배포 승인 프로세스가 된다.

## 롤백

Git의 롤백이 배포 롤백이다.

```bash
# 이전 커밋으로 revert
git revert HEAD
git push

# 에이전트가 감지 → 이전 버전 자동 재배포
```

`kubectl rollout undo`를 기억하거나 실행할 필요가 없다. git revert로 PR을 만들고 merge하면 된다. 롤백 이력도 git log에 남는다.

## 트레이드오프

GitOps는 모든 변경이 PR을 타야 하므로 빠른 핫픽스가 불편해진다. 긴급 상황에서 바로 `kubectl apply`를 실행하고 싶어도 에이전트가 곧 되돌린다. 긴급 우회 절차(에이전트 일시 정지, 긴급 PR 프로세스)를 미리 정해두지 않으면 장애 상황에서 혼란스러울 수 있다.

Secret 관리가 까다롭다. Git에 비밀번호를 올릴 수 없다. Sealed Secrets(클러스터 공개키로 암호화해 Git에 저장), External Secrets Operator(AWS Secrets Manager에서 동기화) 같은 별도 솔루션이 필요하다.

저장소 구조 설계가 중요하다. 초기에 잘못 설계하면 나중에 마이그레이션이 고통스럽다.
