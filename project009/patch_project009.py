from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def require_tool(name: str) -> str:
    tool = shutil.which(name)
    if not tool:
        raise RuntimeError(
            f"Required tool '{name}' was not found in PATH. "
            "Install apktool / Android build-tools before running the patcher."
        )
    return tool


def choose_base_apk(root: Path) -> Path:
    apks = list(root.rglob("*.apk"))
    if not apks:
        raise RuntimeError("No APK files found inside XAPK")

    preferred = [p for p in apks if p.name.lower() in {"base.apk", "app.apk"}]
    if preferred:
        return max(preferred, key=lambda p: p.stat().st_size)
    return max(apks, key=lambda p: p.stat().st_size)


def patch_app_name(decoded: Path, new_name: str) -> list[str]:
    changed: list[str] = []
    res = decoded / "res"
    if res.exists():
        for strings in res.glob("values*/strings.xml"):
            try:
                tree = ET.parse(strings)
                root = tree.getroot()
                touched = False
                for node in root.findall("string"):
                    if node.attrib.get("name") in {
                        "app_name",
                        "application_name",
                        "launcher_name",
                        "game_name",
                    }:
                        node.text = new_name
                        touched = True
                if touched:
                    tree.write(strings, encoding="utf-8", xml_declaration=True)
                    changed.append(str(strings.relative_to(decoded)))
            except ET.ParseError:
                continue

    manifest = decoded / "AndroidManifest.xml"
    if manifest.exists():
        tree = ET.parse(manifest)
        root = tree.getroot()
        app = root.find("application")
        if app is not None:
            label_key = f"{{{ANDROID_NS}}}label"
            old = app.attrib.get(label_key, "")
            if not old.startswith("@string/"):
                app.set(label_key, new_name)
                tree.write(manifest, encoding="utf-8", xml_declaration=True)
                changed.append("AndroidManifest.xml")
    return changed


def inject_project_assets(decoded: Path, project_dir: Path) -> list[str]:
    target = decoded / "assets" / "project009"
    target.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    sources = {
        project_dir / "config" / "project009.json": target / "project009.json",
        project_dir / "NOTICE.md": target / "NOTICE.txt",
    }
    for src, dst in sources.items():
        if src.exists():
            shutil.copy2(src, dst)
            copied.append(str(dst.relative_to(decoded)))

    marker = target / "ALMAS_OFFICIAL"
    marker.write_text(
        "Project 009 | Almas Official | modification layer\n",
        encoding="utf-8",
    )
    copied.append(str(marker.relative_to(decoded)))
    return copied


def add_manifest_metadata(decoded: Path) -> None:
    manifest = decoded / "AndroidManifest.xml"
    tree = ET.parse(manifest)
    root = tree.getroot()
    app = root.find("application")
    if app is None:
        raise RuntimeError("AndroidManifest.xml has no <application> node")

    name_key = f"{{{ANDROID_NS}}}name"
    value_key = f"{{{ANDROID_NS}}}value"

    wanted = {
        "com.almasofficial.project009.EDITION": "Project 009",
        "com.almasofficial.project009.PUBLISHER": "Almas Official",
        "com.almasofficial.project009.ECONOMY": "AO Coin / Gold / Bank / Reputation",
    }

    existing = {
        node.attrib.get(name_key): node
        for node in app.findall("meta-data")
        if node.attrib.get(name_key)
    }

    for key, value in wanted.items():
        node = existing.get(key)
        if node is None:
            node = ET.SubElement(app, "meta-data")
            node.set(name_key, key)
        node.set(value_key, value)

    tree.write(manifest, encoding="utf-8", xml_declaration=True)


def sign_apk(apk: Path, keystore: Path, alias: str, storepass: str, keypass: str | None) -> None:
    apksigner = require_tool("apksigner")
    cmd = [
        apksigner,
        "sign",
        "--ks",
        str(keystore),
        "--ks-key-alias",
        alias,
        "--ks-pass",
        f"pass:{storepass}",
    ]
    if keypass:
        cmd += ["--key-pass", f"pass:{keypass}"]
    cmd += [str(apk)]
    run(cmd)
    run([apksigner, "verify", "--verbose", str(apk)])


def repack_xapk(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())


def patch_xapk(
    source: Path,
    output: Path,
    keystore: Path | None = None,
    alias: str | None = None,
    storepass: str | None = None,
    keypass: str | None = None,
) -> dict:
    apktool = require_tool("apktool")
    project_dir = Path(__file__).resolve().parent
    config = json.loads(
        (project_dir / "config" / "project009.json").read_text(encoding="utf-8")
    )
    app_name = config["patching"]["android_app_label"]

    with tempfile.TemporaryDirectory(prefix="project009-") as tmp_raw:
        tmp = Path(tmp_raw)
        xapk_root = tmp / "xapk"
        decoded = tmp / "decoded"
        xapk_root.mkdir()

        with zipfile.ZipFile(source, "r") as zf:
            zf.extractall(xapk_root)

        base_apk = choose_base_apk(xapk_root)
        original_apk_name = base_apk.name
        print(f"[INFO] Base APK: {base_apk.relative_to(xapk_root)}")

        run([apktool, "d", "-f", "-o", str(decoded), str(base_apk)])

        changed_strings = patch_app_name(decoded, app_name)
        add_manifest_metadata(decoded)
        injected_assets = inject_project_assets(decoded, project_dir)

        unsigned = tmp / "project009-unsigned.apk"
        run([apktool, "b", str(decoded), "-o", str(unsigned)])

        final_apk = tmp / original_apk_name
        shutil.copy2(unsigned, final_apk)

        signed = False
        if keystore:
            if not alias or not storepass:
                raise RuntimeError("--alias and --storepass are required with --keystore")
            sign_apk(final_apk, keystore, alias, storepass, keypass)
            signed = True
        else:
            print(
                "[WARN] APK is rebuilt but unsigned. Android will not install it until it is signed."
            )

        shutil.copy2(final_apk, base_apk)
        repack_xapk(xapk_root, output)

        report = {
            "project": "Project 009",
            "brand": "Almas Official",
            "input": str(source),
            "output": str(output),
            "base_apk": str(base_apk.relative_to(xapk_root)),
            "app_label": app_name,
            "signed": signed,
            "changed_resources": changed_strings,
            "injected_assets": injected_assets,
        }

    report_path = output.with_suffix(output.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Project 009 / Almas Official XAPK patcher")
    parser.add_argument("source", type=Path, help="Input XAPK")
    parser.add_argument("--output", type=Path, default=Path("Project009-AlmasOfficial.xapk"))
    parser.add_argument("--keystore", type=Path)
    parser.add_argument("--alias")
    parser.add_argument("--storepass", default=os.getenv("PROJECT009_STOREPASS"))
    parser.add_argument("--keypass", default=os.getenv("PROJECT009_KEYPASS"))
    args = parser.parse_args()

    report = patch_xapk(
        source=args.source,
        output=args.output,
        keystore=args.keystore,
        alias=args.alias,
        storepass=args.storepass,
        keypass=args.keypass,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
