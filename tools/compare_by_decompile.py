# -*- coding: utf-8 -*-
"""⚠ **自作の突き合わせに、別のやり方で第二の意見を出す。**

`tools/compare_with_released.py` は javap の出力を正規化して比べている。
⚠ **飛び先の番地と `ldc`/`ldc_w` を「同じ」に丸めている**ので、
⚠⚠ **番地だけが変わる本物の変更**は見逃しうる（枝の命令そのものは残しているので、
条件の反転は拾えるはずだが、それも自分の判断）。

そこで**逆コンパイルして Java のソースで比べる**（定石）。
⚠ 逆コンパイラは ForgeGradle が既に落としている ForgeFlower を使う（新たに取らない）。

    py -3.12 tools/compare_by_decompile.py

⚠ 判定: 差が出た class を名指しする。0 件なら自作の道具の結論と一致。
"""
import io
import os
import shutil
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SP = (r"C:\Users\darks\AppData\Local\Temp\claude\c---projects"
      r"\1bd1f62f-c5f0-4841-9273-694275416aea\scratchpad")
BUILT = (r"c:\@projects\minecraft-club\eruto-mc\eruto-origins"
         r"\origins\build\libs\origins-forge-1.20.1-1.10.0.9-all.jar")
RELEASED = os.path.join(SP, "origins-forge-1.20.1-1.10.0.9-all.jar")
FF = (r"C:\Users\darks\.gradle\caches\forge_gradle\maven_downloader"
      r"\net\minecraftforge\forgeflower\2.0.629.0\forgeflower-2.0.629.0.jar")
JAVA = (r"C:\Users\darks\AppData\Roaming\PrismLauncher\java"
        r"\java-runtime-delta\bin\java.exe")
WORK = os.path.join(SP, "secondop")

# 段1で「javac の版の違い」と判定した外側の6件
TARGETS = [
    "io/github/apace100/origins/badge/BadgeFactory.class",
    "io/github/apace100/origins/badge/BadgeManager.class",
    "io/github/apace100/origins/util/ChoseOriginCriterion.class",
    "io/github/edwinmindcraft/origins/api/capabilities/IOriginContainer.class",
    "io/github/edwinmindcraft/origins/api/origin/OriginLayer.class",
    "io/github/edwinmindcraft/origins/common/data/OriginLoader.class",
]


def extract(jar, tag):
    out = os.path.join(WORK, tag)
    if os.path.isdir(out):
        shutil.rmtree(out)
    with zipfile.ZipFile(jar) as zf:
        for name in TARGETS:
            dest = os.path.join(out, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(zf.read(name))
    return out


def decompile(src, tag):
    dst = os.path.join(WORK, tag + "-src")
    os.makedirs(dst, exist_ok=True)
    res = subprocess.run(
        [JAVA, "-jar", FF, "-dgs=1", "-rsy=0", "-din=1", src, dst],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print("!! 逆コンパイルが失敗した（%s）" % tag)
        print(res.stdout[-1500:])
        print(res.stderr[-1500:])
        return None
    return dst


def unwrap_valueof(text):
    """⚠ `String.valueOf(<式>)` を `<式>` へ戻す（括弧を数えて対応を取る）。

    ⚠⚠ **なぜ要るか**: 新しい javac は `"a" + obj` の連結で `String.valueOf` を
    **明示して出す**。⚠ **意味は同じ**（`+` の連結は元からこれをやる）。
    ⚠ ここを丸めないと、⚠⚠ **javac の版が違うだけで全部「差が在る」になり、
    本物の差が埋まる**（鳴り続ける検査は本物を埋める）。

    ⚠ **丸めるのはこの1つだけ。** 他の差は残す。
    """
    token = "String.valueOf("
    out = []
    i = 0
    while True:
        j = text.find(token, i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        k = j + len(token)
        depth = 1
        while k < len(text) and depth:
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
            k += 1
        if depth:                     # 対応が取れない＝丸めない（安全側）
            out.append(text[j:])
            return "".join(out)
        out.append(unwrap_valueof(text[j + len(token):k - 1]))
        i = k


def java_files(root):
    out = {}
    for dirpath, _d, files in os.walk(root):
        for f in files:
            if f.endswith(".java"):
                full = os.path.join(dirpath, f)
                out[os.path.relpath(full, root)] = open(
                    full, encoding="utf-8", errors="replace").read()
    return out


def main():
    for path, label in ((FF, "ForgeFlower"), (JAVA, "java"),
                        (BUILT, "建てた jar"), (RELEASED, "配布された jar")):
        if not os.path.exists(path):
            raise SystemExit("!! %s が無い: %s" % (label, path))

    a_dir = extract(BUILT, "built")
    b_dir = extract(RELEASED, "released")
    print("取り出した class: %d 件ずつ" % len(TARGETS))

    a_src = decompile(a_dir, "built")
    b_src = decompile(b_dir, "released")
    if not a_src or not b_src:
        return 2

    a, b = java_files(a_src), java_files(b_src)
    print("逆コンパイルできた: 建てた版 %d ／ 配布された版 %d" % (len(a), len(b)))
    print()

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    for n in only_a:
        print("  ⚠ 建てた版にしか無い: %s" % n)
    for n in only_b:
        print("  ⚠ 配布された版にしか無い: %s" % n)

    differ, explained = [], []
    for name in sorted(set(a) & set(b)):
        if a[name] == b[name]:
            continue
        # ⚠ **javac の版で説明が付く丸めを当ててから、もう一度比べる**
        if unwrap_valueof(a[name]) == unwrap_valueof(b[name]):
            explained.append(name)
            continue
        differ.append(name)

    print("完全に一致: %d 件" % len(set(a) & set(b) - set(differ) - set(explained)))
    print("⚠ 文字列連結の書き方だけ（javac の版）: %d 件" % len(explained))
    for name in explained:
        print("     %s" % name)

    print("同じ名前で**ソースが違う**: %d / %d" % (differ and len(differ) or 0, len(set(a) & set(b))))
    for name in differ:
        print("  ⚠⚠ %s" % name)
        la, lb = a[name].splitlines(), b[name].splitlines()
        for i, (x, y) in enumerate(zip(la, lb)):
            if x != y:
                print("      最初の食い違い（%d 行目）:" % (i + 1))
                print("        建てた版  : %s" % x.strip()[:120])
                print("        配布された版: %s" % y.strip()[:120])
                break
        else:
            print("      行数が違う: %d / %d" % (len(la), len(lb)))
    print()
    if differ or only_a or only_b:
        print("判定: ⚠⚠ **ソースに差が在る。自作の道具の結論と食い違う**")
        return 1
    print("判定: OK — ⚠ **逆コンパイルしたソースは完全に一致**"
          "（自作の道具の「javac の版の違いだけ」を裏づける）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
