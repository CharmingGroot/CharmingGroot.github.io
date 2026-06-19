---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "015. Kubernetes ConfigMap & Secret — 설정과 민감한 값을 파드와 분리하는 방법"
date: 2026-06-12
tags: [kubernetes, k8s, configmap, secret, env, volume, rbac, external-secrets, vault, encryption]
summary: "설정값을 컨테이너 이미지에 박으면 환경마다 이미지를 다시 빌드해야 한다. ConfigMap은 일반 설정을, Secret은 민감한 값을 파드와 분리해 관리한다. 주입 방식(환경변수, 볼륨), Secret의 base64가 암호화가 아닌 이유, 프로덕션에서 실제로 안전하게 관리하는 방법을 설명한다."
slug: "015-k8s-configmap-secret"
categories: ["쿠버네티스"]
---

설정값을 컨테이너 이미지 안에 하드코딩하면 환경(개발/스테이징/프로덕션)마다 이미지를 다시 빌드해야 한다. ConfigMap과 Secret은 설정값을 이미지와 분리해 k8s 오브젝트로 관리하고, 파드가 시작할 때 주입하는 방식이다. 이미지는 환경에 관계없이 동일하고, 환경마다 다른 값은 오브젝트만 바꾸면 된다.

## ConfigMap

ConfigMap은 **민감하지 않은 일반 설정값**을 저장한다. 환경 이름, 로그 레벨, 타임아웃, 외부 서비스 URL 같은 것들이다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  LOG_LEVEL: "info"
  TIMEOUT: "30"
  DB_HOST: "postgres-service"
  app.properties: |
    server.port=8080
    logging.level.root=info
    feature.new-ui=true
```

`data`의 값은 문자열이다. 단순 키-값뿐 아니라 파이프(`|`)를 써서 설정 파일 전체를 통째로 담을 수도 있다.

## Secret

Secret은 **민감한 값** — 비밀번호, API 키, 토큰, 인증서 — 을 저장한다.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secret
type: Opaque
data:
  DB_PASSWORD: cGFzc3dvcmQxMjM=    # base64 인코딩된 값
  API_KEY: c2VjcmV0a2V5             # base64 인코딩된 값
stringData:                          # 평문으로 쓰면 k8s가 알아서 base64 변환
  ANOTHER_KEY: "plaintext-value"
```

## 중요: base64는 암호화가 아니다

많은 사람이 Secret이 암호화돼 있다고 오해한다. **기본 상태에서 Secret의 값은 base64 인코딩일 뿐이다.** 누구나 `echo cGFzc3dvcmQxMjM= | base64 -d`로 원래 값을 복원할 수 있다. etcd에 저장될 때도 base64 인코딩된 채로, 즉 사실상 평문으로 저장된다.

Secret이 ConfigMap과 다른 이유는 암호화 때문이 아니라 **접근 제어(RBAC) 분리** 때문이다. ConfigMap은 일반 개발자도 읽을 수 있게 하고, Secret은 꼭 필요한 서비스 계정만 읽을 수 있도록 RBAC으로 제한하는 것이다. 또한 Secret에 접근한 이력이 감사 로그에 남는다.

진짜 암호화가 필요하다면 두 가지 방법이 있다.

**Encryption at rest**: etcd에 저장할 때 암호화하도록 API Server를 설정한다. 클러스터 관리자가 `EncryptionConfiguration`을 설정하면 이후 Secret은 암호화돼 저장된다. etcd 파일을 직접 뒤져도 값을 읽을 수 없다.

**External secrets manager**: HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager 같은 전용 비밀 관리 도구를 쓴다. External Secrets Operator 같은 도구가 외부 저장소에서 값을 읽어 k8s Secret으로 동기화한다. 비밀 값이 k8s에 직접 저장되지 않고, 접근 이력 추적과 자동 교체(rotation) 같은 고급 기능을 쓸 수 있다. 프로덕션에서 가장 권장되는 방식이다.

## 파드에 주입하는 두 가지 방법

### 방법 1: 환경변수로 주입

```yaml
spec:
  containers:
  - name: app
    image: my-app:1.0.0
    env:
    # ConfigMap에서 개별 키 가져오기
    - name: LOG_LEVEL
      valueFrom:
        configMapKeyRef:
          name: app-config
          key: LOG_LEVEL
    # Secret에서 개별 키 가져오기
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: app-secret
          key: DB_PASSWORD
    # ConfigMap 전체를 환경변수로 한꺼번에 주입
    envFrom:
    - configMapRef:
        name: app-config
    - secretRef:
        name: app-secret
```

환경변수로 주입하면 앱 코드에서 `os.environ['LOG_LEVEL']`처럼 읽을 수 있어 단순하다. 단점은 **파드가 시작할 때 값이 고정**된다는 것이다. ConfigMap이나 Secret을 나중에 바꿔도 실행 중인 파드의 환경변수는 바뀌지 않는다. 새 값을 반영하려면 파드를 재시작해야 한다.

### 방법 2: 볼륨으로 마운트

```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: config-volume
      mountPath: /etc/config    # 이 경로에 파일로 마운트됨
    - name: secret-volume
      mountPath: /etc/secrets
      readOnly: true            # Secret은 읽기 전용으로 마운트하는 게 안전하다
  volumes:
  - name: config-volume
    configMap:
      name: app-config
  - name: secret-volume
    secret:
      secretName: app-secret
```

ConfigMap의 각 키가 파일 하나로 마운트된다. `app-config`에 `LOG_LEVEL: "info"`가 있으면 `/etc/config/LOG_LEVEL` 파일에 `info`가 내용으로 들어간다. `app.properties` 키로 담은 설정 파일 전체는 `/etc/config/app.properties` 파일로 마운트된다.

볼륨 마운트의 핵심 장점은 **ConfigMap이 갱신되면 마운트된 파일도 자동으로 갱신**된다는 것이다(약 1~2분 지연). 앱이 설정 파일을 주기적으로 다시 읽거나 파일 변경을 감지(inotify)하면 파드 재시작 없이 설정을 반영할 수 있다.

## 불변 ConfigMap / Secret

```yaml
metadata:
  name: app-config
immutable: true
```

`immutable: true`를 설정하면 이 오브젝트는 이후 수정할 수 없다. k8s가 변경 감시를 위한 watch를 걸지 않아도 돼서 API Server 부하가 줄어든다. 설정이 자주 바뀌지 않는다면 성능 최적화로 고려할 수 있다. 변경이 필요하면 새 이름으로 만들고 파드 정의를 업데이트해야 한다.

## 트레이드오프

환경변수 vs 볼륨 마운트의 선택은 **갱신 빈도**가 기준이다. 자주 바뀌지 않는 설정은 환경변수가 단순하고, 재시작 없이 설정을 반영해야 한다면 볼륨 마운트가 맞다.

더 근본적인 트레이드오프는 **Secret을 k8s에 직접 저장할 것이냐, 외부 비밀 관리 도구를 쓸 것이냐**다. 직접 저장하면 단순하지만 etcd 암호화, RBAC 세밀한 설정, Secret rotation을 모두 직접 관리해야 한다. 외부 도구를 쓰면 운영 복잡성이 올라가지만 감사 추적, 자동 교체, 비밀 값 k8s 미저장 같은 보안 수준을 얻는다. 규제가 있거나 보안이 중요한 서비스라면 외부 도구 연동이 사실상 필수다.
