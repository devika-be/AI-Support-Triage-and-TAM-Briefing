from app.triage import triage_ticket


def main() -> None:
    sample_ticket = {
        "subject": "Webhook from CloudSync not reaching PagerDuty",
        "body": (
            "Our CloudSync webhooks are not being delivered to PagerDuty. "
            "We've verified the endpoint is reachable and the secret is correctly configured.\n\n"
            "Last successful delivery: earlier today\n"
            "Failed deliveries since: 4731\n\n"
            "Webhook logs attached. Please advise."
        ),
    }

    result = triage_ticket(sample_ticket)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
