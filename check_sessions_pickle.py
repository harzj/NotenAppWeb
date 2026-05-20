import os, pickle, glob

session_dir = r"d:\git\WebNoten\NotenAppWeb\instance\sessions"
files = glob.glob(os.path.join(session_dir, "*"))
files.sort(key=os.path.getmtime, reverse=True)

for f in files[:3]:
    print(f"=== {os.path.basename(f)} ===")
    try:
        with open(f, 'rb') as fh:
            content = fh.read()
            # Try to find the start of the pickle stream (0x80 0x05 for protocol 5 or 0x80 0x04 etc)
            pickle_start = content.find(b'\x80')
            if pickle_start != -1:
                data = pickle.loads(content[pickle_start:])
                print("Keys:", list(data.keys()))
                for k, v in data.items():
                    if isinstance(v, dict) and 'leistungsnachweise' in v:
                        lns = v['leistungsnachweise']
                        print(f"  Found gradebook in key '{k}' with {len(lns)} LNs")
                        for i, ln in enumerate(lns):
                            ln_typ = ln.get('ln_typ', 'N/A')
                            print(f"  LN {i}: name={ln.get('name','?')}, ln_typ={ln_typ}")
                            if ln_typ == 'ABT':
                                for s in ln.get('schueler', [])[:3]:
                                    print(f"    Student: {s.get('name','?')}, kuerzel={s.get('kuerzel', 'NOT SET')}")
            else:
                print("  Could not find pickle start marker.")
    except Exception as e:
        print(f"  Error reading: {e}")
    print()
