---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-07. Guest 커널과 하이퍼바이저 — VMX, VMCS, VM exit, 반가상화, I/O 가상화, 보안"
date: 2026-06-20
tags: [hypervisor, guest-kernel, vmx, vmcs, vm-exit, vm-entry, paravirtualization, virtio, vfio, sr-iov, vapic, tdx, sev]
summary: "Guest 커널과 하이퍼바이저가 어떻게 경계를 나누고 서로 통신하는지. VMX root/non-root mode, VMCS 구조, VM entry/exit 흐름, VM exit 주요 원인, 반가상화(hypercall/virtio), 인터럽트 가상화(vAPIC), I/O 가상화(emulation/virtio/VFIO/SR-IOV), 보안(VM escape/TDX/SEV-SNP)까지 정리한다."
slug: "arch-07-guest-hypervisor"
categories: ["시스템 아키텍처"]
---

Guest 커널은 자신이 bare metal 위에서 실행된다고 생각한다. 실제로는 VMX non-root mode라는 하드웨어가 만들어 준 새장 안에서 실행된다. 새장은 대부분 투명하다. Guest OS가 평범한 코드를 실행할 때는 하이퍼바이저가 전혀 개입하지 않는다. 특권 명령이나 하이퍼바이저가 관리해야 할 사건이 발생할 때만 CPU가 자동으로 하이퍼바이저로 전환한다(VM exit). 그 경계가 Guest 커널과 하이퍼바이저의 관계 전부다.

## VMX Root vs Non-Root Mode

Intel VT-x는 CPU에 두 가지 실행 모드를 추가했다.

**VMX root mode**: 하이퍼바이저가 실행되는 공간이다. `VMXON` 명령으로 진입한다. ring 0-3이 존재하며 KVM은 ring 0에서, QEMU는 ring 3에서 실행된다. 기존 x86과 동일한 완전한 특권을 가진다.

**VMX non-root mode**: Guest OS와 애플리케이션이 실행되는 공간이다. `VMLAUNCH`/`VMRESUME`으로 진입한다. ring 0-3이 그대로 있어 Guest OS는 ring 0(커널), Guest 애플리케이션은 ring 3(유저)에서 실행된다. 그러나 특정 명령이나 이벤트가 발생하면 하이퍼바이저의 개입 없이 CPU가 자동으로 VMX root로 전환한다(VM exit).

```
VMX root (하이퍼바이저)
     │
     │ VMLAUNCH/VMRESUME (VM entry)
     ↓
VMX non-root (Guest)
     │
     │ 특권 명령, I/O, EPT violation, 외부 인터럽트...
     │ (VM exit)
     ↓
VMX root (하이퍼바이저) → 처리 후 VMRESUME → VMX non-root
```

VM exit는 Guest의 의지와 무관하게 CPU가 하드웨어적으로 발생시킨다. Guest는 VM exit가 일어난 지도 모른다.

## VMCS (VM Control Structure)

VMCS는 vCPU마다 하나씩 존재하는 4KB 구조체다. CPU와 소프트웨어 사이의 공유 상태다.

**Guest State Area**: VM entry 시 CPU에 로드하는 Guest 상태.
- CR0, CR3, CR4 (Guest의 제어 레지스터)
- RFLAGS, RIP, RSP
- 세그먼트 레지스터 (CS/DS/SS/ES/FS/GS)와 descriptor (base, limit, AR)
- GDTR, IDTR, TR, LDTR
- IA32_EFER (Long mode 설정)

**Host State Area**: VM exit 시 CPU에 로드하는 Host(하이퍼바이저) 상태.
- RIP(=VM exit 핸들러 주소), RSP(하이퍼바이저 스택)
- CR0, CR3, CR4, 세그먼트

**VM Execution Controls**: 어떤 사건이 VM exit를 발생시킬지 비트마스크.
- Pin-based: 외부 인터럽트, NMI에 대한 처리 방식
- Processor-based: HLT, INVLPG, MWAIT, RDMSR, WRMSR, RDTSC, I/O instruction 등
- Exception bitmap: 어떤 예외가 VM exit를 발생시킬지 (비트당 예외 하나)
- EPT 활성화, VPID 활성화

**VM Exit Information**: VM exit 발생 시 CPU가 채우는 정보.
- Exit reason (코드)
- Exit qualification (추가 정보, 예: I/O 포트 번호, EPT violation 접근 주소)
- Guest physical address (EPT violation 시 GPA)
- Guest linear address (폴트 발생 GVA)

`VMREAD`, `VMWRITE` 명령으로 VMCS 필드를 읽고 쓴다.

## VM Entry / VM Exit 흐름

**VM Entry (VMLAUNCH/VMRESUME)**:
1. CPU가 VMCS의 VM Execution Controls 유효성 검사
2. VMCS Guest State Area → CPU 레지스터에 로드
3. CPU가 VMX non-root mode로 전환
4. Guest의 RIP부터 실행 재개

**VM Exit**:
1. 트리거 발생 (특권 명령, 인터럽트, EPT violation 등)
2. CPU가 현재 Guest 상태를 VMCS Guest State Area에 저장
3. VMCS Host State Area → CPU 레지스터에 로드
4. VMX root mode로 전환
5. VMCS의 `RIP` (Host State Area) 즉, VM exit 핸들러로 점프

VM exit 비용: 수백~수천 사이클이다. 레지스터 저장/복원, TLB 처리, 파이프라인 플러시가 포함된다. VM exit가 많이 발생하면 성능에 직접 영향을 미친다.

## VM Exit 주요 원인

**CPUID**: Guest가 `CPUID` 명령으로 CPU 기능을 조회하면 VM exit. 하이퍼바이저가 가상 CPUID 정보를 반환한다(실제 CPU 기능과 다르게 노출 가능).

**CR 접근**: Guest가 CR0, CR3, CR4를 변경하려 할 때. Guest CR3 변경은 Guest 프로세스 전환이므로 하이퍼바이저가 인지해야 한다(EPT 관리, TLB invalidation).

**I/O instruction**: `IN`/`OUT` 포트 접근. 가상 디바이스가 특정 포트에 응답해야 한다. 하이퍼바이저/QEMU가 에뮬레이션한다.

**MSR read/write**: `RDMSR`/`WRMSR`. 일부 MSR(TSC, APIC 설정 등)은 가상화 필요.

**EPT violation**: GPA에 EPT 매핑이 없거나 권한 위반. KVM이 EPT를 채우거나 MMIO 에뮬레이션.

**External interrupt**: Host 인터럽트(타이머, NIC 등)가 vCPU 실행 중 발생. "External interrupt exit" 설정 시 VM exit. 인터럽트 처리 후 VM resume.

**Preemption timer**: VMX preemption timer가 만료되면 VM exit. 하이퍼바이저 스케줄링 틱으로 사용한다.

**HLT**: Guest가 유휴 상태(`hlt` 명령)로 진입. 하이퍼바이저가 vCPU 스레드를 sleep 처리.

**VMCALL**: Guest가 명시적으로 하이퍼바이저를 호출(hypercall). 반가상화에서 사용.

## 반가상화 (Paravirtualization)

Guest OS가 하이퍼바이저를 인식하고 협력하는 방식이다. Trap-and-emulate가 성능 오버헤드를 일으키는 부분을 직접 통신으로 대체한다.

**Hypercall**: `VMCALL` 명령으로 하이퍼바이저 서비스를 직접 호출한다. Linux KVM 게스트의 PV(paravirt) 기능들:
- `KVM_CLOCK`: tsc 기반 정밀 시간 동기화. vDSO로 syscall 없이 Guest 시간 제공.
- `PV spinlock`: Guest spinlock을 하이퍼바이저가 인식해 스핀하지 않고 양보. 오버커밋 환경에서 spinlock 낭비 방지.
- `PV IPI`: Guest VM 간 IPI를 직접 처리. VM exit 없이 대상 vCPU를 깨운다.
- `PV MMU`: TLB flush를 배치 처리.

```c
// Guest 커널 내 hypercall 예시 (arch/x86/include/asm/kvm_para.h)
static inline long kvm_hypercall1(unsigned int nr, unsigned long p1)
{
    long ret;
    asm volatile(VMCALL_INSTRUCTION : "=a"(ret) : "0"(nr), "b"(p1));
    return ret;
}
```

**Xen PV (Paravirtualization)**: Xen 초기 방식. Guest 커널 자체를 수정해 모든 특권 명령을 hypercall로 바꿨다. VT-x 없이도 성능이 좋았으나 커널 패치 부담이 컸다. HVM(Hardware Virtual Machine)이 도입된 후 중요도가 낮아졌다.

## 인터럽트 가상화: vAPIC

Guest OS는 LAPIC(Local APIC)에 접근해 인터럽트를 관리한다. LAPIC을 소프트웨어로 완전 에뮬레이션하면 Guest의 모든 APIC 레지스터 접근마다 VM exit가 발생한다.

**APICv (APIC Virtualization, Intel)**: LAPIC 레지스터 접근을 VM exit 없이 처리한다.
- **Virtual APIC Page**: 4KB 페이지에 APIC 레지스터를 매핑. Guest가 메모리 매핑된 APIC 레지스터를 읽을 때 VM exit 없이 처리.
- **Posted Interrupts**: Host가 vCPU에 인터럽트를 주입할 때 VM exit 없이 처리. 전용 Posted Interrupt Descriptor(PID)에 인터럽트 벡터를 표시하고 `WRNV`로 vCPU에 알린다. Guest가 다음 인터럽트 윈도우에서 처리.

**타이머 가상화**: Guest LAPIC 타이머(one-shot, periodic)는 VMX preemption timer 또는 Host hrtimer로 에뮬레이션한다. KVM clock을 쓰면 TSC 기반으로 정확한 시간을 제공한다.

**인터럽트 주입**: I/O 인터럽트(디스크 완료, 네트워크 패킷)를 Guest에 전달할 때 vCPU가 실행 중이면 Posted Interrupt, sleep 중이면 IPI로 깨운 후 주입한다.

## I/O 가상화: emulation → virtio → VFIO → SR-IOV

성능과 호환성의 트레이드오프에 따라 여러 방식이 있다.

**Full Emulation**: QEMU가 실제 하드웨어(e1000 NIC, AHCI 컨트롤러, IDE 디스크)를 소프트웨어로 구현한다. Guest OS가 기존 드라이버를 그대로 쓸 수 있어 호환성이 최고다. 모든 I/O가 QEMU 유저 공간을 통과해 성능이 가장 낮다.

**Virtio (반가상화 I/O)**: Guest OS에 virtio 드라이버가 있으면 에뮬레이션보다 훨씬 빠르다.
- `virtio-blk`, `virtio-net`, `virtio-scsi`, `virtio-balloon`, `virtio-rng`
- **Virtqueue**: Guest와 Host 사이의 공유 링 버퍼. Guest가 디스크립터를 링에 넣고 kick(write to I/O 포트)으로 알림. QEMU가 처리 후 used ring에 완료 표시.
- **vhost-net**: virtio-net의 처리를 QEMU 대신 Host 커널이 직접 담당. QEMU 유저 공간 경유를 없애 레이턴시 감소.
- **vhost-user**: DPDK 기반 유저 공간 패킷 처리 앱과 연결.

**VFIO (Virtual Function I/O)**: 물리 장치(GPU, 고성능 NIC)를 VM에 직접 할당(pass-through)한다.
- IOMMU가 해당 장치의 DMA를 Guest 메모리 범위로 제한 → 안전한 직접 접근
- Guest 드라이버가 물리 장치를 직접 제어 → 에뮬레이션 오버헤드 없음
- GPU pass-through, SR-IOV VF 할당에 쓰인다
- 한 VM에 할당하면 다른 VM이 공유 불가

**SR-IOV (Single Root I/O Virtualization)**: 물리 NIC/SSD를 PF(Physical Function)와 여러 VF(Virtual Function)로 분할한다.
- PF: 전체 장치. 드라이버가 VF를 생성하고 관리.
- VF: 경량 가상 기능. 독립 큐, MSI-X 인터럽트. VFIO로 VM에 직접 할당.
- 예: Intel X710 40GbE NIC → VF 128개 생성 → 128개 VM에 고성능 NIC 제공.
- 성능: full emulation << virtio < SR-IOV ≈ bare metal.

## 보안

**VM Escape**: Guest에서 하이퍼바이저 취약점을 공략해 Host에 접근하는 공격이다.
- CVE-2015-3456(VENOM): QEMU의 Floppy Disk Controller 에뮬레이션 버퍼 오버플로. Guest에서 Host root 획득 가능.
- CVE-2019-14378: QEMU SLiRP TCP 재조합 heap 버퍼 오버플로.
- 방어: QEMU를 seccomp 필터로 제한(최소한의 syscall만 허용), 사용하지 않는 에뮬레이션 장치 비활성화, SELinux/AppArmor로 QEMU 프로세스 격리, 정기 패치.

**TDX (Trust Domain Extensions)**: Intel의 Confidential Computing 기술이다. VM 메모리를 암호화해 하이퍼바이저조차 Guest 메모리를 읽지 못한다.
- CPU가 각 TD(Trust Domain)마다 별도 암호화 키 관리
- Host 하이퍼바이저가 EPT 매핑을 변조해도 암호화된 데이터만 볼 수 있음
- Remote Attestation: Guest 코드가 진짜 TDX VM에서 실행 중임을 원격으로 검증
- 사용 사례: 신뢰할 수 없는 클라우드 공급자에서 민감 데이터 처리(Confidential Computing)

**SEV (Secure Encrypted Virtualization)**: AMD의 대응 기술이다.
- SEV: VM 메모리 암호화. 하이퍼바이저가 Guest 메모리를 평문으로 볼 수 없음.
- SEV-ES (Encrypted State): CPU 레지스터 상태까지 암호화. VM exit 시 Guest 레지스터 노출 방지.
- SEV-SNP (Secure Nested Paging): 메모리 무결성 보장. 하이퍼바이저가 Guest 물리 메모리 매핑을 변조하면 감지.

TDX/SEV 모두 하이퍼바이저 자체가 공격자인 시나리오(malicious cloud provider, compromised hypervisor)를 가정한다. 기존 가상화는 하이퍼바이저를 신뢰했지만, Confidential Computing은 하이퍼바이저를 신뢰하지 않는다.

## 정리

Guest 커널은 VMX non-root mode에서 실행되며 특권 명령이나 하이퍼바이저 관리 사건 발생 시 VM exit가 자동으로 발생한다. VMCS가 Guest/Host 상태를 담는 공유 구조체이고, VM entry/exit마다 레지스터를 로드·저장하는 하드웨어 메커니즘이다. VM exit는 CPUID, CR 접근, I/O, EPT violation, 외부 인터럽트, HLT 등이 주원인이며 수백~수천 사이클의 비용이 든다. 반가상화(hypercall, PV spinlock, virtio)는 Guest가 하이퍼바이저를 인식해 VM exit 없이 협력함으로써 성능을 올린다. APICv는 APIC 접근과 인터럽트 주입을 VM exit 없이 처리한다. I/O 가상화는 full emulation → virtio → VFIO/SR-IOV 순으로 성능이 올라간다. TDX/SEV는 하이퍼바이저도 믿지 않는 Confidential Computing의 기반 기술이다.
