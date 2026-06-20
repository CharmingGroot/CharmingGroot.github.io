---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-05. VM — 구성 요소, Type 1/2, KVM, QEMU, vCPU 스케줄링, 라이브 마이그레이션"
date: 2026-06-20
tags: [vm, hypervisor, kvm, qemu, vcpu, libvirt, qcow2, live-migration, virt, type1, type2]
summary: "VM이 무엇으로 이뤄지고 어떻게 동작하는지. vCPU/vMem/vDisk/vNIC 구성, Type 1 vs Type 2 하이퍼바이저, KVM 아키텍처(Linux 커널 모듈), QEMU와 KVM의 분업, vCPU 스케줄링, VM 라이프사이클, 이미지 포맷(qcow2), 라이브 마이그레이션까지 정리한다."
slug: "arch-05-vm"
categories: ["시스템 아키텍처"]
---

VM(Virtual Machine)은 하이퍼바이저가 소프트웨어로 만든 가상 컴퓨터다. Guest OS 입장에서는 물리 하드웨어처럼 보이는 환경을 제공하면서, 실제로는 Host의 자원을 나눠 쓴다. 컨테이너와 달리 Guest마다 독립된 커널을 실행하기 때문에 격리가 강하고, 다른 OS를 올릴 수 있다.

## VM 구성 요소

VM은 네 가지 가상 자원으로 구성된다.

**vCPU (Virtual CPU)**: Guest OS에게 CPU처럼 보이는 실행 단위다. 실제로는 Host 커널 스레드다. Host의 Linux 스케줄러(CFS)가 vCPU 스레드를 물리 CPU 코어에 스케줄한다. Guest가 물리 코어 수보다 많은 vCPU를 가지면 오버커밋이 발생하고, 경쟁 시 steal time(뺏긴 시간)이 늘어난다.

**vMemory (Guest Physical Memory)**: Guest OS가 물리 메모리라고 생각하는 주소 공간이다. 실제로는 QEMU 프로세스가 `mmap`으로 할당한 Host 가상 주소(HVA) 범위다. Guest Physical Address(GPA)와 Host Physical Address(HPA) 간 변환은 EPT가 담당한다.

**vDisk**: QEMU가 에뮬레이션하는 블록 장치다. 백엔드는 파일(qcow2/raw) 또는 Host 블록 장치(/dev/sdb)다. virtio-blk를 쓰면 에뮬레이션 없이 반가상화 경로로 빠르게 I/O한다.

**vNIC (Virtual NIC)**: QEMU가 에뮬레이션하는 네트워크 인터페이스다. 패킷은 Host의 TAP 인터페이스를 통해 Host 네트워크 스택으로 들어온다. virtio-net + vhost-net을 쓰면 QEMU 유저 공간을 바이패스해 Host 커널이 직접 처리한다.

## Type 1 vs Type 2 하이퍼바이저

**Type 1 (Bare Metal)**: 하드웨어 바로 위에서 실행된다. 별도 Host OS 없이 하이퍼바이저 자체가 하드웨어를 제어한다. 성능이 좋고 프로덕션 환경에 쓴다.
- VMware ESXi, Microsoft Hyper-V, Xen
- KVM: Linux 커널에 내장. 리눅스 커널 자체가 하이퍼바이저가 된다. Type 1으로 분류하는 이유가 여기 있다.

**Type 2 (Hosted)**: Host OS 위에서 애플리케이션으로 실행된다. 개발·테스트 환경에 편리하지만 성능 손해가 있다.
- VirtualBox, VMware Workstation, Parallels(macOS)

KVM은 두 분류의 경계에 있다. 커널 모듈로서는 Type 1(커널이 하이퍼바이저)이지만, QEMU가 유저 공간 프로세스로 실행된다는 점에서 Type 2의 성격도 갖는다.

## KVM 아키텍처

KVM(Kernel-based Virtual Machine)은 Linux 커널 모듈이다. 로드하면 Linux 커널이 하이퍼바이저 기능을 가진다.

```
/dev/kvm          ← KVM 드라이버 인터페이스

QEMU (유저 공간)
  │ ioctl(KVM_CREATE_VM)     → VM 파일 디스크립터 생성
  │ ioctl(KVM_CREATE_VCPU)   → vCPU 파일 디스크립터 생성
  │ ioctl(KVM_SET_USER_MEMORY_REGION)  → GPA→HVA 매핑 등록
  │ ioctl(KVM_RUN)           → vCPU 실행 루프 시작
  ↓
KVM (커널 모듈)
  ├── VMLAUNCH/VMRESUME      → Guest 진입
  ├── VM exit 처리
  │   ├── 단순 처리(EPT miss, CPUID) → KVM에서 처리 후 재진입
  │   └── 복잡 처리(I/O 포트) → ioctl KVM_RUN 반환 → QEMU가 에뮬레이션
  └── 인터럽트 주입, vAPIC 관리
```

KVM은 Intel VT-x (또는 AMD-V)를 직접 사용한다. CPU가 VMX 명령을 지원해야 KVM이 동작한다. `grep vmx /proc/cpuinfo`(Intel) 또는 `grep svm /proc/cpuinfo`(AMD)로 확인한다.

## QEMU와 KVM의 분업

KVM 혼자는 실용적인 VM을 만들 수 없다. CPU와 메모리 가상화만 한다. QEMU가 나머지를 담당한다.

| 역할 | KVM | QEMU |
|---|---|---|
| CPU 가상화 | VT-x로 Guest 코드 직접 실행 | - |
| 메모리 가상화 | EPT 관리 | GPA 범위를 mmap으로 할당 |
| 디바이스 에뮬 | - | AHCI, e1000, USB, VGA, BIOS |
| 반가상화 I/O | vhost-net/vhost-blk | virtio 프론트엔드 |
| 라이프사이클 | - | VM 생성, 설정, 마이그레이션 |
| 펌웨어 | - | SeaBIOS(BIOS), OVMF(UEFI) |

**libvirt**: virsh, virt-manager, OpenStack이 사용하는 QEMU/KVM 위의 관리 레이어다. XML로 VM을 정의하고 QEMU 프로세스를 관리한다.

## vCPU 스케줄링

vCPU는 커널 스레드(`kvm-vcpu-N`)다. CFS가 이 스레드를 물리 CPU 코어에 스케줄한다.

**Guest 관점 vs Host 관점**:
- Guest OS는 자신의 LAPIC 타이머로 스케줄링 틱을 관리한다. PV clock(반가상화 클럭)으로 Host 실시간을 알 수 있다.
- Host 입장에서 vCPU 스레드는 일반 스레드와 동일하다. nice, cgroup cpu quota로 제한할 수 있다.

**Steal Time**: vCPU가 실행되고 싶은데 물리 CPU를 받지 못한 시간이다. Guest의 `/proc/stat`에서 `st` 필드로 나타난다. 클라우드 인스턴스가 느려질 때 steal time이 높으면 Host 오버커밋이 원인이다.

**VM Halt Polling**: Guest가 HLT 명령으로 유휴 진입 시 즉시 vCPU 스레드를 sleep시키면 레이턴시가 증가한다. KVM은 짧은 시간 동안 폴링한 후 실제 sleep하는 방식으로 레이턴시를 줄인다. `/sys/module/kvm/parameters/halt_poll_ns`로 제어.

## VM 라이프사이클

```
정의(XML/CLI) → 생성(KVM_CREATE_VM) → 실행(KVM_RUN 루프)
                                              │
                                     ┌────────┤
                                     │ 일시정지(virsh suspend)
                                     │ 스냅샷(qemu snapshot)
                                     │ 마이그레이션(virsh migrate)
                                     └────────┤
                                              │
                                          종료(ACPI/kill)
```

**스냅샷**: qcow2 내부 스냅샷(이미지 안에 저장, `qemu-img snapshot`) 또는 외부 스냅샷(새 qcow2 파일이 원본을 backing으로 참조). 외부 스냅샷은 기반 이미지를 불변으로 유지하며 여러 VM이 공유할 수 있다(template → clone).

## 이미지 포맷

**raw**: 1:1 바이트 이미지. 크기가 항상 최대 용량을 차지한다. 성능이 가장 좋다. 씬 프로비저닝 없음.

**qcow2 (QEMU Copy-on-Write v2)**: 리눅스 KVM 표준 포맷이다.
- 씬 프로비저닝: 실제 쓴 만큼만 파일이 크다. 100GB 디스크가 실제 5GB만 씀
- Copy-on-Write: 내부 스냅샷 기반
- 압축, 암호화(LUKS) 지원
- Backing file: 다른 qcow2를 기반으로 삼는 체인
- 단점: raw보다 I/O 오버헤드가 있음 (특히 랜덤 쓰기)

```bash
qemu-img create -f qcow2 vm.qcow2 50G
qemu-img info vm.qcow2
qemu-img convert -f qcow2 -O raw vm.qcow2 vm.raw
```

**vmdk**: VMware 포맷. `qemu-img convert`로 상호 변환 가능.

## 라이브 마이그레이션

VM을 중단 없이(또는 최소 다운타임으로) 다른 Host로 이동한다.

**Pre-copy 방식** (기본):
1. Guest가 실행되는 동안 메모리를 반복적으로 대상 Host로 전송
2. 1라운드 후 dirty 페이지를 추적하며 반복 전송 (수렴 단계)
3. dirty 페이지가 충분히 줄면 Guest 잠시 중단(stop-and-copy)
4. CPU 상태와 나머지 dirty 페이지 전송
5. 대상 Host에서 Guest 재개

다운타임은 마지막 stop-and-copy 시간이다. 고속 네트워크와 적은 write-intensive 워크로드에서 수십 ms 수준이다.

**Post-copy**: Guest를 먼저 이동하고 메모리는 Page Fault 시 원본 Host에서 가져온다. 다운타임이 없지만 네트워크 장애 시 VM이 죽는다.

```bash
virsh migrate --live vm qemu+ssh://target/system
```

디스크 마이그레이션은 별도다. 공유 스토리지(NFS, Ceph)를 쓰면 디스크 이동이 필요 없다.

## 정리

VM은 vCPU(커널 스레드) + vMemory(QEMU mmap) + vDisk(파일/블록) + vNIC(TAP)로 구성된다. KVM은 Linux 커널 모듈로 CPU(VT-x)와 메모리(EPT) 가상화를 담당하고, QEMU는 디바이스 에뮬레이션과 라이프사이클 관리를 담당한다. vCPU는 CFS가 스케줄하는 커널 스레드다. 오버커밋 시 steal time이 증가한다. qcow2는 씬 프로비저닝과 스냅샷을 지원하는 표준 포맷이다. 라이브 마이그레이션은 pre-copy로 메모리를 점진 전송하고 짧은 stop-and-copy로 마무리한다.
