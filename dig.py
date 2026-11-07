"""把一个 mp4 变成「我能读的东西」：文字稿 + 关键帧。

用法：
  python dig.py <video.mp4> [--lang zh] [--model base] [--frames 12]
"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

import imageio_ffmpeg


def ffmpeg_exe():
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args):
    p = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise SystemExit("ffmpeg failed (%d): %s" % (p.returncode,
                                                     p.stderr.decode("utf-8", "replace")[-400:]))


def audio(video, outdir):
    wav = os.path.join(outdir, "audio.wav")
    run([ffmpeg_exe(), "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav])
    return wav


def frames(video, outdir, count):
    fdir = os.path.join(outdir, "frames")
    os.makedirs(fdir, exist_ok=True)
    txt = subprocess.run([ffmpeg_exe(), "-i", video], stderr=subprocess.PIPE).stderr.decode(
        "utf-8", "replace")
    h, m, s = txt.split("Duration: ")[1].split(",")[0].strip().split(":")
    dur = int(h) * 3600 + int(m) * 60 + float(s)
    step = max(1.0, dur / float(count))
    made = []
    for i in range(count):
        t = step * (i + 0.5)
        p = os.path.join(fdir, "f%02d.jpg" % i)
        run([ffmpeg_exe(), "-y", "-ss", "%.1f" % t, "-i", video,
             "-frames:v", "1", "-vf", "scale=960:-1", "-q:v", "4", p])
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            made.append((p, t))
    return made


def transcribe(wav, model_name, lang):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, info = model.transcribe(wav, language=lang, vad_filter=False,
                                  beam_size=1, condition_on_previous_text=False)
    lines = []
    for s in segs:
        lines.append("[%02d:%05.2f] %s" % (int(s.start // 60), s.start % 60, s.text.strip()))
        if len(lines) % 40 == 0:
            print("  ...%d segments" % len(lines), flush=True)
    return "\n".join(lines)


if __name__ == "__main__":
    video = sys.argv[1]
    lang = "zh"
    model_name = "base"
    count = 12
    args = sys.argv[2:]
    for i, a in enumerate(args):
        if a == "--lang":
            lang = args[i + 1]
        if a == "--model":
            model_name = args[i + 1]
        if a == "--frames":
            count = int(args[i + 1])

    base = os.path.splitext(os.path.basename(video))[0]
    outdir = os.path.join(os.path.dirname(video), base + "_dig")
    os.makedirs(outdir, exist_ok=True)

    print("1/3 抽音轨", flush=True)
    wav = audio(video, outdir)
    print("2/3 转写（模型 %s，CPU）" % model_name, flush=True)
    text = transcribe(wav, model_name, lang)
    tpath = os.path.join(outdir, "transcript.txt")
    with open(tpath, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("    transcript:", tpath, len(text), "chars")
    print("3/3 抽帧", flush=True)
    made = frames(video, outdir, count)
    for p, t in made:
        print("   frame %s @ %.0fs" % (p, t))
    print("done:", outdir)
