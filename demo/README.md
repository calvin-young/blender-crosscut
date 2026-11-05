# Demo reel

A scripted demo video of Crosscut. Every frame is a real screenshot of Blender running the add-on,
played by a script, then edited into a 1920x1080 MP4 with a title card and captions.

```
demo/crosscut/make.sh pack             # once: pack the synthetic bucket (needs Bucket Builder, ~3 min)
demo/crosscut/make.sh capture          # play every segment in Blender, save frames (~8 min)
demo/crosscut/make.sh capture g_gear   # re-capture one segment (the others replay uncaptured)
demo/crosscut/make.sh edit             # cards, captions, cross-fades -> demo/out/crosscut.mp4
python3 demo/crosscut/edit.py --still 12.5 x.png   # one edited frame, to check without encoding
```

- `crosscut/shots.py`: the segments. Each `yield` is one captured frame at 30 fps.
- `crosscut/edit.py`: the timeline and captions. Changing these only needs `make.sh edit`.
- `lib/`: the capture and edit library, and synthetic mechanical parts.
- `cache/` and `out/` are gitignored. It films a tagged snapshot of the add-on (`CROSSCUT_TAG` in
  `make.sh`), never the working tree, in a private Blender config, so your own is untouched.

Needs a real display (draw handlers don't run in `--background`), Pillow, numpy and ffmpeg, and
[Bucket Builder](https://github.com/calvin-young/blender-bucket-builder) checked out at
`~/dev/blender-bucket-builder`. Only synthetic parts are filmed.
