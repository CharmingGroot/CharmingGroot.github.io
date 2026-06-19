---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "014. Kubernetes Service — 파드 앞에 세우는 고정 엔드포인트"
date: 2026-06-12
tags: [kubernetes, k8s, service, clusterip, nodeport, loadbalancer, ingress, dns, kube-proxy, endpoints]
summary: "파드는 죽었다 새로 만들어지면 IP가 바뀐다. Service는 파드 앞에 서서 항상 같은 주소로 트래픽을 받고, 뒤에 있는 파드들 사이에 로드밸런싱한다. ClusterIP, NodePort, LoadBalancer 세 타입의 차이, Ingress와의 관계, k8s 내부 DNS가 어떻게 동작하는지를 설명한다."
slug: "014-k8s-service"
categories: ["쿠버네티스"]
---

파드는 죽었다 새로 만들어지면 IP가 바뀐다. Deployment가 파드를 자동으로 재생성하니 IP가 언제 바뀔지 알 수 없다. 그래서 파드 IP로 직접 통신하면 안 된다. Service는 이 문제를 해결한다. 레이블 셀렉터로 파드를 찾아 그 앞에 서서, **항상 같은 주소(가상 IP 또는 DNS 이름)** 를 제공하고 뒤에 있는 파드들 사이에 로드밸런싱한다. 파드가 죽고 새로 만들어져도 Service는 자동으로 새 파드를 발견한다.

## 동작 원리

Service가 생성되면 k8s는 **ClusterIP**라는 가상 IP를 하나 할당한다. 이 IP는 Service가 살아있는 한 변하지 않는다. 실제 트래픽은 kube-proxy가 각 노드에서 iptables 또는 IPVS 규칙을 관리하며 실제 파드 IP로 라우팅한다.

Service는 **Endpoints** 오브젝트를 통해 실제 파드 IP 목록을 관리한다. Endpoints 컨트롤러가 레이블 셀렉터와 일치하는 파드의 Ready 상태를 감시하면서, 파드가 추가·제거되거나 Readiness probe 결과가 바뀔 때마다 Endpoints를 갱신한다. kube-proxy는 이 Endpoints를 보고 라우팅 규칙을 업데이트한다.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app-service
spec:
  selector:
    app: my-app       # 이 레이블을 가진 파드들로 트래픽을 보낸다
  ports:
  - protocol: TCP
    port: 80          # Service가 받는 포트
    targetPort: 8080  # 파드가 실제로 listening하는 포트
  type: ClusterIP     # 기본값
```

## 타입 1: ClusterIP

클러스터 내부에서만 접근 가능한 가상 IP를 할당한다. 기본 타입이다. 같은 클러스터 안의 다른 파드들이 이 Service를 호출할 수 있지만, 클러스터 외부에서는 직접 접근할 수 없다.

**서비스 간 내부 통신**에 쓴다. 주문 서비스가 결제 서비스를 호출할 때, 결제 서비스의 파드 IP를 알 필요 없이 `payment-service:8080`처럼 Service 이름으로 부를 수 있다.

## 타입 2: NodePort

ClusterIP 기능에 더해, **모든 워커 노드의 특정 포트를 열어** 클러스터 외부에서도 접근할 수 있게 한다. 노드의 IP 주소와 NodePort로 들어온 트래픽이 Service로 연결된다.

```yaml
spec:
  type: NodePort
  ports:
  - port: 80
    targetPort: 8080
    nodePort: 30080   # 30000~32767 범위, 명시 안 하면 자동 할당
```

외부에서 `<노드IP>:30080`으로 접근하면 Service가 받아 파드로 전달한다. 개발·테스트 환경에서 빠르게 외부 접근을 열 때 유용하다. 프로덕션에서 직접 쓰기는 어렵다 — 노드 IP가 바뀔 수 있고, 30000번대 포트를 외부에 노출하는 것은 보안상 좋지 않으며, 노드가 여러 대면 앞에 별도 로드밸런서가 있어야 한다.

## 타입 3: LoadBalancer

클라우드 환경(AWS, GCP, Azure 등)에서 **외부 로드밸런서를 자동으로 생성**해 Service에 연결한다. 클라우드 프로바이더가 로드밸런서를 만들고, 그 외부 IP를 Service에 달아준다.

```yaml
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8080
```

`kubectl get svc`로 보면 `EXTERNAL-IP` 열에 외부 IP가 붙는다. 프로덕션에서 외부 트래픽을 받는 표준 방법이다. 단점은 Service마다 로드밸런서가 하나씩 생성돼 비용이 붙는다는 것이다. 서비스가 많아지면 비용이 선형으로 늘어난다.

## Ingress — HTTP(S) 트래픽의 단일 진입점

LoadBalancer의 "Service마다 로드밸런서 하나" 문제를 해결하는 것이 **Ingress**다. Ingress는 HTTP/HTTPS 트래픽을 위한 단일 진입점으로, 로드밸런서 하나가 URL 경로나 호스트 이름을 기준으로 여러 Service로 트래픽을 분배한다.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
spec:
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /orders
        pathType: Prefix
        backend:
          service:
            name: order-service
            port:
              number: 80
      - path: /payments
        pathType: Prefix
        backend:
          service:
            name: payment-service
            port:
              number: 80
  tls:
  - hosts:
    - api.example.com
    secretName: tls-secret   # TLS 인증서
```

Ingress 오브젝트만으로는 동작하지 않는다. **Ingress Controller**가 클러스터에 설치돼 있어야 한다. nginx-ingress, Traefik, AWS ALB Ingress Controller 등이 있다. Ingress Controller가 Ingress 오브젝트를 감시하면서 실제 로드밸런서 설정을 갱신한다.

실무에서는 외부 트래픽은 Ingress로, 서비스 간 내부 통신은 ClusterIP Service로 처리하는 것이 일반적이다.

## k8s 내부 DNS

k8s는 클러스터 안에 DNS 서버(`CoreDNS`)를 두어 Service 이름으로 통신할 수 있게 한다. Service가 만들어지면 자동으로 DNS 레코드가 생성된다.

형식은 `<서비스이름>.<네임스페이스>.svc.cluster.local`이다. 같은 네임스페이스 안에서는 서비스 이름만으로 접근할 수 있다. 다른 네임스페이스 서비스에 접근할 때는 `payment-service.finance.svc.cluster.local`처럼 네임스페이스를 포함한 이름을 쓴다.

파드 안에서 `curl http://my-app-service/api`처럼 Service 이름으로 호출하면 CoreDNS가 해당 Service의 ClusterIP로 해석해 준다. 파드 IP가 바뀌어도, 파드가 몇 개로 늘어나도 이 DNS 이름은 변하지 않는다.

## 헤드리스 서비스(Headless Service)

`clusterIP: None`으로 설정하면 가상 IP 없이 DNS가 파드 IP들을 직접 반환하는 헤드리스 서비스가 된다. StatefulSet과 함께 쓰여 각 파드에 안정적인 DNS 이름을 부여하는 데 쓴다. 예를 들어 Redis Cluster에서 각 노드에 직접 접근해야 할 때 유용하다.

## 트레이드오프

Service의 로드밸런싱은 기본적으로 **랜덤 또는 라운드로빈**이다. 요청 크기나 파드의 현재 부하를 고려하지 않는다. 처리 시간이 긴 요청이 특정 파드에 몰리면 그 파드만 느려지는 상황이 생길 수 있다. 이를 더 정교하게 제어하려면 Envoy 같은 레이어 7 프록시나 서비스 메시(Istio 등)가 필요하다.

또한 Service는 TCP/UDP 레벨에서 동작한다. HTTP 헤더, 경로, 메서드를 기준으로 라우팅하려면 Ingress나 서비스 메시를 써야 한다.
