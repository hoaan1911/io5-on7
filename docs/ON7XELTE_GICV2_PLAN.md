# ON7XELTE XNU bring-up: concrete hardware contract

This document records the values extracted from DTBH entry 1 in the supplied Samsung `boot.img`. It is a porting worksheet, not a claim that the XNU platform code already uses these values.

## CPU and memory

- CPU compatible: `arm,cortex-a53`; 8 MPIDRs: `0x0..0x3`, `0x100..0x103`.
- PSCI method: `smc`; CPU_ON `0xc4000003`, CPU_OFF `0x84000002`, CPU_SUSPEND `0xc4000001`.
- RAM bank 0: base `0x40000000`, size `0x3e400000`.
- RAM bank 1: base `0x80000000`, size `0x80000000`.
- Reserved intervals and framebuffer are excluded when the generator chooses the initial contiguous arena. With this DTB, the arena is `0xb0000000..0xefffefff` (size `0x3ffff000`). This avoids the listed multimedia/modem carve-outs and the `0xeffff000` `dram_init` page.
- Existing XNU loader uses a 32 MiB-aligned physical base; do not change this alignment without auditing `tools/mkpayload.py` and `shim/loader.c` together.

## Interrupt controller and timer

The vendor DTB identifies `arm,cortex-a15-gic` / `arm,cortex-a9-gic`, i.e. GICv2, not GICv3.

| Block | Physical base | Size |
|---|---:|---:|
| GIC distributor (GICD) | `0x104e1000` | `0x1000` |
| CPU interface (GICC) | `0x104e2000` | `0x1000` |
| Hypervisor interface (GICH) | `0x104e4000` | `0x2000` |
| Virtual interface (GICV) | `0x104e6000` | `0x2000` |

The architected timer frequency is `26,000,000 Hz`. Its DT interrupt tuples are in standard order: secure physical PPI 13, non-secure physical PPI 14, virtual timer PPI 11, hypervisor PPI 10. The current ADT generator exports `virtual-timer-intid = 11`.

The existing SWEET XNU interrupt path programs GICv3 redistributors and ICC system registers. Patches `0083` and `0084` now add a first ON7XELTE-specific GICv2 Group-1 IRQ path using GICD/GICC MMIO and route PPI 11 to `rtclock_intr`. That source is not yet compiled against the full XNU tree or tested on hardware. It intentionally caps the port at one CPU; SGI/IPI, secondary CPU bring-up, complete interrupt routing and device IRQ integration remain to be implemented.

## Early output and storage

- Existing bootloader framebuffer: base `0x67000000`, 1080×1920, 32-bit pixels, stride 4320 bytes. It is preserved as a reserved range in the generated ADT.
- Serial candidate from DTB: UART2 at `0x13820000`, size `0x100`; whether S-Boot leaves it configured and its pinmux/clock state still needs hardware confirmation.
- eMMC controller: `0x13540000`, size `0x2000`; this is an Exynos DesignWare MMC controller, not the Qualcomm UFS controller in the SWEET driver. A storage driver/root path is still required before iOS can mount its root filesystem.

## Next implementation checkpoints

1. Use the `j7-hello` probe on the phone to verify exception level, DTB pointer, framebuffer format, GICD/GICC ID registers, timer frequency and eMMC version ID.
2. Add an ON7XELTE platform expert selected by `samsung,on7xelte` in the ADT.
3. Compile and review the initial GICv2 distributor/CPU-interface initialization and interrupt acknowledge/EOI path in patch `0083`; do not execute GICv3 redistributor or ICC sysreg code on this board.
4. Validate timer PPI 11 end-to-end, then add GICv2 SGI/IPI and PSCI SMC CPU_ON for the secondary A53s.
5. Audit the 16 KiB page-table assumptions, cache maintenance and physical mapping against the actual S-Boot handoff. The probe and ADT serialization tests do not prove these are correct.
6. Only after serial/framebuffer kernel markers work should eMMC root-device support be attempted. Recovery remains out of scope for all write paths.
