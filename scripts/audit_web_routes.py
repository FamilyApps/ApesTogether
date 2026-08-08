"""One-shot audit of the deployed web surface (api/index.py + registered route
modules): lists every non-API, non-admin page route so the legacy web app can
be classified (keep public / redirect / restyle). Written 2026-08-07 for the
old-website audit; safe to delete afterwards or keep for re-audits."""
import re
import sys

FILES = [
    'api/index.py',
    'mobile_api.py',
    'app.py',
]

ROUTE_RE = re.compile(r"@(?:app|bp|\w+_bp)\.route\(\s*['\"]([^'\"]+)['\"]")


def routes_with_decorators(src):
    """Yield (route, [decorators+def line]) for every @app.route in src."""
    lines = src.splitlines()
    for i, line in enumerate(lines):
        m = ROUTE_RE.match(line.strip())
        if not m:
            continue
        info = []
        j = i + 1
        while j < len(lines):
            s = lines[j].strip()
            if s.startswith('@'):
                info.append(s)
                j += 1
            elif s.startswith('def '):
                info.append(s)
                break
            else:
                break
        yield m.group(1), info


def main():
    for path in FILES:
        try:
            src = open(path, encoding='utf-8').read()
        except OSError:
            print(f'-- {path}: NOT FOUND')
            continue
        entries = [(r, d) for r, d in routes_with_decorators(src)
                   if not r.startswith(('/api', '/admin'))]
        print(f'== {path}: {len(entries)} non-api/admin routes ==')
        for route, decs in sorted(entries):
            print(f'  {route:45s} | {" ".join(decs)}')
        print()


if __name__ == '__main__':
    sys.exit(main())
