# run_interactive.py
# Interactive launcher for the NYC TLC ETL Pipeline.
# Instead of remembering command-line arguments, just run:
#   python3 run_interactive.py
# and answer the questions.

import sys
from run_pipeline import run


def ask(prompt, valid=None, cast=str):
    """
    Ask the user a question and return their answer.
    Keeps asking until they give a valid answer.
    """
    while True:
        answer = input(prompt).strip()
        try:
            answer = cast(answer)
        except (ValueError, TypeError):
            print("  ✗ Please enter a valid value.")
            continue
        if valid and answer not in valid:
            print(f"  ✗ Please choose from: {valid}")
            continue
        return answer


def main():
    print()
    print("=" * 50)
    print("   NYC TLC ETL Pipeline — Interactive Mode")
    print("=" * 50)
    print()
    print("This will download NYC Yellow Taxi data,")
    print("clean it, and load it into your dashboard.")
    print()

    # Ask for year
    year = ask(
        "Which year do you want to process? (e.g. 2024): ",
        cast=int,
        valid=list(range(2019, 2026))
    )

    # Ask for month
    month = ask(
        "Which month? (1-12): ",
        cast=int,
        valid=list(range(1, 13))
    )

    # Ask for sample mode
    print()
    print("Run in sample mode?")
    print("  - sample : fast, processes ~50,000 rows (good for testing)")
    print("  - full   : slow, processes all 2.8 million rows")
    print()
    mode = ask(
        "Enter 'sample' or 'full': ",
        valid=["sample", "full"]
    )

    sample_rows = 0
    if mode == "sample":
        raw = input("How many rows? (press Enter for 50000): ").strip()
        sample_rows = int(raw) if raw else 50000

    # Confirm before running
    print()
    print("-" * 50)
    print(f"  Year  : {year}")
    print(f"  Month : {month:02d}")
    if sample_rows:
        print(f"  Mode  : Sample ({sample_rows:,} rows)")
    else:
        print(f"  Mode  : Full run (~2.8 million rows)")
    print("-" * 50)
    print()

    confirm = ask(
        "Start the pipeline? (yes/no): ",
        valid=["yes", "no", "y", "n"]
    )

    if confirm in ("no", "n"):
        print("\nCancelled. Run again when ready.")
        sys.exit(0)

    print()
    print("Starting pipeline... watch the logs below.")
    print()

    # Run the actual pipeline
    run(year, month, sample_rows=sample_rows)

    print()
    print("=" * 50)
    print("Done! Open http://localhost:3000 to see your data.")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
