# Converts the "Characters" tab of the Fortune's Weave community sheet into data/characters.json.
# Usage: python3 scripts/convert-characters.py <sheet-values.json> data/characters.json
# Input is the Sheets API values response ({"values": [[...]]}) for range Characters!A1:AZ83.
import json, sys
rows = json.load(open(sys.argv[1]))["values"]
STATS = ["hp","str","mag","spd","dex","def","res","lck","cha"]
SKILLS = ["sword","spear","axe","bow","gauntlet","blackMagic","whiteMagic","authority","infantry","riding","armor","flying"]
PATHS = ["cai","dietrich","theodora","leda"]
EMPTY = {"", "-", "---", "N/A"}

def cell(r, i):
    v = r[i].strip() if i < len(r) else ""
    return None if v in EMPTY else v

def num(r, i):
    v = cell(r, i)
    return int(v) if v else None

def items(r, i):
    v = cell(r, i)
    return [x.strip() for x in v.split(",") if x.strip()] if v else []

def lines(r, i):
    v = cell(r, i)
    return [l.strip().lstrip("・").strip() for l in v.split("\n") if l.strip()] if v else []

def skill(r, i):
    name, desc = cell(r, i), cell(r, i + 1)
    return {"name": name, "description": desc} if name or desc else None

def prefs(r, start, keys):
    return {k: items(r, start + n) for n, k in enumerate(keys)}

out = {}
section = "playable"
for r in rows[2:]:
    name = cell(r, 0)
    if not name:
        continue
    if name.startswith("NPCs"):
        section = "npc"; continue
    if name.startswith("Average"):
        break
    growths = {k: num(r, 1 + n) for n, k in enumerate(STATS)}
    growths["total"] = num(r, 10) if any(v is not None for v in growths.values()) else None
    bb = {k: (cell(r, 11 + n) or "").lower() for n, k in enumerate(SKILLS)}
    out[name] = {
        "type": section,
        "growthRates": growths,
        "boons": [k for k, v in bb.items() if v == "boon"],
        "banes": [k for k, v in bb.items() if v == "bane"],
        "personalSkills": {"inherent": skill(r, 23), "equippable": skill(r, 25)},
        "bloodmark": skill(r, 27),
        "recruitment": {p: lines(r, 29 + n) for n, p in enumerate(PATHS)},
        "gifts": prefs(r, 33, ["love", "like"]),
        "temples": prefs(r, 35, ["love", "like", "neutral", "dislike"]),
        "meals": prefs(r, 39, ["love", "like", "neutral", "dislike"]),
        "plays": prefs(r, 43, ["love", "like", "neutral", "dislike"]),
        "roles": prefs(r, 47, ["love", "like", "neutral", "dislike"]),
    }
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
print(len(out), sum(v["type"]=="npc" for v in out.values()))
