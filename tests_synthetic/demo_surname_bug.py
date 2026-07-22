"""Demo script: reproduces the original surname-collision bug in an
isolated copy of the scoring logic (does NOT touch the real, already-fixed
fd_reader/match/name_matching.py), then shows the current fixed behavior
on the same inputs side by side.

Run with:
    .venv/bin/python -m tests_synthetic.demo_surname_bug
"""
from __future__ import annotations

from rapidfuzz import fuzz

from fd_reader.match.name_matching import _best_name_score


def _buggy_name_variants(name: str) -> list[str]:
    """The ORIGINAL _name_variants(): always emits a surname-only variant
    for BOTH sides, regardless of whether a first name is present. This is
    the exact code that caused the bug -- kept here only for this demo."""
    name = name.strip()
    variants = [name]
    if "," in name:
        last, _, first = name.partition(",")
        variants.append(f"{first.strip()} {last.strip()}")
        variants.append(last.strip())  # <- the problematic unconditional surname-only variant
    else:
        parts = name.split()
        if len(parts) >= 2:
            variants.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            variants.append(parts[-1])  # <- same problem on the Yelp side
    return [v.lower().strip() for v in variants if v.strip()]


def _buggy_best_name_score(guest_name: str, yelp_name: str) -> int:
    guest_variants = _buggy_name_variants(guest_name)
    yelp_variants = _buggy_name_variants(yelp_name)
    best = 0
    for g in guest_variants:
        for y in yelp_variants:
            score = fuzz.token_sort_ratio(g, y)
            best = max(best, score)
    return best


def main() -> None:
    guest_name = "Hopkins, Grace"
    reservation_a = "Grace Hopkins"   # the correct, real match
    reservation_b = "Kate Hopkins"    # a DIFFERENT real person, same surname

    print(f"Guest on file: {guest_name!r}")
    print(f"Yelp reservation A: {reservation_a!r} (this really is the same guest)")
    print(f"Yelp reservation B: {reservation_b!r} (a DIFFERENT person, same surname)")
    print()

    print("=== ORIGINAL (buggy) scoring ===")
    score_a_buggy = _buggy_best_name_score(guest_name, reservation_a)
    score_b_buggy = _buggy_best_name_score(guest_name, reservation_b)
    print(f"  score({reservation_a!r}) = {score_a_buggy}")
    print(f"  score({reservation_b!r}) = {score_b_buggy}")
    if score_a_buggy == score_b_buggy:
        print("  -> TIE! match_reservations() could not tell them apart --")
        print("     this is the exact collision that silently attached BOTH")
        print("     reservations to one guest, letting a wrong reservation")
        print("     hide behind a correct one during the notes cross-check.")
    print()

    print("=== CURRENT (fixed) scoring ===")
    score_a_fixed = _best_name_score(guest_name, reservation_a)
    score_b_fixed = _best_name_score(guest_name, reservation_b)
    print(f"  score({reservation_a!r}) = {score_a_fixed}")
    print(f"  score({reservation_b!r}) = {score_b_fixed}")
    if score_a_fixed > score_b_fixed:
        print("  -> Fixed: the real match clearly outscores the different person,")
        print("     so 'Kate Hopkins' is no longer silently attached to Grace's record.")


if __name__ == "__main__":
    main()
