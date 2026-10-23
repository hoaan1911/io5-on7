#!/usr/bin/env python3
"""Offline regression tests against the stock ON7XELTE boot-image DTBH table."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adt
import mkadt_on7xelte as m


def child(node, name):
    found = [x for x in node.children if x.name == name]
    assert len(found) == 1, f'{node.name}: expected exactly one {name}, found {len(found)}'
    return found[0]


def u32prop(node, name): return struct.unpack('<I', child_prop(node, name))[0]
def child_prop(node, name):
    v=node.prop(name)
    assert v is not None, f'{node.name}: missing {name}'
    return v

boot = Path(sys.argv[1] if len(sys.argv)>1 else 'bringup/j7-hello/boot.img')
fdt, meta = m.read_boot_dtb(boot, 1)
source = m.parse_fdt(fdt)
assert 'samsung,exynos7870' in source.strings('compatible')
root, info = m.build_adt(fdt)
blob = adt.serialize(root)
parsed, end = adt.parse(blob)
assert end == len(blob)
assert parsed.name == 'device-tree'
assert parsed.prop('compatible').split(b'\0')[:2] == [b'D22AP', b'iPhone10,3']
chosen=child(parsed,'chosen')
assert struct.unpack('<Q',child_prop(chosen,'dram-base'))[0] == 0xb0000000
assert struct.unpack('<Q',child_prop(chosen,'dram-size'))[0] == 0x3ffff000
mmap=child(chosen,'memory-map')
assert len([x for x in mmap.children if x.name.startswith('ram')]) == 2
assert any(x.name=='reserved-framebuffer' for x in mmap.children)
cpus=child(parsed,'cpus')
assert len(cpus.children)==8
assert [struct.unpack('<Q',x.prop('reg'))[0] for x in cpus.children] == [0,1,2,3,0x100,0x101,0x102,0x103]
armio=child(parsed,'arm-io')
gic=child(armio,'gic')
assert u32prop(gic,'gic-version') == 2
regs=struct.unpack('<8Q',child_prop(gic,'reg'))
assert regs[:4] == (0x104e1000-0x01000000,0x1000,0x104e2000-0x01000000,0x1000)
timer=child(armio,'timer')
assert u32prop(timer,'clock-frequency') == 26000000
assert u32prop(timer,'virtual-timer-intid') == 11
psci=child(parsed,'psci')
assert psci.prop('method') == b'smc\0'
assert info['model'].startswith('Samsung ON7XE LTE')
print(f'PASS: DTBH v{meta["version"]} entry {meta["index"]}; {len(blob)}-byte ADT; 8 CPUs; 2 RAM banks; reserved-aware arena 0xb0000000+0x3ffff000; GICv2; virtual timer PPI 11; PSCI SMC')
