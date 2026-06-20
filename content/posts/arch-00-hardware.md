---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-00. 하드웨어 — CPU, 캐시, 버스, 인터럽트, 특권 레벨, VT-x"
date: 2026-06-20
tags: [hardware, cpu, cache, mesi, apic, dma, pcie, protection-ring, vtx, ept, iommu, numa]
summary: "OS와 VM이 추상화하는 대상의 실체. CPU 내부(레지스터·파이프라인·캐시 계층·MESI), 메모리 버스와 DMA, 인터럽트 컨트롤러(APIC), CPU 특권 레벨(ring 0-3), 하드웨어 가상화 지원(VT-x·EPT·IOMMU), NUMA까지 정리한다."
slug: "arch-00-hardware"
categories: ["시스템 아키텍처"]
---

OS가 무엇을 추상화하는지 이해하려면 그 밑의 하드웨어가 어떻게 생겼는지 알아야 한다. 가상 메모리가 4단계 페이지 테이블로 구현되는 이유, syscall이 ring 전환을 수반하는 이유, 하이퍼바이저가 EPT라는 별도 하드웨어 단계를 요구하는 이유는 모두 하드웨어에 답이 있다.

## CPU 내부 구조

**레지스터**: CPU가 직접 다루는 가장 빠른 저장 공간이다. x86-64 기준으로 범용 레지스터(RAX-R15), 스택 포인터(RSP), 명령 포인터(RIP), 플래그(RFLAGS)가 있다. 제어 레지스터 중 CR3은 현재 프로세스의 페이지 테이블 최상위 주소를 가리킨다. 컨텍스트 스위치 시 CR3을 바꾸는 것이 주소 공간 전환이다.

**파이프라인**: 현대 CPU는 명령을 여러 단계(fetch → decode → execute → writeback)로 나눠 겹쳐 실행한다. Out-of-order 실행은 의존성이 없는 명령을 순서를 바꿔 실행해 지연을 줄인다. 분기 예측(branch prediction)은 조건 분기 결과를 미리 추측해 실행하고 틀리면 파이프라인을 비운다. Spectre 계열 취약점이 분기 예측의 부채널을 악용한다.

**캐시 계층**: DRAM은 CPU보다 수백 배 느리다. 캐시가 격차를 줄인다.

| 계층 | 위치 | 용량 | 지연 |
|---|---|---|---|
| L1i/L1d | 코어 전용 | 32-64KB | ~4 사이클 |
| L2 | 코어 전용 | 256KB-1MB | ~12 사이클 |
| L3 (LLC) | 소켓 공유 | 수 MB-수십 MB | ~40 사이클 |
| DRAM | 외부 | GB 단위 | ~100ns (200-300 사이클) |

캐시는 64바이트 캐시 라인 단위로 올리고 내린다. 메모리를 순서대로 접근하면(spatial locality) 캐시 라인 하나에서 여러 값을 읽어 효율적이다. 뒤죽박죽 접근하면 미스가 잦아 DRAM까지 가는 횟수가 늘어난다.

**MESI 프로토콜**: 멀티코어에서 각 코어 L1 캐시가 같은 메모리의 다른 복사본을 들면 일관성이 깨진다. MESI는 캐시 라인 상태를 Modified · Exclusive · Shared · Invalid 넷 중 하나로 관리한다. 한 코어가 쓰기를 하면 다른 코어의 복사본을 Invalid로 만든다(cache invalidation). **False sharing**은 서로 다른 데이터가 같은 캐시 라인에 들어 한 코어가 쓰면 다른 코어 라인 전체가 무효화되는 현상이다. 멀티스레드 성능 저하의 단골 원인이다.

## 메모리 버스와 DMA

현대 서버는 CPU 다이에 메모리 컨트롤러(IMC)가 내장되어 DRAM과 직접 연결된다(Intel Nehalem 이후). 채널 수와 주파수(DDR4 3200 MHz, DDR5 5600 MHz)가 대역폭을 결정한다.

**DMA (Direct Memory Access)**: I/O 장치가 CPU를 거치지 않고 직접 DRAM에 데이터를 읽고 쓰는 메커니즘이다. CPU가 DMA 컨트롤러에 "이 주소에서 저 주소로 N바이트 옮겨라"고 지시하고 나서 다른 일을 한다. 전송이 완료되면 인터럽트로 알린다. DMA 없이는 디스크 I/O마다 CPU가 바이트를 하나씩 옮겨야 해서 낭비가 심하다.

**PCIe**: 주변장치(GPU, NVMe SSD, NIC)를 CPU와 연결하는 직렬 버스다. Lane 수(x1/x4/x8/x16)와 세대(Gen 3/4/5)가 대역폭을 결정한다. PCIe Gen 4 x16은 약 32 GB/s다.

## 인터럽트 컨트롤러: APIC

인터럽트는 하드웨어가 CPU에게 "일이 생겼다"고 알리는 비동기 신호다. 멀티코어 시대에는 APIC(Advanced PIC)를 쓴다.

- **Local APIC (LAPIC)**: 코어마다 하나. 해당 코어로 오는 인터럽트를 받고, 타이머 인터럽트(스케줄링 틱)를 생성한다. 코어 간 인터럽트(IPI, Inter-Processor Interrupt)도 LAPIC을 통한다. IPI는 TLB shootdown(다른 코어의 TLB 무효화)에 쓰인다.
- **I/O APIC**: 플랫폼 전체의 외부 인터럽트(키보드, 디스크, NIC)를 받아 특정 코어의 LAPIC으로 라우팅한다.
- **MSI (Message Signaled Interrupts)**: PCIe 장치가 메모리 쓰기로 인터럽트를 전달하는 방식이다. 물리 핀 없이 메모리 주소를 쓰므로 많은 인터럽트 벡터를 효율적으로 다룬다.

`/proc/interrupts`로 소스별, 코어별 처리 횟수를 확인할 수 있다.

## CPU 특권 레벨 (Protection Rings)

x86은 ring 0-3을 정의하고 실제로는 둘만 쓴다.

- **Ring 0 (kernel mode)**: 모든 명령 실행 가능. 모든 메모리 접근, 하드웨어 직접 제어, CR 레지스터 변경, 인터럽트 제어(CLI/STI)가 허용된다.
- **Ring 3 (user mode)**: 특권 명령 금지. 시도하면 General Protection Fault(GPF)가 발생하고 커널이 SIGSEGV를 보낸다.

CS 세그먼트 레지스터 하위 2비트(CPL, Current Privilege Level)가 현재 특권 레벨을 나타낸다. 커널 코드는 CPL=0, 유저 코드는 CPL=3. 유저 코드가 ring 0으로 임의 진입할 수 없다. 합법적 진입점은 syscall(소프트웨어 인터럽트)과 하드웨어 인터럽트·예외뿐이다.

## 하드웨어 가상화: Intel VT-x / AMD-V

소프트웨어만으로 VM을 구현하면 Guest OS의 모든 특권 명령을 에뮬레이션해야 해서 느리다. VT-x와 AMD-V는 이를 하드웨어로 지원한다.

**VMX (Virtual Machine Extensions)**: VT-x가 추가한 명령 집합이다.
- `VMXON`: VMX 활성화
- `VMLAUNCH`/`VMRESUME`: VM 실행 시작/재개 (VM entry)
- `VMEXIT`: 특정 조건에서 CPU가 자동으로 하이퍼바이저로 전환

VT-x는 CPU 실행 모드를 둘로 나눈다.
- **VMX root mode**: 하이퍼바이저 실행 공간. 모든 특권을 가짐.
- **VMX non-root mode**: Guest 실행 공간. ring 0-3이 그대로 존재하지만, 특정 명령(I/O 포트 접근, CR3 변경, CPUID 등)이 자동으로 VM exit를 발생시킨다.

Guest OS는 자신이 VMX non-root에서 실행된다는 걸 모른다. 특권 명령을 실행하면 CPU가 자동으로 하이퍼바이저로 전환하고, 하이퍼바이저가 에뮬레이션한 뒤 Guest로 복귀한다.

**EPT (Extended Page Table)**: Guest 물리 주소(GPA)를 Host 물리 주소(HPA)로 변환하는 별도 페이지 테이블이다. EPTP 레지스터에 등록된다. Guest 페이지 테이블(GVA→GPA)과 EPT(GPA→HPA)가 독립적으로 작동하며 MMU가 두 단계를 모두 처리한다. AMD의 대응 기술은 NPT(Nested Page Tables)다.

## IOMMU (VT-d / AMD-Vi)

DMA는 강력하지만 위험하다. 장치가 DMA로 임의의 물리 주소에 쓸 수 있으면 커널 메모리를 덮어쓸 수 있다. IOMMU는 DMA 접근을 페이지 테이블로 제한한다. 매핑이 없는 메모리엔 장치가 접근하지 못한다.

VM에서 IOMMU는 **VFIO**와 **SR-IOV**를 가능하게 한다. 물리 장치(GPU, NIC)를 VM에 직접 할당(pass-through)할 때 IOMMU가 해당 장치의 DMA 범위를 Guest 메모리로만 제한해 안전하게 직접 접근을 허용한다. SR-IOV는 물리 NIC/SSD를 여러 VF(Virtual Function)로 분할해 각 VM에 하나씩 할당한다.

## NUMA (Non-Uniform Memory Access)

멀티 소켓 서버에서 각 소켓(CPU)은 로컬 DRAM에 빠르게 접근하고, 다른 소켓의 DRAM에는 인터커넥트(QPI/UPI)를 통해 더 느리게 접근한다.

- 로컬 메모리 접근: ~70 ns
- 원격 소켓 메모리 접근: ~150+ ns

리눅스 기본 정책: 프로세스는 실행되는 소켓의 로컬 노드에서 메모리를 할당받는다(first-touch). `numactl --hardware`로 노드 구조와 거리를 확인한다. `mbind`/`set_mempolicy` 시스템 콜로 특정 노드를 지정한다. VM에서도 vNUMA를 설정하면 Guest OS가 NUMA 토폴로지를 인식해 최적화한다.

## 정리

하드웨어를 아는 만큼 OS와 VM의 동작이 명확해진다. 캐시 계층이 있어서 TLB가 필요하고 컨텍스트 스위치 비용이 생긴다. MESI가 일관성을 유지하지만 false sharing이 성능을 해친다. Protection ring이 있어서 커널-유저 분리와 syscall 메커니즘이 필요하다. VT-x/EPT 없이는 VM 특권 명령을 소프트웨어로 에뮬레이션해야 한다. IOMMU 없이는 장치 pass-through가 안전하지 않다. NUMA를 모르면 멀티 소켓 서버에서 메모리 접근 비용이 비대칭적으로 나빠진다.
