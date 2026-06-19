---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "050. Crossplane Composition — 인프라 추상화와 셀프서비스"
date: 2026-06-13
tags: [crossplane, kubernetes, composition, xrd, xr, claim, composite-resource, platform-engineering, abstraction]
summary: "Crossplane의 Managed Resource는 AWS 리소스를 1:1로 선언한다. Composition은 그 위의 추상화 레이어다. 여러 Managed Resource를 묶어 'PostgreSQL 데이터베이스 하나 주세요'라는 단순한 요청으로 VPC, 서브넷, 보안 그룹, RDS 인스턴스를 한꺼번에 프로비저닝할 수 있게 한다. XRD, XR, Claim의 3계층 구조를 설명한다."
slug: "050-crossplane-composition"
categories: ["IaC · 플랫폼"]
---

Crossplane의 Managed Resource만으로 운영하면 앱 팀이 VPC, 서브넷, 보안 그룹, RDS를 각각 선언해야 한다. 인프라 세부사항을 알아야 하고, 잘못 설정할 여지가 많다. Composition은 이 복잡성을 인프라 팀이 흡수하고 앱 팀에게 단순한 인터페이스를 제공하는 메커니즘이다.

"PostgreSQL 데이터베이스 하나 주세요. 스몰 사이즈로."

이 한 줄 요청이 VPC 피어링, 서브넷 선택, 보안 그룹, 파라미터 그룹, RDS 인스턴스, 백업 설정을 자동으로 처리하게 만드는 것이 Composition의 목적이다.

## 3계층 구조

```
XRD (CompositeResourceDefinition)
  ← 인프라 팀이 "어떤 리소스 타입을 제공할지" 정의

XR (CompositeResource)
  ← Composition으로 실제 리소스들이 생성되는 중간 오브젝트

Claim
  ← 앱 팀이 네임스페이스에서 "이 타입의 리소스를 요청"
```

### XRD — 인터페이스 정의

어떤 커스텀 리소스 타입을 제공할지 정의한다. Claim이 가질 수 있는 파라미터(spec)와 연결 정보(connectionSecretKeys)를 선언한다.

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xpostgresqlinstances.platform.example.com
spec:
  group: platform.example.com
  names:
    kind: XPostgreSQLInstance
    plural: xpostgresqlinstances
  claimNames:                          # 앱 팀이 쓰는 Claim 타입 이름
    kind: PostgreSQLInstance
    plural: postgresqlinstances
  versions:
  - name: v1alpha1
    served: true
    referenceable: true
    schema:
      openAPIV3Schema:
        type: object
        properties:
          spec:
            type: object
            properties:
              parameters:
                type: object
                properties:
                  storageGB:
                    type: integer
                    default: 20
                  size:
                    type: string
                    enum: ["small", "medium", "large"]
                    default: small
                  region:
                    type: string
                    default: ap-northeast-2
  connectionSecretKeys:
  - host
  - port
  - username
  - password
  - database
```

### Composition — 어떻게 만들지 정의

XRD로 정의한 타입을 실제로 어떤 Managed Resource 조합으로 만들지 구현한다.

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: xpostgresqlinstances.aws.platform.example.com
spec:
  compositeTypeRef:
    apiVersion: platform.example.com/v1alpha1
    kind: XPostgreSQLInstance
  resources:
  - name: rdsinstance
    base:
      apiVersion: rds.aws.upbound.io/v1beta1
      kind: Instance
      spec:
        forProvider:
          region: ap-northeast-2
          engine: postgres
          engineVersion: "15.4"
          skipFinalSnapshot: true
          publiclyAccessible: false
          multiAz: false
          dbName: main
          username: admin
        writeConnectionSecretToRef:
          namespace: crossplane-system
    patches:
    - type: FromCompositeFieldPath
      fromFieldPath: spec.parameters.storageGB
      toFieldPath: spec.forProvider.allocatedStorage
    - type: FromCompositeFieldPath
      fromFieldPath: spec.parameters.size
      toFieldPath: spec.forProvider.instanceClass
      transforms:
      - type: map
        map:
          small:  db.t3.micro
          medium: db.t3.medium
          large:  db.r6g.large
    - type: FromCompositeFieldPath
      fromFieldPath: spec.parameters.region
      toFieldPath: spec.forProvider.region
  - name: rds-subnet-group
    base:
      apiVersion: rds.aws.upbound.io/v1beta1
      kind: SubnetGroup
      spec:
        forProvider:
          region: ap-northeast-2
          subnetIdRefs:
          - name: private-subnet-a
          - name: private-subnet-b
```

`patches`가 핵심이다. Claim의 `spec.parameters.size: "small"`이 `spec.forProvider.instanceClass: "db.t3.micro"`로 변환된다. 앱 팀은 인스턴스 타입 이름을 몰라도 된다.

### Claim — 앱 팀의 요청

앱 팀이 자신의 네임스페이스에서 Claim을 만든다.

```yaml
apiVersion: platform.example.com/v1alpha1
kind: PostgreSQLInstance
metadata:
  name: order-service-db
  namespace: order-service
spec:
  parameters:
    size: small
    storageGB: 50
  writeConnectionSecretToRef:
    name: db-credentials    # 연결 정보를 이 Secret에 저장
```

이게 전부다. VPC, 서브넷, 보안 그룹, 파라미터 그룹을 몰라도 된다. 인프라 팀이 정의한 `small` 규격대로 모든 것이 만들어진다.

```bash
kubectl get postgresqlinstances -n order-service
# NAME               READY   SYNCED   CONNECTION-SECRET   AGE
# order-service-db   True    True     db-credentials      5m
```

연결 정보가 `db-credentials` Secret에 자동으로 저장된다.

```yaml
# 앱 Deployment에서 Secret 마운트
env:
- name: DB_HOST
  valueFrom:
    secretKeyRef:
      name: db-credentials
      key: host
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: db-credentials
      key: password
```

## Platform Engineering

이 구조가 **Platform Engineering**의 핵심 패턴이다. 인프라 팀이 플랫폼(Composition, XRD)을 만들고, 앱 팀이 셀프서비스로 인프라를 프로비저닝한다. 인프라 팀의 보안/비용 정책이 Composition 안에 인코딩돼 있어, 앱 팀이 실수로 정책을 위반하기 어렵다.

## 트레이드오프

Composition 작성이 복잡하다. `patches`, `transforms`, `patchSets` 문법이 직관적이지 않고, 중첩 구조를 참조하는 `FromCompositeFieldPath` 표현식이 길어진다. 인프라 팀에서 이 YAML을 작성하고 유지하는 비용이 상당하다.

Composition이 여러 Managed Resource를 만들 때 일부가 실패하면 전체 롤백이 안 된다. 성공한 것들은 남아 있고, 실패한 것만 재시도된다. 인프라 부분 생성 상태가 생길 수 있어 정리가 까다롭다.

Upbound(Crossplane 메인 컨트리뷰터)의 **Upbound Marketplace**에서 검증된 Composition 예시를 볼 수 있고, 직접 작성 전에 참고하면 시간을 절약할 수 있다.
