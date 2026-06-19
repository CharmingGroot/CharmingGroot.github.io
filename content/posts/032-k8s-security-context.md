---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "032. Kubernetes Security Context & Pod Security Admission — 컨테이너를 안전하게 실행하기"
date: 2026-06-12
tags: [kubernetes, k8s, security-context, pod-security-admission, rbac, capabilities, non-root, readonly-rootfs, seccomp, privileged]
summary: "컨테이너를 root로 실행하면 컨테이너 탈출 시 호스트 노드도 위험해진다. Security Context는 파드·컨테이너 수준에서 실행 권한을 제한하고, Pod Security Admission은 클러스터 수준에서 보안 기준선을 강제한다. 실무에서 자주 쓰는 설정과 각 제약의 의미를 설명한다."
slug: "032-k8s-security-context"
categories: ["쿠버네티스"]
---

컨테이너는 격리된 환경이지만 완벽한 격리는 아니다. 컨테이너가 root 권한으로 실행되고 있을 때 취약점으로 컨테이너를 탈출하면 호스트 노드에도 root 권한을 얻을 수 있다. 파일시스템에 쓸 수 있는 컨테이너는 악성 코드가 내부에서 변조를 시도할 여지를 준다.

Security Context는 파드와 컨테이너가 어떤 권한으로 실행될지를 선언한다. 불필요한 권한을 제거해 공격 표면을 줄이는 것이 목적이다. Pod Security Admission은 Namespace 단위로 보안 정책을 강제하는 클러스터 레벨 메커니즘이다.

## Security Context 기본 설정

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      securityContext:              # Pod 레벨 — 모든 컨테이너에 적용
        runAsNonRoot: true          # root(uid 0)로 실행 금지
        runAsUser: 1000             # UID 1000으로 실행
        runAsGroup: 3000            # GID 3000으로 실행
        fsGroup: 2000               # 볼륨 파일 소유 그룹
        seccompProfile:
          type: RuntimeDefault      # 기본 seccomp 프로필 적용
      containers:
      - name: app
        image: my-app:1.0.0
        securityContext:            # 컨테이너 레벨 — 이 컨테이너에만 적용
          allowPrivilegeEscalation: false    # setuid 바이너리로 권한 상승 금지
          readOnlyRootFilesystem: true       # 컨테이너 루트 파일시스템 읽기 전용
          capabilities:
            drop:
            - ALL                   # 모든 Linux capabilities 제거
            add:
            - NET_BIND_SERVICE      # 1024 미만 포트 바인딩 허용 (필요 시만)
        volumeMounts:
        - name: tmp
          mountPath: /tmp           # 쓰기가 필요한 경로는 별도 볼륨
        - name: cache
          mountPath: /app/cache
      volumes:
      - name: tmp
        emptyDir: {}
      - name: cache
        emptyDir: {}
```

### 각 설정의 의미

**`runAsNonRoot: true`**: 이미지가 root 사용자(uid 0)로 실행되도록 설정돼 있으면 파드 시작을 거부한다. 이미지의 `USER` 지시어로 non-root 사용자를 설정한 이미지만 실행된다.

**`readOnlyRootFilesystem: true`**: 컨테이너의 루트 파일시스템을 읽기 전용으로 마운트한다. 악성 코드나 취약점이 컨테이너 내부에서 바이너리를 수정하거나 새 파일을 만드는 것을 막는다. `/tmp`처럼 쓰기가 필요한 경로는 `emptyDir` 볼륨으로 별도 제공한다.

**`allowPrivilegeEscalation: false`**: `setuid` 또는 `setgid` 비트가 설정된 바이너리를 실행해 프로세스 권한이 올라가는 것을 막는다. `sudo` 같은 것이 작동하지 않는다.

**`capabilities`**: Linux는 root 권한을 세분화한 capabilities로 관리한다. `CAP_NET_ADMIN`(네트워크 설정), `CAP_SYS_ADMIN`(광범위한 시스템 작업) 같은 것들이다. 기본 컨테이너 런타임은 일부 capabilities를 부여하는데, `drop: [ALL]`로 모두 제거하고 실제로 필요한 것만 `add`한다.

**`seccompProfile: RuntimeDefault`**: 시스템 콜 필터를 적용한다. 컨테이너가 정상 동작에 필요하지 않은 시스템 콜을 호출하는 것을 차단한다. `RuntimeDefault`는 컨테이너 런타임이 제공하는 기본 프로필을 쓴다.

### Dockerfile에서 non-root 설정

컨테이너가 non-root로 실행되려면 이미지 자체도 준비돼야 한다.

```dockerfile
FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .

# non-root 사용자 생성 및 파일 소유권 변경
RUN addgroup -g 1001 appgroup && \
    adduser -u 1001 -G appgroup -s /bin/sh -D appuser && \
    chown -R appuser:appgroup /app

USER appuser                    # 이후 명령과 컨테이너 실행이 이 사용자로

EXPOSE 3000
CMD ["node", "server.js"]
```

## Pod Security Admission — 클러스터 레벨 정책

Security Context는 개별 파드에 설정한다. 모든 파드에 이를 강제하려면 Namespace 단위로 정책을 적용하는 **Pod Security Admission(PSA)** 을 쓴다. k8s 1.25에서 GA, 기존 PodSecurityPolicy를 대체한다.

PSA는 세 가지 보안 표준(Standard)을 정의한다.

**`privileged`**: 제한 없음. 모든 파드 허용. kube-system Namespace에 적합하다.

**`baseline`**: 최소한의 제한. 명백히 위험한 설정(privileged 컨테이너, hostPath 볼륨, hostNetwork 등)만 차단한다. 기존 애플리케이션 대부분이 수정 없이 통과한다.

**`restricted`**: 강력한 제한. non-root 실행, readOnlyRootFilesystem, capabilities drop, seccompProfile 강제 등. 현재 best practice를 모두 강제한다.

각 표준은 세 가지 모드로 적용할 수 있다.

**`enforce`**: 정책 위반 파드 생성을 거부한다.

**`audit`**: 위반이 있어도 파드는 만들어지지만 감사 로그에 기록된다. 기존 클러스터에 정책을 먼저 적용해볼 때 쓴다.

**`warn`**: 위반 시 경고 메시지를 반환하지만 파드는 만들어진다.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    pod-security.kubernetes.io/enforce: restricted      # 위반 시 거부
    pod-security.kubernetes.io/enforce-version: v1.28
    pod-security.kubernetes.io/audit: restricted        # 감사 로그
    pod-security.kubernetes.io/warn: restricted         # 경고
```

세 모드를 동시에 설정할 수 있다. 새 클러스터에 `restricted`를 점진적으로 도입할 때 `warn`과 `audit`을 먼저 켜서 위반 파드를 파악한 뒤 `enforce`를 추가하는 방식이 안전하다.

## Privileged 컨테이너

일부 시스템 컴포넌트(CNI 플러그인, 노드 에이전트, eBPF 기반 도구)는 호스트 수준 접근이 필요해 privileged 컨테이너로 실행된다.

```yaml
securityContext:
  privileged: true              # 호스트와 거의 동일한 권한. 매우 위험.
```

privileged 컨테이너는 호스트 파일시스템 전체에 접근하고, 장치를 마운트하고, 커널 파라미터를 변경할 수 있다. 불가피한 시스템 컴포넌트에만 쓰고, 애플리케이션에는 절대 쓰지 않는다. PSA `baseline`은 이를 차단한다.

## 최소 권한 원칙 체크리스트

실무에서 파드 보안을 점검할 때 확인하는 항목들이다.

```
□ runAsNonRoot: true 또는 runAsUser != 0
□ readOnlyRootFilesystem: true (쓰기 필요 경로는 emptyDir)
□ allowPrivilegeEscalation: false
□ capabilities.drop: [ALL], 필요한 것만 add
□ privileged: false (기본값이지만 명시)
□ hostPID: false, hostIPC: false, hostNetwork: false
□ Namespace에 PSA 레이블 적용
```

## 트레이드오프

`readOnlyRootFilesystem: true`를 적용하면 쓰기를 시도하는 컨테이너가 실행 중에 오류를 낸다. 임시 파일, 로그, 캐시를 루트 파일시스템에 쓰는 애플리케이션은 수정이 필요하다. 처음부터 설계할 때 쓰기 경로를 볼륨으로 분리해두면 문제가 없지만, 기존 이미지는 변환 비용이 있다.

`restricted` PSA 표준은 `seccompProfile`을 필수로 요구한다. 일부 오래된 또는 특수한 이미지는 기본 seccomp 프로필이 차단하는 시스템 콜을 쓸 수 있다. `RuntimeDefault` 프로필이 차단하는 syscall 목록은 컨테이너 런타임(containerd, cri-o)마다 약간 다르다. 문제가 생기면 `Unconfined`로 풀거나 커스텀 seccomp 프로필을 작성해야 한다.
