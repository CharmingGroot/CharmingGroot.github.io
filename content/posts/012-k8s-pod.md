---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "012. Kubernetes Pod — 컨테이너를 감싸는 가장 작은 실행 단위"
date: 2026-06-12
tags: [kubernetes, k8s, pod, container, sidecar, init-container, lifecycle, resources, requests, limits]
summary: "Pod는 k8s에서 배포되는 가장 작은 단위다. 컨테이너가 하나 이상 묶인 실행 단위이고, 같은 파드 안의 컨테이너들은 네트워크와 볼륨을 공유한다. 파드의 라이프사이클, 리소스 요청과 제한, 사이드카 패턴, 초기화 컨테이너가 무엇인지, 그리고 파드를 직접 만들어 쓰지 않는 이유를 설명한다."
slug: "012-k8s-pod"
categories: ["쿠버네티스"]
---

Pod는 k8s에서 배포되는 **가장 작은 단위**다. Docker에서 컨테이너가 그 역할을 하는 것과 달리, k8s에서는 컨테이너를 직접 다루지 않고 파드를 통해 다룬다. 파드는 하나 이상의 컨테이너를 묶은 래퍼(wrapper)로, 같은 파드 안의 컨테이너들은 같은 네트워크 네임스페이스(= 같은 IP, 같은 포트 공간)와 볼륨을 공유한다.

## 왜 컨테이너 위에 파드가 있나

컨테이너 하나만으로 충분한데 왜 파드라는 개념을 하나 더 두는지 의아할 수 있다. 이유는 "밀접하게 연관된 컨테이너들을 함께 배치하고 함께 스케일하는" 패턴이 실제로 많기 때문이다. 앱 컨테이너 옆에 로그 수집기, 프록시, 설정 동기화 컨테이너를 붙이는 패턴이 대표적이다. 이런 컨테이너들은 같은 노드에 있어야 하고, localhost로 통신해야 하며, 항상 함께 시작되고 종료돼야 한다. 파드가 그 "함께 움직이는 단위"를 정의한다.

파드는 고유한 IP 하나를 갖는다. 파드 안의 컨테이너들은 이 IP를 공유하므로 `localhost`로 서로 통신한다. 포트 충돌만 없으면 된다.

## 파드를 직접 만들어 쓰지 않는 이유

파드 하나를 `kubectl apply -f pod.yaml`로 만들 수 있지만, 실제로 그렇게 하는 경우는 거의 없다. **파드는 한번 죽으면 그냥 사라지기 때문이다.** k8s는 직접 만든 파드를 다시 살려주지 않는다. 파드가 실행 중인 노드가 죽어도, 파드 안 컨테이너가 계속 실패해도 마찬가지다.

실제 운영에서는 파드를 직접 정의하는 대신 **파드를 관리해 주는 상위 오브젝트**를 쓴다. Deployment가 파드 개수를 유지하고 업데이트를 관리하며, DaemonSet이 모든 노드에 파드를 올리고, StatefulSet이 순서와 영구 저장소가 필요한 파드를 다룬다. 이 상위 오브젝트들이 파드 템플릿을 갖고 있고, 필요할 때 파드를 만들고 죽이는 일을 맡는다.

## 파드 정의

파드 정의에서 핵심은 `spec.containers`다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  containers:
  - name: app
    image: my-app:1.0.0
    ports:
    - containerPort: 8080
    env:
    - name: ENV
      value: production
    resources:
      requests:
        cpu: "100m"       # 0.1 코어
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "512Mi"
  - name: log-collector   # 사이드카 컨테이너
    image: fluentd:latest
    volumeMounts:
    - name: app-logs
      mountPath: /var/log/app
  volumes:
  - name: app-logs
    emptyDir: {}
```

## 리소스 요청(requests)과 제한(limits)

파드 정의에서 `resources`는 운영에서 가장 중요한 설정 중 하나다.

`requests`는 이 컨테이너가 실행되기 위해 보장받아야 할 최소 자원이다. 스케줄러는 이 값을 보고 요청을 감당할 여유가 있는 노드를 고른다. 요청한 만큼은 이 파드를 위해 노드에 예약된다.

`limits`는 이 컨테이너가 쓸 수 있는 최대 자원이다. CPU가 limits를 초과하면 스로틀링(throttling)이 걸려 속도가 느려진다. 메모리가 limits를 초과하면 컨테이너가 OOMKilled(Out of Memory Kill)로 종료된다.

CPU는 `m`(밀리코어) 단위로 표현한다. `100m`은 1코어의 10%다. 메모리는 `Mi`(메비바이트), `Gi`(기비바이트) 단위를 쓴다.

실무에서 이 설정을 제대로 안 하면 두 가지 문제가 생긴다. requests 없이 limits만 있으면 스케줄러가 파드를 아무 노드에나 올려도 되는 줄 알고 이미 꽉 찬 노드에 올릴 수 있다. requests를 너무 크게 잡으면 노드에 실제로 여유가 있어도 스케줄러가 올릴 자리가 없다고 판단해 파드가 Pending 상태로 멈춘다. HPA가 CPU 사용률을 기준으로 스케일하려면 `requests`가 반드시 있어야 한다 — 사용률은 requests 대비로 계산되기 때문이다.

## 파드의 라이프사이클

파드는 생성부터 종료까지 여러 상태를 거친다.

`Pending`: 파드가 생성됐지만 아직 노드에 스케줄되지 않았거나, 이미지를 받는 중이다.

`Running`: 적어도 하나의 컨테이너가 실행 중이다. 모든 컨테이너가 정상이라는 뜻은 아니다.

`Succeeded`: 모든 컨테이너가 정상적으로 종료됐다(exit code 0). 배치 작업에서 볼 수 있다.

`Failed`: 하나 이상의 컨테이너가 실패로 종료됐다.

`Unknown`: API Server가 파드 상태를 알 수 없는 상태. 보통 파드가 실행 중인 노드와 통신이 끊겼을 때다.

컨테이너 재시작 정책(`restartPolicy`)이 이 전환에 영향을 준다. `Always`(기본값, 항상 재시작), `OnFailure`(실패 시에만), `Never`(재시작 안 함)가 있다. 배치 잡은 `OnFailure`나 `Never`를 쓴다.

## 초기화 컨테이너(init container)

파드의 메인 컨테이너들이 시작하기 전에 순서대로 실행되는 컨테이너다. 모든 초기화 컨테이너가 성공적으로 종료돼야 메인 컨테이너가 시작된다.

```yaml
spec:
  initContainers:
  - name: wait-for-db
    image: busybox
    command: ['sh', '-c', 'until nc -z db-service 5432; do sleep 2; done']
  containers:
  - name: app
    image: my-app:1.0.0
```

"DB가 뜰 때까지 기다렸다가 앱을 시작한다", "앱에 필요한 설정 파일을 볼륨에 내려받는다", "DB 마이그레이션을 먼저 실행한다"처럼 메인 앱 시작 전에 선행돼야 할 작업에 쓴다. 의존성이 있는 서비스 간 시작 순서를 맞추는 가장 깔끔한 방법이다.

## 사이드카 패턴

메인 컨테이너와 함께 같은 파드 안에서 실행되는 보조 컨테이너를 사이드카(sidecar)라 한다. 오토바이의 사이드카처럼 메인 몸체를 보조하는 역할이다.

대표적인 사이드카 용도:

- **로그 수집**: 앱 컨테이너가 파일에 로그를 쓰면, 로그 수집기(Fluentd, Filebeat)가 같은 볼륨을 마운트해 읽어 중앙으로 보낸다.
- **프록시**: Envoy, Istio의 사이드카 프록시가 앱 컨테이너의 모든 트래픽을 가로채 트레이싱·메트릭 수집·트래픽 제어를 한다. 서비스 메시가 이 패턴으로 동작한다.
- **설정 동기화**: 외부 설정 소스(Vault, etcd)를 주기적으로 읽어 로컬 파일로 내려주는 컨테이너.

사이드카의 장점은 메인 앱 코드를 건드리지 않고 기능을 붙인다는 것이다. 단점은 파드마다 사이드카가 따라붙으므로 그만큼 자원이 더 든다는 것이다.

## 트레이드오프

파드는 k8s의 모든 것의 토대다. 잘 이해하면 이후 Deployment, Service, DaemonSet 같은 상위 오브젝트들이 파드 위에서 어떻게 동작하는지 자연스럽게 따라온다.

주의할 점은 파드가 **일시적(ephemeral)** 이라는 것이다. 파드는 언제든 죽고 새로 만들어질 수 있다. IP가 바뀌고, 로컬 파일시스템(`emptyDir`)이 사라진다. 상태를 파드 안에 저장하면 안 된다. 영구 저장이 필요하면 PersistentVolume을 붙이거나, 상태를 외부 저장소(DB, 오브젝트 스토리지)에 두어야 한다. 이 일시성을 설계의 전제로 받아들이는 것이 k8s 위에서 서비스를 설계하는 출발점이다.
