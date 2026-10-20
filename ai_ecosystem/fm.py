"""Minimal, dependency-free YAML-subset frontmatter parser/dumper.

Supports what core/ files use: scalars (plain, quoted, bool, int, null), inline lists [a, b],
block lists (- item), lists of maps (- key: v / continuation keys), nested maps (indent), and
block scalars (| and >). Uses PyYAML instead when it is installed, for full YAML.
"""
import json
import re

try:  # pragma: no cover - optional
    import yaml as _yaml
except Exception:  # noqa: BLE001
    _yaml = None

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


class FrontmatterError(ValueError):
    pass


def split(text):
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def scalar(v):
    v = v.strip()
    if v == "":
        return None
    if (v[0] == v[-1]) and v[0] in "\"'" and len(v) >= 2:
        if v[0] == '"':
            try:
                return json.loads(v)
            except ValueError:
                return v[1:-1]
        return v[1:-1].replace("''", "'")
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [scalar(x) for x in _split_commas(inner)] if inner else []
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        out = {}
        for part in _split_commas(inner):
            k, _, val = part.partition(":")
            out[k.strip().strip("\"'")] = scalar(val)
        return out
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    # strip trailing comment on plain scalars
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return v


def _split_commas(s):
    parts, depth, cur, q = [], 0, "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def parse_yaml(src):
    if _yaml is not None:
        try:
            d = _yaml.safe_load(src)
            return d or {}
        except Exception as e:  # noqa: BLE001
            raise FrontmatterError(str(e))
    lines = [l.rstrip("\n") for l in src.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if any("\t" in l[: _indent(l) + 1] for l in lines):
        raise FrontmatterError("tabs are not allowed for indentation")
    val, i = _block(lines, 0, 0)
    if i != len(lines):
        raise FrontmatterError(f"could not parse line: {lines[i]!r}")
    return val if isinstance(val, dict) else {}


def _block(lines, i, ind):
    if i < len(lines) and lines[i].lstrip().startswith("- ") or (i < len(lines) and lines[i].strip() == "-"):
        return _list(lines, i, _indent(lines[i]))
    return _map(lines, i, ind)


def _map(lines, i, ind):
    out = {}
    while i < len(lines):
        line = lines[i]
        cur = _indent(line)
        if cur < ind:
            break
        if cur > ind:
            raise FrontmatterError(f"unexpected indentation: {line!r}")
        s = line.strip()
        if s.startswith("- "):
            break
        if ":" not in s:
            raise FrontmatterError(f"expected 'key: value': {line!r}")
        k, _, v = s.partition(":")
        k = k.strip().strip("\"'")
        v = v.strip()
        i += 1
        if v in ("|", ">", "|-", ">-"):
            buf = []
            while i < len(lines) and _indent(lines[i]) > cur:
                buf.append(lines[i].strip())
                i += 1
            out[k] = ("\n" if v.startswith("|") else " ").join(buf)
        elif v == "":
            if i < len(lines) and _indent(lines[i]) > cur:
                out[k], i = _block(lines, i, _indent(lines[i]))
            elif i < len(lines) and _indent(lines[i]) == cur and lines[i].strip().startswith("- "):
                out[k], i = _list(lines, i, cur)
            else:
                out[k] = None
        else:
            out[k] = scalar(v)
    return out, i


def _list(lines, i, ind):
    out = []
    while i < len(lines) and _indent(lines[i]) == ind and lines[i].strip().startswith("-"):
        s = lines[i].strip()[1:].strip()
        i += 1
        if re.match(r"^[\w\-\"']+\s*:(\s|$)", s) and not s.startswith(("{", "[")):
            # list of maps: re-indent first pair and following deeper lines
            child = [" " * (ind + 2) + s]
            while i < len(lines) and _indent(lines[i]) > ind:
                child.append(lines[i])
                i += 1
            val, _ = _map(child, 0, ind + 2)
            out.append(val)
        elif s == "":
            val, i = _block(lines, i, _indent(lines[i]))
            out.append(val)
        else:
            out.append(scalar(s))
    return out, i


def parse(text):
    """Return (meta: dict, body: str). Files without frontmatter return ({}, text)."""
    raw, body = split(text)
    if raw is None:
        return {}, text
    return parse_yaml(raw), body.lstrip("\n")


def _q(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, int):
        return str(v)
    s = str(v)
    if s == "" or re.search(r"[:#\[\]{},&*!|>'\"%@`]|^\s|\s$|^-", s) or s.lower() in ("true", "false", "yes", "no", "null"):
        return json.dumps(s)
    return s


def dump(meta):
    """Dump a dict as YAML frontmatter text (without the --- fences)."""
    out = []

    def emit(k, v, ind):
        pad = " " * ind
        if isinstance(v, dict):
            out.append(f"{pad}{k}:")
            for kk, vv in v.items():
                emit(kk, vv, ind + 2)
        elif isinstance(v, list):
            if all(not isinstance(x, (dict, list)) for x in v):
                out.append(f"{pad}{k}: [{', '.join(_q(x) for x in v)}]")
            else:
                out.append(f"{pad}{k}:")
                for item in v:
                    if isinstance(item, dict):
                        first = True
                        for kk, vv in item.items():
                            prefix = f"{pad}  - " if first else f"{pad}    "
                            if isinstance(vv, list):
                                out.append(f"{prefix}{kk}: [{', '.join(_q(x) for x in vv)}]")
                            else:
                                out.append(f"{prefix}{kk}: {_q(vv)}")
                            first = False
                    else:
                        out.append(f"{pad}  - {_q(item)}")
        elif isinstance(v, str) and "\n" in v:
            out.append(f"{pad}{k}: |")
            out.extend(f"{pad}  {ln}" for ln in v.split("\n"))
        else:
            out.append(f"{pad}{k}: {_q(v)}")

    for k, v in meta.items():
        if v is None:
            continue
        emit(k, v, 0)
    return "\n".join(out)


def render(meta, body):
    return "---\n" + dump(meta) + "\n---\n\n" + body.lstrip("\n")
