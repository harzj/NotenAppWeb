import os, pickle, glob

session_dir = r"d:\git\WebNoten\NotenAppWeb\instance\sessions"
files = glob.glob(os.path.join(session_dir, "*"))
files.sort(key=os.path.getmtime, reverse=True)

for f in files[:3]:
    print(f"=== {os.path.basename(f)} (modified: {os.path.getmtime(f)}) ===")
    try:
        with open(f, 'rb') as fh:
            data = pickle.load(fh)
        print("Keys:", list(data.keys()))
        # Check for gradebook data
        for k, v in data.items():
            if isinstance(v, dict) and 'leistungsnachweise' in v:
                lns = v['leistungsnachweise']
                print(f"  Found gradebook with {len(lns)} LNs")
                for i, ln in enumerate(lns):
                    ln_typ = ln.get('ln_typ', 'N/A')
                    print(f"  LN {i}: name={ln.get('name','?')}, ln_typ={ln_typ}")
                    if ln_typ == 'ABT':
                        for s in ln.get('schueler', [])[:3]:
                            print(f"    Student: {s.get('name','?')}, kuerzel={s.get('kuerzel', 'NOT SET')}")
    except Exception as e:
        print(f"  Error reading: {e}")
    print()
