# Pokémon Web App 🎮

A modern, responsive Flask web application for exploring Pokémon, moves, and battle type matchups powered by PokéAPI with a resilient multi-tier disk and in-memory caching engine.

---

## Features

- **🏠 Home & One-Stop-Shop Hub (`/`)**:
  - Central landing portal linking to Pokédex, MoveDex, AbilityDex, ItemDex, and Type Matchup Tool.
  - Dedicated **Developer Diagnostics & Cache Telemetry Hub**:
    - Live metrics HUD (Pokémon, Moves, Abilities, Items, Extra entities, Hit Rate %, Total Hits/Misses).
    - Independent cache controls (Backup, Reset, Recover) for all 5 caches.
    - Verbose Logging toggle button and live 40-line `cache_log.txt` audit terminal.

- **📖 Pokédex (`/pokedex`)**:
  - Clean, clutter-free browsing of 1,025+ Pokémon with high-resolution artwork, types, and stats.
  - Full pagination with `⏮ First`, `← Prev`, `Next →`, and `Last ⏭` controls.
  - Multi-mode search: Substring, wildcards (`*saur`, `char*`), and regex (`re:^pik.*`).
  - Filter by Type and Generation (1–10).
  - Global sort across all Pokémon by ID, Name, BST, Base Stats, Height, and Weight, with reverse order support.
  - Quick randomizer (`?random=true`) for sampling random Pokémon.

- **🔍 Pokémon Detail (`/pokemon/<name>`)**:
  - Dual high-res artwork display for normal and shiny variants.
  - **Interactive Ability Cards**: Switch between normal and hidden abilities with direct links to AbilityDex.
  - **Interactive Pokédex Version Dropdown**: Explore official Pokédex entries across all game versions.
  - Dynamic 0–255 color spectrum stat bars.
  - Defensive type effectiveness table (immunities, resistances, 2×/4× weaknesses).
  - Evolution line and alternate form variants with direct sprite links.
  - Comprehensive learnset table categorized by learn method and level.

- **⚔️ MoveDex (`/movedex`) & Move Details (`/move/<name>`)**:
  - Search and filter all Pokémon battle moves by Type and Damage Class (Physical, Special, Status).
  - Sort moves by Name, Base Power, Accuracy, or PP with First/Last pagination.
  - Move detail view with comprehensive stats and an image grid of every Pokémon that can learn the move.

- **✨ AbilityDex (`/abilitydex`) & Ability Details (`/ability/<name>`)**:
  - Explore Pokémon passive traits, hidden abilities, and field passives.
  - Search by ability name or keywords in effect summaries, filter by debut Generation, and sort by Pokémon count.
  - Ability detail view with effect breakdown and clickable roster of all Pokémon with that ability.

- **🎒 ItemDex (`/itemdex`) & Item Details (`/item/<name>`)**:
  - Catalog of held items, Mega Stones, Berries, medicine, Poké Balls, and evolutionary items.
  - Item detail view with official sprite, category, cost in Pokédollars, and gameplay descriptions.

- **🛡️ Type Effectiveness Tool (`/type_tool`)**:
  - **Defense Mode**: Multi-type calculator supporting up to 3 defensive types, calculating exact multipliers (from 8× vulnerability down to ⅛× / 0× immunities) with a list of matching Pokémon.
  - **Offense Mode**: Multi-type offensive coverage calculator for up to 4 attacking move types with full move breakdown.

- **👥 Championship Teambuilder (`/teambuilder`)**:
  - **6-Slot Interactive Roster**: Species, held item, ability, Tera Type, 4 moves, nature, and full EV/IV customization with live Level 50 / 100 stat calculations.
  - **Mega Stone Held Items & Protection**: 58 canonical Mega Stones (including Mega X, Y, and Z forms) permanently locked against Knock Off stripping or Trick/Switcheroo item swapping.
  - **Serebii Champions Format Validation**: Dynamic legality checks against official tournament rules (`data/champions_roster.json`), correctly enforcing Heatran bans while approving legal staples like Archaludon.
  - **18-Type Defensive Synergy Matrix**: Identifies shared team weaknesses with high-risk warnings and dynamic Tera preview.
  - **Offensive Coverage Analysis**: Evaluates Super Effective coverage across all 18 types and physical/special damage category distribution.
  - **Speed Tier Radar & Benchmarks**: Compares team speed stats against top tournament benchmarks with 1-click Tailwind (2×) and Trick Room toggles.
  - **VGC Tactical Readiness Checklist**: Verifies presence of essential tournament roles (Speed Control, Fake Out, Redirection, Intimidate, Weather/Terrain, Anti-Setup, Priority).
  - **Swiss Tournament Matchup Notes**: Dedicated game plan scratchpad saved per team.
  - **Universal Import / Export**: Full two-way compatibility with Pokémon Showdown / Smogon Pokepaste format.
  - **Pre-Loaded Sample Meta Teams**: Ready-to-use tournament archetypes including Regulation H Championship Balance, Tailwind Hyper Offense, and Trick Room.

- **🏟️ Showdown Battle Simulator (`/simulator`)**:
  - **VGC & Smogon Tournament Engine**: Full turn-by-turn simulation adhering to official Gen 9 competitive mechanics (3,126+ lines in `battle_engine.py`).
  - **💍 Omni Ring Mechanics**: Unified generational gimmick allowing one activation per match:
    - **Terastallization**: Pure mono-type defensive and offensive STAB conversion.
    - **Mega Evolution**: Strictly validated by held Mega Stone (e.g. Charizardite X/Y, Lucarionite, Mewtwonite X/Y, Rayquaza Dragon Ascent, and upcoming canonical forms like Mega Z).
    - **Gigantamax**: 3-turn titan transformation with 1.5× HP multiplier, converting status moves to Max Guard (priority +4) and damaging attacks to standard Max Moves or exclusive species G-Max moves (Lapras Aurora Veil, Blastoise Rain, Charizard Sun, Corviknight Hazard/Screen Clear, Urshifu Protect Pierce).
  - **⚡ Dynamic Mid-Turn Speed Recalculation**: Mega Evolution speed shifts and Tailwind activation dynamically re-order queued actions mid-turn before the next combatant moves.
  - **🛡️ Consecutive Protection Decay Formula**: Protect, Detect, Spiky Shield, and Max Guard follow official Gen 6–9 exponential decay ($(1/3)^n \to 100\%, 33.3\%, 11.1\%, 3.7\% \dots$), resetting on failure, switches, or non-protection moves, with Champion AI anti-spam penalties.
  - **🔋 PP Deduction, Pressure & Struggle Execution**: Every executed move decrements current PP; zero-PP moves are disabled in the HUD. When all moves reach 0 PP or when a Pokémon is locked into a 0-PP move by a Choice item (Choice Band, Choice Specs, Choice Scarf), the simulator automatically executes Struggle (50 BP physical typeless strike with 25% max HP recoil), eliminating player soft-locks with an active Struggle button in the HUD. Opponent's `Pressure` taxes 2 PP per attack targeting them and announces its presence on entry.
  - **🔥 Thermal Exchange, Well-Baked Body & Absorption Suite**: Baxcalibur's `Thermal Exchange` provides complete burn immunity and +1 Attack on Fire hits. Dachsbun's `Well-Baked Body` provides 0× Fire damage and +2 Defense. Includes Earth Eater, Water/Volt Absorb, Sap Sipper, Motor Drive, and Lightning Rod/Storm Drain.
  - **☠️ Entry Hazard Switch-In Faint Suppression**: Fainting from entry hazards (Stealth Rock, Spikes, Steelsurge) upon switching in immediately suppresses the Pokémon's switch-in ability (Intimidate, Drizzle, Drought, etc.) and prompts for a replacement without activation.
  - **🧸 Generation 9 Substitute Mechanics**: Official decoy creation (25% max HP cost), exact damage absorption with zero spillover damage to Pokémon, full immunity to direct status moves and secondary effects, sound moves & Infiltrator bypass, and Baton Pass / Shed Tail inheritance.
  - **👻 Semi-Invulnerable & Crash Moves**: Two-turn semi-invulnerable charging for Phantom Force, Shadow Force, Fly, Dig, Dive, and Bounce (with Phantom Force lifting Protect/Max Guard). High Jump Kick and Jump Kick inflict 50% max HP crash recoil on miss or protect.
  - **⚡ Paradox Booster Energy**: Instantly consumed on turn 1 entry to activate Protosynthesis or Quark Drive without weather/terrain.
  - **📂 Saved & Custom Team Selection**: Pre-battle launchpad dropdowns populate with all user-saved teams created in the Championship Teambuilder alongside sample meta rosters.
  - **Pre-Battle Launchpad & Match Setup**: Custom human trainer names (persisted in `localStorage`), Champion AI opponent selection with 🎲 randomizer, game mode toggle (Player vs AI / Spectator), and turn timers.
  - **AI Difficulty Slider (1–100) & Knowledge Reset**: From novice randomized moves to World Champion deep Minimax lookahead. Dedicated endpoint (`POST /api/simulator/knowledge/reset`) for clean dual-tier memory and disk cache flushing.
  - **📉 Self-Stat Drop Drawback Attacks**: High-power moves (Clanging Scales -1 Def, Superpower -1 Atk/-1 Def, Overheat -2 SpA, Leaf Storm -2 SpA, Close Combat -1 Def/-1 SpD) apply stat penalties immediately upon dealing damage or hitting a Substitute, while preserving stats if blocked or immune.
  - **💥 Fixed-Damage & Suicide Moves**: Accurate tournament implementation of Final Gambit (deals damage equal to attacker's current HP and faints user; fails without fainting user against Ghost-types, Protect, or miss), Seismic Toss/Night Shade (level-based damage), Super Fang/Ruination (50% target HP), and Explosion/Self-Destruct with official tiebreak adjudication.
  - **🌿 Competitive Items & Weather Synergies**: Full simulation of Weakness Policy (+2 Atk, +2 SpA when surviving super-effective attack), White Herb (single-use restoration clearing negative stages from Intimidate, Sticky Web, Shell Smash, and debuffs), Power Herb (Meteor Beam, Solar Beam/Blade, Skull Bash, Geomancy, Sky Attack), Sandstorm 1.5× Sp. Def boost for Rock types, and Snow 1.5× Defense boost for Ice types (with Cloud Nine/Air Lock suppression).
  - **🛡️ Protection Targeting Scope & Failure Decay**: Exponential failure degradation on consecutive Protect/Detect uses ($(1/3)^n$), with precise targeting scope ensuring Protect only blocks incoming attacks/debuffs and NEVER prevents opponents from executing self-status moves (Bulk Up, Swords Dance, Recover, Substitute) or setting field hazards. Urshifu's Unseen Fist punches through Protect with contact moves.
  - **🥊 Rage Fist & Last Respects Dynamic Scaling**: Annihilape's Rage Fist scales from 50 BP up to 350 BP (+50 BP per attack hit taken, counting multi-hits, with permanent switch/faint persistence and Iron Fist boost). Houndstone/Basculegion's Last Respects scales dynamically via $\text{Power} = 50 + (20 \times \text{fainted\_allies})$ (up to 150 BP).
  - **👑 Supreme Overlord & Fallen Ally Synergy**: Kingambit gains +10% damage per fallen teammate (up to +50% at 5 fainted allies) with switch-in entry announcements.
  - **🎯 Multi-Hit Suite, Skill Link & Loaded Dice**: Full simulation of 2–5 hit moves (Icicle Spear, Bullet Seed, Rock Blast, Scale Shot) and fixed multi-hits (Dragon Darts, Surging Strikes, Population Bomb). Skill Link guarantees 5 hits; Loaded Dice guarantees 4 or 5 hits. Hits break Focus Sash/Sturdy, bust Mimikyu's Disguise on hit 1 while remaining strikes deal damage, break Substitutes with spillover damage, and proc Archaludon's Stamina per hit.
  - **🧪 Poison-Type Toxic Bypass & Gen 9 Status Suite**: Toxic bypasses all accuracy checks to never miss and hits through semi-invulnerable turns (Fly, Dig, Dive, Bounce) when used by a Poison-type. Complete Gen 9 status mechanics: Burn (1/16 chip, -50% physical Attack, Guts 1.5× boost), regular Poison (1/8 chip), Bad Poison / Toxic ($N/16$ chip), Sleep (1–3 turns, Electric/Misty Terrain immunity), Freeze (20% thaw roll, thawing Fire moves like Flare Blitz/Scald thaw before attacking), and Paralysis (-50% Speed, 25% fully paralyzed roll).
  - **🩸 Recoil & Drain Actual Damage Capping**: Recoil attacks (Brave Bird, Flare Blitz, Head Smash, Wave Crash) and Drain attacks (Giga Drain, Drain Punch) calculate recoil and recovery strictly from the damage *actually inflicted* on the defender (capped by defender's remaining HP), eliminating disproportionate recoil when finishing off low-HP foes. Rock Head and Magic Guard provide complete recoil immunity (with Magic Guard also blocking Life Orb recoil).
  - **Arena UI Enhancements**: Edge-docked active cards (player docked left, opponent docked right), centered sprites, smooth gradual opacity fadeout on central announcements (1.8s) eliminating sprite overlap, and direct fainted replacement from the horizontal roster rail.

- **📘 Master Operational Guide (`/guide`)**:
  - Exhaustive user manual covering all features, navigation shortcuts, teambuilder strategy, EV/IV optimization, and competitive battle mechanics.

- **🛠️ Developer Technical Manual (`/developer`)**:
  - Comprehensive reference documenting all 53 route decorators across 52 endpoints, 12 backend engines, 9 disk data schemas, 16 frontend templates, damage formulas, and 34 documented bugfixes.

- **💖 Cached Favorites & Shiny Mode**:
  - Heart icon on every Pokédex card with atomic disk persistence in `data/favorites_cache.json`.
  - One-click Shiny mode toggle in the Pokédex navbar to display all species in their canonical shiny palettes.

- **🌙 Dark / Light Mode**:
  - Seamless dark theme toggle with persistent user preference via `localStorage`.

---

## Project Structure

```text
pokemon-web-app/
├── app.py                       # Main Flask routing, controllers, and view logic (53 routes)
├── utils/
│   ├── battle_engine.py         # Showdown-accurate Gen 9 battle engine (Omni Ring, Mega Stones, Dynamic Speed)
│   ├── battle_ai.py             # Heuristics & Minimax decision tree AI (1–100 difficulty)
│   ├── battle_knowledge.py      # Self-learning reinforcement cache engine
│   ├── ai_coach.py              # Tactical advice & misplay detection engine
│   ├── cache.py                 # Multi-tier thread-safe RLock disk & in-memory caching engine
│   ├── default_datasets.py      # Fallback datasets (Mega Stones, G-Max moves, move overrides)
│   ├── pokeapi.py               # PokéAPI client with HTTP session pooling and retries
│   ├── type_effectiveness.py    # Type matchup matrices, Fractions calculations, and Freeze-Dry
│   ├── teambuilder_storage.py   # Disk cache manager for 60 sample teams & meta items
│   ├── special_pokemon.py       # Deterministic classification sets (Legendaries, Paradox, Regional)
│   ├── favorites.py             # User favorites list disk persistence
│   ├── naming.py                # Centralized humanization & canonical naming engine
│   └── logger.py                # Timestamped file audit logging
├── templates/                   # Jinja2 HTML templates
│   ├── home.html                # Landing page & Cache Telemetry Hub
│   ├── pokedex.html             # Main Pokédex view with regex search, shiny toggle, & favorites
│   ├── teambuilder.html         # Championship Teambuilder with 4 modes & AI Coach
│   ├── simulator.html           # Showdown-style turn-by-turn battle arena & match setup
│   ├── operational_guide.html   # Master Operational & Strategy User Guide
│   ├── developer_docs.html      # Technical Developer Architecture Reference Manual
│   ├── pokemon_detail.html      # Individual Pokémon profile view
│   ├── movedex.html             # Battle moves browser
│   ├── move_detail.html         # Individual move details and learnable Pokémon grid
│   ├── abilitydex.html          # Abilities browser
│   ├── ability_detail.html      # Individual ability details and Pokémon roster
│   ├── itemdex.html             # Item catalog browser
│   ├── item_detail.html         # Individual item details view
│   ├── type_view.html           # Single type relations and Pokémon roster
│   ├── generation_view.html     # Generation-specific Pokédex view
│   └── type_tool.html           # Interactive multi-type effectiveness calculator
├── static/
│   └── style.css                # Responsive styles, CSS variables, dark mode, animations
└── data/                        # Persistent cache files and backups
    ├── pokemon_cache.json       # Core Pokémon endpoint cache (1,025+ species)
    ├── extra_cache.json         # Species, varieties, forms, evolution, and lists
    ├── moves_cache.json         # Move definitions and global index (559+ moves)
    ├── abilities_cache.json     # Ability data cache
    ├── items_cache.json         # Item definitions and catalog
    ├── mega_stones_cache.json   # 58 canonical Mega Stone species & form mappings
    ├── gmax_moves_cache.json    # Dynamic signature & standard G-Max move overrides
    ├── move_overrides_cache.json# Dynamic competitive move data overrides
    ├── sample_teams.json        # 60 cached championship sample teams (15 per mode)
    ├── competitive_items.json   # 103 competitive items (including 58 Mega Stones)
    ├── champions_roster.json    # Official Serebii Champions tournament roster
    ├── favorites_cache.json     # User favorited Pokémon list
    ├── battle_knowledge_cache.json # Learned AI state-action heuristics
    └── cache_log.txt            # Operational audit log
```

---

## Quickstart

### 1. Requirements
- Python 3.10+
- Flask & Requests

### 2. Running the App
The project is located under `ag_coding/Pokemon/pokemon-web-app`. Activate the virtual environment and start the development server:

```bash
cd /Users/francistallo/Desktop/ag_coding/Pokemon/pokemon-web-app
source .venv/bin/activate
python app.py
```

The application will start at `http://127.0.0.1:5001/` (configured to port 5001 by default to avoid macOS AirPlay Receiver conflicts on port 5000).

### 3. Running Automated Unit Tests
Execute the full test suite (verifying damage formulas, type effectiveness, naming cache, routes, and memory bounds):

```bash
./.venv/bin/python -m unittest discover -s tests
```
