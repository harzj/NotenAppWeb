import os, glob

session_dir = r"d:\git\WebNoten\NotenAppWeb\instance\sessions"
files = glob.glob(os.path.join(session_dir, "*"))
files.sort(key=os.path.getmtime, reverse=True)

for f in files[:3]:
    print(f"=== {os.path.basename(f)} ===")
    try:
        with open(f, 'rb') as fh:
            content = fh.read(64)
            print(f"  Start of file: {content!r}")
    except Exception as e:
        print(f"  Error reading: {e}")
