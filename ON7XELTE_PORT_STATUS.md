# ON7XELTE XNU port status and work plan

Target: Samsung Galaxy J7 Prime SM-G610F (`on7xelte`), Exynos 7870.

This repository combines two inputs:
- The earlier `wardevsa`-derived XNU project and its SWEET-specific XNU patch series.
- The J7 Prime `hello` shim from the accompanying `ios-j7prime-hello.zip`.

They serve different purposes. The J7 shim is an early hardware bring-up probe; the existing XNU patches are primarily for SWEET (Redmi Note 10 Pro, Qualcomm SM7150). Neither input, by itself or combined, is a finished iOS/XNU port for ON7XELTE.

## Current implemented milestone

- `tools/mkadt_on7xelte.py` extracts the selected DTB from the Samsung `DTBH` table, parses the FDT, and emits the project's serialized Apple Device Tree (ADT) format. It records all eight Cortex-A53 MPIDRs, both RAM banks, the reserved-memory intervals, the S-Boot framebuffer, GICv2 MMIO windows, the 26 MHz architected timer and PSCI SMC method.
- The generator computes a single contiguous bootstrap arena after excluding the DTB's reserved ranges and the framebuffer. For the supplied revision-1 DTB this currently resolves to `0xb0000000 + 0x3ffff000`; the generator and tests recompute it from the input rather than blindly copying a donor device's addresses.
- `tools/test_mkadt_on7xelte.py` validates the ADT serialization and the board properties against the supplied stock boot image.
- `.github/workflows/on7xelte-adt.yml` runs those tests and publishes the ADT.
- XNU patches `0082`–`0084` add an `ON7XELTE` compile configuration, a first single-CPU GICv2 Group-1 timer IRQ path, and a minimal ON7XELTE platform expert. These source patches have passed patch-format/repository validation, but have **not** yet been compiled against the full XNU tree in this offline environment. `.github/workflows/xnu.yml` is the compile-only CI path.

The ADT is a porting artifact, not a proven bootable tree. The `bringup/j7-hello` probe is a separate hardware handoff diagnostic; it is **not XNU** and must not be described as an iOS kernel.

The source package includes `bringup/j7-hello/boot.img`, copied from the user-supplied archive. Keep this repository **private** unless you remove that firmware image and arrange for the workflow to obtain a legally redistributable device-specific input.

## Device facts grounded in the supplied diagnostics and upstream device tree

- SoC: Samsung Exynos 7870; ARM Cortex-A53 CPU cluster.
- GIC distributor base: `0x104e1000`; CPU interface base: `0x104e2000`, per upstream Exynos 7870 device tree.
- eMMC controller used by the probe: `0x13540000`, also present in the supplied `/proc/iomem` capture.
- Display engine nodes in supplied diagnostics: DSI `0x14800000`, DECON/framebuffer `0x14830000`.
- The supplied diagnostics show RAM ranges `0x40000000-0x7d7fffff` and `0x80000000-0xffffffff`. Do not replace these with a guessed single 1-GB range without checking the live device tree and reserved-memory regions.
- Display panel reported by the stock kernel: `td4300`; touchscreen: Synaptics RMI4 on I2C bus 5 at address `0x70`.

References:
- Linux upstream Exynos 7870 device tree: https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/master/arch/arm64/boot/dts/exynos/exynos7870.dtsi
- Linux upstream J7 Prime device tree: https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/master/arch/arm64/boot/dts/exynos/exynos7870-on7xelte.dts
- Apple XNU source: https://github.com/apple-oss-distributions/xnu

## Required porting work

1. Run the J7 probe and capture its screen/log output. Confirm the actual entry exception level, DTB pointer, display framebuffer behavior, GIC ID registers and eMMC controller ID. A failed or blank display is not proof that the CPU did not execute the shim.
2. Validate the generated ADT on-device and against XNU’s actual `SecureDT` consumers. The generator now emits the expected serialized node/property structure, but schema compatibility with every XNU consumer has not yet been demonstrated.
3. A minimal platform expert and a single-CPU GICv2 timer IRQ path are now present as patches, but they need to compile and be validated on hardware. The full GICv2 controller, SGI/IPI, secondary-CPU bring-up, and storage/display drivers remain incomplete. Existing SWEET patches still contain Qualcomm/SWEET assumptions and must not be applied blindly.
4. Implement the Exynos 7870 boot CPU path, exception-level transition, GICv2 setup, architected timer, PSCI/SMP, MMU page tables and cache maintenance.
5. Add early serial/framebuffer console and a viable storage/root-device path. Display, touch, Wi-Fi and cellular are separate later milestones.
6. Build against a pinned XNU source revision and pinned macOS/Xcode toolchain. Keep build logs and exact source revision with every artifact.
7. Only after the image format and handoff are verified should a non-destructive boot test be considered. Do not write the recovery partition.

## Honest milestone labels

- `j7-hello`: bare-metal hardware probe, not XNU.
- `SWEET` build artifact: control build for the donor port, not compatible with ON7XELTE.
- `ON7XELTE XNU`: compile target, basic platform expert, and first GICv2 timer path added as source patches; not yet compiled or boot-validated.
