#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Fuzzy Matching Test Script for legal-doc-diff-rag
This script calculates and compares various fuzzy matching scores between two input texts.
It displays standard `thefuzz` metrics alongside custom scoring methods from the project.
"""

import os
import sys

# Ensure project root is in the python path for importing src
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try importing thefuzz
try:
    from thefuzz import fuzz
except ImportError:
    print("\n\033[91m[Warning] Package 'thefuzz' is not installed in the current environment.\033[0m")
    print("Please activate your virtual environment and install it, or run:")
    print("  pip install thefuzz\n")
    fuzz = None

# Try importing project-specific scoring functions
try:
    from src.core.matching.scoring import get_title_sim, extract_keywords, jaccard
    HAS_PROJECT_SCORING = True
except ImportError:
    HAS_PROJECT_SCORING = False


# ANSI Color Codes for beautiful terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(title: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}")
    print(f" {title.center(58)}")
    print(f"{'=' * 60}{Colors.ENDC}\n")


def get_color_for_score(score: float) -> str:
    """Returns color based on score (0 to 100)"""
    if score >= 80:
        return Colors.OKGREEN
    elif score >= 50:
        return Colors.OKCYAN
    elif score >= 30:
        return Colors.WARNING
    else:
        return Colors.FAIL


def run_tests(text1: str, text2: str):
    print_header("FUZZY MATCHING TEST RESULTS")
    
    # Print input texts
    print(f"{Colors.BOLD}Text 1:{Colors.ENDC} {Colors.OKBLUE}\"{text1}\"{Colors.ENDC}")
    print(f"{Colors.BOLD}Text 2:{Colors.ENDC} {Colors.OKBLUE}\"{text2}\"{Colors.ENDC}")
    print("-" * 60)

    results = []

    # 1. Standard thefuzz metrics (0-100 scale)
    if fuzz:
        fuzz_metrics = [
            ("fuzz.ratio", fuzz.ratio, 
             "Simple edit distance ratio (checks exact character matches)"),
            ("fuzz.partial_ratio", fuzz.partial_ratio, 
             "Best substring match ratio (good for substring/substring search)"),
            ("fuzz.token_sort_ratio", fuzz.token_sort_ratio, 
             "Sorts tokens alphabetically first (ignores word order)"),
            ("fuzz.token_set_ratio", fuzz.token_set_ratio, 
             "Set-based comparison (ignores word order, duplicates, and subsets)"),
            ("fuzz.partial_token_sort_ratio", fuzz.partial_token_sort_ratio, 
             "Combination of substring match + token sort"),
            ("fuzz.partial_token_set_ratio", fuzz.partial_token_set_ratio, 
             "Combination of substring match + token set"),
            ("fuzz.WRatio", fuzz.WRatio, 
             "Weighted ratio (intelligent fallback depending on text lengths)"),
            ("fuzz.QRatio", fuzz.QRatio, 
             "Quick ratio (quick comparison after basic cleaning)"),
        ]

        for name, func, desc in fuzz_metrics:
            try:
                score = func(text1, text2)
                results.append((name, score, desc))
            except Exception as e:
                results.append((name, None, f"Error: {e}"))
    else:
        print(f"{Colors.WARNING}Standard thefuzz metrics skipped because package is missing.{Colors.ENDC}")

    # 2. Project custom matching methods (0.0 - 1.0 scale, converted to 0-100)
    if HAS_PROJECT_SCORING:
        # Title Similarity
        try:
            title_sim_val = get_title_sim(text1, text2) * 100.0
            results.append((
                "project.get_title_sim", 
                title_sim_val, 
                "Project's official title similarity metric (token_sort_ratio / 100)"
            ))
        except Exception as e:
            results.append(("project.get_title_sim", None, f"Error: {e}"))

        # Lexical Jaccard (Keywords: Numbers, Dates, Names)
        try:
            kw1 = extract_keywords(text1)
            kw2 = extract_keywords(text2)
            jaccard_val = jaccard(kw1, kw2) * 100.0
            kw_details = f"Extracts Numbers/Dates/Names. Match: {list(kw1.intersection(kw2))} of {list(kw1.union(kw2))}"
            results.append((
                "project.lexical_jaccard", 
                jaccard_val, 
                f"Jaccard similarity on key entities. {kw_details}"
            ))
        except Exception as e:
            results.append(("project.lexical_jaccard", None, f"Error: {e}"))
    else:
        print(f"{Colors.WARNING}Project custom scoring skipped (could not import src.core.matching.scoring).{Colors.ENDC}")

    # Print Table Header
    print(f"{Colors.BOLD}{'Method':<32} | {'Score':<6} | {'Description'}{Colors.ENDC}")
    print("-" * 100)

    # Print Table Rows
    for name, score, desc in results:
        if score is None:
            score_str = "N/A"
            color = Colors.FAIL
        else:
            score_str = f"{score:5.1f}%"
            color = get_color_for_score(score)

        print(f"{Colors.BOLD}{name:<32}{Colors.ENDC} | {color}{score_str:<6}{Colors.ENDC} | {desc}")
    
    print("-" * 100)


def main():
    # Default example texts (Vietnamese Legal Document scenarios)
    default_text1 = "Nghị định 15/2020/NĐ-CP xử phạt vi phạm hành chính bưu chính viễn thông"
    default_text2 = "Nghị định số 15/2020/NĐ-CP về xử phạt vi phạm hành chính trong lĩnh vực bưu chính, viễn thông"

    print_header("Fuzzy Matching Tester CLI")
    print("Options:")
    print("  [1] Run with default legal document example")
    print("  [2] Enter custom texts interactively")
    print("  [3] Exit")
    
    try:
        choice = input(f"\nSelect an option (default is {Colors.BOLD}1{Colors.ENDC}): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        return

    if choice == '2':
        try:
            print("\n" + "-" * 50)
            text1 = input(f"{Colors.BOLD}Enter Text 1:{Colors.ENDC}\n").strip()
            text2 = input(f"\n{Colors.BOLD}Enter Text 2:{Colors.ENDC}\n").strip()
            print("-" * 50)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return
    elif choice == '3':
        print("Exiting.")
        return
    else:
        text1 = default_text1
        text2 = default_text2
        print(f"\nUsing default legal examples...")

    if not text1 or not text2:
        print(f"{Colors.FAIL}Error: Both input texts must be non-empty!{Colors.ENDC}")
        return

    run_tests(text1, text2)


if __name__ == "__main__":
    # If arguments are passed directly through CLI, e.g., python temp.py "text a" "text b"
    if len(sys.argv) >= 3:
        run_tests(sys.argv[1], sys.argv[2])
    else:
        main()
