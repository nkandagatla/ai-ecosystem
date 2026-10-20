"""Safe file writer: tracks every file, managed block, JSON key and directory it creates
so uninstall/update touch only what ai-ecosystem added."""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

MARKERS = {
    "md": ("<!-- ai-ecosystem:begin -->", "<!-- ai-ecosystem:end -->"),
    "toml": ("# ai-ecosystem:begin (managed; edits inside are overwritten)", "# ai-ecosystem:end"),
}
GUARD_MARK = "ai-ecosystem-guard"


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def strip_block(text, kind="md"):
    b, e = MARKERS[kind]
    return re.sub(r"\n*" + re.escape(b) + r".*?" + re.escape(e) + r"\n?", "\n", text, flags=re.S).strip("\n")


def warn(msg):
    print(f"  note: {msg}", file=sys.stderr)


class Out:
    def __init__(self, root, dry=False, prev=None, force=False):
        self.root = Path(root)
        self.dry, self.force = dry, force
        self.prev = prev or {}
        self.files = {}      # rel -> sha256 of what we wrote
        self.blocks = {}     # rel -> marker kind
        self.json = {}       # rel -> {"created": bool, "keys": [[...]], "arrays": [[...]]}
        self.dirs = []       # rel dirs we created
        self.kept = []       # user-modified files we refused to overwrite
        self.planned = []

    # -- helpers -------------------------------------------------------------
    def _mkparents(self, rel):
        parts = Path(rel).parts[:-1]
        for i in range(1, len(parts) + 1):
            d = Path(*parts[:i])
            if not (self.root / d).exists():
                if str(d) not in self.dirs:
                    self.dirs.append(str(d))
                if not self.dry:
                    (self.root / d).mkdir()

    def _was_ours(self, rel):
        return rel in self.prev.get("files", {})

    def _writable(self, rel, new_hash):
        p = self.root / rel
        if not p.exists() or self.force:
            return True
        cur = sha(p.read_bytes())
        if cur == new_hash:
            return True
        old = self.prev.get("files", {}).get(rel)
        if old is not None and cur == old:
            return True  # ours and unmodified
        if old is None:
            warn(f"{rel} exists and was not created by ai-ecosystem; kept (use --force to overwrite)")
        else:
            warn(f"{rel} was modified locally; kept (use --force to overwrite)")
        self.kept.append(rel)
        return False

    # -- writers -------------------------------------------------------------
    def write(self, rel, text, mode=None):
        data = text.encode() if isinstance(text, str) else text
        h = sha(data)
        self.planned.append(rel)
        if not self._writable(rel, h):
            if self._was_ours(rel):
                self.files[rel] = self.prev["files"][rel]  # keep tracking it
            return
        self.files[rel] = h
        if self.dry:
            return
        self._mkparents(rel)
        p = self.root / rel
        p.write_bytes(data)
        if mode:
            p.chmod(mode)

    def copytree(self, rel, src, skip=()):
        src = Path(src)
        for f in sorted(src.rglob("*")):
            if f.is_file() and f.name not in skip and "__pycache__" not in f.parts:
                self.write(f"{rel}/{f.relative_to(src).as_posix()}", f.read_bytes(), mode=f.stat().st_mode & 0o777)

    def block(self, rel, text, kind="md"):
        """Insert/replace a managed block, preserving everything else in the file."""
        self.planned.append(rel)
        self.blocks[rel] = kind
        if self.dry:
            return
        self._mkparents(rel)
        p = self.root / rel
        cur = strip_block(p.read_text(), kind) if p.exists() else ""
        b, e = MARKERS[kind]
        p.write_text((cur + "\n\n" if cur.strip() else "") + f"{b}\n{text.rstrip()}\n{e}\n")

    def merge_json(self, rel, path, entries, defaults=None):
        """Add entries (dict) under the key path, never overwriting keys the user already has."""
        p = self.root / rel
        self.planned.append(rel)
        rec = self.json.setdefault(rel, {"created": None, "keys": [], "arrays": [], "defaults": []})
        data = self._load_json(p, rec)
        if data is None:
            return
        for k, v in (defaults or {}).items():
            if k not in data:
                data[k] = v
                rec["defaults"].append(k)
        node = data
        for k in path:
            node = node.setdefault(k, {})
        ours = {tuple(x) for x in self.prev.get("json", {}).get(rel, {}).get("keys", [])}
        for k, v in entries.items():
            if k in node and tuple(path + [k]) not in ours and node[k] != v:
                warn(f"{rel}: '{'.'.join(path + [k])}' already defined by you; kept")
                continue
            node[k] = v
            rec["keys"].append(path + [k])
        self._save_json(p, rel, data)

    def append_json(self, rel, path, item, defaults=None):
        """Append item to an array at path, replacing an earlier ai-ecosystem item (GUARD_MARK)."""
        p = self.root / rel
        self.planned.append(rel)
        rec = self.json.setdefault(rel, {"created": None, "keys": [], "arrays": [], "defaults": []})
        data = self._load_json(p, rec)
        if data is None:
            return
        for k, v in (defaults or {}).items():
            if k not in data:
                data[k] = v
                rec["defaults"].append(k)
        node = data
        for k in path[:-1]:
            node = node.setdefault(k, {})
        arr = [x for x in node.get(path[-1], []) if GUARD_MARK not in json.dumps(x)]
        arr.append(item)
        node[path[-1]] = arr
        rec["arrays"].append(path)
        self._save_json(p, rel, data)

    def _load_json(self, p, rec):
        prev_rec = self.prev.get("json", {}).get(str(p.relative_to(self.root)), {})
        if rec["created"] is None:
            rec["created"] = prev_rec.get("created", not p.exists())
            rec["defaults"] = list(prev_rec.get("defaults", []))
        if self.dry and not p.exists():
            return {}
        if not p.exists():
            return {}
        try:
            d = json.loads(p.read_text() or "{}")
        except ValueError as e:
            warn(f"{p}: invalid JSON ({e}); not modified")
            return None
        if not isinstance(d, dict):
            warn(f"{p}: top-level JSON is not an object; not modified")
            return None
        return d

    def _save_json(self, p, rel, data):
        if self.dry:
            return
        self._mkparents(rel)
        p.write_text(json.dumps(data, indent=2) + "\n")

    def manifest(self, **meta):
        return dict(meta, files=self.files, blocks=self.blocks,
                    json={k: v for k, v in self.json.items()},
                    dirs=sorted(set(self.dirs) | set(self.prev.get("dirs", [])), key=lambda d: (-len(Path(d).parts), d)))


def remove_json(root, rel, rec, force=False):
    p = Path(root) / rel
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text() or "{}")
    except ValueError:
        warn(f"{rel}: invalid JSON; left untouched")
        return
    for path in rec.get("keys", []):
        node, ok = data, True
        for k in path[:-1]:
            if not isinstance(node, dict) or k not in node:
                ok = False
                break
            node = node[k]
        if ok and isinstance(node, dict):
            node.pop(path[-1], None)
    for path in rec.get("arrays", []):
        node = data
        for k in path[:-1]:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        if isinstance(node, dict) and isinstance(node.get(path[-1]), list):
            node[path[-1]] = [x for x in node[path[-1]] if GUARD_MARK not in json.dumps(x)]
    # prune containers that became empty along recorded paths
    for path in rec.get("keys", []) + rec.get("arrays", []):
        for depth in range(len(path), 0, -1):
            node = data
            for k in path[:depth - 1]:
                node = node.get(k, {}) if isinstance(node, dict) else {}
            key = path[depth - 1]
            if isinstance(node, dict) and node.get(key, None) in ({}, []):
                node.pop(key)
    if data and all(k in rec.get("defaults", []) for k in data):
        data = {}
    if rec.get("created") and not data:
        p.unlink()
    else:
        p.write_text(json.dumps(data, indent=2) + "\n")


def remove_paths(root, files, blocks, jsons, dirs, keep_modified=True, only=None):
    """Remove tracked artifacts. Returns list of kept (user-modified) files."""
    root = Path(root)
    kept = []
    for rel, h in files.items():
        if only is not None and rel not in only:
            continue
        p = root / rel
        if not p.exists():
            continue
        if keep_modified and sha(p.read_bytes()) != h:
            warn(f"{rel} was modified locally; kept")
            kept.append(rel)
            continue
        p.unlink()
    for rel, kind in blocks.items():
        if only is not None and rel not in only:
            continue
        p = root / rel
        if p.exists():
            t = strip_block(p.read_text(), kind)
            p.unlink() if not t.strip() else p.write_text(t + "\n")
    for rel, rec in jsons.items():
        if only is not None and rel not in only:
            continue
        remove_json(root, rel, rec)
    for d in sorted(dirs, key=lambda d: -len(Path(d).parts)):
        p = root / d
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            pass
    return kept
