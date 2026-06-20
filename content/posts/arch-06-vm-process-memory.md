---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-06. VM의 프로세스와 가상 메모리 레이어 — GVA/GPA/HPA, EPT, Shadow PT, 메모리 오버커밋"
date: 2026-06-20
tags: [vm, ept, shadow-page-table, gva, gpa, hpa, memory-virtualization, balloon, ksm, vnuma, overcommit]
summary: "VM 안의 프로세스가 쓰는 메모리가 물리 메모리에 닿기까지의 두 단계 변환. Guest 페이지 테이블(GVA→GPA), EPT(GPA→HPA), Shadow Page Table(EPT 이전), EPT violation 처리, 메모리 오버커밋(balloon/KSM), vNUMA까지 정리한다."
slug: "arch-06-vm-process-memory"
categories: ["시스템 아키텍처"]
---

VM 안의 프로세스는 내부에서 보면 일반 프로세스와 동일하다. Guest OS가 `mm_struct`와 `vm_area_struct`를 관리하고, 4단계 페이지 테이블이 Guest 가상 주소를 변환한다. 차이는 그 변환이 **Guest 물리 주소(GPA)**에서 끝나지 않는다는 것이다. GPA는 하이퍼바이저가 만든 허구의 주소 공간이다. 실제 물리 메모리(HPA)에 닿으려면 한 번 더 변환이 필요하다. 이 두 단계가 VM 메모리 가상화의 핵심이다.

## 세 층의 주소 공간

VM 안의 메모리를 이해하려면 주소 공간이 세 층으로 쌓여 있음을 먼저 파악해야 한다.

```
GVA (Guest Virtual Address)   ← Guest 프로세스의 가상 주소
   │ Guest 페이지 테이블로 변환
GPA (Guest Physical Address)  ← Guest OS가 물리 주소라 착각하는 주소
   │ EPT(또는 Shadow PT)로 변환
HVA (Host Virtual Address)    ← QEMU 프로세스의 가상 주소 (mmap 영역)
   │ Host 페이지 테이블로 변환
HPA (Host Physical Address)   ← 실제 물리 메모리
```

HVA 단계는 QEMU 내부에서 GPA→HVA 매핑을 관리하고, 실제 변환(HVA→HPA)은 Host 커널 페이지 테이블이 한다. EPT는 GPA→HPA를 직접 매핑한다(HVA를 거치지만 하드웨어는 GPA→HPA로 본다).

## Guest 페이지 테이블: GVA → GPA

Guest OS는 일반 OS처럼 페이지 테이블을 관리한다. Guest의 CR3이 가리키는 PGD, 4단계 페이지 테이블, PTE가 GVA → GPA 변환을 담당한다. Guest OS는 GPA를 물리 주소로 알고 페이지 테이블에 적는다. 이 전체 과정은 일반 프로세스의 메모리 관리(arch-04)와 동일하다.

Guest 안의 프로세스 관점:
- `malloc()`이 `brk()`/`mmap()` syscall을 부름
- Guest OS가 VMA 생성 후 첫 접근 시 Guest 페이지 폴트
- Guest OS가 GPA를 할당하고 Guest PTE에 GPA를 씀

여기까지는 하이퍼바이저가 전혀 개입하지 않는다. Guest OS가 GPA 범위 안에서 스스로 메모리를 관리한다.

## EPT: GPA → HPA

Intel VT-x의 EPT(Extended Page Table)는 GPA를 HPA로 변환하는 별도 하드웨어 구조다.

**구조**: EPT도 4단계 테이블이다(PML4E → PDPTE → PDE → PTE). 하이퍼바이저가 설정하고 EPTP(EPT Pointer) 레지스터에 등록한다.

**변환 과정**:
```
Guest 메모리 접근 발생
  ↓
MMU: Guest CR3 → GVA→GPA 변환 (Guest 페이지 테이블 walk)
  페이지 테이블 각 단계(PGD/PUD/PMD/PTE)에서 얻은 GPA 주소들을
  EPT를 통해 HPA로 다시 변환
  ↓
최종 물리 주소(HPA) 획득
```

4단계 Guest 페이지 테이블 walk 중 각 단계에서 얻은 페이지 테이블 항목 주소가 GPA다. 이것을 다시 EPT로 변환해야 한다. 최악의 경우 **4 × 4 + 1 = 17번의 메모리 접근**이 필요하다(각 Guest PT 단계마다 EPT 4단계 walk + 최종 데이터 접근).

TLB가 이 비용을 줄인다. 최근 변환 결과(GVA→HPA)를 TLB에 캐시한다. EPT 없이 Shadow PT를 쓸 때와 비교해 TLB 구조가 달라진다: Shadow PT는 GVA→HPA를 직접 담지만 EPT는 GVA→GPA와 GPA→HPA가 분리된 두 구조다.

**VPID (Virtual Processor ID)**: VM exit 후 TLB를 전부 비우지 않아도 되게 하는 태그다. 각 vCPU에 VPID를 부여하면 VM exit 시 해당 VPID의 엔트리만 선택적으로 무효화한다.

AMD의 대응 기술은 **NPT (Nested Page Tables)** 또는 RVI(Rapid Virtualization Indexing)다.

## Shadow Page Table: EPT 이전

VT-x/EPT가 없던 시절의 소프트웨어 방식이다. 이해하면 EPT의 가치가 더 명확해진다.

하이퍼바이저가 **GVA → HPA**를 직접 매핑한 세 번째 페이지 테이블(Shadow PT)을 만들어 CPU의 CR3에 올린다. Guest가 CR3을 읽거나 쓰려 할 때 VM exit → 하이퍼바이저가 Shadow PT로 교체한다.

문제:
- Guest가 자신의 페이지 테이블을 수정하면 Shadow PT도 동기화해야 한다. 이를 위해 Guest 페이지 테이블 페이지를 읽기 전용으로 마킹 → Guest가 수정하면 write fault → 하이퍼바이저가 Shadow PT 갱신.
- 프로세스마다 Guest PT가 있으므로 Shadow PT도 프로세스마다 필요 → 메모리와 관리 부담이 크다.
- 모든 Guest CR3 변경이 VM exit를 유발 → 프로세스 스위치마다 VMexit.

EPT는 이 모든 복잡성을 하드웨어로 해결한다.

## EPT Violation 처리

GPA에 대한 EPT 매핑이 없거나 권한 위반이면 **EPT violation**이 발생해 VM exit한다.

```
KVM VM exit 핸들러 (kvm_vmx_exit_handlers[EXIT_REASON_EPT_VIOLATION])
  ↓
GPA 확인 → memslot 탐색
  ↓
memslot: QEMU가 KVM_SET_USER_MEMORY_REGION으로 등록한 GPA→HVA 매핑
  GPA = 0x0 ~ 0x80000000  →  HVA = 0x7f0000000000 (QEMU mmap)
  ↓
HVA에서 HPA 구하기 (get_user_pages)
  ↓
EPT 엔트리 채우기 (HPA 주소, 접근 권한 설정)
  ↓
VMRESUME
```

**MMIO 처리**: GPA가 메모리 맵 I/O 영역(예: 디바이스 레지스터)이면 EPT에 매핑하지 않고 의도적으로 violation을 발생시켜 QEMU가 에뮬레이션하게 한다.

## 메모리 오버커밋

Host RAM의 합보다 모든 VM의 vMemory 합이 크더라도 실제 사용량이 적으면 동작한다. 이를 위한 두 가지 기법이 있다.

**Balloon Driver (virtio-balloon)**: Guest OS 안에 설치된 balloon 드라이버가 메모리를 할당·반납하는 메커니즘이다.

```
Host 메모리 부족 감지
  ↓
하이퍼바이저 → balloon 드라이버에 "메모리 더 요구" 신호
  ↓
balloon 드라이버: Guest OS에서 메모리 할당
  → Guest 입장에서 가용 메모리 감소
  → 할당한 페이지를 Host에 반납
  ↓
Host: 해당 물리 페이지를 다른 VM에 사용
```

반대로 Host 메모리가 여유 있으면 balloon을 수축해 Guest에게 메모리를 돌려준다. Guest OS가 balloon 드라이버를 지원해야 한다.

**KSM (Kernel Samepage Merging)**: Host 커널이 여러 VM의 메모리 페이지를 스캔해 내용이 동일한 페이지를 물리 하나로 합치는 기법이다.

```
ksmd 데몬: 모든 VM 메모리 페이지 내용 해시
  동일 해시 페이지 발견
  → 내용 비교 확인
  → COW로 물리 페이지 하나를 가리키게 PTE 수정
  → 어느 VM이 수정하면 COW로 분리
```

같은 OS 이미지 여러 VM을 띄우면 커널 코드, 공유 라이브러리 페이지가 같을 가능성이 높아 효과가 크다. 시간당 수십 GB 절약도 가능하다. `/sys/kernel/mm/ksm/`으로 제어.

단점: ksmd 스캔 자체가 CPU를 소비하고, 합쳐진 페이지가 수정되면 COW 비용이 발생한다. 타이밍 공격(Rowhammer, 측면 채널)의 공격 면이 넓어진다는 보안 우려도 있다.

**madvise(MADV_DONTNEED)**: Guest 안의 앱이 쓰지 않는 메모리를 커널에 반납하는 힌트다. Guest OS → Guest 커널 → EPT violation 처리 시 물리 페이지 해제 → Host가 재사용.

## vNUMA

물리 서버가 NUMA 아키텍처이면 VM 안에도 NUMA 정보를 노출해 Guest OS가 NUMA-aware 최적화를 할 수 있다.

**설정 방법**: QEMU는 ACPI의 SRAT(System Resource Affinity Table)와 SLIT(System Locality Information Table)로 Guest에게 vNUMA 토폴로지를 알린다. Guest OS가 부팅 시 이 테이블을 파싱해 NUMA 노드 수, 각 노드의 메모리 범위, 노드 간 접근 비용을 파악한다.

**Host NUMA와 맞추기 (NUMA pinning)**:
```bash
# QEMU: Guest의 NUMA 노드 0을 Host NUMA 노드 0에 고정
-numa node,mem=4G,cpus=0-3,nodeid=0
-numatune 0,nodeset=0
```
Host NUMA 토폴로지와 vNUMA가 일치하면 Guest 프로세스의 로컬 메모리 할당이 실제 로컬 DRAM 접근으로 이어져 NUMA 이점을 그대로 활용한다.

맞추지 않으면 Guest가 로컬이라 생각한 메모리가 실제로는 원격 소켓에 있어 성능이 나빠진다.

## 정리

VM 안의 프로세스는 Guest OS의 일반 프로세스다. Guest 페이지 테이블이 GVA→GPA를 변환하고, EPT가 GPA→HPA를 변환한다. 두 단계가 중첩되므로 최악의 경우 17번의 메모리 접근이 필요하지만 TLB(VPID 태깅)가 대부분을 캐시한다. EPT 이전의 Shadow PT는 하이퍼바이저가 GVA→HPA를 직접 관리했는데 Guest PT 동기화 오버헤드가 컸다. EPT violation은 GPA 매핑이 없을 때 발생하며 KVM이 EPT를 채운다. 메모리 오버커밋은 balloon driver(Guest가 메모리 반납)와 KSM(동일 페이지 물리 합산)으로 구현한다. vNUMA는 Guest에게 NUMA 토폴로지를 노출해 Host NUMA와 맞추면 실제 성능 이점을 활용한다.
