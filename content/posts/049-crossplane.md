---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "049. Crossplane — k8s로 AWS 인프라를 선언하기"
date: 2026-06-13
tags: [crossplane, kubernetes, iac, aws, crd, provider, managed-resource, gitops, terraform]
summary: "Crossplane은 k8s CRD를 이용해 AWS, GCP 같은 클라우드 인프라를 선언적으로 관리하는 오픈소스다. VPC, RDS, S3 같은 클라우드 리소스를 k8s 오브젝트처럼 선언하면 컨트롤러가 실제 인프라를 프로비저닝한다. Terraform과 철학적으로 무엇이 다른지, Provider 구조, Managed Resource 개념을 설명한다."
slug: "049-crossplane"
categories: ["IaC · 플랫폼"]
---

Terraform으로 인프라를 관리하면 k8s 선언과 인프라 선언이 분리된다. k8s YAML은 git → Argo CD 흐름으로 적용되고, Terraform은 별도 파이프라인을 탄다. 두 시스템의 상태를 따로 관리해야 한다.

Crossplane은 이 경계를 없앤다. k8s 안에서 CRD로 클라우드 인프라를 선언한다. `kubectl apply`로 RDS 인스턴스를 만들고, `kubectl get rdsinstances`로 상태를 확인한다. k8s의 Reconcile 루프가 인프라 desired state를 실현한다.

## Terraform과의 철학 차이

Terraform은 **파이프라인 도구**다. `terraform apply`를 실행하는 시점에 변경을 적용하고, 그 이후에는 drift가 생겨도 모른다. 누군가 콘솔에서 수정하면 다음 apply까지 state와 실제가 달라진 채로 존재한다.

Crossplane은 **지속 Reconcile**이다. k8s 컨트롤러가 계속 실제 상태를 desired state와 비교한다. 누군가 콘솔에서 RDS 설정을 바꾸면 컨트롤러가 감지하고 원래 상태로 되돌린다. Git에 선언된 것이 항상 실제 상태다.

```
Terraform:   코드 → (pipeline 실행 시) → 인프라
Crossplane:  코드 → k8s → (항상) → 인프라 (drift 자동 수정)
```

## 구조

### Provider

특정 클라우드를 제어하는 플러그인이다. `provider-aws`, `provider-gcp`, `provider-azure` 등이 있다. Provider를 설치하면 해당 클라우드 리소스에 대응하는 CRD들이 클러스터에 등록된다.

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws
spec:
  package: xpkg.upbound.io/upbound/provider-aws:v1.0.0
```

Provider가 설치되면 `VPC`, `Subnet`, `RDSInstance`, `S3Bucket` 같은 CRD를 쓸 수 있다.

### ProviderConfig — 인증 설정

Provider가 어떤 AWS 계정을 사용할지 설정한다.

```yaml
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: IRSA    # IAM Roles for Service Accounts (EKS 권장)
```

IRSA를 쓰면 별도 Access Key 없이 k8s ServiceAccount에 IAM Role을 붙여 AWS API를 호출한다.

### Managed Resource — 클라우드 리소스 선언

Provider가 제공하는 CRD로 실제 클라우드 리소스를 선언한다.

```yaml
# VPC 선언
apiVersion: ec2.aws.upbound.io/v1beta1
kind: VPC
metadata:
  name: production-vpc
spec:
  forProvider:
    region: ap-northeast-2
    cidrBlock: 10.0.0.0/16
    enableDnsHostnames: true
    tags:
      Environment: production
  providerConfigRef:
    name: default
```

```yaml
# RDS 인스턴스 선언
apiVersion: rds.aws.upbound.io/v1beta1
kind: Instance
metadata:
  name: production-db
spec:
  forProvider:
    region: ap-northeast-2
    instanceClass: db.t3.medium
    engine: postgres
    engineVersion: "15.4"
    dbName: myapp
    username: admin
    allocatedStorage: 100
    storageType: gp3
    multiAz: true
    vpcSecurityGroupIdRefs:
    - name: db-security-group
  writeConnectionSecretToRef:
    namespace: production
    name: db-credentials    # 연결 정보를 Secret으로 자동 저장
```

`writeConnectionSecretToRef`가 강력한 기능이다. RDS가 생성되면 엔드포인트, 포트, 비밀번호를 자동으로 k8s Secret에 저장한다. 앱이 이 Secret을 마운트해서 DB 연결에 쓴다.

```bash
# 상태 확인
kubectl get rdsinstances
kubectl describe rdsinstance production-db

# 조건 확인
kubectl get rdsinstance production-db -o jsonpath='{.status.conditions}'
```

## 실제로 어떻게 썼나

Crossplane을 통한 k8s 상태관리와 AWS 인프라 관리 자동화 경험에서, 일반적인 패턴은 이렇다.

앱 팀이 `RDSInstance` CR을 만들면 인프라 팀이 리뷰하고 merge한다. Argo CD가 k8s에 적용하고, Crossplane이 실제 RDS를 프로비저닝한다. DB 엔드포인트와 비밀번호는 Secret으로 자동 생성돼 앱이 바로 사용한다. 인프라 팀이 AWS 콘솔에서 수동으로 만들어 정보를 전달하는 과정이 사라진다.

드리프트 수정도 강력하다. 누군가 콘솔에서 RDS 인스턴스 타입을 바꾸면 Crossplane이 감지하고 `db.t3.medium`으로 되돌린다. Git이 진실의 원천이 된다.

## 트레이드오프

Crossplane의 가장 큰 어려움은 **Provider CRD의 복잡도**다. AWS 리소스 하나를 Terraform으로 만들 때 HCL 30줄이면 되는 것이 Crossplane에서는 훨씬 길어지고, 중간 리소스(SecurityGroup, Subnet 연결 등)를 각각 별도 CR로 선언해야 한다.

컨트롤러가 지속적으로 AWS API를 폴링하므로 API 호출 비용과 rate limit를 신경써야 한다. 리소스가 수백 개가 되면 AWS API throttling이 문제가 될 수 있다.

Terraform은 실무 레퍼런스와 커뮤니티가 훨씬 많다. 새 AWS 서비스 지원도 Terraform 프로바이더가 먼저 나오는 경우가 많다. Crossplane은 k8s 중심 조직에서 GitOps 파이프라인을 단일화하려는 목적에 가장 잘 맞는다.
