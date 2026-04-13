#!/usr/bin/env python3
"""OmniPublish - 图片批量重命名"""

import argparse, os, sys

def rename_images(folder, prefix="image", start=1, digits=2, separator="_", dry_run=False):
    """Batch rename images in folder with sequential numbering."""
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
    files = sorted([
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in exts and not f.startswith(".")
        and "_cover" not in f.lower()
    ])

    if not files:
        print("[ERROR] No image files found in folder")
        return

    renames = []
    for i, fname in enumerate(files):
        ext = os.path.splitext(fname)[1]
        num = str(start + i).zfill(digits)
        new_name = f"{prefix}{separator}{num}{ext}"
        renames.append((fname, new_name))

    # Check for conflicts
    existing = set(os.listdir(folder))
    new_names = {r[1] for r in renames}
    old_names = {r[0] for r in renames}
    conflicts = (new_names & existing) - old_names
    if conflicts:
        print(f"[WARN]  Naming conflicts detected: {conflicts}")
        print("[WARN]  Using temp names to avoid conflicts")

    if dry_run:
        print(f"[DRY]   Preview ({len(renames)} files):")
        for old, new in renames:
            print(f"        {old} → {new}")
        return

    # Rename via temp names to avoid conflicts
    temp_renames = []
    for old, new in renames:
        temp = f"__omnipub_temp_{old}"
        src = os.path.join(folder, old)
        tmp = os.path.join(folder, temp)
        os.rename(src, tmp)
        temp_renames.append((temp, new))

    count = 0
    for temp, new in temp_renames:
        src = os.path.join(folder, temp)
        dst = os.path.join(folder, new)
        os.rename(src, dst)
        count += 1

    # Print results
    for old, new in renames:
        print(f"[RENAME] {old} → {new}")
    print(f"\n[OK]    Renamed: {count} files")

def main():
    parser = argparse.ArgumentParser(description="OmniPublish Image Renamer")
    parser.add_argument("--folder", required=True, help="Image folder path")
    parser.add_argument("--prefix", default="image", help="Filename prefix")
    parser.add_argument("--start", type=int, default=1, help="Start number")
    parser.add_argument("--digits", type=int, default=2, help="Number padding digits")
    parser.add_argument("--separator", default="_", help="Separator between prefix and number")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't rename")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"[ERROR] Not a directory: {args.folder}")
        sys.exit(1)

    rename_images(args.folder, args.prefix, args.start, args.digits, args.separator, args.dry_run)

if __name__ == "__main__":
    main()
