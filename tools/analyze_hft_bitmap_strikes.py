#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
import tempfile
import zipfile
from pathlib import Path


def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def u32(b,o): return struct.unpack_from('<I',b,o)[0]


def hexdump(b: bytes, start: int, length: int = 256):
    end=min(len(b),start+length)
    for o in range(start,end,16):
        row=b[o:min(end,o+16)]
        asc=''.join(chr(x) if 32 <= x < 127 else '.' for x in row)
        print(f'{o:08X}  {row.hex(" "):<47}  {asc}')


def scan_offset_tables(b: bytes, block: int, counts):
    print(' OFFSET TABLE SCAN')
    for count in counts:
        for unit,unpack in ((2,u16),(4,u32)):
            for pos in range(block,min(block+512,len(b)-unit*8)):
                try: vals=[unpack(b,pos+unit*i) for i in range(min(count,16))]
                except Exception: continue
                if not all(vals[i] <= vals[i+1] for i in range(len(vals)-1)): continue
                # Relative offsets commonly begin after their directory.
                expected=count*unit
                if not (max(0,expected-64) <= vals[0] <= expected+2048): continue
                # Full-table last value must point inside file if the table fits.
                if pos+unit*count > len(b): continue
                try: last=unpack(b,pos+unit*(count-1))
                except Exception: continue
                if last < vals[0] or pos+last > len(b): continue
                print(f'  candidate pos=0x{pos:X} unit={unit} count={count} first={vals[0]} first16={vals} last={last}')


def target_occurrences(b: bytes, lo: int, hi: int):
    print(' TARGET HNC CODE OCCURRENCES near strike')
    for code in (0x3404,0x340E,0x340F,0x3410,0x3411):
        needle=struct.pack('<H',code); poss=[]; p=lo
        while True:
            p=b.find(needle,p,hi)
            if p<0: break
            poss.append(p); p+=1
        print(f'  0x{code:04X}: {[hex(p) for p in poss[:20]]}')


def analyze(name: str, b: bytes):
    print('\n'+'='*80)
    print(name,'size',len(b),'marker',hex(u16(b,0x1A0)),'upem',u16(b,0x17A),'baseline',u16(b,0x194))
    print('header start/end',hex(u16(b,0x204)),hex(u16(b,0x206)),'outline start/end/count',hex(u16(b,0x220)),hex(u16(b,0x222)),u16(b,0x224))
    off14=u32(b,0x20C); off16=u32(b,0x21A)
    print('candidate strike offsets: off14@20C=',off14,hex(off14),'size14 field=',u16(b,0x216),'off16@21A=',off16,hex(off16),'size16 field=',u16(b,0x21E))
    print('global bounds-ish 0226..022E',[u16(b,o) for o in range(0x226,0x230,2)])
    for label,off in [('strike14',off14),('strike16',off16)]:
        if not (0x230 <= off < len(b)):
            print(label,'offset invalid'); continue
        print(f'--- {label} @0x{off:X} ---')
        hexdump(b,off,320)
        scan_offset_tables(b,off,[u16(b,0x224), u16(b,0x206)-u16(b,0x204)+1, 1024,960,946,384])
        target_occurrences(b,max(0,off-512),min(len(b),off+8192))

    # Inspect outline records for the same target indices for structural comparison.
    count=u16(b,0x224); base=0x230; start=u16(b,0x220)
    print('--- TARGET OUTLINE RECORD BYTES ---')
    for code in (0x3404,0x340E,0x340F,0x3410,0x3411):
        idx=code-start
        if not (0 <= idx < count): continue
        rel=u32(b,base+4*idx); o=base+rel; L=u16(b,o)
        print(f' code=0x{code:04X} idx={idx} rel={rel} abs=0x{o:X} len={L} bytes={b[o:o+min(2+L,96)].hex(" ")}')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('zip',type=Path)
    ap.add_argument('--fonts',nargs='*',default=['SPSMJ.HFT','SPJGT.HFT','TETGRSP.HFT'])
    a=ap.parse_args()
    with zipfile.ZipFile(a.zip) as z:
        lookup={Path(n).name.upper():n for n in z.namelist() if not n.endswith('/')}
        for fn in a.fonts:
            key=fn.upper()
            if key not in lookup:
                print('MISSING',fn); continue
            analyze(fn,z.read(lookup[key]))

if __name__=='__main__': main()
