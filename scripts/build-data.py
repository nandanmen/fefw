# Builds data/characters.json and data/skills.json from the Fortune's Weave community sheet.
# Usage: python3 scripts/build-data.py <spreadsheet.json> <out-dir>
# Input is a Sheets API spreadsheets.get response with grid data (formattedValue) for the tabs in TABS.
import json, os, re, sys

TABS = ["Characters", "Combat Arts", "Equipable Skills", "Black Magic", "White Magic", "Magic Scrolls",
        "Sword", "Spear", "Axe", "Bow", "Gauntlet", "Authority", "Riding", "Infantry", "Armor", "Flying"]
STATS = ["hp", "str", "mag", "spd", "dex", "def", "res", "lck", "cha"]
SKILL_LINES = ["sword", "spear", "axe", "bow", "gauntlet", "blackMagic", "whiteMagic", "authority",
               "infantry", "riding", "armor", "flying"]
LEARNSET_TABS = dict(zip(["Sword", "Spear", "Axe", "Bow", "Gauntlet", "Black Magic", "White Magic", "Authority",
                          "Infantry", "Riding", "Armor", "Flying"], SKILL_LINES))
WEAPON_TABS = {"Sword": "Sword", "Spear": "Spear", "Axe": "Axe", "Bow": "Bow", "Gauntlet": "Gauntlet"}
FAIRE = {"Sword": "Swordfaire", "Spear": "Spearfaire", "Axe": "Axefaire", "Bow": "Bowfaire", "Gauntlet": "Fistfaire"}
PATHS = ["cai", "dietrich", "theodora", "leda"]
EMPTY = {"", "-", "--", "---", "N/A", "[Unknown]"}
# Greek letters the sheet sometimes types as Latin lookalikes (e.g. "Mire B" vs "Mire Β").
GREEK = str.maketrans("ΒΤΖΘθ", "BTZθθ")
# Spelling variants in learnset tabs -> canonical skill name.
ALIASES = {"Narrow Defence": "Narrow Defense"}


def load(path):
    data = json.load(open(path))
    tabs = {}
    for s in data["sheets"]:
        rows = []
        for r in s["data"][0].get("rowData", []):
            vals = [c.get("formattedValue", "") for c in r.get("values", [])]
            while vals and not vals[-1].strip():
                vals.pop()
            rows.append(vals)
        tabs[s["properties"]["title"]] = rows
    return tabs


def cell(r, i):
    v = r[i].strip() if i < len(r) else ""
    # "[Unknown]", "[Macuil]" etc. are placeholders, not values.
    return None if v in EMPTY or re.fullmatch(r"\[.*\]", v) else v


def num(r, i):
    v = cell(r, i)
    return int(v) if v else None


def items(r, i):
    v = cell(r, i)
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def lines(r, i):
    v = cell(r, i)
    return [l.strip().lstrip("・").strip() for l in v.split("\n") if l.strip()] if v else []


PARTS = {"I": 1, "II": 2, "III": 3}
SECTIONS = {"First": 1, "Second": 2, "Third": 3, "Fourth": 4, "Fifth": 5}


def recruitment(r, i):
    """Splits a recruitment cell into part/chapter/support/renown; anything else goes to notes.
    The prologue is part 0, and Part III's sections count as chapters."""
    out = {"part": None, "chapter": None, "support": None, "renown": None, "notes": []}
    for line in lines(r, i):
        m = re.fullmatch(r"(?:Part (I+) Chapter (\d+)|Prologue: \w+ Chapter (\d+)|Part (I+) (\w+) Section)"
                         r"(?: \((.+)\))?", line)
        if m and out["part"] is None:
            part, chapter, prologue, s_part, section, note = m.groups()
            if prologue:
                out["part"], out["chapter"] = 0, int(prologue)
            elif section:
                out["part"], out["chapter"] = PARTS[s_part], SECTIONS[section]
            else:
                out["part"], out["chapter"] = PARTS[part], int(chapter)
            if note:
                out["notes"].append(note)
        elif m := re.fullmatch(r"Support Lv (\d+)", line):
            out["support"] = int(m[1])
        elif m := re.fullmatch(r"(\d+) Renown", line):
            out["renown"] = int(m[1])
        else:
            out["notes"].append(line)
    return out if any(out.values()) else None


def prefs(r, start, keys):
    return {k: items(r, start + n) for n, k in enumerate(keys)}


def compact(d):
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


skills = {}


TYPE_LABELS = {"combatArt": "Combat Art", "spell": "Spell", "ability": "Ability", "bloodmark": "Bloodmark"}


def add_skill(name, entry):
    """Adds a skill and returns the key it is stored under."""
    name = ALIASES.get(name, name)
    if name in skills and skills[name]["type"] != entry["type"]:
        # Different things share a name (e.g. the Barrier spell and the Bishop's Barrier skill).
        name = f"{name} ({TYPE_LABELS[entry['type']]})"
    if name in skills:
        # Same skill listed on several tabs: keep the first, fill in anything it lacks.
        for k, v in entry.items():
            skills[name].setdefault(k, v)
        return name
    skills[name] = entry
    return name


# --- Combat arts ---------------------------------------------------------------------------------

ART_SECTIONS = {"General Combat Arts": "general", "Weapon-Specific Arts": "weaponSpecific",
                "Class Mastery Arts": "classMastery", "Class Mastery": "classMastery", "Hidden Arts": "hidden"}
ART_SOURCE_KEY = {"weaponSpecific": "weapon", "classMastery": "class", "hidden": "dreadWarrior"}


def art_fields(r):
    return compact({"cost": cell(r, 1), "might": cell(r, 2), "hit": cell(r, 3), "crit": cell(r, 4),
                    "range": cell(r, 5), "description": cell(r, 6)})


def read_arts(rows, category, start=0, stop_at_blank_run=False):
    kind, last = None, None
    for r in rows[start:]:
        name = cell(r, 0)
        if not name:
            continue
        if name in ART_SECTIONS:
            kind = ART_SECTIONS[name]; continue
        if len(r) == 1 and name not in skills and not name.endswith("+"):
            # A new weapon heading on the Combat Arts tab ("Spears", "Authority", ...).
            category, kind = {"Swords": "Sword", "Spears": "Spear", "Axes": "Axe", "Bows": "Bow",
                              "Gauntlets": "Gauntlet"}.get(name, name), "general"
            continue
        if name == "Name" or kind is None:
            continue
        if name.endswith("+") and last == name[:-1]:
            upgrade = art_fields(r)
            if ART_SOURCE_KEY.get(kind) and cell(r, 7):
                upgrade[ART_SOURCE_KEY[kind]] = cell(r, 7)
            skills[last].setdefault("upgrade", upgrade)
            continue
        entry = {"type": "combatArt", "category": category, "kind": kind, **art_fields(r)}
        src = ART_SOURCE_KEY.get(kind)
        if src and cell(r, 7):
            entry[src] = cell(r, 7)
        last = add_skill(name, entry)


def build(tabs):
    for tab, cat in WEAPON_TABS.items():
        rows = tabs[tab]
        start = next(i for i, r in enumerate(rows) if r and r[0].strip() == "General Combat Arts")
        read_arts(rows, cat, start)
    read_arts(tabs["Combat Arts"], "Sword")

    # --- Spells ----------------------------------------------------------------------------------
    scrolls = {}
    for r in tabs["Magic Scrolls"][1:]:
        if cell(r, 0):
            scrolls[cell(r, 0).translate(GREEK)] = {"item": cell(r, 1), "description": cell(r, 9)}
    for tab, school in [("Black Magic", "black"), ("White Magic", "white")]:
        rows = tabs[tab]
        start = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Name")
        for r in rows[start + 1:]:
            name = cell(r, 0)
            if not name:
                break
            entry = compact({"type": "spell", "school": school, "might": cell(r, 1), "hit": cell(r, 2),
                             "range": cell(r, 3), "weight": cell(r, 4), "crit": cell(r, 5), "uses": cell(r, 6),
                             "description": cell(r, 7), "effect": cell(r, 8)})
            scroll = scrolls.get(name.translate(GREEK))
            if scroll:
                entry.setdefault("description", scroll["description"])
                if scroll["item"]:
                    entry["learnedFrom"] = scroll["item"]
            elif school == "black" and cell(r, 12) and cell(r, 12) != "None":
                entry["learnedFrom"] = cell(r, 12)
            add_skill(name, entry)

    # --- Abilities (Equipable Skills tab) --------------------------------------------------------
    rows = tabs["Equipable Skills"]
    section, group = None, None
    for r in rows:
        head = cell(r, 0)
        if head in ("Class Mastery Skills", "Learned Skills", "Personal Skills", "Thermae Skills"):
            section = head; continue
        if section == "Class Mastery Skills" and cell(r, 1) and cell(r, 1) != "Skill Name":
            add_skill(cell(r, 1), {"type": "ability", "category": "classMastery", "description": cell(r, 2),
                                   "class": cell(r, 3)})
        elif section == "Learned Skills" and cell(r, 1) and cell(r, 1) != "Ability":
            group = head or group
            name, desc = cell(r, 1), cell(r, 2)
            if group == "Weapon":
                if name == "(Weapon)-faire":
                    for weapon, faire in FAIRE.items():
                        add_skill(faire, {"type": "ability", "category": "weapon",
                                          "description": desc.replace("(weapon type)", weapon.lower() + "s")})
                continue
            add_skill(name, {"type": "ability", "category": group.lower(), "description": desc})
        elif section == "Thermae Skills" and cell(r, 1) and cell(r, 1) != "Ability":
            add_skill(cell(r, 1), {"type": "ability", "category": "thermae", "description": cell(r, 2),
                                   "baths": items(r, 3)})
    for school in ("Black", "White"):
        add_skill(f"{school} Magic Mastery", {"type": "ability", "category": "weapon", "description": None})

    # --- Characters ------------------------------------------------------------------------------
    def personal(names, descs, category):
        """Register personal skills; returns their names. Two description lines on one skill are base/upgraded."""
        names = [n.strip() for n in (names or "").split("\n") if n.strip() and n.strip() not in EMPTY]
        descs = [d.strip() for d in (descs or "").split("\n") if d.strip() and d.strip() not in EMPTY]
        out = []
        for i, n in enumerate(names):
            if len(names) == 1:
                mine = descs
            else:
                mine = descs[i:i + 1] if i < len(names) - 1 else descs[i:]
            entry = {"type": "ability", "category": category, "description": mine[0] if mine else None}
            if len(names) == 1 and len(mine) == 2 and category == "personalEquippable":
                entry["upgrade"] = {"description": mine[1]}
            elif len(mine) > 1:
                entry["description"] = "\n".join(mine)
            out.append(add_skill(n, entry))
        return out

    def bloodmark(name, desc):
        return add_skill(name, {"type": "bloodmark", "description": desc}) if name else None

    characters, order, section = {}, [], "playable"
    for r in tabs["Characters"][2:]:
        name = cell(r, 0)
        if not name:
            continue
        if name.startswith("NPCs"):
            section = "npc"; continue
        if name.startswith("Average"):
            break
        growths = {k: num(r, 1 + n) for n, k in enumerate(STATS)}
        growths["total"] = num(r, 10) if any(v is not None for v in growths.values()) else None
        bb = {k: (cell(r, 11 + n) or "").lower() for n, k in enumerate(SKILL_LINES)}
        order.append(name)
        characters[name] = {
            "type": section,
            "growthRates": growths,
            "boons": [k for k, v in bb.items() if v == "boon"],
            "banes": [k for k, v in bb.items() if v == "bane"],
            "personalSkills": {"inherent": personal(cell(r, 23), cell(r, 24), "personalInherent"),
                               "equippable": personal(cell(r, 25), cell(r, 26), "personalEquippable")},
            "bloodmark": bloodmark(cell(r, 27), cell(r, 28)),
            "recruitment": {p: recruitment(r, 29 + n) for n, p in enumerate(PATHS)},
            "gifts": prefs(r, 33, ["love", "like"]),
            "temples": prefs(r, 35, ["love", "like", "neutral", "dislike"]),
            "meals": prefs(r, 39, ["love", "like", "neutral", "dislike"]),
            "plays": prefs(r, 43, ["love", "like", "neutral", "dislike"]),
            "roles": prefs(r, 47, ["love", "like", "neutral", "dislike"]),
            "learnsets": {},
        }

    # --- Learnsets -------------------------------------------------------------------------------
    unresolved = set()
    for tab, line in LEARNSET_TABS.items():
        rows = tabs[tab]
        ranks = [(i, h.strip()) for i, h in enumerate(rows[0]) if re.fullmatch(r"[DCBAS]\+?", h.strip())]
        for r in rows[1:]:
            name = cell(r, 0)
            if name not in characters:
                if name and name.startswith("Automatic"):
                    break
                continue
            learnset = {}
            for i, rank in ranks:
                for entry in re.split(r"[,\n]", cell(r, i) or ""):
                    # Drop notes like "(prologue)" or "(Lv. 45)".
                    skill = re.sub(r"\s*\(.*?\)\s*", " ", entry).strip()
                    if not skill:
                        continue
                    skill = ALIASES.get(skill, skill)
                    base = skill.rstrip("+")
                    if skill not in skills and base not in skills:
                        # Named in a learnset but never described in the sheet.
                        unresolved.add(base)
                        add_skill(base, {"type": "ability", "category": line, "description": None})
                    learnset.setdefault(rank, []).append(skill)
            characters[name]["learnsets"][line] = learnset
    for c in characters.values():
        if not c["learnsets"]:
            del c["learnsets"]

    return characters, unresolved


if __name__ == "__main__":
    tabs = load(sys.argv[1])
    characters, unresolved = build(tabs)
    out = sys.argv[2]
    json.dump(characters, open(os.path.join(out, "characters.json"), "w"), ensure_ascii=False, indent=2)
    json.dump(dict(sorted(skills.items())), open(os.path.join(out, "skills.json"), "w"), ensure_ascii=False, indent=2)
    print(f"{len(characters)} characters, {len(skills)} skills")
    if unresolved:
        print("Learnset skills with no description in the sheet:", sorted(unresolved))
