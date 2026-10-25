#!/usr/bin/env python
"""여유 메모리 확인 — 레인을 더 띄울지, 빌드를 돌려도 될지 판단하는 숫자.

  python memguard.py                 여유 메모리(GB) 출력
  python memguard.py --min 2.5       미만이면 종료 코드 1 (새 레인·빌드 금지 신호)

기준(실측 — references/environment.md §6): 측정 중 여유 < 1.5GB 면 새 레인을 띄우지 않는다.
브라우저 ≈ 2~3GB, 에뮬레이터 ≈ 2~4GB, 에이전트 터미널 1개 ≈ 0.5~0.7GB, Gradle 데몬 ≈ 1~2GB.
이 스크립트는 아무것도 죽이지 않는다 — 정리는 사람이 허용한 프로세스만(유휴 빌드 데몬 등) 직접 한다.
"""
import argparse
import platform
import re
import subprocess
import sys


def free_gb():
    sysname = platform.system()
    if sysname == 'Windows':
        out = subprocess.run(['powershell', '-NoProfile', '-Command',
                              '(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'],
                             capture_output=True, text=True).stdout
        return int(re.findall(r'\d+', out)[0]) / 1024 / 1024
    if sysname == 'Darwin':
        out = subprocess.run(['vm_stat'], capture_output=True, text=True).stdout
        page = int(re.search(r'page size of (\d+)', out).group(1))
        pages = sum(int(re.search(rf'{k}:\s+(\d+)', out).group(1)) for k in ('Pages free', 'Pages inactive'))
        return pages * page / 1024 ** 3
    for line in open('/proc/meminfo'):
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) / 1024 / 1024
    return -1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--min', type=float)
    a = p.parse_args()
    gb = free_gb()
    ok = a.min is None or gb >= a.min
    print(f'free {gb:.1f}GB' + ('' if a.min is None else f' (min {a.min}GB → {"OK" if ok else "LOW"})'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
