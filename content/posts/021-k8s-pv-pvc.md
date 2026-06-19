---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "021. Kubernetes PV & PVC — 파드가 죽어도 데이터가 살아남는 구조"
date: 2026-06-12
tags: [kubernetes, k8s, persistentvolume, persistentvolumeclaim, storageclass, stateful, volume, storage]
summary: "파드는 일시적이라 로컬 파일시스템도 파드와 함께 사라진다. PersistentVolume(PV)은 파드 수명과 분리된 저장소를 추상화하고, PersistentVolumeClaim(PVC)은 파드가 그 저장소를 요청하는 방식이다. 정적 프로비저닝과 동적 프로비저닝, StorageClass, 접근 모드, 반환 정책이 무엇인지, 실제 운영에서 어떻게 쓰이는지를 설명한다."
slug: "021-k8s-pv-pvc"
categories: ["쿠버네티스"]
---

파드는 일시적이다. 파드가 죽고 새로 만들어지면 그 안에서 컨테이너가 썼던 파일은 사라진다. 애플리케이션 로그나 캐시 파일이라면 괜찮지만, DB 데이터나 사용자가 업로드한 파일이라면 치명적이다. 이 문제를 해결하는 것이 PersistentVolume(PV)과 PersistentVolumeClaim(PVC)이다.

PV는 클러스터에 실제로 존재하는 저장소 자원이다. AWS EBS, GCP Persistent Disk, NFS 서버, 로컬 디스크 등 다양한 저장소를 k8s 오브젝트로 추상화한다. PVC는 파드가 "이런 저장소가 필요하다"고 요청하는 티켓이다. PVC가 제출되면 k8s가 조건에 맞는 PV를 찾아 연결(bind)한다. 파드는 PVC를 볼륨으로 마운트해 쓴다.

## 정적 프로비저닝

관리자가 PV를 미리 만들어두고, 파드가 PVC로 요청하면 매칭해 주는 방식이다.

```yaml
# 1. 관리자가 PV를 만든다
apiVersion: v1
kind: PersistentVolume
metadata:
  name: my-pv
spec:
  capacity:
    storage: 10Gi
  accessModes:
  - ReadWriteOnce           # 하나의 노드에서 읽기/쓰기
  persistentVolumeReclaimPolicy: Retain   # PVC 삭제 후 PV 보존
  storageClassName: standard
  hostPath:                 # 노드의 로컬 경로 (개발용)
    path: /data/my-app
```

```yaml
# 2. 파드가 PVC로 저장소를 요청한다
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-pvc
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi          # 5Gi 이상의 PV를 요청
  storageClassName: standard
```

```yaml
# 3. 파드에서 PVC를 볼륨으로 마운트한다
spec:
  containers:
  - name: app
    volumeMounts:
    - name: data
      mountPath: /var/data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: my-pvc
```

k8s가 PVC의 조건(용량, 접근 모드, storageClassName)에 맞는 PV를 찾아 1:1로 연결한다. 연결된 PV는 다른 PVC에 할당되지 않는다.

## 동적 프로비저닝과 StorageClass

정적 프로비저닝은 관리자가 PV를 미리 만들어야 해서 번거롭다. StorageClass를 쓰면 PVC 요청 시 PV가 자동으로 생성되는 **동적 프로비저닝**이 가능하다.

StorageClass는 "어떤 종류의 저장소를 어떻게 만들지"를 정의한다. 클라우드 환경에서는 AWS EBS CSI 드라이버, GCP PD CSI 드라이버 등이 StorageClass와 연동돼 PVC가 생성될 때 실제 디스크를 자동으로 만들고 PV로 등록한다.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast
provisioner: ebs.csi.aws.com      # AWS EBS CSI 드라이버
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
reclaimPolicy: Delete             # PVC 삭제 시 실제 디스크도 삭제
volumeBindingMode: WaitForFirstConsumer   # 파드가 스케줄된 노드 영역에 맞게 생성
allowVolumeExpansion: true        # 용량 확장 허용
```

`volumeBindingMode: WaitForFirstConsumer`는 중요한 설정이다. 기본값(`Immediate`)으로 두면 PVC가 생성되는 즉시 디스크가 만들어지는데, 그 디스크가 특정 가용 영역(AZ)에 생성되면 파드가 다른 AZ에 스케줄되는 상황이 생길 수 있다. `WaitForFirstConsumer`는 파드가 어느 노드에 스케줄될지 결정된 후 그 노드의 AZ에 맞게 디스크를 만든다.

동적 프로비저닝을 쓰는 PVC는 `storageClassName`만 지정하면 된다.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-pvc
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: fast
  resources:
    requests:
      storage: 20Gi
```

## 접근 모드

PV가 동시에 몇 개의 노드에서 마운트될 수 있는지를 정의한다.

`ReadWriteOnce(RWO)`: 하나의 노드에서만 읽기/쓰기로 마운트 가능. 가장 흔하다. AWS EBS, GCP PD 같은 블록 스토리지가 이 모드를 지원한다.

`ReadOnlyMany(ROX)`: 여러 노드에서 읽기 전용으로 마운트 가능. 설정 파일이나 정적 자산을 여러 파드에 배포할 때 쓸 수 있다.

`ReadWriteMany(RWX)`: 여러 노드에서 읽기/쓰기로 마운트 가능. NFS, Azure Files, AWS EFS 같은 네트워크 파일시스템이 지원한다. 여러 파드가 같은 저장소를 공유해야 할 때 필요하지만, 지원하는 저장소 종류가 제한적이고 성능이 낮을 수 있다.

`ReadWriteOncePod(RWOP)`: k8s 1.22+. 단 하나의 파드에서만 마운트 가능. RWO보다 더 엄격하다.

## 반환 정책(Reclaim Policy)

PVC가 삭제됐을 때 PV를 어떻게 처리할지 정의한다.

`Retain`: PV를 보존한다. 데이터가 사라지지 않는다. 관리자가 수동으로 정리하거나 재사용해야 한다. 실수로 PVC를 삭제했을 때 데이터를 복구할 수 있다.

`Delete`: PV와 실제 저장소(EBS 볼륨 등)를 함께 삭제한다. StorageClass의 동적 프로비저닝 기본값이 이것인 경우가 많다. 비용이 자동으로 정리되지만 데이터도 함께 사라진다.

`Recycle`: 데이터를 지우고(`rm -rf /data/*`) PV를 재사용 가능 상태로 만든다. 지금은 Deprecated됐다.

프로덕션 DB 데이터라면 `Retain`을 쓰고 PV 삭제를 수동으로 통제하는 것이 안전하다.

## 용량 확장

StorageClass에 `allowVolumeExpansion: true`가 설정돼 있으면 PVC의 용량을 늘릴 수 있다.

```bash
kubectl patch pvc my-pvc -p '{"spec":{"resources":{"requests":{"storage":"50Gi"}}}}'
```

줄이는 것은 대부분의 저장소에서 지원하지 않는다. 처음부터 적절한 크기를 잡는 것이 중요하고, 작게 잡고 필요할 때 늘리는 전략이 현실적이다.

## 트레이드오프

PV/PVC의 추상화는 파드가 저장소 구현을 몰라도 된다는 이점을 준다. 개발 환경에서는 `hostPath`를, 프로덕션에서는 EBS를 쓰더라도 파드 정의는 같다. PVC 이름만 같으면 된다.

감수할 것은 블록 스토리지(RWO)를 여러 파드가 공유하지 못한다는 제약이다. 여러 파드가 같은 파일에 쓰고 읽어야 한다면 RWX를 지원하는 NFS나 EFS 같은 공유 파일시스템이 필요하고, 이는 성능과 비용 측면에서 다른 판단을 요구한다. 또한 동적 프로비저닝으로 만들어진 PV는 `reclaimPolicy: Delete`가 기본이어서, 실수로 PVC를 지우면 데이터가 사라질 수 있다. 중요한 데이터라면 StorageClass를 `Retain`으로 설정하거나 별도 백업 정책을 두어야 한다.
