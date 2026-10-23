#!/usr/bin/env python3
"""Generate an Apple Device Tree-shaped ADT from the Samsung ON7XELTE DTB.

This is an early-boot porting ADT, not proof that the existing SWEET XNU kernel
supports Exynos 7870. Uses only Python stdlib and the repository's adt.py.
"""
import argparse, os, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adt

ANDROID_MAGIC = b'ANDROID!'
DTBH_MAGIC = b'DTBH'
FDT_MAGIC = 0xd00dfeed


def be32(b, off=0): return struct.unpack_from('>I', b, off)[0]
def le32(b, off=0): return struct.unpack_from('<I', b, off)[0]
def u32(*xs): return struct.pack('<' + 'I'*len(xs), *xs)
def u64(*xs): return struct.pack('<' + 'Q'*len(xs), *xs)
def cstr(s): return s.encode() + b'\0'
def cstrs(*xs): return b''.join(cstr(x) for x in xs)

class FNode:
    def __init__(self, name): self.name, self.props, self.children, self.parent = name, {}, [], None
    def child(self, name): return next((x for x in self.children if x.name == name), None)
    def get(self, key, default=None): return self.props.get(key, default)
    def strings(self, key):
        v = self.get(key, b'')
        return [x.decode('ascii', 'replace') for x in v.split(b'\0') if x]
    def path(self):
        a=[]; n=self
        while n and n.parent: a.append(n.name); n=n.parent
        return '/' + '/'.join(reversed(a))


def parse_fdt(blob):
    if len(blob) < 40 or be32(blob) != FDT_MAGIC: raise ValueError('not a flattened device tree (FDT)')
    total, off_struct, off_strings, off_rsv, ver, last, boot, sz_strings, sz_struct = struct.unpack_from('>9I', blob, 4)
    if total > len(blob) or total < 40: raise ValueError('invalid FDT totalsize')
    strings = blob[off_strings:off_strings+sz_strings]
    end = off_struct + sz_struct; pos=off_struct; stack=[]; root=None
    while pos < end:
        tok=be32(blob,pos); pos += 4
        if tok == 1:
            z=blob.index(b'\0',pos,end); name=blob[pos:z].decode('ascii','replace'); pos=(z+4)&~3
            n=FNode(name)
            if stack: n.parent=stack[-1]; stack[-1].children.append(n)
            else: root=n
            stack.append(n)
        elif tok == 2:
            if not stack: raise ValueError('unbalanced FDT END_NODE')
            stack.pop()
        elif tok == 3:
            ln,no=struct.unpack_from('>II',blob,pos); pos+=8
            if no >= len(strings): raise ValueError('bad FDT string offset')
            e=strings.find(b'\0',no)
            if e < 0: raise ValueError('unterminated FDT property name')
            name=strings[no:e].decode('ascii','replace')
            if not stack: raise ValueError('property outside node')
            stack[-1].props[name]=blob[pos:pos+ln]; pos=(pos+ln+3)&~3
        elif tok == 4: continue
        elif tok == 9: break
        else: raise ValueError(f'unknown FDT token {tok:#x} at {pos-4:#x}')
    if root is None: raise ValueError('FDT has no root')
    return root


def read_boot_dtb(path, index):
    img=Path(path).read_bytes()
    if img[:8] != ANDROID_MAGIC: raise ValueError('boot image does not begin with ANDROID!')
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, dt_size, _ = struct.unpack_from('<10I',img,8)
    off=page
    for sz in (kernel_size, ramdisk_size, second_size): off += ((sz+page-1)//page)*page
    dt=img[off:off+dt_size]
    if dt[:4] != DTBH_MAGIC: raise ValueError('boot image DT area is not a Samsung DTBH table')
    version,count=struct.unpack_from('<II',dt,4)
    if index >= count: raise ValueError(f'DTB index {index} out of range; table has {count} entries')
    chip,plat,sub,rev,rev_end,dtoff,size,space=struct.unpack_from('<8I',dt,12+32*index)
    raw=dt[dtoff:dtoff+size]
    if len(raw)<8 or be32(raw)!=FDT_MAGIC: raise ValueError('selected DTBH entry is not an FDT')
    return raw[:be32(raw,4)], {'version':version,'count':count,'index':index,'chip':chip,'platform':plat,'subtype':sub,'rev':rev,'rev_end':rev_end}


def prop_u32(node, key, default=None):
    b=node.get(key)
    if b is None: return default
    if len(b)<4: raise ValueError(f'{node.path()} property {key} shorter than u32')
    return be32(b)


def decode_reg(node):
    parent=node.parent
    ac=prop_u32(parent,'#address-cells',2) if parent else 2
    sc=prop_u32(parent,'#size-cells',1) if parent else 1
    b=node.get('reg')
    if b is None: return []
    stride=(ac+sc)*4
    if not stride or len(b)%stride: return []
    out=[]
    for i in range(0,len(b),stride):
        addr=int.from_bytes(b[i:i+ac*4],'big'); size=int.from_bytes(b[i+ac*4:i+stride],'big') if sc else 0
        out.append((addr,size))
    return out


def walk(n):
    yield n
    for c in n.children: yield from walk(c)


def adt_node(name, props=(), children=()):
    n=adt.Node(); n.props=[('name',0,cstr(name))]+[(k,0,v) for k,v in props]; n.children=list(children); return n


def get_compat(root, tokens):
    for n in walk(root):
        if any(t in n.strings('compatible') for t in tokens): return n
    return None


def build_adt(fdt):
    root=parse_fdt(fdt)
    compat=root.strings('compatible'); model=root.get('model',b'Samsung Galaxy J7 Prime\0').split(b'\0')[0].decode('ascii','replace')
    if not any('exynos7870' in x.lower() for x in compat) and not any('on7xelte' in x.lower() for x in compat):
        raise ValueError('input DTB does not identify as Exynos 7870 / ON7XELTE: '+repr(compat))
    mem=[]; reserved=[]
    for n in walk(root):
        if n.get('device_type',b'').split(b'\0')[0] == b'memory' or n.name.startswith('memory@'):
            mem.extend(decode_reg(n))
    rm=root.child('reserved-memory')
    if rm:
        for n in rm.children:
            reserved.extend((a,s,n.name) for a,s in decode_reg(n) if s)
    mem=[(a,s) for a,s in mem if s]
    if not mem: raise ValueError('no RAM ranges found in input DTB')
    mem.sort()
    # The current loader/pmap contract supports one contiguous arena. Find the
    # largest 32-MiB-aligned gap in RAM after excluding every DTB reserved region
    # and the known S-Boot framebuffer. Publish all banks separately for future
    # multi-bank pmap work; do not pretend the holes are allocatable RAM.
    occupied=[(a,a+s) for a,s,_ in reserved if s]
    occupied.append((0x67000000,0x67000000+1080*1920*4))
    candidates=[]
    align=0x02000000
    for bank_base,bank_size in mem:
        bank_end=bank_base+bank_size
        blocks=sorted((max(a,bank_base),min(b,bank_end)) for a,b in occupied if a<bank_end and b>bank_base)
        cursor=bank_base
        for lo,hi in blocks:
            if lo>cursor:
                start=(cursor+align-1)&~(align-1)
                if start<lo: candidates.append((lo-start,start))
            cursor=max(cursor,hi)
        if cursor<bank_end:
            start=(cursor+align-1)&~(align-1)
            if start<bank_end: candidates.append((bank_end-start,start))
    if not candidates: raise ValueError('no contiguous RAM arena remains after reserved regions')
    arena_size,first_base=max(candidates)
    first_size=arena_size
    if arena_size < 0x08000000: raise ValueError(f'only {arena_size:#x} bytes of contiguous RAM remain; refusing tiny arena')
    chosen=adt_node('chosen', [
        ('dram-base',u64(first_base)), ('dram-size',u64(first_size)),
        ('random-seed',os.urandom(64)), ('debug-enabled',u32(1)),
        ('firmware-version',cstr('on7xelte-sboot')), ('system-firmware-version',cstr('on7xelte-sboot')),
        ('boot-args',cstr('debug=0x8 keepsyms=1 serial=3')),
        ('unique-chip-id',u64(0x4f4e3758454c5445)), ('chip-id',u32(0x7870)),
        ('display-scale',u32(3)),
    ], [adt_node('memory-map')])
    # Attach explicit memory bank children for later platform code. These are not
    # substitutes for XNU pmap changes; the first bank is the only bootstrap arena.
    mmap=chosen.children[0]
    for i,(a,s) in enumerate(mem):
        mmap.children.append(adt_node(f'ram{i}', [('reg',u64(a,s)),('bank-index',u32(i))]))
    for i,(a,s,name) in enumerate(reserved):
        mmap.children.append(adt_node(f'reserved{i}', [('reg',u64(a,s)),('description',cstr(name))]))
    mmap.children.append(adt_node('reserved-framebuffer', [('reg',u64(0x67000000,1080*1920*4)),('description',cstr('S-Boot framebuffer; exclude from allocator'))]))

    cpus_node=root.child('cpus'); cpus=[]
    if cpus_node:
        for n in cpus_node.children:
            if n.get('device_type',b'').split(b'\0')[0] != b'cpu': continue
            reg=n.get('reg',b'')
            if not reg: continue
            mpidr=int.from_bytes(reg,'big')
            cpu_id=len(cpus)
            cpus.append(adt_node(f'cpu{cpu_id}', [
                ('device_type',cstr('cpu')), ('compatible',cstrs('arm,cortex-a53','ARM,v8')),
                ('reg',u64(mpidr)), ('cpu-id',u32(cpu_id)), ('state',cstr('running' if cpu_id==0 else 'stopped')),
                ('enable-method',cstr('psci')),
            ]))
    if not cpus: raise ValueError('no Cortex-A CPU nodes found in DTB')
    cpus_adt=adt_node('cpus',[('#address-cells',u32(2)),('#size-cells',u32(0))],cpus)

    gic=get_compat(root,['arm,cortex-a15-gic','arm,cortex-a9-gic'])
    if not gic: raise ValueError('could not find the GICv2 controller in the input DTB')
    gregs=decode_reg(gic)
    if len(gregs)<2: raise ValueError('GIC DTB node lacks distributor/cpu-interface reg ranges')
    gic_adt=adt_node('gic',[('compatible',cstrs('arm,cortex-a15-gic','arm,cortex-a9-gic')),
        ('interrupt-controller',b''),('reg',b''.join(u64(a-0x01000000,s) for a,s in gregs)),('gic-version',u32(2))])

    timer=get_compat(root,['arm,armv8-timer'])
    timer_freq=prop_u32(timer,'clock-frequency',26000000) if timer else 26000000
    # DT binding order: secure physical (13), non-secure physical (14), virtual (11), hypervisor (10).
    timer_irqs=timer.get('interrupts',b'') if timer else b''
    irq_cells=[be32(timer_irqs,i) for i in range(0,len(timer_irqs),4)] if timer_irqs and len(timer_irqs)%4==0 else []
    vtimer_intid=irq_cells[7] if len(irq_cells)>=9 else 11
    if vtimer_intid not in (11,19,27):
        raise ValueError(f'unexpected virtual timer INTID {vtimer_intid}; refusing to guess')
    timer_adt=adt_node('timer',[('compatible',cstr('arm,armv8-timer')),('clock-frequency',u32(timer_freq)),('virtual-timer-intid',u32(vtimer_intid))])

    serial=get_compat(root,['samsung,exynos7870-uart','samsung,exynos-uart'])
    # The serial console is only advertised, not assumed enabled; the bootloader
    # may already have initialized UART2 and pinmux.
    serial_adt=adt_node('serial',[('compatible',cstr('samsung,exynos7870-uart')),('reg',u64(0x13820000-0x01000000,0x100)),('status',cstr('okay'))])

    fb=adt_node('on7xelte-fbcon',[('reg',u64(0x67000000,1080*1920*4)),('width',u32(1080)),('height',u32(1920)),('stride',u32(1080*4)),('format',cstr('a8r8g8b8'))])
    emmc=get_compat(root,['samsung,exynos-dw-mshc'])
    emmc_nodes=[]
    for n in walk(root):
        if any('exynos-dw-mshc' in x for x in n.strings('compatible')):
            for a,s in decode_reg(n):
                emmc_nodes.append(adt_node(n.name.split('@')[0],[('compatible',cstrs(*n.strings('compatible'))),('reg',u64(a-0x01000000,s)),('status',n.get('status',cstr('okay')))]))
    disp=adt_node('disp0',[('device_type',cstr('display-subsystem')),('compatible',cstrs('samsung,exynos7870-decon','simple-framebuffer')),('canvas-width',u32(1080)),('canvas-height',u32(1920)),('framebuffer-base',u64(0x67000000))])
    armio=adt_node('arm-io',[
        ('device_type',cstr('on7xelte-io')),('compatible',cstrs('samsung,on7xelte-io','arm-io')),
        ('#address-cells',u32(2)),('#size-cells',u32(2)),('ranges',u64(0,0x01000000,0x100000000-0x01000000)),
    ],[gic_adt,timer_adt,serial_adt,disp]+emmc_nodes)
    psci=adt_node('psci',[('compatible',cstr('arm,psci')),('method',cstr('smc')),('cpu_on',u32(0xc4000003)),('cpu_off',u32(0x84000002)),('cpu_suspend',u32(0xc4000001))])
    buttons=adt_node('buttons',[('button-names',cstrs('volup','voldown','power','home')),('home-button-type',u32(1))])
    out=adt_node('device-tree',[
        ('compatible',cstrs('D22AP','iPhone10,3','samsung,on7xelte','samsung,exynos7870','AppleARM')),
        ('model',cstr('iPhone10,3')),('target-type',cstr('D22')),('target-sub-type',cstr('D22AP')),
        ('manufacturer',cstr('Apple Inc.')),('#address-cells',u32(2)),('#size-cells',u32(2)),
        ('board-model',cstr(model)),('board-compatible',cstrs(*compat)),
    ],[chosen,cpus_adt,armio,fb,buttons,psci])
    return out, {'model':model,'compatible':compat,'memory':mem,'reserved':reserved,'arena':(first_base,first_size),'cpu_count':len(cpus),'gic_regs':gregs,'timer_hz':timer_freq}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('output',help='output raw Apple Device Tree (ADT) file')
    ap.add_argument('--boot-image',default='bringup/j7-hello/boot.img',help='Samsung Android boot image containing DTBH table')
    ap.add_argument('--dtb',help='use a raw FDT instead of extracting DTB from --boot-image')
    ap.add_argument('--dtb-index',type=int,default=1,help='DTBH entry index (default: revision 1)')
    ap.add_argument('--dump',action='store_true')
    a=ap.parse_args()
    if a.dtb:
        fdt=Path(a.dtb).read_bytes(); meta={'source':a.dtb}
    else:
        fdt,meta=read_boot_dtb(a.boot_image,a.dtb_index)
    tree,info=build_adt(fdt)
    blob=adt.serialize(tree)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_bytes(blob)
    print(f'{a.output}: {len(blob)} bytes Apple ADT serialization')
    print(f'source={meta}; board={info["model"]!r}; compatible={info["compatible"]}')
    print(f'CPUs={info["cpu_count"]}; RAM={[(hex(x),hex(s)) for x,s in info["memory"]]}; reserved={len(info["reserved"])}')
    print(f'contiguous XNU arena={hex(info["arena"][0])}+{hex(info["arena"][1])}')
    print(f'GICv2 regs={[(hex(x),hex(s)) for x,s in info["gic_regs"]]}; timer={info["timer_hz"]} Hz')
    # Round-trip through this repository's ADT parser to catch malformed output.
    parsed,end=adt.parse(blob)
    if end != len(blob): raise SystemExit(f'ADT round-trip did not consume all bytes: {end}/{len(blob)}')
    if a.dump: adt.dump(parsed)

if __name__=='__main__': main()
