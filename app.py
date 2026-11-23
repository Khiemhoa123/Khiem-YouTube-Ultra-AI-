
# -*- coding: utf-8 -*-
# KHIEM YOUTUBE V8.2 SMART CONTENT MATCHING
# Main application
# Requires existing:
# capcut.py
# semantic.py
# turbo_cache.py
# smart_selector_v81.py
# smart_content_v82.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import subprocess as sp
import json
import re
import random
import hashlib
import math
import tempfile
import threading
import os
import shutil
import traceback

from turbo_cache import digest_cached, duration_cached
from smart_content_v82 import rank_adjustment

from smart_selector_v81 import (
    image_allowed as v81_image_allowed,
    remember_image as v81_remember_image,
    is_export as v81_is_export,
    save_timeline_report as v81_save_report,
)

VERSION = "KHIEM YOUTUBE V10.0 CORE"

A = {'.mp3', '.wav', '.m4a', '.flac'}
I = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
V = {
    '.mp4', '.mov', '.mkv', '.webm',
    '.avi', '.m4v', '.mts', '.mpeg', '.mpg'
}


def run(args):
    p = sp.run(
        args,
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        creationflags=getattr(sp, 'CREATE_NO_WINDOW', 0)
    )
    if p.returncode:
        raise RuntimeError(
            p.stderr.decode(errors='replace')[-2500:]
        )
    return p.stdout


def duration(p):
    return float(run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1',
        str(p)
    ]))


def number(p):
    m = re.match(r'^(\d+)', p.name)
    return int(m[1]) if m else None


def indexed(root, ext):
    d = {}
    for p in sorted(Path(root).iterdir()):
        if p.is_file() and p.suffix.lower() in ext:
            n = number(p)
            if n is None or n in d:
                raise ValueError(
                    'Tên thiếu hoặc trùng số thứ tự: ' + str(p)
                )
            d[n] = p
    return d


def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def words(s):
    return set(re.findall(r'\w{3,}', s.lower()))


def times(s, mode):
    a = [
        float(x)
        for x in re.split(r'[,;\s]+', s.strip())
        if x
    ]
    if (
        not a
        or any(not math.isfinite(x) or x <= 0 for x in a)
        or (mode == 'Cố định' and len(a) != 1)
    ):
        raise ValueError('Thời lượng không hợp lệ')
    return a


# ============================================================
# V8.2 SMART CONTENT MATCHING
# ============================================================

def content_adjustment(src, query, script, log):
    try:
        return float(rank_adjustment(
            source=src,
            query=query,
            script=script
        ))
    except Exception as e:
        log('V8.2 chấm điểm lỗi: ' + str(e))
        return 0.0


# ============================================================
# TIMELINE PLANNER
# ============================================================

def plan(c, log):
    shared = None
    if c.get('project_folder'):
        from auto_project_v11 import discover
        shared = discover(c['project_folder'], c.get('interview_file'))
        voices, scripts = shared['voice'], shared['txt']
        log('AUTO PROJECT: %d voice, %d TXT, %d ảnh, %d video; không sao chép file.' %
            (len(voices), len(scripts), len(shared['images']), len(shared['videos'])))
    else:
        voices = indexed(c['voice'], A)
        scripts = indexed(c['txt'], {'.txt'})
    from smart_script_first_v12 import prepare as prepare_story, score_media, query_at
    story = prepare_story(scripts, log)
    fps = int(c['fps'])

    # Stable selection for identical inputs, useful for repeatable CapCut edits.
    import hashlib
    seed = hashlib.sha256(json.dumps({
        "name": c.get("name", ""),
        "voices": [(n, str(p), p.stat().st_size, p.stat().st_mtime_ns)
                   for n, p in sorted(voices.items())],
        "speed": c.get("speed", "Smart"),
        "video_goal": c.get("target_video_percent", 60),
        "min_video": c.get("min_video_percent", 30),
        "planner_revision": "scan_all_balance_20261123"
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(seed[:8], "big"))
    used = set()
    used_images = []
    intervals = {}
    video_source_use = {}
    hashes = {}
    lens = {}
    label_cache = {}
    parts = []

    elapsed = 0.0
    frames = 0

    ai = None

    if c.get('ai'):
        from semantic import Semantic
        try:
            ai = Semantic(log, c.get('speed', 'Smart'))
        except Exception as e:
            log(
                'CẢNH BÁO: CLIP không chạy, '
                'dùng tên file và TXT: ' + str(e)
            )

    if not voices:
        raise ValueError('Không có voice')

    if set(voices) != set(scripts):
        raise ValueError(
            'Số thứ tự voice và TXT không khớp'
        )

    counts = [int(c['vn']), int(c['an'])]
    pattern = (
        ['video'] * counts[0]
        + ['image'] * counts[1]
    )

    if min(counts) < 0 or not pattern:
        raise ValueError('Số cảnh không hợp lệ')

    ts = {
        k: times(c[k + 'time'], c[k + 'mode'])
        for k in ['video', 'image']
    }

    for n, p in sorted(voices.items()):
        dur = duration_cached(p)

        script = story["sections"][n]["text"]
        tokens = script.split()

        pools = {}

        for kind, ext, root in [
            ('image', I, c['images']),
            ('video', V, c['videos'])
        ]:
            # Strict section ownership: only numbered top-level folders.
            base = Path(root).resolve()
            folders = sorted(
                x for x in base.iterdir()
                if x.is_dir() and number(x) == n
                and x.resolve().parent == base
            )
            if len(folders) > 1:
                raise ValueError(f'Phần {n}: nhiều thư mục trùng số trong {base}.')
            allowed = set(shared[kind + 's']) if shared is not None else None

            pools[kind] = []

            for folder in folders:
                for src in sorted(folder.rglob('*')):
                    if not src.resolve().is_relative_to(folder.resolve()):
                        continue
                    if allowed is not None and src not in allowed:
                        continue
                    if (
                        not src.is_file()
                        or src.suffix.lower() not in ext
                    ):
                        continue

                    try:
                        h = hashes.setdefault(
                            src, digest_cached(src)
                        )

                        if kind == 'video':
                            if h not in lens:
                                lens[h] = duration_cached(src)

                            if (
                                not math.isfinite(lens[h])
                                or lens[h] <= 0
                            ):
                                raise ValueError(
                                    'Thời lượng không hợp lệ'
                                )

                            # Preserve V8.1 working behavior.
                            # Do not discard source videos here.
                            if v81_is_export(src, c):
                                log(
                                    'V10: Bỏ video đã xuất: '
                                    + str(src)
                                )
                                continue

                        pools[kind].append(src)

                    except Exception as e:
                        log(f'Bỏ qua {src}: {e}')

            log(
                f'Phần {n} | {kind}: '
                f'{len(pools[kind])} file | folder: '
                + (
                    ', '.join(map(str, folders))
                    or 'KHÔNG TÌM THẤY'
                )
            )

            if kind == 'video':
                total_video = sum(
                    lens[h]
                    for h in {
                        hashes[x] for x in pools[kind]
                    }
                )
                log(
                    f'Tổng video nguồn: '
                    f'{total_video:.2f}s'
                )

        if not pools['image'] and not pools['video']:
            raise ValueError(f'FOLDER LOCK: Phần {n} không có tư liệu trong thư mục riêng. Không lấy chéo.')
        log(f'FOLDER LOCK: Phần {n} chỉ sử dụng tư liệu trong thư mục cùng số.')

        aligned = []

        if c.get('align') and ai:
            log(f'Whisper: phần {n}')
            try:
                aligned = ai.transcribe(p)
            except Exception as e:
                log(
                    'Whisper lỗi, dùng TXT ước tính: '
                    + str(e)
                )

        elapsed += dur
        end = math.ceil(elapsed * fps)
        target = end - frames
        pos = 0
        clips = []

        def pick(kind, nf, context, query):
            t = nf / fps
            candidates = []

            for src in pools[kind]:
                h = hashes[src]
                start = 0.0
                gap = 0.0

                if kind == 'image':
                    if h in used:
                        continue

                    if not v81_image_allowed(
                        src, used_images
                    ):
                        continue

                else:
                    bounds = sorted(
                        intervals.get(h, [])
                    )
                    gaps = []
                    cur = 0.0

                    for l, r in bounds + [
                        (lens[h], lens[h])
                    ]:
                        if l - cur + 1e-9 >= t:
                            gaps.append((
                                cur,
                                max(cur, l - t)
                            ))
                        cur = max(cur, r)

                    if not gaps:
                        continue

                    l, r = max(
                        gaps,
                        key=lambda g: g[1] - g[0]
                    )

                    gap = r - l
                    start = rng.choice([l, r])

                # Read filename/sidecar once, not on every candidate scoring.
                if src not in label_cache:
                    label = src.stem
                    side = src.with_suffix(src.suffix + '.txt')
                    if side.exists():
                        try:
                            label += ' ' + side.read_text(
                                encoding='utf-8-sig', errors='replace'
                            )
                        except OSError:
                            pass
                    label_cache[src] = words(label)
                score = len(context & label_cache[src])
                # Script-first ranking: prefer the actual narrated topic and named person.
                score += score_media(query, src, story, n, src.stem.replace('_', ' ').replace('-', ' '))

                # Existing CLIP scoring
                if ai:
                    if kind == 'image':
                        starts = [start]
                    else:
                        starts = sorted(set(
                            round(x, 6)
                            for x in (
                                l,
                                (l + r) / 2,
                                r
                            )
                        ))

                    try:
                        best = max(
                            (
                                ai.score(
                                    kind,
                                    src,
                                    x,
                                    t,
                                    query
                                ),
                                x
                            )
                            for x in starts
                        )

                        if best[0] <= -1:
                            log(
                                'V10: Bỏ tư liệu AI không đọc được: '
                                + str(src)
                            )
                            continue

                        score = (
                            score * 0.12
                            + best[0]
                        )
                        start = best[1]

                    except Exception as e:
                        log(
                            'CLIP chấm điểm lỗi, '
                            'dùng tên file: '
                            + str(e)
                        )

                # V8.2 context-aware scoring
                adjustment = content_adjustment(
                    src,
                    query,
                    script,
                    log
                )

                score += adjustment

                if kind == 'video':
                    if (
                        not math.isfinite(start)
                        or start < 0
                        or start + t > lens[h] + 0.001
                    ):
                        continue

                    overlap = any(
                        start < right - 0.001
                        and start + t > left + 0.001
                        for left, right in intervals.get(h, [])
                    )

                    if overlap:
                        continue

                if kind == 'video':
                    # Every usable downloaded source gets a fair chance before
                    # returning to a source already represented on the timeline.
                    score += 2.5 if video_source_use.get(h, 0) == 0 else 0.0
                    score -= min(1.0, video_source_use.get(h, 0) * 0.15)
                candidates.append((
                    score,
                    gap,
                    rng.random(),
                    src,
                    h,
                    start
                ))

            return (
                max(candidates)
                if candidates
                else None
            )

        smart_timeline = str(c.get('smart_timeline', '1')).lower() not in ('0', 'false', 'off')
        min_video = max(0.30, min(1.0, float(c.get('min_video_percent', 30)) / 100))
        goal_video = max(min_video, min(1.0, float(c.get('target_video_percent', 60)) / 100))
        video_frames = 0
        warned_shortage = False
        image_streak = 0
        ts['video'] = [5, 6, 7, 8]
        ts['image'] = [4, 5, 6]

        while pos < target:
            preferred = pattern[len(clips) % len(pattern)]
            selected = None
            options = []
            kinds = ('video', 'image') if smart_timeline else (
                preferred, 'image' if preferred == 'video' else 'video'
            )
            for kind in kinds:
                nf = min(
                    target - pos,
                    max(
                        1,
                        round(
                            rng.choice(ts[kind])
                            * fps
                        )
                    )
                )

                mid = int(
                    len(tokens)
                    * (pos + nf / 2)
                    / max(target, 1)
                )

                query = query_at(story["sections"][n], (pos + nf / 2) / max(target, 1))

                spoken = ' '.join(
                    w for a, b, w in aligned
                    if (
                        b >= pos / fps
                        and a <= (pos + nf) / fps
                    )
                )

                # Prefer the real spoken words when alignment is available.
                # Add a small amount of script context for entity matching.
                query = (spoken + ' ' + query[:180]).strip() if spoken else query

                context = (
                    words(query)
                    | words(re.sub(
                        r'^\d+\s*[- ]*|number\s+\d+',
                        '',
                        scripts[n].stem,
                        flags=re.I
                    ))
                )

                candidate = pick(kind, nf, context, query)
                if kind == 'video' and not candidate:
                    for seconds in (7, 6, 5):
                        smaller = min(target - pos, seconds * fps)
                        if smaller >= nf: continue
                        candidate = pick(kind, smaller, context, query)
                        if candidate:
                            nf = smaller
                            break
                if candidate:
                    options.append((kind, nf, candidate))
                    if not smart_timeline:
                        break

            if smart_timeline and options:
                def option_score(option):
                    kind_, nf_, item_ = option
                    base = item_[0]
                    if kind_ != 'video':
                        return base
                    current = video_frames / max(1, pos)
                    projected = (video_frames + nf_) / max(1, pos + nf_)
                    if projected < min_video:
                        return base + 0.65
                    if current < goal_video:
                        return base + 0.28
                    return base

                videos = [o for o in options if o[0] == 'video']
                need_video = video_frames < min_video * (pos + max(o[1] for o in options))
                best_image = max((o for o in options if o[0] == 'image'),
                                 key=option_score, default=None)
                best_video = max(videos, key=option_score, default=None)
                # Video sources have already been filtered by the creator.
                # Use all valid footage, even when semantic matching is weak.
                # Reserve enough timeline to reach the minimum when possible.
                remaining = target - pos
                required = max(0, math.ceil(min_video * target) - video_frames)
                last_is_video = bool(clips and clips[-1]['type'] == 'video')
                urgent = required >= remaining - 2 * fps
                if best_video and (urgent or (not last_is_video and
                        (required > 0 or image_streak >= 3 or video_frames < goal_video * pos))):
                    chosen = best_video
                elif best_image:
                    chosen = best_image
                else:
                    chosen = best_video or max(options, key=option_score)
                if image_streak >= 3 and chosen[0] == 'image':
                    log(f'Phần {n}: vượt 3 ảnh liên tiếp do thiếu video phù hợp.')
                kind, nf, selected = chosen
                if need_video and not videos and not warned_shortage:
                    log(f'Phần {n}: thiếu video phù hợp, tiếp tục với ảnh.')
                    warned_shortage = True
            elif options:
                kind, nf, selected = options[0]

            if not selected:
                raise ValueError(
                    f'Phần {n}: hết tư liệu '
                    f'tại {pos / fps:.2f}s'
                )

            if kind != preferred:
                log(
                    f'Phần {n}, {pos / fps:.2f}s: '
                    f'thay {preferred} bằng {kind}'
                )

            score, _, _, src, h, start = selected
            t = nf / fps

            log(
                f'Phần {n} {pos / fps:.2f}s | '
                f'{src.name} | '
                f'nguồn {start:.2f}s | '
                f'điểm {score:.3f} | '
                f'{query[:160]}'
            )

            if kind == 'image':
                used.add(h)
                v81_remember_image(
                    src,
                    used_images
                )
            else:
                intervals.setdefault(
                    h, []
                ).append((
                    start,
                    start + t
                ))
                video_source_use[h] = video_source_use.get(h, 0) + 1

            clips.append(dict(
                part=n,
                type=kind,
                source=str(src.resolve()),
                source_start=start,
                start=(frames + pos) / fps,
                frames=nf,
                duration=t,
                effect=rng.choice(
                    c['effects'] or ['Tĩnh']
                )
            ))

            pos += nf
            if kind == 'video':
                video_frames += nf
                image_streak = 0
            else:
                image_streak += 1

        if smart_timeline:
            actual = 100 * video_frames / max(1, target)
            log(f'AI SMART TIMELINE phần {n}: video {actual:.1f}% theo thời lượng; '
                f'tối thiểu {min_video*100:.0f}%, mục tiêu {goal_video*100:.0f}%.')
            if actual + 0.01 < min_video * 100:
                log(f'CẢNH BÁO: Phần {n} chưa đạt 30% video; nguồn hợp lệ hoặc vị trí dựng không đủ. Đã tận dụng các cảnh video có thể chọn.')

        parts.append(dict(
            number=n,
            voice=str(p.resolve()),
            duration=dur,
            clips=clips
        ))

        frames = end

        log(
            f'Phần {n}: '
            f'{len(clips)} cảnh, '
            f'{dur:.2f}s'
        )

    v81_save_report(c, parts, log)

    video_count = sum(
        s['type'] == 'video'
        for part in parts
        for s in part['clips']
    )

    image_count = sum(
        s['type'] == 'image'
        for part in parts
        for s in part['clips']
    )

    log(
        f'V8.2: {video_count} cảnh video, '
        f'{image_count} cảnh ảnh'
    )

    return parts


# ============================================================
# MP4 RENDER
# Kept as an optional function.
# CapCut export uses the existing capcut.py.
# ============================================================

def render(c, parts, log, progress):
    out = Path(c['out'])
    out.mkdir(parents=True, exist_ok=True)

    name = c['name']
    fps = int(c['fps'])
    w, h = map(int, c['res'].split('x'))

    total = sum(
        len(p['clips']) for p in parts
    )
    index = 0

    enc = (
        [
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',
            '-cq', '20'
        ]
        if c['gpu']
        else [
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '20'
        ]
    )

    fit = (
        f'scale={w}:{h}:'
        'force_original_aspect_ratio=decrease:'
        'force_divisible_by=2,'
        f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,'
        'setsar=1'
    )

    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)
        paths = []

        for p in parts:
            for s in p['clips']:
                dest = tmp / f'{index:06}.mp4'
                nf = s['frames']

                z = float(
                    c['iz']
                    if s['type'] == 'image'
                    else c['vz']
                ) / 100

                if c.get('background') == 'Nền mờ':
                    base = (
                        'split=2[bg][fg];'
                        f'[bg]scale={w}:{h}:'
                        'force_original_aspect_ratio=increase,'
                        f'crop={w}:{h},'
                        'setsar=1,'
                        f'gblur=sigma={float(c.get("blur", 30))}'
                        '[b];'
                        f'[fg]scale={w}:{h}:'
                        'force_original_aspect_ratio=decrease:'
                        'force_divisible_by=2,'
                        'setsar=1[f];'
                        '[b][f]overlay=(W-w)/2:(H-h)/2:'
                        'format=auto,setsar=1'
                    )
                else:
                    color = {"Nền trắng":"white", "Nền xám":"gray", "Nền xanh đen":"0x101722"}.get(c.get("background"), "black")
                    base = fit.replace(":(oh-ih)/2,", ":(oh-ih)/2:color=" + color + ",")

                if s['type'] == 'image':
                    e = s['effect']
                    frac = f'on/{max(1, nf - 1)}'
                    ease = (
                        f'(1-cos(PI*{frac}))/2'
                    )

                    if e == 'Zoom in':
                        expr = (
                            f'1+{z-1}*{ease}'
                        )
                    elif e == 'Zoom out':
                        expr = (
                            f'{z}-{z-1}*{ease}'
                        )
                    else:
                        expr = '1'

                    vf = (
                        base
                        + f',scale={w*2}:{h*2}:'
                        'flags=lanczos,'
                        f"zoompan=z='{expr}':"
                        "x='iw/2-iw/zoom/2':"
                        "y='ih/2-ih/zoom/2':"
                        f'd={nf}:s={w}x{h}:fps={fps},'
                        'setsar=1'
                    )

                    inp = [
                        '-i', s['source']
                    ]

                else:
                    zw = max(
                        w,
                        round(w * z / 2) * 2
                    )
                    zh = max(
                        h,
                        round(h * z / 2) * 2
                    )

                    vf = (
                        base
                        + f',scale={zw}:{zh},'
                        f'crop={w}:{h},'
                        f'fps={fps},'
                        'tpad=stop_mode=clone:'
                        'stop_duration=0.15'
                    )

                    inp = [
                        '-ss',
                        str(s['source_start']),
                        '-i',
                        s['source']
                    ]

                vf += ',format=yuv420p'

                cmd = [
                    'ffmpeg',
                    '-v', 'error',
                    '-y',
                    '-filter_threads', '2'
                ] + inp + [
                    '-filter_complex_threads', '2',
                    '-filter_complex', vf,
                    '-frames:v', str(nf),
                    '-an'
                ]

                tail = [
                    '-pix_fmt', 'yuv420p',
                    '-threads', '4',
                    str(dest)
                ]

                try:
                    run(cmd + enc + tail)
                except RuntimeError:
                    if enc[1] != 'h264_nvenc':
                        raise

                    log(
                        'NVENC lỗi, chuyển CPU'
                    )
                    enc = [
                        '-c:v', 'libx264',
                        '-preset', 'veryfast',
                        '-crf', '20'
                    ]
                    run(cmd + enc + tail)

                paths.append(dest)
                index += 1
                progress(
                    90 * index / total
                )

        mode = c.get(
            'transition', 'Không'
        )

        flat = [
            q for p in parts
            for q in p['clips']
        ]

        if mode != 'Không' and len(paths) > 1:
            half = max(
                1,
                round(
                    float(
                        c.get('transition_time', .5)
                    ) * fps / 2
                )
            )

            cuts = [
                min(
                    half,
                    flat[j]['frames'] // 3,
                    flat[j + 1]['frames'] // 3
                )
                for j in range(len(paths) - 1)
            ]

            result = []

            def segment(
                inputs,
                filtergraph,
                count,
                dest
            ):
                run([
                    'ffmpeg',
                    '-v', 'error',
                    '-y',
                    '-filter_complex_threads', '2'
                ] + inputs + [
                    '-filter_complex',
                    filtergraph,
                    '-r', str(fps),
                    '-frames:v', str(count),
                    '-an'
                ] + enc + [
                    '-pix_fmt', 'yuv420p',
                    '-threads', '4',
                    str(dest)
                ])

            for j, src in enumerate(paths):
                left = cuts[j - 1] if j else 0
                right = (
                    cuts[j]
                    if j < len(cuts)
                    else 0
                )

                n = flat[j]['frames']
                core = tmp / f'core{j:06}.mp4'

                segment(
                    ['-i', str(src)],
                    (
                        '[0:v]trim='
                        f'start_frame={left}:'
                        f'end_frame={n-right},'
                        'setpts=PTS-STARTPTS'
                    ),
                    n - left - right,
                    core
                )

                result.append(core)

                if right:
                    k = right
                    sec = k / fps

                    trans = {
                        'Dissolve': 'fade',
                        'Fade': 'fadeblack',
                        'Slide Left': 'slideleft',
                        'Slide Right': 'slideright',
                        'Blur': 'hblur',
                        'Zoom Transition': 'zoomin', 'Mờ đen': 'fadeblack'
                    }

                    style = (
                        random.choice(
                            list(trans.values())
                        )
                        if mode == 'Random'
                        else trans[mode]
                    )

                    bridge = (
                        tmp / f'bridge{j:06}.mp4'
                    )

                    graph = (
                        '[0:v]trim='
                        f'start_frame={n-k},'
                        'setpts=PTS-STARTPTS,'
                        'tpad=stop_mode=clone:'
                        f'stop_duration={2*sec:.9f},'
                        f'fps={fps},settb=AVTB[a];'
                        '[1:v]trim='
                        f'end_frame={k},'
                        'setpts=PTS-STARTPTS,'
                        'tpad=start_mode=clone:'
                        f'start_duration={sec:.9f}:'
                        'stop_mode=clone:'
                        f'stop_duration={sec:.9f},'
                        f'fps={fps},settb=AVTB[b];'
                        '[a][b]xfade='
                        f'transition={style}:'
                        f'duration={2*sec:.9f}:'
                        'offset=0,'
                        'tpad=stop_mode=clone:'
                        'stop_duration=1,'
                        'format=yuv420p'
                    )

                    segment(
                        [
                            '-i', str(src),
                            '-i', str(paths[j + 1])
                        ],
                        graph,
                        2 * k,
                        bridge
                    )

                    result.append(bridge)

                progress(
                    90 + 8 * (j + 1) / len(paths)
                )

            paths = result

        listing = tmp / 'list.txt'

        listing.write_text(
            ''.join(
                f"file '{p.name}'\n"
                for p in paths
            ),
            encoding='utf-8'
        )

        visual = tmp / 'visual.mp4'

        run([
            'ffmpeg',
            '-v', 'error',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(listing),
            '-c', 'copy',
            str(visual)
        ])

        aud = []

        for j, p in enumerate(parts):
            dest = tmp / f'a{j}.wav'

            run([
                'ffmpeg',
                '-v', 'error',
                '-y',
                '-i', p['voice'],
                '-vn',
                '-ar', '48000',
                '-ac', '2',
                '-c:a', 'pcm_s16le',
                str(dest)
            ])

            aud.append(dest)

        listing.write_text(
            ''.join(
                f"file '{p.name}'\n"
                for p in aud
            ),
            encoding='utf-8'
        )

        audio = tmp / 'audio.wav'

        run([
            'ffmpeg',
            '-v', 'error',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(listing),
            '-c', 'copy',
            str(audio)
        ])

        dest = out / (name + '.mp4')

        run([
            'ffmpeg',
            '-v', 'error',
            '-y',
            '-i', str(visual),
            '-i', str(audio),
            '-map', '0:v',
            '-map', '1:a',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '320k',
            '-movflags', '+faststart',
            str(dest)
        ])

        progress(100)
        log('Hoàn thành: ' + str(dest))


# ============================================================
# APPLICATION UI
# ============================================================

def main():
    root = tk.Tk()
    root.title(VERSION)
    root.geometry('1100x780')

    panel = ttk.Frame(root, padding=15)
    panel.pack(
        fill='both',
        expand=True
    )

    panel.columnconfigure(1, weight=1)
    panel.columnconfigure(3, weight=1)

    vals = {}
    row = 0
    slot = 0

    def field(
        key,
        label,
        default='',
        options=None,
        folder=False
    ):
        nonlocal row, slot

        col = 0 if folder else slot * 2

        var = tk.StringVar(value=default)
        vals[key] = var

        ttk.Label(
            panel,
            text=label
        ).grid(
            row=row,
            column=col,
            sticky='w',
            pady=1
        )

        if options:
            widget = ttk.Combobox(
                panel,
                textvariable=var,
                values=options,
                state='readonly'
            )
        else:
            widget = ttk.Entry(
                panel,
                textvariable=var
            )

        widget.grid(
            row=row,
            column=col + 1,
            columnspan=2 if folder else 1,
            sticky='ew',
            padx=8
        )

        if folder:
            def choose():
                p = filedialog.askdirectory()
                if p:
                    var.set(p)

            ttk.Button(
                panel,
                text='Chọn thư mục',
                command=choose
            ).grid(
                row=row,
                column=3
            )

        if folder:
            row += 1
        else:
            slot = 1 - slot
            if slot == 0:
                row += 1

    ttk.Label(
        panel,
        text='KHIÊM YOUTUBE V10.0 CORE',
        font=('Segoe UI', 20, 'bold')
    ).grid(
        row=row,
        columnspan=4,
        pady=8
    )
    row += 1

    for k, label in [
        ('voice', 'Voice MP3'),
        ('txt', 'Kịch bản TXT'),
        ('images', 'Ảnh (folder 1,2,3...)'),
        ('videos', 'Video (folder 1,2,3...)'),
        ('out', 'Nơi xuất')
    ]:
        field(k, label, folder=True)

    field(
        'draft_root',
        'Nơi lưu dự án CapCut',
        str(
            Path(
                os.environ.get('LOCALAPPDATA', '')
            )
            / 'CapCut/User Data/Projects/com.lveditor.draft'
        ),
        folder=True
    )

    field(
        'sample',
        'Mẫu CapCut khác (không bắt buộc)',
        folder=True
    )

    field(
        'name',
        'Tên dự án',
        'New Project'
    )

    field(
        'speed',
        'Chế độ AI',
        'Smart',
        ['Fast', 'Smart', 'Deep']
    )

    field(
        'vn',
        'Số video mỗi chu kỳ',
        '1'
    )

    field(
        'an',
        'Số ảnh mỗi chu kỳ',
        '3'
    )

    for k, label in [
        ('video', 'Video'),
        ('image', 'Ảnh')
    ]:
        field(
            k + 'mode',
            label + ' - chế độ',
            'Cố định',
            ['Cố định', 'Random']
        )

        field(
            k + 'time',
            label + ' - giây',
            '5'
        )

    field(
        'background',
        'Hiệu ứng nền',
        'Nền mờ',
        ['Nền đen', 'Nền mờ']
    )

    field(
        'blur',
        'Độ mờ nền',
        '30'
    )

    field(
        'transition',
        'Chuyển cảnh',
        'Dissolve',
        [
            'Không',
            'Dissolve',
            'Fade',
            'Slide Left',
            'Slide Right',
            'Blur',
            'Zoom Transition',
            'Random'
        ]
    )

    field(
        'transition_time',
        'Chuyển cảnh (giây)',
        '0.5',
        ['0.3', '0.5', '0.7', '1.0']
    )

    field(
        'iz',
        'Zoom ảnh tối đa (%)',
        '110'
    )

    field(
        'vz',
        'Zoom video (%)',
        '100'
    )

    field(
        'res',
        'Độ phân giải',
        '3840x2160',
        [
            '3840x2160',
            '2560x1440',
            '1920x1080'
        ]
    )

    field(
        'fps',
        'FPS',
        '30',
        ['24', '30', '60']
    )

    row += slot
    slot = 0

    gpu = tk.BooleanVar(value=True)

    ttk.Checkbutton(
        panel,
        text='NVIDIA NVENC (CPU dự phòng)',
        variable=gpu
    ).grid(
        row=row,
        columnspan=4,
        sticky='w'
    )
    row += 1

    effects = {
        e: tk.BooleanVar(value=e != 'Tĩnh')
        for e in [
            'Zoom in',
            'Zoom out',
            'Tĩnh'
        ]
    }

    ef = ttk.Frame(panel)
    ef.grid(
        row=row,
        columnspan=4,
        sticky='w'
    )
    row += 1

    for e, v in effects.items():
        ttk.Checkbutton(
            ef,
            text=e,
            variable=v
        ).pack(side='left')

    ai = tk.BooleanVar(value=True)
    align = tk.BooleanVar(value=True)

    opts = ttk.Frame(panel)
    opts.grid(
        row=row,
        columnspan=4,
        sticky='w'
    )
    row += 1

    ttk.Checkbutton(
        opts,
        text='AI CLIP offline',
        variable=ai
    ).pack(side='left')

    ttk.Checkbutton(
        opts,
        text='Whisper đồng bộ voice',
        variable=align
    ).pack(side='left')

    bar = ttk.Progressbar(panel)
    bar.grid(
        row=row,
        columnspan=4,
        sticky='ew',
        pady=5
    )
    row += 1

    status = tk.Text(
        panel,
        height=6
    )
    status.grid(
        row=row,
        columnspan=4,
        sticky='nsew'
    )

    panel.rowconfigure(row, weight=1)
    row += 1

    buttons = []
    cached = {}
    queue = []
    busy = False
    queue_running = [False]

    def start(mode, job=None):
        nonlocal busy

        c = {
            k: v.get()
            for k, v in vals.items()
        }

        c.update(
            ai=ai.get(),
            align=align.get(),
            gpu=gpu.get(),
            effects=[
                e for e, v in effects.items()
                if v.get()
            ]
        )

        if job is not None:
            c = job

        try:
            if any(
                not c[k]
                or not Path(c[k]).is_dir()
                for k in [
                    'voice',
                    'txt',
                    'images',
                    'videos',
                    'out'
                ]
            ):
                raise ValueError(
                    'Hãy chọn đủ thư mục'
                )

            if (
                not c['name']
                or re.search(
                    r'[<>:"/\\|?*]',
                    c['name']
                )
            ):
                raise ValueError(
                    'Tên dự án không hợp lệ'
                )

            if not 0 <= float(c['blur']) <= 100:
                raise ValueError(
                    'Độ mờ từ 0 đến 100'
                )

            if any(
                not 100 <= float(c[k]) <= 150
                for k in ['iz', 'vz']
            ):
                raise ValueError(
                    'Zoom từ 100 đến 150'
                )

        except Exception as e:
            messagebox.showerror(
                'Lỗi',
                str(e)
            )
            return

        if (
            mode == 'render'
            and (
                Path(c['out'])
                / (c['name'] + '.mp4')
            ).exists()
            and not messagebox.askyesno(
                'Ghi đè',
                'Ghi đè MP4?'
            )
        ):
            return

        if mode in (
            'queue_mp4',
            'queue_capcut'
        ):
            actual_mode = (
                'render'
                if mode == 'queue_mp4'
                else 'capcut'
            )

            queue.append((
                actual_mode,
                dict(c)
            ))

            status.insert(
                'end',
                f'Đã thêm {c["name"]} | '
                f'Hàng đợi: {len(queue)}\n'
            )
            return

        if busy:
            return

        busy = True

        for b in buttons:
            b.config(state='disabled')

        bar['value'] = 0

        def work():
            def log(s):
                with (
                    Path(c['out'])
                    / 'run_log.txt'
                ).open(
                    'a',
                    encoding='utf-8'
                ) as f:
                    f.write(s + '\n')

                def update_log():
                    status.insert(
                        'end',
                        s + '\n'
                    )
                    status.see('end')

                root.after(
                    0,
                    update_log
                )

            def progress(value):
                root.after(
                    0,
                    lambda: bar.configure(
                        value=value
                    )
                )

            try:
                log(
                    '=== KHIÊM YOUTUBE V10.0 CORE ==='
                )
                log('Chế độ: ' + mode)

                key = json.dumps(
                    {
                        k: v
                        for k, v in c.items()
                        if k not in (
                            'out',
                            'name',
                            'draft_root',
                            'sample',
                            'gpu',
                            'background',
                            'blur',
                            'transition',
                            'transition_time',
                            'iz',
                            'vz',
                            'res'
                        )
                    },
                    sort_keys=True
                )

                # V10: Rebuild timeline to reflect current files.
                # Avoid stale media selections.
                parts = plan(c, log)
                cached.clear()
                cached[key] = parts
                log('V10: Timeline được cập nhật từ tư liệu hiện tại')

                timeline = (
                    Path(c['out'])
                    / (
                        c['name']
                        + '.timeline.json'
                    )
                )

                timeline.write_text(
                    json.dumps(
                        parts,
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding='utf-8'
                )

                log(
                    'Kiểm tra tư liệu thành công'
                )

                if mode == 'check':
                    progress(100)

                elif mode == 'render':
                    render(
                        c,
                        parts,
                        log,
                        progress
                    )

                elif mode == 'capcut':
                    from capcut import export
                    export(c, parts, log)
                    progress(100)

                if mode in (
                    'render',
                    'capcut'
                ):
                    try:
                        import winsound
                        winsound.Beep(
                            1000,
                            200
                        )
                    except Exception:
                        pass

                log('HOÀN THÀNH.')

            except Exception as e:
                log('LỖI: ' + str(e))
                log(traceback.format_exc())

            finally:
                root.after(
                    0,
                    finish
                )

        threading.Thread(
            target=work,
            daemon=True
        ).start()

    def finish():
        nonlocal busy

        busy = False

        for b in buttons:
            b.config(state='normal')

        if queue_running[0]:
            next_job()

    def next_job():
        if busy:
            return

        if not queue:
            queue_running[0] = False
            return

        m, c = queue.pop(0)
        start(m, c)

        if not busy:
            root.after(
                0,
                next_job
            )

    def run_queue():
        queue_running[0] = True
        next_job()

    for j, (label, mode) in enumerate([
        ('KIỂM TRA TƯ LIỆU', 'check'),
        ('XUẤT MP4', 'render'),
        ('XUẤT CAPCUT', 'capcut')
    ]):
        b = ttk.Button(
            panel,
            text=label,
            command=lambda m=mode: start(m)
        )
        b.grid(
            row=row,
            column=j,
            sticky='ew',
            pady=8
        )
        buttons.append(b)

    ttk.Button(
        panel,
        text='Mở thư mục xuất',
        command=lambda: (
            os.startfile(vals['out'].get())
            if Path(
                vals['out'].get()
            ).is_dir()
            else None
        )
    ).grid(
        row=row + 1,
        column=2
    )

    q = ttk.Frame(panel)
    q.grid(
        row=row + 2,
        columnspan=4,
        sticky='ew'
    )

    queue_actions = [
        (
            'Thêm MP4',
            lambda: start('queue_mp4')
        ),
        (
            'Thêm CapCut',
            lambda: start('queue_capcut')
        ),
        (
            'Chạy hàng đợi',
            run_queue
        ),
        (
            'Dừng sau job',
            lambda: queue_running.__setitem__(
                0, False
            )
        ),
        (
            'Xóa hàng đợi',
            queue.clear
        )
    ]

    for label, cmd in queue_actions:
        ttk.Button(
            q,
            text=label,
            command=cmd
        ).pack(
            side='left',
            padx=2
        )

    root.mainloop()


if __name__ == '__main__':
    main()
