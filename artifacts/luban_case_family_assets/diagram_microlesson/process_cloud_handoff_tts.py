#!/usr/bin/env python3
"""Build synced per-beat TTS for Claude Design DC handoff zip bundles."""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request, uuid, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
FINISHED = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/finished"
ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
MODEL, SR, RATE, VOLUME, GAP, BUFFER = "cosyvoice-v3-flash", 24000, 0.95, 65, 0.4, 0.5
TEACHER, STUDENT = "longanhuan_v3", "longlaotie_v3"
REUSE_LIBRARY = None

def fail(message):
    raise RuntimeError(message)

def decode_name(name):
    for encoding in ("gbk", "utf-8"):
        try: return name.encode("cp437").decode(encoding)
        except (UnicodeEncodeError, UnicodeDecodeError): pass
    return name

def key_from_env():
    env = ROOT / ".env"
    if env.exists():
        for raw in env.read_text("utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_DASHSCOPE_API_KEY")
    if not key: fail("missing DASHSCOPE_API_KEY or ALIYUN_DASHSCOPE_API_KEY")
    return key

def extract_zip(source, destination):
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            if item.is_dir(): continue
            rel = PurePosixPath(decode_name(item.filename))
            if rel.is_absolute() or not rel.parts or any(p in ("", ".", "..") for p in rel.parts):
                fail(f"unsafe zip member: {item.filename!r}")
            out = destination.joinpath(*rel.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(item))

def dc_data(page):
    parser = r'''
const fs=require("fs"),vm=require("vm"),source=fs.readFileSync(process.argv[1],"utf8");
function get(name){const m=new RegExp("\\b"+name+"\\s*=\\s*\\[").exec(source);if(!m)throw Error("missing "+name);
 const start=source.indexOf("[",m.index);let depth=0,q="",esc=false;
 for(let i=start;i<source.length;i++){const c=source[i];if(q){if(esc)esc=false;else if(c==="\\")esc=true;else if(c===q)q="";continue}
  if(c==="'"||c==='"'||c===String.fromCharCode(96)){q=c;continue}if(c==="[")depth++;else if(c==="]"){depth--;if(!depth)return source.slice(start,i+1)}}throw Error("unclosed "+name)}
const read=n=>vm.runInNewContext("("+get(n)+")",Object.create(null),{timeout:1000});
const endNarr=(()=>{const m=/\bendNarr\s*=\s*([^;]+);/.exec(source);return m?vm.runInNewContext("("+m[1]+")",Object.create(null),{timeout:1000}):null})();
console.log(JSON.stringify({beats:read("beats"),narr:read("narr"),qa:read("qa"),endNarr}));
'''
    result = subprocess.run(["node", "-e", parser, str(page)], check=True, text=True, capture_output=True)
    data = json.loads(result.stdout)
    if not all(isinstance(data.get(name), list) for name in ("beats", "narr", "qa")):
        fail(f"invalid DC arrays: {page.name}")
    return data

def norm(text):
    return (str(text or "").replace("A、B", "A 和 B").replace("C、D", "C 和 D").replace("/", "、")
            .replace("（", "，").replace("）", "，").replace("(", "，").replace(")", "，")
            .replace("【", "").replace("】", ""))

def duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], text=True).strip())

def transcode(source, output):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ar", str(SR), "-ac", "1", "-b:a", "96k", str(output)], check=True)

def create_silence(output):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", str(GAP), "-ar", str(SR), "-ac", "1", "-b:a", "96k", str(output)], check=True)

def concat(parts, output, work):
    listing = work / f"concat-{uuid.uuid4().hex}.txt"
    listing.write_text("\n".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'" for p in parts), "utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-ar", str(SR), "-ac", "1", "-b:a", "96k", str(output)], check=True)

def synthesize(text, voice, output, key):
    payload = json.dumps({"model": MODEL, "input": {"text": norm(text), "voice": voice, "format": "mp3", "sample_rate": SR, "rate": RATE, "volume": VOLUME, "language_hints": ["zh"]}}, ensure_ascii=False).encode()
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(ENDPOINT, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=90) as response:
                url = json.loads(response.read().decode()).get("output", {}).get("audio", {}).get("url")
            if not url: fail("Aliyun response missing output.audio.url")
            raw = output.with_suffix(".raw.mp3")
            with urllib.request.urlopen(url, timeout=90) as response: raw.write_bytes(response.read())
            transcode(raw, output)
            raw.unlink(missing_ok=True)
            return
        except Exception as exc:
            last = exc
            time.sleep(2 ** attempt)
    fail(f"Aliyun TTS failed after retries: {last}")

def find_pages(extracted):
    files = [p for p in extracted.rglob("*.dc.html") if not ({"finished", "templates"} & set(p.relative_to(extracted).parts)) and "模板" not in p.name]
    def dedupe(pages):
        selected = {}
        for page in pages:
            key = page.name
            if key not in selected or len(page.relative_to(extracted).parts) < len(selected[key].relative_to(extracted).parts): selected[key] = page
        return list(selected.values())
    teaches = dedupe([p for p in files if "讲解" in p.name])
    practices = dedupe([p for p in files if "练习" in p.name or "随堂练" in p.name])
    if not teaches or not practices: fail(f"expected teaching pages plus practice pages; got teach={len(teaches)} practice={len(practices)}")
    ranks = {"_上": 0, "_中": 1, "_下": 2}
    teaches.sort(key=lambda p: next((v for k, v in ranks.items() if k in p.stem), 3))
    practices.sort(key=lambda p: next((v for k, v in ranks.items() if k in p.stem), 3))
    return teaches, practices

def part(page, total):
    if total == 1: return None
    for token, name in (("_上", "up"), ("_中", "middle"), ("_下", "down")):
        if token in page.stem: return name
    return "part"

def paired_practice(teach, practices, total):
    suffix = part(teach, total)
    matches = [page for page in practices if part(page, total) == suffix]
    if len(matches) == 1: return matches[0]
    if total == 1 and len(practices) == 1: return practices[0]
    fail(f"cannot uniquely pair practice page for {teach.name}")

def copy_assets(extracted, stage):
    roots = [extracted] if (extracted / "support.js").is_file() else [p.parent for p in extracted.rglob("support.js")]
    if len(roots) != 1: fail("handoff zip lacks a unique support.js")
    asset_root = roots[0]
    for item in asset_root.rglob("*"):
        if item.is_file() and not item.name.endswith(".dc.html") and "__MACOSX" not in item.parts:
            out = stage / item.relative_to(asset_root)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, out)
    if not (stage / "support.js").is_file(): fail("handoff zip lacks support.js")

def reusable(existing):
    found = {}
    for manifest in existing.glob("audio/**/manifest.json"):
        try: data = json.loads(manifest.read_text("utf-8"))
        except (OSError, json.JSONDecodeError): continue
        for segment in data.get("segments", []):
            text, ident = segment.get("text"), segment.get("id")
            audio = manifest.parent / f"{ident}.mp3"
            if text and ident and audio.is_file(): found[text] = (audio, duration(audio))
    return found

def reusable_library(preferred):
    """Index every prior finished card, while giving the current card precedence."""
    global REUSE_LIBRARY
    if REUSE_LIBRARY is None:
        REUSE_LIBRARY = {}
        for card in FINISHED.glob("P40_*"):
            REUSE_LIBRARY.update(reusable(card))
    found = dict(REUSE_LIBRARY)
    if preferred.exists(): found.update(reusable(preferred))
    return found

def segments(data):
    output = []
    for i, beat in enumerate(data["beats"]):
        if not isinstance(beat, list) or len(beat) < 3: fail(f"invalid beat #{i}: {beat!r}")
        ident, old_duration = str(beat[0]), float(beat[2]) - float(beat[1])
        label = beat[3] if len(beat) > 3 else "讲解"
        if i < len(data["narr"]):
            output.append({"id": ident, "kind": "teach", "text": str(data["narr"][i]), "old_duration": old_duration, "label": label})
        elif i - len(data["narr"]) < len(data["qa"]):
            qa = data["qa"][i - len(data["narr"])]
            if not isinstance(qa, dict) or not qa.get("q") or not qa.get("a"): fail(f"invalid QA for {ident}")
            output.append({"id": ident, "kind": "qa", "q": str(qa["q"]), "a": str(qa["a"]), "text": f'{qa["q"]}。{qa["a"]}', "old_duration": old_duration, "label": label})
        elif i == len(data["beats"]) - 1 and data.get("endNarr"):
            output.append({"id": ident, "kind": "teach", "text": str(data["endNarr"]), "old_duration": old_duration, "label": label})
        else:
            output.append({"id": ident, "kind": "visual_only", "text": "", "old_duration": old_duration, "label": label})
    return output

def patch_page(source, beats, total, audio_base, version, links):
    for old, new in links.items(): source = source.replace(old, new)
    source, count = re.subn(r'(?m)^\s*audioBase\s*=\s*["\'][^"\']*["\'];', f'  audioBase="{audio_base}";', source, count=1)
    if count != 1: fail("audioBase not found")
    if re.search(r"(?m)^\s*audioVersion\s*=", source):
        source = re.sub(r'(?m)^\s*audioVersion\s*=\s*["\'][^"\']*["\'];', f'  audioVersion="{version}";', source, count=1)
    else:
        source = source.replace(f'  audioBase="{audio_base}";', f'  audioBase="{audio_base}";\n  audioVersion="{version}";', 1)
    source, count = re.subn(r"(?m)^\s*DUR\s*=\s*[0-9.]+\s*;", f"  DUR = {total:.3f};", source, count=1)
    if count != 1: fail("DUR not found")
    literal = json.dumps(beats, ensure_ascii=False, separators=(",", ":"))
    source, count = re.subn(r"(?s)\bbeats\s*=\s*\[.*?\];\s*\n\s*(endNarr\s*=\s*.*?;\s*\n\s*)?keycards\s*=", lambda match: f"  beats={literal};\n  {match.group(1) or ''}keycards=", source, count=1)
    if count != 1: fail("beats not found")
    source, count = re.subn(r'(<input\b[^>]*\btype="range"[^>]*\bmax=")[^"]*(")', r'\1{{ durSec }}\2', source, count=1)
    if count != 1: fail("progress range not found")
    if "durSec:this.DUR" not in source:
        source, count = re.subn(r"(DUR\s*:\s*this\.DUR)(?=\s*,)", r"\1,durSec:this.DUR", source, count=1)
        if count != 1: fail("renderVals durSec insertion failed")
    replacement = '''speakBeat(ai){ this.stopSpeak(); this._audioStarted=false; if(this.state.muted)return; if(ai==null||!this.beats[ai])return; const text=this.speechText(ai); if(!text)return; const id=this.beats[ai][0]; let used=false; try{ const a=new Audio(this.audioBase+id+".mp3?v="+this.audioVersion); a.preload="auto"; this._audio=a; a.addEventListener("error",()=>{ if(!used){used=true;this._audioStarted=false;this._audio=null;this.webSpeak(text);} }); a.addEventListener("playing",()=>{ used=true;this._audioStarted=true; }); a.addEventListener("ended",()=>{ this._audioStarted=false; }); const p=a.play(); if(p&&p.catch)p.catch(()=>{ if(!used){used=true;this._audioStarted=false;this._audio=null;this.webSpeak(text);} }); }catch(e){ this._audioStarted=false;this.webSpeak(text); } }
  setSpeechPaused(p){'''
    source, count = re.subn(r"(?s)\bspeakBeat\(ai\)\{.*?\}\s*\n\s*setSpeechPaused\(p\)\{", replacement, source, count=1)
    if count != 1: fail("speakBeat not found")
    loop = source.find("loop(ts){")
    start, end = source.find("let nt=this.state.t+dt;", loop), source.find("if(nt>=this.DUR)", loop)
    if loop < 0 or start < 0 or end < start: fail("playback clock not found")
    gate = '''let nt=this.state.t+dt; const ab=this._activeBeat; if(ab!=null&&this.beats[ab]){const curStart=this.beats[ab][1],curEnd=this.beats[ab][2]; if(this._audio&&!this._audio.ended){ if(!this._audioStarted) nt=Math.min(nt,curStart+0.04); else if(!this._audio.paused&&isFinite(this._audio.currentTime)) nt=Math.max(curStart,Math.min(curEnd-0.02,curStart+this._audio.currentTime)); } if(nt>=curEnd && this._audio && !this._audio.paused && !this._audio.ended && (!isFinite(this._audio.duration)||this._audio.currentTime<this._audio.duration-0.08)) nt=Math.min(nt,curEnd-0.02);}
      '''
    return source[:start] + gate + source[end:]

def build_page(page, stage, audio_dir, reuse, key, dry_run):
    data, work = dc_data(page), stage / f".tts-{uuid.uuid4().hex[:8]}"
    work.mkdir(); audio_dir.mkdir(parents=True, exist_ok=True)
    gap = work / "gap.mp3"
    if not dry_run: create_silence(gap)
    cursor, beats, audit = 0.0, [], []
    try:
        for segment in segments(data):
            output, reused = audio_dir / f'{segment["id"]}.mp3', False
            if segment["kind"] == "visual_only": actual = segment["old_duration"]
            elif segment["text"] in reuse:
                old, actual = reuse[segment["text"]]
                if not dry_run: shutil.copy2(old, output)
                reused = True
            elif dry_run: actual = segment["old_duration"]
            elif segment["kind"] == "teach":
                synthesize(segment["text"], TEACHER, output, key); actual = duration(output)
            else:
                q, a = work / f'{segment["id"]}-q.mp3', work / f'{segment["id"]}-a.mp3'
                synthesize(segment["q"], STUDENT, q, key); synthesize(segment["a"], TEACHER, a, key)
                concat([q, gap, a], output, work); actual = duration(output)
            window, start = actual if segment["kind"] == "visual_only" else actual + BUFFER, round(cursor, 3)
            cursor += window
            beats.append([segment["id"], start, round(cursor, 3), segment["label"]])
            audit.append({**segment, "duration": round(actual, 3), "window": round(window, 3), "reused": reused})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"beats": beats, "duration": round(cursor, 3), "segments": audit}

def preserve_legacy_artifacts(previous, stage):
    """Keep pre-existing non-player artifacts when refreshing a handoff package."""
    dynamic_roots = {"audio", "support.js", "tts-audit.json"}
    for item in previous.rglob("*"):
        if not item.is_file(): continue
        rel = item.relative_to(previous)
        if rel.parts[0] in dynamic_roots or item.name.endswith(".dc.html"): continue
        output = stage / rel
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, output)

def publish(card_id, zip_path, dry_run):
    if not re.fullmatch(r"P40_[A-Z0-9]+", card_id): fail(f"invalid card ID: {card_id}")
    if not zip_path.is_file(): fail(f"missing zip: {zip_path}")
    target, reuse, key = FINISHED / card_id, None, None
    reuse = reusable_library(target)
    if not dry_run: key = key_from_env()
    with tempfile.TemporaryDirectory(prefix=f"handoff-{card_id}-") as temporary:
        extracted = Path(temporary) / "source"; extracted.mkdir(); extract_zip(zip_path, extracted)
        teaches, practices = find_pages(extracted)
        stage = FINISHED / f".{card_id}.tts-stage-{uuid.uuid4().hex[:8]}"; stage.mkdir(parents=True)
        try:
            copy_assets(extracted, stage)
            names = {}
            for page in practices:
                suffix = part(page, len(teaches)) if len(practices) > 1 else None
                names[page] = f"{card_id}.practice{'.'+suffix if suffix else ''}.dc.html"
            for page in teaches:
                suffix = part(page, len(teaches)); names[page] = f"{card_id}.teach{'.'+suffix if suffix else ''}.dc.html"
            links, manifests, version = {p.name: name for p, name in names.items()}, [], time.strftime("%Y%m%d%H%M%S")
            for page in teaches:
                suffix = part(page, len(teaches)); audio_base = f"audio/{suffix}/" if suffix else "audio/"
                built = build_page(page, stage, stage / audio_base, reuse, key, dry_run)
                (stage / names[page]).write_text(patch_page(page.read_text("utf-8"), built["beats"], built["duration"], audio_base, version, links), "utf-8")
                (stage / audio_base / "manifest.json").write_text(json.dumps({
                    "page": names[page], "model": MODEL, "sampleRate": SR, "rate": RATE,
                    "volume": VOLUME, "teacherVoice": TEACHER, "studentVoice": STUDENT,
                    "segments": built["segments"],
                }, ensure_ascii=False, indent=2), "utf-8")
                manifests.append({"page": names[page], "audioBase": audio_base, **built})
            for practice in practices:
                practice_html = practice.read_text("utf-8")
                for old, new in links.items(): practice_html = practice_html.replace(old, new)
                (stage / names[practice]).write_text(practice_html, "utf-8")
            (stage / "tts-audit.json").write_text(json.dumps({"cardId": card_id, "zip": zip_path.name, "model": MODEL, "sampleRate": SR, "rate": RATE, "volume": VOLUME, "teacherVoice": TEACHER, "studentVoice": STUDENT, "pages": manifests}, ensure_ascii=False, indent=2), "utf-8")
            pages, beats = len(teaches), sum(len(m["segments"]) for m in manifests)
            if dry_run: print(f"DRY-RUN {card_id}: {pages} teaching page(s), {beats} beat(s)"); return
            backup = FINISHED / f".{card_id}.tts-backup-{uuid.uuid4().hex[:8]}"
            if target.exists(): target.rename(backup)
            try:
                if backup.exists(): preserve_legacy_artifacts(backup, stage)
                stage.rename(target)
            except Exception:
                if backup.exists(): backup.rename(target)
                raise
            shutil.rmtree(backup, ignore_errors=True)
            print(f"DONE {card_id}: {pages} teaching page(s), {beats} beat(s)")
        finally:
            if stage.exists(): shutil.rmtree(stage, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", action="append", required=True, metavar="CARD_ID=ZIP")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for job in args.job:
        if "=" not in job: fail(f"invalid --job: {job}")
        card_id, zip_path = job.split("=", 1)
        publish(card_id, Path(zip_path).expanduser(), args.dry_run)

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr); raise SystemExit(1)
