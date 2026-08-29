# -*- coding: utf-8 -*-
"""建てた jar が、**配布された Origins の jar と同じ中身か**を確かめる。

⚠⚠ **なぜ要るか**: この repo は上流を統合していく土台で、最初にやることは
「まだ何も変えていない状態で、配布された物と同じ物が出る」を示すこと。
⚠ **それを人の目で確かめると必ず取りこぼす**（class は 800 本を超える）。

⚠ **バイト単位では一致しない。** 建てる時刻・Gradle の版・**javac の版**で必ず変わる。
そこで、違いを次のように仕分けて、⚠ **説明の付かない差が0であること**を判定にする:

  ① 項目の顔ぶれ            … 片方にしか無い物が在ったら ⚠⚠（即 NG）
  ② メソッドの顔ぶれ        … 新しい javac は橋渡しのメソッドを1つ足すことがある
  ③ 文字列の連結の作り方    … 新しい javac は連結の前に String.valueOf を挟む
  ④ 飛び先の番地 / ldc_w    … ⚠ ①〜③で命令が増えると**後ろが全部ずれる**。原因ではなく結果

使い方:

    py -3.12 tools/compare_with_released.py            # 配布版が無ければ落とす
    py -3.12 tools/compare_with_released.py --built <jar>

終了コード 0 = 説明の付かない差が無い。1 = 在る（中身を見て判断する）。
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_BUILT = os.path.join(
    ROOT, "origins", "build", "libs", "origins-forge-1.20.1-1.10.0.9-all.jar")
API = "https://api.modrinth.com/v2/project/origins-forge/version"
RELEASED_VERSION = "1.20.1-1.10.0.9"

# 建てるたびに必ず変わる項目（中身の違いとして数えない）
NOISE = {"META-INF/MANIFEST.MF", "META-INF/jarjar/metadata.json"}

POOL = re.compile(r"#\d+")
ADDR = re.compile(r"^\s*\d+:\s*")
SIG = re.compile(r"^  \S.*\(.*\);\s*$")
BRANCH = re.compile(r"^(if\w*|goto\w*|jsr\w*|tableswitch|lookupswitch)\s+\d+$")
EXC = re.compile(r"^\d+\s+\d+\s+\d+\s+(Class .*|any)$")
WIDE = re.compile(r"^ldc_w\b")
CONCAT = ("String.valueOf", "makeConcatWithConstants")


def find_javap():
    """javap を探す。⚠ 素の `java` は 8 なので、17 以上のものが要る。"""
    candidates = [
        os.path.join(os.environ.get("JAVA_HOME", ""), "bin", "javap.exe"),
        os.path.expandvars(r"%APPDATA%\PrismLauncher\java"
                           r"\java-runtime-delta\bin\javap.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise SystemExit("!! javap（17以上）が見つからない。JAVA_HOME を指定して回す")


def download_released(dest):
    with urllib.request.urlopen(API, timeout=60) as res:
        data = json.load(res)
    for v in data:
        if v.get("version_number") != RELEASED_VERSION:
            continue
        for f in v.get("files", []):
            if f["filename"].endswith("-all.jar"):
                print(f"配布版を落とす: {f['filename']}  {f['size']:,} バイト")
                urllib.request.urlretrieve(f["url"], dest)
                return True
    return False


def entries(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return {i.filename: i.CRC for i in zf.infolist() if not i.is_dir()}


def member(blob, name):
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return zf.read(name)


def javap(javap_path, data, work, tag, name):
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, name.replace("/", "_"))
    with open(out, "wb") as fh:
        fh.write(data)
    res = subprocess.run([javap_path, "-p", "-c", out], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    return res.stdout


def norm(text):
    """比べる前に、**原因ではなく結果として動くもの**を消す。"""
    lines = []
    for line in text.splitlines():
        line = POOL.sub("#N", line)
        line = ADDR.sub("", line)
        line = re.sub(r"\s+", " ", line).strip()
        line = WIDE.sub("ldc", line)
        if BRANCH.match(line):
            line = line.split()[0] + " #T"
        elif EXC.match(line):
            line = "EXC " + line.split(None, 3)[3]
        lines.append(line)
    return lines


def methods(text):
    return {l.strip() for l in text.splitlines() if SIG.match(l)}


def classify(javap_path, work, a_data, b_data, name):
    ta = javap(javap_path, a_data, work, "built", name)
    tb = javap(javap_path, b_data, work, "released", name)
    ma, mb = methods(ta), methods(tb)
    if ma != mb:
        extra, missing = sorted(ma - mb), sorted(mb - ma)
        if missing:
            return ("⚠⚠ 建てた版にメソッドが足りない", extra, missing)
        return ("橋渡しのメソッドが増えている（javac の版）", extra, [])
    na, nb = norm(ta), norm(tb)
    if na == nb:
        return ("番号と番地だけの差", [], [])
    only_a = [l for l in set(na) - set(nb) if l]
    only_b = [l for l in set(nb) - set(na) if l]
    rest_a = [l for l in only_a if not any(c in l for c in CONCAT)]
    rest_b = [l for l in only_b if not any(c in l for c in CONCAT)]
    if not rest_a and not rest_b:
        return ("文字列の連結の作り方だけ（javac の版）", [], [])
    return ("⚠⚠ 説明の付かない差", rest_a[:5], rest_b[:5])


def walk(javap_path, work, blob_a, blob_b, label, report, problems):
    ea, eb = entries(blob_a), entries(blob_b)
    only_a = sorted(set(ea) - set(eb))
    only_b = sorted(set(eb) - set(ea))
    for name in only_a:
        problems.append(f"⚠⚠ {label} :: 建てた版にしか無い: {name}")
    for name in only_b:
        problems.append(f"⚠⚠ {label} :: 配布された版にしか無い: {name}")

    for name in sorted(set(ea) & set(eb)):
        if ea[name] == eb[name] or name in NOISE:
            continue
        if name.endswith(".jar"):
            walk(javap_path, work, member(blob_a, name), member(blob_b, name),
                 name.rsplit("/", 1)[-1], report, problems)
            continue
        if not name.endswith(".class"):
            problems.append(f"⚠⚠ {label} :: class ではない項目の中身が違う: {name}")
            continue
        verdict, extra, missing = classify(
            javap_path, work, member(blob_a, name), member(blob_b, name), name)
        report.setdefault(verdict, []).append((label, name, extra, missing))
        if verdict.startswith("⚠⚠"):
            problems.append(f"⚠⚠ {label} :: {name}")


def load_allow(path):
    """⚠ **説明の付く差**を宣言する表。1行1つ、`#` から後ろは注記。

    ⚠ **これを空にしない**。当部が中身を変えていく以上、差は必ず出る。
    ⚠ **使われなかった行も報告する**——期待していた差が消えたということなので、
       宣言のほうが古い（消し忘れ）か、変更が消えたかのどちらか。
    """
    allow = {}
    if not path:
        return allow
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, _, why = line.partition("#")
            allow[name.strip()] = why.strip() or "（理由が書かれていない）"
    return allow


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--built", default=DEFAULT_BUILT)
    ap.add_argument("--released")
    ap.add_argument("--allow", help="説明の付く差を宣言した表（tools/expected-diffs-*.txt）")
    args = ap.parse_args()

    if not os.path.exists(args.built):
        raise SystemExit(f"!! 建てた jar が無い: {args.built}\n"
                         "   先に `gradlew build` を回す")

    work = tempfile.mkdtemp(prefix="eruto-origins-cmp-")
    released = args.released or os.path.join(work, "released.jar")
    if not os.path.exists(released):
        if not download_released(released):
            raise SystemExit(f"!! 配布版 {RELEASED_VERSION} の -all.jar が見つからない")

    javap_path = find_javap()
    with open(args.built, "rb") as fh:
        a = fh.read()
    with open(released, "rb") as fh:
        b = fh.read()

    print(f"建てた版    : {len(a):,} バイト  {args.built}")
    print(f"配布された版: {len(b):,} バイト  {released}")
    print()

    allow = load_allow(args.allow)
    report, problems = {}, []
    walk(javap_path, work, a, b, "origins-forge-all", report, problems)

    total = sum(len(v) for v in report.values())
    print(f"中身が違う class（同梱の jar の中も含む）: {total}")
    for verdict in sorted(report):
        print(f"    {len(report[verdict]):4d} 件  {verdict}")
    print()

    # 宣言してある差を外す。⚠ **どれが使われたかを必ず出す**
    used, rest = set(), []
    for line in problems:
        hit = next((k for k in allow if line.endswith(k)), None)
        if hit:
            used.add(hit)
            continue
        rest.append(line)

    if allow:
        print(f"説明の付く差として宣言してあるもの: {len(allow)} 件")
        for name in sorted(allow):
            mark = "当たった" if name in used else "⚠ 当たらなかった"
            print(f"    [{mark}] {name} — {allow[name]}")
        unused = sorted(set(allow) - used)
        if unused:
            print("⚠⚠ 当たらなかった宣言が在る。"
                  "期待していた差が消えている——宣言が古いか、変更が落ちたかのどちらか")
        print()

    if rest:
        print(f"!! 説明の付かない差: {len(rest)} 件")
        for line in rest[:40]:
            print(f"    {line}")
        return 1
    if allow and set(allow) - used:
        return 1
    print("判定: OK — 説明の付かない差は無い")
    return 0


if __name__ == "__main__":
    sys.exit(main())
