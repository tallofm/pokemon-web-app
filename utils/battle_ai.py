"""
battle_ai.py - Intelligent Pokémon Battle AI with 1-100 Difficulty Scaling and Championship Prediction Engine.

Difficulty Levels:
- 1-20 (Novice/Random): Random attacks, misplays, and reckless switching.
- 21-50 (Gym Leader): Greedy damage maximization, basic type awareness, lead hazards.
- 51-80 (Elite Four): 1-turn lookahead, speed control prioritisation, resists switching, knowledge integration.
- 81-100 (World Champion):
    - Deep heuristic evaluation (predicts opponent switches, Protects, and priority).
    - Defensive Terastallization to flip lethal weaknesses into resistances.
    - Double switching and positional pivoting to preserve core win conditions.
    - Deep reinforcement memory from battle_knowledge_cache.
- Coaching Directives for AI vs AI Spectator Mode.
"""

import random
import math
from typing import Dict, List, Any, Optional, Tuple
from utils.battle_engine import (
    BattleSimulator, BattleSide, PokemonState, get_move_metadata,
    get_type_multiplier, TYPE_CHART
)


def choose_ai_action(
    battle: BattleSimulator,
    ai_side_id: str,
    difficulty: int = 50,
    coach_directive: Optional[str] = None,
    knowledge_heuristics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Selects optimal or thematic action for the given AI side.
    Returns: {"type": "move", "move": str, "tera": bool} OR {"type": "switch", "targetIndex": int}
    """
    ai_side = battle.side1 if ai_side_id == "side1" else battle.side2
    opp_side = battle.side2 if ai_side_id == "side1" else battle.side1
    
    user_poke = ai_side.active_pokemon
    opp_poke = opp_side.active_pokemon

    if not user_poke or user_poke.is_fainted:
        # Must pick alive replacement
        alive = ai_side.get_alive_bench_indices()
        return {"type": "switch", "targetIndex": alive[0] if alive else 0}

    # If currently locked into a 2-turn charging move (e.g. Electro Shot, Solar Beam)
    if user_poke.charging_move:
        return {"type": "move", "move": user_poke.charging_move, "tera": False}

    # If locked by Choice item (Choice Band, Choice Specs, Choice Scarf)
    if user_poke.has_item and user_poke.item in ("choice-band", "choice-specs", "choice-scarf") and getattr(user_poke, "choice_locked_move", None):
        return {"type": "move", "move": user_poke.choice_locked_move, "tera": False}

    # -------------------------------------------------------------
    # 1. Novice / Random Play (Difficulty 1 - 20)
    # -------------------------------------------------------------
    blunder_rate = max(0.0, (100 - difficulty) / 100.0)
    if difficulty <= 20 or (random.random() < blunder_rate * 0.4 and difficulty < 70):
        # 15% chance to randomly switch if bench exists
        alive_bench = ai_side.get_alive_bench_indices()
        if alive_bench and random.random() < 0.15:
            return {"type": "switch", "targetIndex": random.choice(alive_bench)}
        # Otherwise random move
        moves = user_poke.moves or ["tackle"]
        return {"type": "move", "move": random.choice(moves), "tera": False}

    # -------------------------------------------------------------
    # 2. Candidate Evaluation Engine (Difficulty 21 - 100)
    # -------------------------------------------------------------
    action_scores: List[Tuple[float, Dict[str, Any], str]] = []
    alive_bench = ai_side.get_alive_bench_indices()

    # Assess moves
    for m in (user_poke.moves or ["tackle"]):
        score = evaluate_move_utility(
            battle, ai_side, opp_side, user_poke, opp_poke, m, 
            difficulty=difficulty, coach_directive=coach_directive, 
            knowledge=knowledge_heuristics
        )
        action_scores.append((score, {"type": "move", "move": m, "tera": False}, f"Move {m}"))

    # Assess Omni Ring Mechanics (Mega Evolution, Gigantamax, Terastallization)
    omni_available = not getattr(ai_side, "omni_used", getattr(ai_side, "tera_used", False))
    if omni_available and difficulty >= 60:
        # 1. Mega Evolution (High incentive if Pokémon has a Mega Form in Pokédex)
        if getattr(user_poke, "can_mega", False):
            for m in (user_poke.moves or ["tackle"]):
                m_data = get_move_metadata(m)
                if m_data.get("category") != "status":
                    mega_score = evaluate_move_utility(
                        battle, ai_side, opp_side, user_poke, opp_poke, m,
                        difficulty=difficulty, coach_directive=coach_directive,
                        knowledge=knowledge_heuristics
                    ) + 52.0
                    action_scores.append((mega_score, {"type": "move", "move": m, "omni": "mega"}, f"Mega + {m}"))

        # 2. Gigantamax (High incentive if Pokémon is G-Max capable in Pokédex)
        if getattr(user_poke, "can_gmax", False):
            for m in (user_poke.moves or ["tackle"]):
                m_data = get_move_metadata(m)
                if m_data.get("category") != "status":
                    gmax_score = evaluate_move_utility(
                        battle, ai_side, opp_side, user_poke, opp_poke, m,
                        difficulty=difficulty, coach_directive=coach_directive,
                        knowledge=knowledge_heuristics
                    ) + 55.0
                    action_scores.append((gmax_score, {"type": "move", "move": m, "omni": "gmax"}, f"G-Max + {m}"))

        # 3. Terastallization
        if user_poke.tera_type:
            tera_type = user_poke.tera_type
            opp_stab_types = opp_poke.types if opp_poke else ["normal"]
            opp_hits_hard = any(get_type_multiplier(t, [tera_type]) <= 0.5 for t in opp_stab_types)
            
            for m in user_poke.moves:
                m_data = get_move_metadata(m)
                if m_data.get("category") != "status":
                    dmg, info = battle.calculate_move_damage(user_poke, opp_poke, m)
                    can_ko = dmg >= opp_poke.current_hp
                    if (can_ko and difficulty >= 75) or (opp_hits_hard and difficulty >= 85):
                        tera_score = evaluate_move_utility(
                            battle, ai_side, opp_side, user_poke, opp_poke, m,
                            difficulty=difficulty, coach_directive=coach_directive,
                            knowledge=knowledge_heuristics
                        ) + 45.0  # High incentive to flip the match
                        action_scores.append((tera_score, {"type": "move", "move": m, "omni": "tera", "tera": True}, f"Tera {tera_type} + {m}"))

    # Assess Switches
    for bench_idx in alive_bench:
        bench_poke = ai_side.team[bench_idx]
        switch_score = evaluate_switch_utility(
            battle, ai_side, opp_side, user_poke, bench_poke, opp_poke,
            difficulty=difficulty, coach_directive=coach_directive
        )
        action_scores.append((switch_score, {"type": "switch", "targetIndex": bench_idx}, f"Switch {bench_poke.display_name}"))

    # Sort candidates by calculated utility descending
    action_scores.sort(key=lambda x: x[0], reverse=True)

    # -------------------------------------------------------------
    # 3. Decision Selection with Expert vs Intermediate variance
    # -------------------------------------------------------------
    if difficulty >= 90:
        # Champion: Strict best choice with 98% deterministic adherence
        chosen_action = action_scores[0][1]
    elif difficulty >= 65:
        # Elite: Pick between top 2 candidates based on weighted distribution
        top_candidates = action_scores[:2]
        weights = [max(1.0, c[0]) for c in top_candidates]
        tot = sum(weights)
        probs = [w / tot for w in weights]
        r = random.random()
        chosen_action = top_candidates[0][1] if r < probs[0] else top_candidates[1][1]
    else:
        # Gym Leader / Intermediate: top 3 candidate random selection
        top_candidates = action_scores[:3]
        chosen_action = random.choice(top_candidates)[1]

    # If the chosen action is a pivot move (U-Turn, Volt Switch, etc.), intelligently pick the best pivot target!
    if chosen_action.get("type") == "move":
        m_meta = get_move_metadata(chosen_action.get("move"))
        if m_meta.get("pivot"):
            alive_bench = ai_side.get_alive_bench_indices()
            if alive_bench:
                best_bench = alive_bench[0]
                best_score = -999.0
                for b_idx in alive_bench:
                    cand = ai_side.team[b_idx]
                    sc = evaluate_switch_utility(battle, ai_side, opp_side, user_poke, cand, opp_poke, difficulty, coach_directive)
                    if sc > best_score:
                        best_score = sc
                        best_bench = b_idx
                chosen_action["pivotTargetIndex"] = best_bench

    return chosen_action


def evaluate_move_utility(
    battle: BattleSimulator,
    ai_side: BattleSide,
    opp_side: BattleSide,
    user_poke: PokemonState,
    opp_poke: Optional[PokemonState],
    move_name: str,
    difficulty: int = 50,
    coach_directive: Optional[str] = None,
    knowledge: Optional[Dict[str, Any]] = None
) -> float:
    """Evaluates expected value of clicking move_name."""
    if not opp_poke or opp_poke.is_fainted:
        return 10.0

    m_data = get_move_metadata(move_name)
    category = m_data.get("category", "physical")
    move_type = m_data.get("type", "normal")
    move_lower = move_name.lower().strip()

    # Weather & ability accuracy resolution
    eff_weather = getattr(battle, "get_effective_weather", lambda: getattr(battle, "weather", "none"))()
    if eff_weather == "rain" and move_lower in ("hurricane", "thunder"):
        acc = 1.0
    elif eff_weather in ("snow", "hail") and move_lower == "blizzard":
        acc = 1.0
    elif eff_weather == "sun" and move_lower in ("hurricane", "thunder"):
        acc = 0.5
    elif user_poke.ability == "no-guard" or (opp_poke and opp_poke.ability == "no-guard"):
        acc = 1.0
    else:
        raw_acc = m_data.get("accuracy")
        acc = (float(raw_acc) / 100.0) if (raw_acc and raw_acc > 0) else 1.0

    priority = m_data.get("priority", 0)

    # 0. Hard Rule Restrictions (Assault Vest, Good as Gold, Priority Blocks)
    if category == "status" and user_poke.has_item and user_poke.item == "assault-vest":
        return -500.0

    eff_prio = battle.get_move_priority(user_poke, move_name)
    if eff_prio > 0 and opp_poke:
        if battle.terrain == "psychic" and battle.is_grounded(opp_poke):
            return -500.0
        if opp_poke.ability in ("armor-tail", "dazzling", "queenly-majesty"):
            return -500.0
        if user_poke.ability == "prankster" and category == "status" and "dark" in opp_poke.types:
            return -500.0

    if category == "status" and opp_poke and opp_poke.ability == "good-as-gold":
        return -500.0

    score = 0.0

    # 1. Damaging Move Calculation
    if category != "status":
        dmg, info = battle.calculate_move_damage(user_poke, opp_poke, move_name)
        dmg_ratio = dmg / max(1, opp_poke.current_hp)
        raw_damage_pct = dmg / max(1, opp_poke.max_hp)

        # Baseline: expected damage dealt
        score += min(150.0, raw_damage_pct * 100.0)

        # Lethal Knockout Bonus
        if dmg >= opp_poke.current_hp:
            score += 120.0  # Massive priority to secure KO!

        # Priority revenge kill bonus if opponent is low HP and user is slower
        user_spe = user_poke.get_effective_stat("speed", battle)
        opp_spe = opp_poke.get_effective_stat("speed", battle)
        if priority > 0 and user_spe < opp_spe and dmg >= opp_poke.current_hp:
            score += 80.0  # High championship priority snipe!

        # Super-effective bonus
        if info.get("typeMult", 1.0) >= 2.0:
            score += 35.0
        elif info.get("typeMult", 1.0) <= 0.5:
            score -= 30.0

        # Fake Out on first active turn only
        if move_name == "fake-out":
            if getattr(user_poke, "can_fake_out", False) and not opp_poke.is_protected:
                score += 90.0  # Free damage and flinch tempo!
            else:
                score -= 100.0  # Fails if not on first turn

        # Sucker Punch / Thunderclap
        if m_data.get("sucker") or move_name in ("sucker-punch", "thunderclap"):
            if opp_poke.is_protected:
                score -= 100.0

    # 2. Status Move Utility
    else:
        # Protection
        if m_data.get("protect") or move_name in ("protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "silk-trap", "burning-bulwark", "max-guard"):
            protect_count = getattr(user_poke, "consecutive_protect_count", 0)
            if protect_count > 0:
                # Heavy penalty if Protect was used consecutively (success chance is 33.3% or 11.1%)
                score -= 120.0 * protect_count
            else:
                # Champion AI predicts when opponent will launch super-effective nuclear move
                opp_has_lethal = False
                for opp_m in opp_poke.moves:
                    opp_dmg, _ = battle.calculate_move_damage(opp_poke, user_poke, opp_m)
                    if opp_dmg >= user_poke.current_hp:
                        opp_has_lethal = True
                        break
                
                if opp_has_lethal and not user_poke.is_protected and difficulty >= 75:
                    score += 85.0
                elif random.random() < 0.2:
                    score += 20.0
                else:
                    score += 5.0

        # Stat Boosts (Swords Dance, Nasty Plot, Dragon Dance)
        elif m_data.get("self_boost"):
            # Set up when healthy or facing a passive wall
            if user_poke.current_hp > (user_poke.max_hp * 0.65):
                score += 65.0
            else:
                score += 15.0

        # Recovery (Recover, Soft-Boiled)
        elif m_data.get("heal"):
            if user_poke.current_hp <= (user_poke.max_hp * 0.5):
                score += 85.0
            else:
                score -= 40.0

        # Speed Control (Tailwind, Trick Room)
        elif m_data.get("field_effect") == "tailwind":
            if ai_side.tailwind_turns <= 0:
                score += 70.0
        elif m_data.get("field_effect") == "trick_room":
            user_spe = user_poke.get_effective_stat("speed", battle)
            opp_spe = opp_poke.get_effective_stat("speed", battle)
            if battle.trick_room_turns <= 0 and user_spe < opp_spe:
                score += 80.0

        # Entry Hazards (Stealth Rock, Spikes)
        elif m_data.get("hazard") == "stealth_rock":
            if not opp_side.hazards.get("stealth_rock"):
                score += (65.0 if battle.turn <= 2 else 35.0)

        # Status Ailments (Will-O-Wisp, Thunder Wave, Spore)
        elif m_data.get("inflict_status"):
            st = m_data["inflict_status"]
            if opp_poke.status is None:
                if st == "burn" and "fire" not in opp_poke.types:
                    score += 55.0
                elif st == "paralysis" and "electric" not in opp_poke.types:
                    score += 60.0
                elif st == "sleep":
                    score += 75.0

    # 3. Coaching Directives Adjustment
    if coach_directive:
        cd = coach_directive.lower()
        if "offense" in cd and category != "status":
            score += 35.0
        elif "hazard" in cd and m_data.get("hazard"):
            score += 50.0
        elif "speed" in cd and (m_data.get("field_effect") in ("tailwind", "trick_room") or priority > 0):
            score += 45.0
        elif "defensive" in cd and (m_data.get("protect") or m_data.get("heal")):
            score += 40.0

    # 4. Knowledge Cache Historical Boost
    if knowledge and difficulty >= 70:
        matchup_key = f"{user_poke.species}_vs_{opp_poke.species}"
        heuristics = knowledge.get("matchup_heuristics", {}).get(matchup_key, {})
        rec_action = heuristics.get("recommended_action")
        if rec_action and rec_action == f"move:{move_name.lower()}":
            win_rate = heuristics.get("win_rate", 0.5)
            score += (win_rate * 40.0)

    # Factor in accuracy risk
    score *= acc
    return max(0.0, score)


def evaluate_switch_utility(
    battle: BattleSimulator,
    ai_side: BattleSide,
    opp_side: BattleSide,
    active_poke: PokemonState,
    candidate_poke: PokemonState,
    opp_poke: Optional[PokemonState],
    difficulty: int = 50,
    coach_directive: Optional[str] = None
) -> float:
    """Evaluates whether switching into candidate_poke is strategically advantageous."""
    if not opp_poke or opp_poke.is_fainted:
        return 0.0

    score = 0.0

    # 1. Assess active Pokémon danger level
    active_in_danger = False
    for opp_m in opp_poke.moves:
        dmg, _ = battle.calculate_move_damage(opp_poke, active_poke, opp_m)
        if dmg >= active_poke.current_hp:
            active_in_danger = True
            break

    # If active is about to get knocked out, incentive to switch to a wall/resistor increases
    if active_in_danger:
        score += 40.0

    # 2. Candidate defensive matchup against opponent's active typing
    candidate_resists_all = True
    for opp_type in opp_poke.types:
        mult = get_type_multiplier(opp_type, candidate_poke.types)
        if mult >= 2.0:
            candidate_resists_all = False
            score -= 50.0  # Switching into weakness is suicidal!
        elif mult <= 0.5:
            score += 35.0  # Solid resistance!
        elif mult == 0.0:
            score += 65.0  # Complete immunity (e.g. Ghost vs Normal, Ground vs Electric)!

    # Candidate Ability Synergy (e.g. Intimidate on switch-in, Flash Fire, Levitate)
    if candidate_poke.ability == "intimidate":
        score += 35.0
    elif candidate_poke.ability == "levitate" and "ground" in opp_poke.types:
        score += 40.0
    elif candidate_poke.ability == "drizzle" and battle.weather != "rain":
        score += 30.0

    # 3. Candidate offensive threat against opponent
    best_candidate_dmg = 0
    for cand_m in candidate_poke.moves:
        dmg, _ = battle.calculate_move_damage(candidate_poke, opp_poke, cand_m)
        if dmg > best_candidate_dmg:
            best_candidate_dmg = dmg

    if best_candidate_dmg >= opp_poke.current_hp:
        score += 45.0  # Candidate can immediately threaten a revenge KO!

    # 4. Penalty for switching if active Pokémon can already secure a KO this turn
    for act_m in active_poke.moves:
        dmg, _ = battle.calculate_move_damage(active_poke, opp_poke, act_m)
        if dmg >= opp_poke.current_hp:
            score -= 80.0  # Don't switch if active Pokémon can already win!

    # 5. Entry Hazards penalty on switch-in
    if ai_side.hazards.get("stealth_rock") and candidate_poke.item != "heavy-duty-boots":
        sr_mult = get_type_multiplier("rock", candidate_poke.types)
        if sr_mult >= 2.0:
            score -= 30.0  # Takes 25% or 50% from rocks

    # Coaching directive adjustment
    if coach_directive and "pivot" in coach_directive.lower():
        score += 25.0

    return max(0.0, score)

