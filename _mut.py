import subprocess, sys, pathlib, json
R = pathlib.Path(__file__).parent
TESTS = ["tests/strategy/test_panel_features.py",
         "tests/fencemodel/test_model_validation.py",
         "tests/fencemodel/test_post_slot.py",
         "tests/strategy/test_site_conditions.py",
         "tests/api/test_api.py", "tests/scenarios", "tests/fencemodel"]
MUTS = json.loads((R / "_muts.json").read_text())
name = sys.argv[1]
path, old, new = MUTS[name]
f = R / path
orig = f.read_text()
assert orig.count(old) == 1, (name, orig.count(old))
f.write_text(orig.replace(old, new))
try:
    p = subprocess.run(["uv", "run", "pytest", "-q", "--no-header", "-p",
                        "no:randomly", "--tb=no", *TESTS],
                       cwd=R, capture_output=True, text=True)
    bad = [l for l in p.stdout.splitlines()
           if l.startswith("FAILED") or l.startswith("ERROR")]
    print(name, "->", len(bad), "failures")
    for l in bad:
        print("   ", l.split(" - ")[0])
    if not bad:
        print(p.stdout.splitlines()[-1])
finally:
    f.write_text(orig)
