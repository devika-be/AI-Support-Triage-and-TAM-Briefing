import sys

from app.account_brief import build_account_brief


def main() -> None:
    account_id = sys.argv[1] if len(sys.argv) > 1 else "ACC-8113"
    result = build_account_brief(account_id)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
